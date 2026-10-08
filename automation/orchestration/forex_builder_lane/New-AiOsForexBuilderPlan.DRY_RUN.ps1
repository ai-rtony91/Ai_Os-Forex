param(
    [Parameter(Mandatory = $true)]
    [string]$GoalText,
    [string]$ProposedJsonPath = "Reports/forex_builder_lane/forex_builder_plan.json",
    [string]$ProposedMarkdownPath = "Reports/forex_builder_lane/forex_builder_plan.md"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Get-AiOsRepoRoot {
    $repoRoot = (& git rev-parse --show-toplevel 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoRoot)) {
        throw "REVIEW_REQUIRED: Unable to resolve repository root."
    }
    return $repoRoot.Trim()
}

function Resolve-AiOsPath {
    param(
        [Parameter(Mandatory = $true)][string]$PathHint,
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )
    if ([string]::IsNullOrWhiteSpace($PathHint)) {
        return [string]::Empty
    }
    if ([System.IO.Path]::IsPathRooted($PathHint)) {
        return [System.IO.Path]::GetFullPath($PathHint)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $PathHint))
}

function New-SafeCommand {
    param([string]$GoalText, [string]$Category)
    return ('.\aios.ps1 -Mode autonomy -Goal "Plan paper-safe implementation for ' + $Category + ' related to: ' + $GoalText + '"')
}

function Classify-Goal {
    param([string]$GoalText)

    $lower = $GoalText.ToLowerInvariant()
    $categories = @()
    if ($lower -match "signal|alert|intake|paper[_ -]?signal|source") { $categories += "paper_signal_intake" }
    if ($lower -match "replay|histor|backtest") { $categories += "paper_replay" }
    if ($lower -match "route|preview|paper route|execution path") { $categories += "paper_route_preview" }
    if ($lower -match "quality|accuracy|precision|recall|metrics|score") { $categories += "execution_quality" }
    if ($lower -match "latency|lag|delay|timing") { $categories += "latency_ledger" }
    if ($lower -match "regime|market state|state filter") { $categories += "regime_filter" }
    if ($lower -match "risk|training risk|risk model|guardrails") { $categories += "risk_training" }
    if ($lower -match "dashboard|report|summary|status") { $categories += "dashboard_reporting" }
    if ($lower -match "content|curriculum|lesson|training module") { $categories += "training_content" }
    if ($lower -match "fixture|sample|synthetic|data set|stub|mock") { $categories += "data_fixtures" }
    if ($lower -match "validate|validation|governance|checker") { $categories += "validation" }
    if ($categories.Count -eq 0) {
        $categories = @("paper_signal_intake", "paper_replay", "validation")
    }
    return , $categories
}

function Detect-ForbiddenKeywords {
    param([string]$GoalText)
    $lower = $GoalText.ToLowerInvariant()
    return @(
        "live trade", "live trading", "live_trading", "real trade", "real orders", 
        "real order", "order placement", "broker", "webhook", "credential", "secret",
        "real api", "api key", "sso", "token"
    ) | Where-Object { $lower.Contains($_) }
}

function Render-PacketText {
    param(
        [string]$GoalText,
        [string[]]$Categories
    )
    $categoryList = ($Categories | ForEach-Object { "- " + $_ }) -join "`n"
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    return @"
CODEX-ONLY PROMPT
AI_OS EXECUTION TOKEN: PENDING_FOREX_BUILDER_PLAN
AUTHORITY FILES: do_not_modify

PACKET ID: AIOS-FOREX-BUILDER-PLAN-$timestamp
MODE: DRY_RUN_FIRST_BUILD_PLAN

# Forex Builder Safe Paper-Only Plan

Goal:
$GoalText

Planned safe categories:
$categoryList

Execution intent:
- Paper-only implementation only
- No live trading
- No broker execution
- No credential work
- No real webhook sends
"@
}

try {
    $repoRoot = Get-AiOsRepoRoot
    $proposedJson = Resolve-AiOsPath -PathHint $ProposedJsonPath -RepoRoot $repoRoot
    $proposedMarkdown = Resolve-AiOsPath -PathHint $ProposedMarkdownPath -RepoRoot $repoRoot

    $blocked = Detect-ForbiddenKeywords -GoalText $GoalText
    $isBlocked = $blocked.Count -gt 0
    $mappedCategories = Classify-Goal -GoalText $GoalText
    $packetText = Render-PacketText -GoalText $GoalText -Categories $mappedCategories
    $proposedPacketPath = Join-Path (Split-Path -Parent $proposedMarkdown) "forex_builder_next_packet.md"

    $categoryActions = @()
    foreach ($category in $mappedCategories) {
        $categoryActions += [ordered]@{
            category = $category
            safe_command = New-SafeCommand -GoalText $GoalText -Category $category
            allowed = $true
            notes = "paper-safe lane"
        }
    }

    $nextActions = if ($isBlocked) { @() } else { @($categoryActions) }
    $forbiddenMatches = @()
    $blockedCommands = @()

    $report = [ordered]@{
        schema_version = "AIOS-FOREX-BUILDER-LANE-PLAN-V1"
        created_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        mode = "paper_only_plan"
        goal = $GoalText
        mapped_categories = $mappedCategories
        paper_only = $true
        blocked_keywords = $blocked
        blocked_commands = $blockedCommands
        can_progress = -not $isBlocked
        next_actions = $nextActions
        packet_metadata = [ordered]@{
            packet_id = "AIOS-FOREX-BUILDER-PLAN"
            proposed_packet_path = $proposedPacketPath
            packet_text = $packetText
            safety = @(
                "paper only",
                "no live trading",
                "no broker execution",
                "no real orders",
                "no credentials",
                "no real webhook"
            )
        }
        proposed_markdown_path = $proposedMarkdown
        proposed_json_path = $proposedJson
    }

    $markdown = @"
# Forex Builder Lane Plan

## Goal
$GoalText

## Paper-only Categories
$( $mappedCategories | ForEach-Object { "- " + $_ } )

## What can run safely next
$( $categoryActions | ForEach-Object { "- " + $_.category + ": " + $_.safe_command } )

## Required safeguards
- Paper-only outputs only
- No live trading
- No broker execution
- No real webhook sends
- No credentials or secret mutation
"@

    Write-Output ($report | ConvertTo-Json -Depth 20)

    if ($isBlocked -or $blockedCommands.Count -gt 0) {
        exit 1
    }
    exit 0
} catch {
    $errorMessage = "REVIEW_REQUIRED: $($_.Exception.Message)"
    $errorReport = [ordered]@{
        schema_version = "AIOS-FOREX-BUILDER-LANE-PLAN-V1"
        created_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        mode = "paper_only_plan"
        goal = $GoalText
        mapped_categories = @()
        paper_only = $true
        blocked_keywords = @()
        blocked_commands = @("review_required")
        can_progress = $false
        next_actions = @()
        packet_metadata = [ordered]@{
            packet_id = "AIOS-FOREX-BUILDER-PLAN"
            proposed_packet_path = ""
            packet_text = $errorMessage
            safety = @(
                "paper only",
                "no live trading",
                "no broker execution",
                "no real orders",
                "no credentials",
                "no real webhook"
            )
        }
        proposed_markdown_path = $proposedMarkdown
        proposed_json_path = $proposedJson
    }
    Write-Output ($errorReport | ConvertTo-Json -Depth 20)
    exit 1
}
