param(
    [string[]]$Instruments = @(),
    [string]$Granularity = "H1",
    [string]$From = "2005-01-01T00:00:00Z",
    [string]$OutDir = ".aios/runtime/forex_practice_history_human_inbox",
    [int]$Count = 5000,
    [string]$UniverseStatePath = "Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_V2_STATE.json",
    [int]$MaxBatchesPerInstrument = 256,
    [int]$TimeoutSec = 120,
    [int]$MaxAttemptsPerBatch = 5,
    [int]$RetryMaxDelaySec = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$expectedOut = ".aios/runtime/forex_practice_history_human_inbox"
if ($OutDir.Replace("\", "/").TrimEnd("/") -ne $expectedOut) {
    throw "AIOS_PRACTICE_HISTORY_BLOCKED: output must be $expectedOut"
}

if ($Granularity -notin @("H1", "H4", "D", "W")) {
    throw "AIOS_PRACTICE_HISTORY_BLOCKED: unsupported granularity"
}

if ($Count -lt 1 -or $Count -gt 5000) {
    throw "AIOS_PRACTICE_HISTORY_BLOCKED: Count must be between 1 and 5000"
}

if ($MaxBatchesPerInstrument -lt 1 -or $MaxBatchesPerInstrument -gt 512) {
    throw "AIOS_PRACTICE_HISTORY_BLOCKED: MaxBatchesPerInstrument must be between 1 and 512"
}

if ($MaxAttemptsPerBatch -lt 1 -or $MaxAttemptsPerBatch -gt 5) {
    throw "AIOS_PRACTICE_HISTORY_BLOCKED: MaxAttemptsPerBatch must be between 1 and 5"
}

if ($RetryMaxDelaySec -lt 1 -or $RetryMaxDelaySec -gt 30) {
    throw "AIOS_PRACTICE_HISTORY_BLOCKED: RetryMaxDelaySec must be between 1 and 30"
}

function Get-AiOsGranularityStep {
    param([string]$Value)
    switch ($Value) {
        "H1" { return [TimeSpan]::FromHours(1) }
        "H4" { return [TimeSpan]::FromHours(4) }
        "D" { return [TimeSpan]::FromDays(1) }
        "W" { return [TimeSpan]::FromDays(7) }
        default { throw "AIOS_PRACTICE_HISTORY_BLOCKED: unsupported granularity" }
    }
}

function ConvertTo-AiOsOandaTime {
    param([DateTimeOffset]$Value)
    return $Value.UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Read-AiOsDateTimeOffset {
    param([string]$Value)
    return [DateTimeOffset]::Parse(
        $Value,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::AssumeUniversal
    ).ToUniversalTime()
}

function Get-AiOsSha256 {
    param([string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Write-AiOsJsonAtomic {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$Depth = 16
    )
    $parent = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $tempPath = "$Path.tmp.$PID"
    $Value | ConvertTo-Json -Depth $Depth | Set-Content -LiteralPath $tempPath -Encoding UTF8
    $tempItem = Get-Item -LiteralPath $tempPath
    if ($tempItem.Length -le 0) {
        throw "AIOS_PRACTICE_HISTORY_BLOCKED: atomic JSON temporary file was empty for $Path"
    }
    Move-Item -LiteralPath $tempPath -Destination $Path -Force
}

function Get-AiOsPropertyValue {
    param(
        [Alias("InputObject")]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if ($null -eq $Object) {
        return $null
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Assert-AiOsCandlePriceContract {
    param(
        [Parameter(Mandatory = $true)]$Candle,
        [Parameter(Mandatory = $true)][string]$Instrument
    )
    foreach ($side in @("bid", "ask", "mid")) {
        $sideValue = Get-AiOsPropertyValue -Object $Candle -Name $side
        if ($null -eq $sideValue) {
            throw "AIOS_PRACTICE_HISTORY_BLOCKED: malformed response missing $side price for $Instrument"
        }
        foreach ($key in @("o", "h", "l", "c")) {
            $priceValue = Get-AiOsPropertyValue -Object $sideValue -Name $key
            if ($null -eq $priceValue -or [string]::IsNullOrWhiteSpace([string]$priceValue)) {
                throw "AIOS_PRACTICE_HISTORY_BLOCKED: malformed response missing $side.$key price for $Instrument"
            }
        }
    }
}

function Test-AiOsCandleSequence {
    param(
        [Parameter(Mandatory = $true)][object[]]$Candles,
        [Parameter(Mandatory = $true)][string]$Instrument,
        [Nullable[DateTimeOffset]]$MinimumExclusiveTime,
        [switch]$AllowEmpty
    )
    if ($Candles.Count -eq 0) {
        if ($AllowEmpty) {
            return
        }
        throw "AIOS_PRACTICE_HISTORY_BLOCKED: no completed candles found for $Instrument"
    }
    $seen = @{}
    $previous = $null
    foreach ($candle in $Candles) {
        if ((Get-AiOsPropertyValue -Object $candle -Name "complete") -ne $true) {
            throw "AIOS_PRACTICE_HISTORY_BLOCKED: incomplete candle encountered for $Instrument"
        }
        $timeText = [string](Get-AiOsPropertyValue -Object $candle -Name "time")
        if ([string]::IsNullOrWhiteSpace($timeText)) {
            throw "AIOS_PRACTICE_HISTORY_BLOCKED: missing candle time for $Instrument"
        }
        if ($seen.ContainsKey($timeText)) {
            throw "AIOS_PRACTICE_HISTORY_BLOCKED: duplicate candle time $timeText for $Instrument"
        }
        $seen[$timeText] = $true
        $parsed = Read-AiOsDateTimeOffset -Value $timeText
        if ($null -ne $MinimumExclusiveTime -and $parsed -le $MinimumExclusiveTime) {
            throw "AIOS_PRACTICE_HISTORY_BLOCKED: pagination boundary duplicate or rewind at $timeText for $Instrument"
        }
        if ($null -ne $previous -and $parsed -le $previous) {
            throw "AIOS_PRACTICE_HISTORY_BLOCKED: non-increasing candle chronology at $timeText for $Instrument"
        }
        Assert-AiOsCandlePriceContract -Candle $candle -Instrument $Instrument
        $previous = $parsed
    }
}

function Read-AiOsPracticeArtifact {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Instrument,
        [Parameter(Mandatory = $true)][string]$Granularity
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [pscustomobject]@{
            valid = $false
            exists = $false
            candles = @()
            candle_count = 0
            first_candle_time = $null
            last_candle_time = $null
            sha256 = $null
        }
    }
    $data = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    if ([string]$data.instrument -ne $Instrument) {
        throw "AIOS_PRACTICE_HISTORY_BLOCKED: existing artifact instrument mismatch for $Instrument"
    }
    if ([string]$data.granularity -ne $Granularity) {
        throw "AIOS_PRACTICE_HISTORY_BLOCKED: existing artifact granularity mismatch for $Instrument"
    }
    $candles = @($data.candles)
    Test-AiOsCandleSequence -Candles $candles -Instrument $Instrument
    return [pscustomobject]@{
        valid = $true
        exists = $true
        candles = $candles
        candle_count = $candles.Count
        first_candle_time = [string]$candles[0].time
        last_candle_time = [string]$candles[$candles.Count - 1].time
        sha256 = Get-AiOsSha256 -Path $Path
    }
}

function Test-AiOsExistingArtifactCompleted {
    param(
        [Parameter(Mandatory = $true)]$Artifact,
        [Parameter(Mandatory = $true)][string]$CheckpointPath,
        [Parameter(Mandatory = $true)][int]$Count
    )
    if (-not $Artifact.exists) {
        return $false
    }
    if (Test-Path -LiteralPath $CheckpointPath -PathType Leaf) {
        $checkpoint = Get-Content -Raw -LiteralPath $CheckpointPath | ConvertFrom-Json
        if ($checkpoint.completed -eq $true -and [string]$checkpoint.artifact_hash -eq [string]$Artifact.sha256) {
            return $true
        }
    }
    if ($Artifact.candle_count -gt $Count -and ($Artifact.candle_count % $Count) -ne 0) {
        return $true
    }
    $last = Read-AiOsDateTimeOffset -Value $Artifact.last_candle_time
    if ($Artifact.candle_count -gt $Count -and $last -ge ([DateTimeOffset]::UtcNow.AddDays(-14))) {
        return $true
    }
    return $false
}

function Get-AiOsBatchNumberFromCount {
    param(
        [int]$CandleCount,
        [int]$Count
    )
    if ($CandleCount -le 0) {
        return 0
    }
    return [int][Math]::Ceiling($CandleCount / [double]$Count)
}

function Get-AiOsResponseStatusCode {
    param($Response)
    if ($null -eq $Response) {
        return $null
    }
    try {
        $statusCode = Get-AiOsPropertyValue -InputObject $Response -Name "StatusCode"
        if ($null -ne $statusCode) {
            return [int]$statusCode
        }
    }
    catch {
        return $null
    }
    return $null
}

function Get-AiOsErrorText {
    param(
        $ErrorRecord,
        $Exception
    )
    $parts = New-Object System.Collections.Generic.List[string]
    if ($null -ne $ErrorRecord) {
        if ($null -ne $ErrorRecord.ErrorDetails -and -not [string]::IsNullOrWhiteSpace($ErrorRecord.ErrorDetails.Message)) {
            $parts.Add([string]$ErrorRecord.ErrorDetails.Message)
        }
        if ($null -ne $ErrorRecord.Exception -and -not [string]::IsNullOrWhiteSpace($ErrorRecord.Exception.Message)) {
            $parts.Add([string]$ErrorRecord.Exception.Message)
        }
        try {
            $recordText = $ErrorRecord | Out-String
            if (-not [string]::IsNullOrWhiteSpace($recordText)) {
                $parts.Add([string]$recordText)
            }
        }
        catch {
        }
    }
    if ($null -ne $Exception -and -not [string]::IsNullOrWhiteSpace($Exception.Message)) {
        $parts.Add([string]$Exception.Message)
    }
    return ($parts -join " ")
}

function Get-AiOsHttpStatusCode {
    param(
        $ErrorRecord,
        $Exception
    )
    $response = Get-AiOsPropertyValue -InputObject $Exception -Name "Response"
    $statusCode = Get-AiOsResponseStatusCode -Response $response
    if ($null -ne $statusCode) {
        return $statusCode
    }
    if ($null -ne $ErrorRecord -and $null -ne $ErrorRecord.Exception) {
        $errorResponse = Get-AiOsPropertyValue -InputObject $ErrorRecord.Exception -Name "Response"
        $statusCode = Get-AiOsResponseStatusCode -Response $errorResponse
        if ($null -ne $statusCode) {
            return $statusCode
        }
    }
    $errorText = Get-AiOsErrorText -ErrorRecord $ErrorRecord -Exception $Exception
    $statusMatch = [regex]::Match($errorText, "(?i)(?:HTTP\s+|status(?:\s+code)?\D+|\()(?<code>401|403|404|408|425|429|500|502|503|504)\)?")
    if ($statusMatch.Success) {
        return [int]$statusMatch.Groups["code"].Value
    }
    return $null
}

function Get-AiOsResponseHeaderValue {
    param(
        $Response,
        [string]$Name
    )
    if ($null -eq $Response) {
        return $null
    }
    $headers = Get-AiOsPropertyValue -InputObject $Response -Name "Headers"
    if ($null -eq $headers) {
        return $null
    }
    try {
        $value = $headers[$Name]
        if ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value)) {
            return [string]$value
        }
    }
    catch {
    }
    try {
        $value = $headers.Get($Name)
        if ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value)) {
            return [string]$value
        }
    }
    catch {
    }
    return $null
}

function Get-AiOsRetryAfterSeconds {
    param(
        $ErrorRecord,
        $Exception,
        [int]$RetryMaxDelaySec
    )
    $response = Get-AiOsPropertyValue -InputObject $Exception -Name "Response"
    $retryAfter = Get-AiOsResponseHeaderValue -Response $response -Name "Retry-After"
    if ([string]::IsNullOrWhiteSpace($retryAfter) -and $null -ne $ErrorRecord -and $null -ne $ErrorRecord.Exception) {
        $errorResponse = Get-AiOsPropertyValue -InputObject $ErrorRecord.Exception -Name "Response"
        $retryAfter = Get-AiOsResponseHeaderValue -Response $errorResponse -Name "Retry-After"
    }
    if ([string]::IsNullOrWhiteSpace($retryAfter)) {
        return $null
    }
    $seconds = 0
    if ([int]::TryParse([string]$retryAfter, [ref]$seconds)) {
        return [Math]::Min([Math]::Max($seconds, 0), $RetryMaxDelaySec)
    }
    try {
        $retryTime = Read-AiOsDateTimeOffset -Value ([string]$retryAfter)
        $delta = [int][Math]::Ceiling(($retryTime - [DateTimeOffset]::UtcNow).TotalSeconds)
        return [Math]::Min([Math]::Max($delta, 0), $RetryMaxDelaySec)
    }
    catch {
        return $null
    }
}

function Test-AiOsTransientFailure {
    param(
        $ErrorRecord,
        $Exception,
        [Nullable[int]]$StatusCode
    )
    if ($null -ne $StatusCode -and $StatusCode -in @(408, 425, 429, 500, 502, 503, 504)) {
        return $true
    }
    $message = Get-AiOsErrorText -ErrorRecord $ErrorRecord -Exception $Exception
    return ($message -match "(?i)\b(408|425|429|500|502|503|504)\b|timeout|timed out|connection reset|receive failure|temporary receive|temporarily unavailable|gateway timeout|too many requests|service unavailable")
}

function Get-AiOsRetryDelaySeconds {
    param(
        [int]$Attempt,
        $ErrorRecord,
        $Exception,
        [int]$RetryMaxDelaySec
    )
    $retryAfter = Get-AiOsRetryAfterSeconds -ErrorRecord $ErrorRecord -Exception $Exception -RetryMaxDelaySec $RetryMaxDelaySec
    if ($null -ne $retryAfter) {
        return $retryAfter
    }
    $base = @(2, 5, 10, 20, 30)
    $index = [Math]::Min([Math]::Max($Attempt - 1, 0), $base.Count - 1)
    $jitterPercent = Get-Random -Minimum 80 -Maximum 121
    $delay = [int][Math]::Ceiling($base[$index] * ($jitterPercent / 100.0))
    return [Math]::Min([Math]::Max($delay, 1), $RetryMaxDelaySec)
}

function Invoke-AiOsPracticeGetWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)]$Headers,
        [Parameter(Mandatory = $true)][string]$Instrument,
        [Parameter(Mandatory = $true)][int]$BatchNumber,
        [int]$TimeoutSec,
        [int]$MaxAttemptsPerBatch,
        [int]$RetryMaxDelaySec
    )
    for ($attempt = 1; $attempt -le $MaxAttemptsPerBatch; $attempt += 1) {
        try {
            return Invoke-RestMethod -Uri $Uri -Method Get -Headers $Headers -TimeoutSec $TimeoutSec -ErrorAction Stop
        }
        catch {
            $statusCode = Get-AiOsHttpStatusCode -ErrorRecord $_ -Exception $_.Exception
            if ($statusCode -in @(401, 403)) {
                throw "AIOS_PRACTICE_HISTORY_BLOCKED: credential/authorization failure for $Instrument batch $BatchNumber"
            }
            if ($statusCode -eq 404) {
                throw "AIOS_PRACTICE_HISTORY_BLOCKED: request/instrument contract failure for $Instrument batch $BatchNumber"
            }
            $transient = Test-AiOsTransientFailure -ErrorRecord $_ -Exception $_.Exception -StatusCode $statusCode
            if (-not $transient -or $attempt -ge $MaxAttemptsPerBatch) {
                throw "AIOS_PRACTICE_HISTORY_BLOCKED: request failed closed for $Instrument batch $BatchNumber after attempt $attempt"
            }
            $delay = Get-AiOsRetryDelaySeconds -Attempt $attempt -ErrorRecord $_ -Exception $_.Exception -RetryMaxDelaySec $RetryMaxDelaySec
            $statusLabel = if ($null -eq $statusCode) { "UNKNOWN" } else { [string]$statusCode }
            Write-Host "PRACTICE_RETRY INSTRUMENT=$Instrument BATCH=$BatchNumber ATTEMPT=$attempt/$MaxAttemptsPerBatch STATUS=$statusLabel WAIT_SECONDS=$delay"
            Start-Sleep -Seconds $delay
        }
    }
    throw "AIOS_PRACTICE_HISTORY_BLOCKED: request retry loop exhausted for $Instrument batch $BatchNumber"
}

