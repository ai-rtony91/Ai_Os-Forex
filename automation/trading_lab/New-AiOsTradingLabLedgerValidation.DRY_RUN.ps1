param()

$ErrorActionPreference = "Stop"

# Legacy scaffold preview only. The docs/AI_OS/trading_laboratory paths below are historical planning targets, not current authority.
# This DRY_RUN script must not be treated as approval for APPLY, live trading, broker execution, real webhooks, real orders, credentials, commit, push, merge, or deployment.

$ExpectedRootName = "Ai.Os"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RepoName = Split-Path -Leaf $RepoRoot

if ($RepoName -ne $ExpectedRootName) {
    throw "Repo root verification failed. Expected '$ExpectedRootName' but found '$RepoName' at '$RepoRoot'."
}

$Timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$ReportPath = Join-Path $RepoRoot "Reports\health\TRADING_LAB_LEDGER_VALIDATION_DRY_RUN_$Timestamp.md"

$PlannedFolders = @(
    "docs/AI_OS/trading_laboratory/validation"
)

$PlannedFiles = @(
    "automation/trading_lab/New-AiOsTradingLabLedgerValidation.DRY_RUN.ps1",
    "automation/trading_lab/New-AiOsTradingLabLedgerValidation.APPLY.ps1",
    "docs/AI_OS/trading_laboratory/validation/README_FOLDER_PURPOSE.txt",
    "docs/AI_OS/trading_laboratory/validation/TRADING_LAB_SCHEMA_VALIDATION_SPEC.md",
    "docs/AI_OS/trading_laboratory/validation/VALIDATION_RULES_DRAFT.md",
    "docs/AI_OS/trading_laboratory/validation/VALIDATION_RESULT_TEMPLATE.json",
    "docs/AI_OS/trading_laboratory/validation/VALIDATION_ERROR_CODES_DRAFT.md",
    "docs/AI_OS/trading_laboratory/paper_trades/PAPER_TRADE_LEDGER_COLUMNS.md",
    "docs/AI_OS/trading_laboratory/signal_logs/SIGNAL_LOG_COLUMNS.md",
    "docs/AI_OS/trading_laboratory/metrics/EXPECTANCY_CALCULATION_NOTES.md"
)

function Get-PathStatus {
    param(
        [string]$RelativePath,
        [string]$Kind
    )

    $FullPath = Join-Path $RepoRoot ($RelativePath -replace "/", "\")
    if ($Kind -eq "folder") {
        if (Test-Path -LiteralPath $FullPath -PathType Container) { return "SKIPPED_EXISTS" }
        $Parent = Split-Path -Parent $FullPath
        if (-not (Test-Path -LiteralPath $Parent -PathType Container)) { return "BLOCKED_PARENT_MISSING" }
        return "WOULD_CREATE"
    }

    if (Test-Path -LiteralPath $FullPath -PathType Leaf) { return "SKIPPED_EXISTS" }
    $ParentPath = Split-Path -Parent $FullPath
    $RelativeParent = ($ParentPath.Substring($RepoRoot.Length).TrimStart("\") -replace "\\", "/")
    $ParentPlanned = $PlannedFolders -contains $RelativeParent
    if ((Test-Path -LiteralPath $ParentPath -PathType Container) -or $ParentPlanned) { return "WOULD_CREATE" }
    return "BLOCKED_PARENT_MISSING"
}

$FolderRows = foreach ($Path in $PlannedFolders) {
    [pscustomobject]@{
        Path = $Path
        Type = "folder"
        Status = Get-PathStatus -RelativePath $Path -Kind "folder"
    }
}

$FileRows = foreach ($Path in $PlannedFiles) {
    [pscustomobject]@{
        Path = $Path
        Type = "file"
        Status = Get-PathStatus -RelativePath $Path -Kind "file"
    }
}

$AllRows = @($FolderRows) + @($FileRows)
$WouldCreateCount = @($AllRows | Where-Object { $_.Status -eq "WOULD_CREATE" }).Count
$SkippedExistingCount = @($AllRows | Where-Object { $_.Status -eq "SKIPPED_EXISTS" }).Count
$BlockedParentMissingCount = @($AllRows | Where-Object { $_.Status -eq "BLOCKED_PARENT_MISSING" }).Count

$Report = @()
$Report += "# AI_OS Trading Laboratory Ledger + Schema Validation DRY_RUN Report"
$Report += ""
$Report += "- Mode: DRY_RUN"
$Report += "- Repo root: $RepoRoot"
$Report += "- Timestamp: $Timestamp"
$Report += "- Proposed report path: $ReportPath"
$Report += "- Would-create count: $WouldCreateCount"
$Report += "- Skipped-existing count: $SkippedExistingCount"
$Report += "- Blocked-parent-missing count: $BlockedParentMissingCount"
$Report += "- Safety: no credentials, no broker/live trading logic, no backend/API calls, no persistence, no live order path"
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
$Report += "DRY_RUN made no validation scaffold changes. This report is emitted to stdout; no files are written."
$Report += ""
$Report += "DRY_RUN COMPLETE - REVIEW BEFORE APPLY"

Write-Output ($Report -join [Environment]::NewLine)

Write-Host "Repo root: $RepoRoot"
Write-Host "Proposed report path: $ReportPath"
Write-Host "Would-create count: $WouldCreateCount"
Write-Host "Skipped-existing count: $SkippedExistingCount"
Write-Host "Blocked-parent-missing count: $BlockedParentMissingCount"
Write-Host "DRY_RUN COMPLETE - REVIEW BEFORE APPLY"
