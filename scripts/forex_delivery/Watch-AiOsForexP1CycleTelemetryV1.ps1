param(
    [Parameter(Mandatory=$true)][string]$TelemetryPath,
    [Parameter(Mandatory=$false)][string]$ExperienceLedgerPath = '',
    [Parameter(Mandatory=$false)][string]$EventsPath = '',
    [Parameter(Mandatory=$false)][string]$CampaignStatePath = '',
    [Parameter(Mandatory=$false)][string]$ActiveSessionPath = '',
    [Parameter(Mandatory=$false)][int]$RefreshSeconds = 1
)
$ErrorActionPreference = "Stop"

if ($RefreshSeconds -lt 1) { throw 'REFRESH_SECONDS_MUST_BE_POSITIVE' }

# Read-only monitor: it reads persisted JSON/JSONL only and never opens a
# network, process-control, scheduler, or runtime-write path.
function Format-Age([Nullable[double]]$Seconds) {
    if ($null -eq $Seconds) { return 'UNKNOWN' }
    $value = [Math]::Max(0, [int][Math]::Floor($Seconds))
    if ($value -lt 60) { return ('{0}s' -f $value) }
    $span = [TimeSpan]::FromSeconds($value)
    if ($value -lt 3600) { return ('{0:00}:{1:00}' -f [int]$span.TotalMinutes, $span.Seconds) }
    if ($value -lt 86400) { return ('{0:00}:{1:00}:{2:00}' -f [int]$span.TotalHours, $span.Minutes, $span.Seconds) }
    return ('{0}d {1:00}:{2:00}:{3:00}' -f [int]$span.TotalDays, $span.Hours, $span.Minutes, $span.Seconds)
}

function Parse-Utc([object]$Value) {
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) { return $null }
    try { return ([DateTimeOffset]::Parse([string]$Value)).ToUniversalTime() } catch { return $null }
}

