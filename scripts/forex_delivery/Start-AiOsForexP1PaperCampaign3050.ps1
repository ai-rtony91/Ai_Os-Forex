param(
    [string]$RepoRoot = 'C:\Dev\Ai.Os',
    [int]$Cycles = 288
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git'))) { throw 'REPO_ROOT_INVALID' }
$branch = (& git -C $RepoRoot branch --show-current).Trim()
if ($branch -ne 'main') { throw "CANONICAL_MAIN_REQUIRED: $branch" }
if ($Cycles -lt 1 -or $Cycles -gt 288) { throw 'CYCLES_OUT_OF_RANGE' }
$runner = Join-Path $RepoRoot 'automation\forex_engine\forex_p1_paper_autostart_v1.py'
if (-not (Test-Path -LiteralPath $runner)) { throw 'AUTOSTART_MISSING' }
$state = Join-Path $RepoRoot '.aios\runtime\forex_p1_supertrend_paper_sessions\active.json'
if (Test-Path -LiteralPath $state) {
    $active = Get-Content -LiteralPath $state -Raw | ConvertFrom-Json
    if ($active.status -in @('RUNNING','ACTIVE','WAITING_FOR_NEXT_RUN')) { throw 'CAMPAIGN_ALREADY_ACTIVE' }
}
& python $runner --repo-root $RepoRoot --cycles $Cycles --reviewer 'Human Owner Anthony'
if ($LASTEXITCODE -ne 0) { throw "PAPER_AUTOSTART_FAILED: $LASTEXITCODE" }
