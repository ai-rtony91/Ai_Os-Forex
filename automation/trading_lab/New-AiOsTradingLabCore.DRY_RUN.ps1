param()

$ErrorActionPreference = "Stop"

# Legacy scaffold preview only. The docs/AI_OS/trading_laboratory paths below are historical planning targets, not current authority.
# This DRY_RUN script must not be treated as approval for APPLY, live trading, broker execution, real webhooks, real orders, credentials, commit, push, merge, or deployment.

$ExpectedRootName = "Ai.Os"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RepoName = Split-Path -Leaf $RepoRoot

if ($RepoName -ne $ExpectedRootName) {
    throw "Repo root verification failed. Expected folder '$ExpectedRootName' but found '$RepoName' at '$RepoRoot'."
}

$Timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$ReportPath = Join-Path $RepoRoot "Reports\health\TRADING_LAB_CORE_DRY_RUN_$Timestamp.md"

$PlannedFolders = @(
    "docs/AI_OS/trading_laboratory",
    "docs/AI_OS/trading_laboratory/telemetry",
    "docs/AI_OS/trading_laboratory/paper_trades",
    "docs/AI_OS/trading_laboratory/signal_logs",
    "docs/AI_OS/trading_laboratory/regime_analysis",
    "docs/AI_OS/trading_laboratory/expectancy",
    "docs/AI_OS/trading_laboratory/postmortems",
    "docs/AI_OS/trading_laboratory/replay",
    "docs/AI_OS/trading_laboratory/metrics",
    "docs/AI_OS/trading_laboratory/schemas",
    "docs/AI_OS/trading_laboratory/reports",
    "automation/trading_lab"
)

$PlannedFiles = @(
    "automation/trading_lab/New-AiOsTradingLabCore.DRY_RUN.ps1",
    "automation/trading_lab/New-AiOsTradingLabCore.APPLY.ps1",
    "automation/trading_lab/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/telemetry/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/paper_trades/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/signal_logs/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/regime_analysis/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/expectancy/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/postmortems/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/replay/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/metrics/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/schemas/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/reports/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/README.md",
    "docs/AI_OS/trading_laboratory/TRADING_LAB_CORE_SPEC.md",
    "docs/AI_OS/trading_laboratory/schemas/signal.schema.json",
    "docs/AI_OS/trading_laboratory/schemas/execution.schema.json",
    "docs/AI_OS/trading_laboratory/schemas/regime.schema.json",
    "docs/AI_OS/trading_laboratory/schemas/trade_outcome.schema.json",
    "docs/AI_OS/trading_laboratory/schemas/expectancy_metrics.schema.json",
    "docs/AI_OS/trading_laboratory/paper_trades/PAPER_TRADE_LEDGER_TEMPLATE.csv",
    "docs/AI_OS/trading_laboratory/signal_logs/SIGNAL_LOG_TEMPLATE.csv",
    "docs/AI_OS/trading_laboratory/regime_analysis/REGIME_TAGGING_RULES_DRAFT.md",
    "docs/AI_OS/trading_laboratory/expectancy/EXPECTANCY_METRICS_DRAFT.md",
    "docs/AI_OS/trading_laboratory/postmortems/TRADE_POSTMORTEM_TEMPLATE.md",
    "docs/AI_OS/trading_laboratory/replay/REPLAY_RECORD_TEMPLATE.json",
    "docs/AI_OS/trading_laboratory/metrics/TRADING_LAB_METRICS_TEMPLATE.csv",
    "docs/AI_OS/trading_laboratory/reports/TRADING_LAB_DAILY_REPORT_TEMPLATE.md"
)

$FolderRows = foreach ($Path in $PlannedFolders) {
    $FullPath = Join-Path $RepoRoot ($Path -replace "/", "\")
    [pscustomobject]@{
        Path = $Path
        Type = "folder"
        Status = if (Test-Path -LiteralPath $FullPath -PathType Container) { "SKIPPED_EXISTS" } else { "WOULD_CREATE" }
    }
}

$FileRows = foreach ($Path in $PlannedFiles) {
    $FullPath = Join-Path $RepoRoot ($Path -replace "/", "\")
    [pscustomobject]@{
        Path = $Path
        Type = "file"
        Status = if (Test-Path -LiteralPath $FullPath -PathType Leaf) { "SKIPPED_EXISTS" } else { "WOULD_CREATE" }
    }
}

$AllRows = @($FolderRows + $FileRows)
$WouldCreateCount = @($AllRows | Where-Object { $_.Status -eq "WOULD_CREATE" }).Count
$SkippedExistingCount = @($AllRows | Where-Object { $_.Status -eq "SKIPPED_EXISTS" }).Count

$Report = @()
$Report += "# AI_OS Trading Laboratory Core DRY_RUN Report"
$Report += ""
$Report += "- Mode: DRY_RUN"
$Report += "- Repo root: $RepoRoot"
$Report += "- Timestamp: $Timestamp"
$Report += "- Proposed report path: $ReportPath"
$Report += "- Would-create count: $WouldCreateCount"
$Report += "- Skipped-existing count: $SkippedExistingCount"
$Report += "- Safety: no backend, no API calls, no credentials, no persistence, no broker/trading automation, no live order path"
$Report += ""
$Report += "## Planned Folders"
$Report += ""
foreach ($Row in $FolderRows) {
    $Report += "- $($Row.Status): $($Row.Path)"
}
$Report += ""
$Report += "## Planned Files"
$Report += ""
foreach ($Row in $FileRows) {
    $Report += "- $($Row.Status): $($Row.Path)"
}
$Report += ""
$Report += "## Boundary"
$Report += ""
$Report += "DRY_RUN made no scaffold changes. This report is emitted to stdout; no files are written."
$Report += ""
$Report += "DRY_RUN COMPLETE - REVIEW REPORT BEFORE APPLY"

Write-Output ($Report -join [Environment]::NewLine)

Write-Host "Repo root: $RepoRoot"
Write-Host "Proposed report path: $ReportPath"
Write-Host "Would-create count: $WouldCreateCount"
Write-Host "Skipped-existing count: $SkippedExistingCount"
Write-Host "DRY_RUN COMPLETE - REVIEW REPORT BEFORE APPLY"