function Read-LastJsonLine([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $lines = @(Get-Content -LiteralPath $Path -ErrorAction Stop | Where-Object { $_.Trim() })
    for ($index = $lines.Count - 1; $index -ge 0; $index--) {
        try { return ($lines[$index] | ConvertFrom-Json) } catch { }
    }
    return $null
}

$telemetryDirectory = Split-Path -Parent $TelemetryPath
$runtimeDirectory = Split-Path -Parent $telemetryDirectory
$ledgerPath = if ($ExperienceLedgerPath) { $ExperienceLedgerPath } else { Join-Path $telemetryDirectory 'AIOS_FOREX_P1_EXPERIENCE_LEDGER.jsonl' }
$eventsFile = if ($EventsPath) { $EventsPath } else { Join-Path (Join-Path $runtimeDirectory 'forex_p1_paper_autostart_v1') 'events.jsonl' }
$stateFile = if ($CampaignStatePath) { $CampaignStatePath } else { Join-Path $telemetryDirectory 'AIOS_FOREX_SUPERTREND_30_TRADE_CAMPAIGN_STATE.json' }
$activeFile = if ($ActiveSessionPath) { $ActiveSessionPath } else { Join-Path $telemetryDirectory 'active.json' }

while ($true) {
    $now = [DateTimeOffset]::UtcNow
    $record = Read-LastJsonLine $TelemetryPath
    $event = $null
    if (Test-Path -LiteralPath $eventsFile) {
        $eventLines = @(Get-Content -LiteralPath $eventsFile | Where-Object { $_.Trim() })
        for ($eventIndex = $eventLines.Count - 1; $eventIndex -ge 0; $eventIndex--) {
            try {
                $candidateEvent = $eventLines[$eventIndex] | ConvertFrom-Json
                if ($candidateEvent.status -eq 'READY' -and $candidateEvent.observed_at_utc) {
                    $event = $candidateEvent
                    break
                }
            } catch { }
        }
    }
    $state = if (Test-Path -LiteralPath $stateFile) { Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json } else { $null }
    $active = if (Test-Path -LiteralPath $activeFile) { Get-Content -LiteralPath $activeFile -Raw | ConvertFrom-Json } else { $null }
    $experiences = @()
    if (Test-Path -LiteralPath $ledgerPath) {
        $experiences = @(Get-Content -LiteralPath $ledgerPath | Where-Object { $_.Trim() } | ForEach-Object { try { $_ | ConvertFrom-Json } catch { } })
    }

    $runtimeStart = Parse-Utc $event.observed_at_utc
    $campaignStart = Parse-Utc $state.started_utc
    $cycleCompleted = Parse-Utc $record.cycle_completed_utc
    $nextCheck = Parse-Utc $record.next_check_at_utc
    $runtimeAge = if ($runtimeStart) { ($now - $runtimeStart).TotalSeconds } else { $null }
    $campaignAge = if ($campaignStart) { ($now - $campaignStart).TotalSeconds } else { $null }
    $cycleAge = if ($cycleCompleted) { ($now - $cycleCompleted).TotalSeconds } else { $null }
    $nextCheckIn = if ($nextCheck) { [Math]::Max(0, ($nextCheck - $now).TotalSeconds) } else { $null }
    $freshness = if ($record -and $record.history_freshness_result -eq 'FRESH' -and $record.snapshot_freshness_result -eq 'FRESH') { 'FRESH' } elseif ($record -and $record.cycle_action -eq 'WAIT_FOR_DATA') { 'STALE' } else { 'UNAVAILABLE' }
    $direction = if ($record -and $record.supertrend_direction) { $record.supertrend_direction } else { 'NONE' }
    $rejection = if ($record -and $record.rejection_reasons) { ($record.rejection_reasons -join ',') } else { 'NONE' }
    $shadowCount = @($experiences | Where-Object { $_.shadow_classification -eq 'SHADOW_COUNTERFACTUAL' }).Count
    $falseNegativeCount = @($experiences | Where-Object { $_.outcome_classification -eq 'FALSE_NEGATIVE' }).Count
    $position = if ($active -and $active.status -eq 'ACTIVE') { "ACTIVE $($active.direction) $($active.units)" } elseif ($record) { [string]$record.active_position_status } else { 'UNKNOWN' }

    Clear-Host
    @(
        'AIOS FOREX P1 LIVE MONITOR  PAPER_ONLY',
        ('RUNTIME AGE: {0}' -f (Format-Age $runtimeAge)),
        ('CAMPAIGN AGE: {0}' -f (Format-Age $campaignAge)),
        ('CYCLE AGE: {0}' -f (Format-Age $cycleAge)),
        ('NEXT CHECK IN: {0}' -f (Format-Age $nextCheckIn)),
        ('CYCLE: {0}/{1}' -f $(if ($record) { $record.cycle_number } else { '?' }), $(if ($record) { $record.maximum_cycles } else { '?' })),
        ('QUALIFYING: {0}/30' -f $(if ($state) { $state.accepted_qualifying_trades } else { '?' })),
        ('SIGNAL: {0}  ACTION: {1}' -f $direction, $(if ($record) { $record.cycle_action } else { 'UNKNOWN' })),
        ('DATA: {0}  ATR: {1}/{2}  BODY: {3}/{4}' -f $freshness, $(if ($record) { $record.atr_actual } else { '?' }), $(if ($record) { $record.minimum_atr } else { '?' }), $(if ($record) { $record.candle_body_ratio } else { '?' }), $(if ($record) { $record.minimum_candle_body_ratio } else { '?' })),
        ('SUPERTREND: {0}  H1: {1}  RSI: {2}  SPREAD: {3}' -f $direction, $(if ($record) { $record.h1_shadow_state } else { 'UNKNOWN' }), $(if ($record) { $record.rsi } else { 'UNKNOWN' }), $(if ($record) { $record.spread } else { 'UNKNOWN' })),
        ('POSITION: {0}  PAPER P/L: {1}  MFE: {2}  MAE: {3}' -f $position, $(if ($state) { $state.net_pl } else { '?' }), $(if ($record) { $record.mfe_r } else { '?' }), $(if ($record) { $record.mae_r } else { '?' })),
        ('EXPERIENCE COUNT: {0}  SHADOW COUNT: {1}  FALSE NEGATIVES: {2}' -f $experiences.Count, $shadowCount, $falseNegativeCount),
        ('REJECTION: {0}' -f $rejection),
        'Press Ctrl+C to stop the read-only monitor.'
    ) -join [Environment]::NewLine
    Start-Sleep -Seconds $RefreshSeconds
}