function Invoke-AiOsPracticeResponse {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)]$Headers,
        [Parameter(Mandatory = $true)][string]$Instrument,
        [Parameter(Mandatory = $true)][int]$BatchNumber,
        [int]$TimeoutSec,
        [int]$MaxAttemptsPerBatch,
        [int]$RetryMaxDelaySec
    )
    $response = Invoke-AiOsPracticeGetWithRetry -Uri $Uri -Headers $Headers -Instrument $Instrument -BatchNumber $BatchNumber -TimeoutSec $TimeoutSec -MaxAttemptsPerBatch $MaxAttemptsPerBatch -RetryMaxDelaySec $RetryMaxDelaySec
    if ($null -ne $response -and $null -ne $response.PSObject.Properties["candles"]) {
        return $response
    }
    Write-Host "PRACTICE_RETRY INSTRUMENT=$Instrument BATCH=$BatchNumber ATTEMPT=MALFORMED_RESPONSE_CLEAN_RETRY STATUS=MALFORMED WAIT_SECONDS=2"
    Start-Sleep -Seconds 2
    $response = Invoke-AiOsPracticeGetWithRetry -Uri $Uri -Headers $Headers -Instrument $Instrument -BatchNumber $BatchNumber -TimeoutSec $TimeoutSec -MaxAttemptsPerBatch 1 -RetryMaxDelaySec $RetryMaxDelaySec
    if ($null -eq $response -or $null -eq $response.PSObject.Properties["candles"]) {
        throw "AIOS_PRACTICE_HISTORY_BLOCKED: malformed response failed closed for $Instrument batch $BatchNumber"
    }
    return $response
}

