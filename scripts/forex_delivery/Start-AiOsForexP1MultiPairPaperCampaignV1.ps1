param(
    [string]$RepoRoot = 'C:\Dev\Ai.Os',
    [int]$Cycles = 288,
    [switch]$PreflightOnly
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git'))) { throw 'REPO_ROOT_INVALID' }
$branch = (& git -C $RepoRoot branch --show-current).Trim()
if ($branch -ne 'codex/forex-all-pairs-paper-total-closure-v1' -and $branch -ne 'main') {
    throw "NORMALIZED_MULTI_PAIR_BRANCH_REQUIRED: $branch"
}
if ($Cycles -lt 1 -or $Cycles -gt 288) { throw 'CYCLES_OUT_OF_RANGE' }
$runner = Join-Path $RepoRoot 'scripts\forex_delivery\run_forex_p1_multipair_normalized_paper_campaign_v1.py'
if (-not (Test-Path -LiteralPath $runner)) { throw 'NORMALIZED_MULTIPAIR_RUNNER_MISSING' }
$runtimeRoot = Join-Path $RepoRoot '.aios\runtime\forex_p1_multipair_normalized_paper_campaign_v1'
if ($PreflightOnly) {
    Write-Output "PREFLIGHT_ONLY:TRUE"
    Write-Output "SEGMENT_EXIT_CODE:0"
    return
}
& python $runner --repo-root $RepoRoot --runtime-root $runtimeRoot --cycles $Cycles --reviewer 'Human Owner Anthony' --report-json
$exitCode = $LASTEXITCODE
$statePath = Join-Path $runtimeRoot 'AIOS_FOREX_MULTIPAIR_NORMALIZED_PAPER_CAMPAIGN_STATE.json'
if ($exitCode -eq 0 -and (Test-Path -LiteralPath $statePath)) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        Write-Output "SEGMENT_STATUS:$($state.segment_status)"
        Write-Output "SEGMENT_STOP_REASON:$($state.segment_stop_reason)"
        Write-Output "LAST_ACTION:$($state.last_action)"
        Write-Output "LATEST_REJECTION_REASON:$($state.latest_rejection_reason)"
        Write-Output "ACCEPTED_QUALIFYING_TRADES:$($state.accepted_qualifying_trades)"
        Write-Output "ACTIVE_POSITION_STATUS:$($state.active_position_status)"
    } catch {
        Write-Output "SEGMENT_STATE_READ_FAILED"
    }
}
Write-Output "SEGMENT_EXIT_CODE:$exitCode"
if ($exitCode -ne 0) { throw "NORMALIZED_MULTIPAIR_CAMPAIGN_FAILED: $exitCode" }
