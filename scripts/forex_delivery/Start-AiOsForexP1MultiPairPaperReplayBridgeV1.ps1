param(
    [string]$RepoRoot = 'C:\Dev\Ai.Os',
    [int]$CandleCount = 500,
    [switch]$Json
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git'))) { throw 'REPO_ROOT_INVALID' }
& python (Join-Path $RepoRoot 'scripts\forex_delivery\run_forex_multipair_m5_replay_v1.py') --runtime-root (Join-Path $RepoRoot '.aios\runtime\forex_multipair_m5_replay_v1') --candle-count $CandleCount @(
    if ($Json) { '--json' }
)
if ($LASTEXITCODE -ne 0) { throw "MULTIPAIR_REPLAY_BRIDGE_FAILED: $LASTEXITCODE" }