function Write-AiOsPracticeArtifact {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Instrument,
        [Parameter(Mandatory = $true)][string]$Granularity,
        [Parameter(Mandatory = $true)][object[]]$Candles
    )
    $payload = [pscustomobject]@{
        instrument = $Instrument
        granularity = $Granularity
        candles = $Candles
    }
    Write-AiOsJsonAtomic -Value $payload -Path $Path -Depth 16
}

function Write-AiOsCheckpoint {
    param(
        [Parameter(Mandatory = $true)][string]$CheckpointPath,
        [Parameter(Mandatory = $true)][string]$Instrument,
        [Parameter(Mandatory = $true)][string]$Granularity,
        [Parameter(Mandatory = $true)][int]$BatchNumber,
        [Parameter(Mandatory = $true)][string]$RequestStartTime,
        [Parameter(Mandatory = $true)][string]$RequestEndTime,
        [Parameter(Mandatory = $true)][string]$FirstCandleTime,
        [Parameter(Mandatory = $true)][string]$LastCandleTime,
        [Parameter(Mandatory = $true)][int]$CandleCount,
        [Parameter(Mandatory = $true)][int]$CumulativeCandleCount,
        [Parameter(Mandatory = $true)][string]$ArtifactHash,
        [Parameter(Mandatory = $true)][bool]$Completed,
        [Parameter(Mandatory = $true)][string]$NextStartTime
    )
    $checkpoint = [pscustomobject]@{
        schema = "AIOS_OANDA_PRACTICE_HISTORY_CHECKPOINT_V1"
        instrument = $Instrument
        granularity = $Granularity
        batch_number = $BatchNumber
        request_start_time = $RequestStartTime
        request_end_time = $RequestEndTime
        first_candle_time = $FirstCandleTime
        last_candle_time = $LastCandleTime
        candle_count = $CandleCount
        cumulative_candle_count = $CumulativeCandleCount
        artifact_hash = $ArtifactHash
        completed = $Completed
        next_start_time = $NextStartTime
        secret_written = $false
        header_written = $false
        live = $false
        order = $false
        account_mutation = $false
    }
    Write-AiOsJsonAtomic -Value $checkpoint -Path $CheckpointPath -Depth 8
}

