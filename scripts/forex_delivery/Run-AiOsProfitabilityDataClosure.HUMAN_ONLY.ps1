param(
    [string]$RepoRoot = "C:\Dev\Ai.Os",
    [string]$OfficialScript = "scripts/forex_delivery/Download-AiOsOfficialForexResearchData.HUMAN_ONLY.ps1",
    [string]$PracticeScript = "scripts/forex_delivery/Acquire-AiOsOandaPracticeHistory.HUMAN_ONLY.ps1",
    [string]$StatePath = "Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_DATA_CLOSURE_STATE_V1.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-AiOsRepoRoot {
    param([string]$ExpectedRoot)
    $resolved = (Resolve-Path -LiteralPath ".").Path
    if ($resolved -ne $ExpectedRoot) {
        throw "AIOS_DATA_CLOSURE_BLOCKED: run from $ExpectedRoot"
    }
}

function Assert-AiOsHumanOnlyScript {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "AIOS_DATA_CLOSURE_BLOCKED: script not found $Path"
    }
}

Assert-AiOsRepoRoot -ExpectedRoot $RepoRoot
Assert-AiOsHumanOnlyScript -Path $OfficialScript
Assert-AiOsHumanOnlyScript -Path $PracticeScript

Write-Host "AIOS Profitability Data Closure - Human Only"
Write-Host "Run this outside Codex. Do not paste tokens or account data into Codex."
Write-Host "Step 1/2: official public data download."
& powershell -NoProfile -ExecutionPolicy Bypass -File $OfficialScript
if ($LASTEXITCODE -ne 0) {
    throw "AIOS_DATA_CLOSURE_BLOCKED: official data helper failed"
}

Write-Host "Step 2/2: OANDA Practice GET-only history acquisition."
Write-Host "Enter the Practice token only into the masked prompt opened by the helper."
& powershell -NoProfile -ExecutionPolicy Bypass -File $PracticeScript
if ($LASTEXITCODE -ne 0) {
    throw "AIOS_DATA_CLOSURE_BLOCKED: Practice history helper failed"
}

$officialReady = Test-Path -LiteralPath ".aios/runtime/forex_official_data_human_inbox"
$practiceManifest = Test-Path -LiteralPath ".aios/runtime/forex_practice_history_human_inbox/practice_history.manifest.json"
$state = [pscustomobject]@{
    schema = "AIOS_FOREX_PROFITABILITY_DATA_CLOSURE_STATE_V1"
    status = "HUMAN_DATA_CLOSURE_COMMAND_COMPLETE"
    created_by = "Human Owner outside Codex"
    official_data_ready = [bool]$officialReady
    practice_history_ready = [bool]$practiceManifest
    secret_value_exposed = $false
    live_host_contacted = $false
    order_attempted = $false
    broker_mutation = $false
    funding_attempted = $false
}

$stateDir = Split-Path -Parent $StatePath
if (-not [string]::IsNullOrWhiteSpace($stateDir)) {
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
}
$state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $StatePath -Encoding UTF8
$state | ConvertTo-Json -Depth 8