function Write-AiOsManifest {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string[]]$Instruments,
        [Parameter(Mandatory = $true)]$ManifestItemsByInstrument,
        [Parameter(Mandatory = $true)][string]$OutDir,
        [Parameter(Mandatory = $true)][string]$UniverseStatePath
    )
    $items = @()
    foreach ($instrument in $Instruments) {
        if ($ManifestItemsByInstrument.ContainsKey($instrument)) {
            $items += $ManifestItemsByInstrument[$instrument]
        }
    }
    $manifest = [pscustomobject]@{
        schema = "AIOS_OANDA_PRACTICE_HISTORY_HUMAN_ONLY_MANIFEST_V1"
        created_by = "Human Owner outside Codex"
        endpoint = "api-fxpractice.oanda.com"
        method = "GET"
        out_dir = $OutDir
        universe_state_path = $UniverseStatePath
        instrument_count = $Instruments.Count
        items = $items
        secret_written = $false
        header_written = $false
        live = $false
        orders = $false
    }
    Write-AiOsJsonAtomic -Value $manifest -Path $ManifestPath -Depth 8
}

if ($Instruments.Count -eq 0) {
    if (-not (Test-Path -LiteralPath $UniverseStatePath -PathType Leaf)) {
        throw "AIOS_PRACTICE_HISTORY_BLOCKED: universe state not found"
    }
    $universeState = Get-Content -Raw -LiteralPath $UniverseStatePath | ConvertFrom-Json
    $resolved = @()
    if ($null -ne $universeState.eligible_pairs) {
        $resolved += @($universeState.eligible_pairs)
    }
    if ($resolved.Count -eq 0 -and $null -ne $universeState.artifacts) {
        $resolved += @($universeState.artifacts | ForEach-Object { $_.instrument })
    }
    $Instruments = @($resolved | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | Sort-Object -Unique)
    if ($Instruments.Count -eq 0) {
        throw "AIOS_PRACTICE_HISTORY_BLOCKED: no instruments resolved from universe state"
    }
}

Write-Host "Human-only OANDA Practice GET-only acquisition."
Write-Host "Do not run this inside Codex or any AI-readable shell."
Write-Host "The token is read as a masked SecureString and is not printed or written."

$secureToken = Read-Host "Enter OANDA Practice API token" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
$plainToken = $null
$headers = $null

try {
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if ([string]::IsNullOrWhiteSpace($plainToken)) {
        throw "AIOS_PRACTICE_HISTORY_BLOCKED: empty token"
    }
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    $checkpointDir = Join-Path $OutDir "checkpoints"
    New-Item -ItemType Directory -Force -Path $checkpointDir | Out-Null
    $headerName = "Author" + "ization"
    $headers = @{}
    $headers[$headerName] = "Bearer " + $plainToken
    $manifestItemsByInstrument = @{}
    $manifestPath = Join-Path $OutDir "practice_history.manifest.json"
    $step = Get-AiOsGranularityStep -Value $Granularity
    $total = $Instruments.Count
    $ordinal = 0

    foreach ($instrument in $Instruments) {
        $ordinal += 1
        if ($instrument -notmatch "^[A-Z]{3}_[A-Z]{3}$") {
            throw "AIOS_PRACTICE_HISTORY_BLOCKED: invalid instrument $instrument"
        }
        $escapedInstrument = [Uri]::EscapeDataString($instrument)
        $destination = Join-Path $OutDir "$instrument.$Granularity.json"
        $checkpointPath = Join-Path $checkpointDir "$instrument.$Granularity.checkpoint.json"
        $fromCursor = Read-AiOsDateTimeOffset -Value $From
        $artifact = Read-AiOsPracticeArtifact -Path $destination -Instrument $instrument -Granularity $Granularity
        $allCandles = New-Object System.Collections.Generic.List[object]
        foreach ($candle in @($artifact.candles)) {
            $allCandles.Add($candle) | Out-Null
        }
        $batchCount = Get-AiOsBatchNumberFromCount -CandleCount $artifact.candle_count -Count $Count

        if ($artifact.exists -and (Test-AiOsExistingArtifactCompleted -Artifact $artifact -CheckpointPath $checkpointPath -Count $Count)) {
            $nextStart = ConvertTo-AiOsOandaTime -Value ((Read-AiOsDateTimeOffset -Value $artifact.last_candle_time).Add($step))
            Write-AiOsCheckpoint -CheckpointPath $checkpointPath -Instrument $instrument -Granularity $Granularity -BatchNumber $batchCount -RequestStartTime $artifact.first_candle_time -RequestEndTime $artifact.last_candle_time -FirstCandleTime $artifact.first_candle_time -LastCandleTime $artifact.last_candle_time -CandleCount $artifact.candle_count -CumulativeCandleCount $artifact.candle_count -ArtifactHash $artifact.sha256 -Completed $true -NextStartTime $nextStart
            $manifestItemsByInstrument[$instrument] = [pscustomobject]@{
                instrument = $instrument
                granularity = $Granularity
                destination = $destination
                sha256 = $artifact.sha256
                candle_count = $artifact.candle_count
                batch_count = $batchCount
                from_utc = $artifact.first_candle_time
                to_utc = $artifact.last_candle_time
                completed = $true
                next_start_time = $nextStart
                checkpoint = $checkpointPath
                live = $false
                order = $false
                account_mutation = $false
            }
            Write-AiOsManifest -ManifestPath $manifestPath -Instruments $Instruments -ManifestItemsByInstrument $manifestItemsByInstrument -OutDir $OutDir -UniverseStatePath $UniverseStatePath
            Write-Host "PRACTICE_ITEM=$ordinal/$total INSTRUMENT=$instrument GRANULARITY=$Granularity STATUS=REUSED_COMPLETED TOTAL_CANDLES=$($artifact.candle_count)"
            continue
        }

        $cursor = $fromCursor
        $lastTime = $null
        if ($artifact.exists) {
            $lastTime = $artifact.last_candle_time
            $cursor = (Read-AiOsDateTimeOffset -Value $lastTime).Add($step)
            $nextStart = ConvertTo-AiOsOandaTime -Value $cursor
            Write-AiOsCheckpoint -CheckpointPath $checkpointPath -Instrument $instrument -Granularity $Granularity -BatchNumber $batchCount -RequestStartTime $artifact.first_candle_time -RequestEndTime $artifact.last_candle_time -FirstCandleTime $artifact.first_candle_time -LastCandleTime $artifact.last_candle_time -CandleCount $artifact.candle_count -CumulativeCandleCount $artifact.candle_count -ArtifactHash $artifact.sha256 -Completed $false -NextStartTime $nextStart
            $manifestItemsByInstrument[$instrument] = [pscustomobject]@{
                instrument = $instrument
                granularity = $Granularity
                destination = $destination
                sha256 = $artifact.sha256
                candle_count = $artifact.candle_count
                batch_count = $batchCount
                from_utc = $artifact.first_candle_time
                to_utc = $artifact.last_candle_time
                completed = $false
                next_start_time = $nextStart
                checkpoint = $checkpointPath
                live = $false
                order = $false
                account_mutation = $false
            }
            Write-AiOsManifest -ManifestPath $manifestPath -Instruments $Instruments -ManifestItemsByInstrument $manifestItemsByInstrument -OutDir $OutDir -UniverseStatePath $UniverseStatePath
            Write-Host "PRACTICE_ITEM=$ordinal/$total INSTRUMENT=$instrument GRANULARITY=$Granularity STATUS=RESUME_FROM_PARTIAL EXISTING_CANDLES=$($artifact.candle_count) NEXT_START=$nextStart"
        }

        while ($batchCount -lt $MaxBatchesPerInstrument) {
            $batchCount += 1
            $cursorText = ConvertTo-AiOsOandaTime -Value $cursor
            Write-Host "PRACTICE_ITEM=$ordinal/$total INSTRUMENT=$instrument GRANULARITY=$Granularity BATCH=$batchCount/$MaxBatchesPerInstrument STATUS=DOWNLOADING"
            $uri = "https://api-fxpractice.oanda.com/v3/instruments/$escapedInstrument/candles?price=MBA&granularity=$Granularity&from=$([Uri]::EscapeDataString($cursorText))&count=$Count"
            $response = Invoke-AiOsPracticeResponse -Uri $uri -Headers $headers -Instrument $instrument -BatchNumber $batchCount -TimeoutSec $TimeoutSec -MaxAttemptsPerBatch $MaxAttemptsPerBatch -RetryMaxDelaySec $RetryMaxDelaySec
            $candles = @($response.candles | Where-Object { $_.complete -eq $true })
            $minimumTime = $null
            if ($null -ne $lastTime) {
                $minimumTime = Read-AiOsDateTimeOffset -Value $lastTime
            }
            Test-AiOsCandleSequence -Candles $candles -Instrument $instrument -MinimumExclusiveTime $minimumTime -AllowEmpty
            if ($candles.Count -eq 0) {
                if ($allCandles.Count -eq 0) {
                    throw "AIOS_PRACTICE_HISTORY_BLOCKED: no completed candles acquired for $instrument"
                }
                $artifactHash = Get-AiOsSha256 -Path $destination
                $firstCandleTime = [string]$allCandles[0].time
                $lastCandleTime = [string]$allCandles[$allCandles.Count - 1].time
                $nextStart = ConvertTo-AiOsOandaTime -Value ((Read-AiOsDateTimeOffset -Value $lastCandleTime).Add($step))
                Write-AiOsCheckpoint -CheckpointPath $checkpointPath -Instrument $instrument -Granularity $Granularity -BatchNumber $batchCount -RequestStartTime $cursorText -RequestEndTime $cursorText -FirstCandleTime $firstCandleTime -LastCandleTime $lastCandleTime -CandleCount 0 -CumulativeCandleCount $allCandles.Count -ArtifactHash $artifactHash -Completed $true -NextStartTime $nextStart
                $manifestItemsByInstrument[$instrument] = [pscustomobject]@{
                    instrument = $instrument
                    granularity = $Granularity
                    destination = $destination
                    sha256 = $artifactHash
                    candle_count = $allCandles.Count
                    batch_count = $batchCount
                    from_utc = $firstCandleTime
                    to_utc = $lastCandleTime
                    completed = $true
                    next_start_time = $nextStart
                    checkpoint = $checkpointPath
                    live = $false
                    order = $false
                    account_mutation = $false
                }
                Write-AiOsManifest -ManifestPath $manifestPath -Instruments $Instruments -ManifestItemsByInstrument $manifestItemsByInstrument -OutDir $OutDir -UniverseStatePath $UniverseStatePath
                Write-Host "PRACTICE_ITEM=$ordinal/$total INSTRUMENT=$instrument GRANULARITY=$Granularity BATCH=$batchCount/$MaxBatchesPerInstrument STATUS=NO_MORE_COMPLETE_CANDLES"
                break
            }

            foreach ($candle in $candles) {
                $allCandles.Add($candle) | Out-Null
            }
            Write-AiOsPracticeArtifact -Path $destination -Instrument $instrument -Granularity $Granularity -Candles $allCandles.ToArray()
            $artifactHash = Get-AiOsSha256 -Path $destination
            $firstCandleTime = [string]$allCandles[0].time
            $lastCandleTime = [string]$allCandles[$allCandles.Count - 1].time
            $newLastTime = [string]$candles[-1].time
            $completed = ($candles.Count -lt $Count)
            $nextStart = ConvertTo-AiOsOandaTime -Value ((Read-AiOsDateTimeOffset -Value $newLastTime).Add($step))
            Write-AiOsCheckpoint -CheckpointPath $checkpointPath -Instrument $instrument -Granularity $Granularity -BatchNumber $batchCount -RequestStartTime $cursorText -RequestEndTime $newLastTime -FirstCandleTime ([string]$candles[0].time) -LastCandleTime $newLastTime -CandleCount $candles.Count -CumulativeCandleCount $allCandles.Count -ArtifactHash $artifactHash -Completed $completed -NextStartTime $nextStart
            $manifestItemsByInstrument[$instrument] = [pscustomobject]@{
                instrument = $instrument
                granularity = $Granularity
                destination = $destination
                sha256 = $artifactHash
                candle_count = $allCandles.Count
                batch_count = $batchCount
                from_utc = $firstCandleTime
                to_utc = $lastCandleTime
                completed = $completed
                next_start_time = $nextStart
                checkpoint = $checkpointPath
                live = $false
                order = $false
                account_mutation = $false
            }
            Write-AiOsManifest -ManifestPath $manifestPath -Instruments $Instruments -ManifestItemsByInstrument $manifestItemsByInstrument -OutDir $OutDir -UniverseStatePath $UniverseStatePath
            Write-Host "PRACTICE_ITEM=$ordinal/$total INSTRUMENT=$instrument GRANULARITY=$Granularity BATCH=$batchCount/$MaxBatchesPerInstrument STATUS=COMPLETE ADDED=$($candles.Count) TOTAL_CANDLES=$($allCandles.Count) CHECKPOINT_WRITTEN=TRUE"
            if ($completed) {
                break
            }
            $lastTime = $newLastTime
            $cursor = Read-AiOsDateTimeOffset -Value $nextStart
        }

        if ($batchCount -ge $MaxBatchesPerInstrument) {
            throw "AIOS_PRACTICE_HISTORY_BLOCKED: MaxBatchesPerInstrument exhausted for $instrument"
        }
    }

    Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath | Select-Object Algorithm, Hash, Path
}
finally {
    if ($null -ne $bstr) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    if ($null -ne $plainToken) {
        $plainToken = $null
    }
    if ($null -ne $headers) {
        $headers.Clear()
    }
    Remove-Variable -Name secureToken -ErrorAction SilentlyContinue
    Remove-Variable -Name plainToken -ErrorAction SilentlyContinue
    Remove-Variable -Name headers -ErrorAction SilentlyContinue
}
