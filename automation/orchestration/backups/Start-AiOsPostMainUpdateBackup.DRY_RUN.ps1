<#
Schema/contract reference: AIOS_POST_MAIN_UPDATE_BACKUP_PLAN.v1
Mode: DRY_RUN
blocked_capabilities:
  - robocopy_execution
  - backup_snapshot_creation
  - state_file_write
  - scheduler_registration
  - repo_mutation
  - git_mutation
  - delete_or_mirror_behavior
next_safe_action: Review the generated RoboCopy preview and approve an exact destination before any backup run.
commit_performed: NO / push_performed: NO
#>

[CmdletBinding()]
param(
    [string]$SourceRepo = "C:\Dev\Ai.Os",
    [string]$BackupRoot = "D:\T9_FOB",
    [string]$StateFilePath = "telemetry\backup_reports\AIOS_POST_MAIN_UPDATE_BACKUP_STATE.json",
    [string]$BackupTimeslotLabel = "manual",
    [string]$BackupWindowStart = "",
    [string]$BackupWindowEnd = "",
    [switch]$OutputJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workDeltaScript = Join-Path $PSScriptRoot "Get-AiOsBackupWorkDelta.ps1"
$courtesySosScript = Join-Path $PSScriptRoot "New-AiOsBackupCourtesySos.ps1"
. $workDeltaScript
. $courtesySosScript

function ConvertTo-AiOsFullPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    return [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
}

function ConvertTo-AiOsRelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $fullRoot = ConvertTo-AiOsFullPath -Path $Root
    $fullPath = ConvertTo-AiOsFullPath -Path $Path
    if ($fullPath.StartsWith($fullRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $fullPath.Substring($fullRoot.Length).TrimStart("\").Replace("\", "/")
    }

    return $fullPath.Replace("\", "/")
}

function Read-AiOsBackupState {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }

    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    }
    catch {
        return [pscustomobject]@{
            schema = "AIOS_POST_MAIN_UPDATE_BACKUP_STATE_PARSE_ERROR.v1"
            parse_error = $_.Exception.Message
            state_path = $Path
        }
    }
}

function Get-AiOsObjectPropertyValue {
    param(
        [AllowNull()][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()][object]$Default = $null
    )

    if ($null -eq $Object) {
        return $Default
    }

    if ($Object.PSObject.Properties.Name -contains $Name) {
        return $Object.$Name
    }

    return $Default
}

function Get-AiOsNamedBaseline {
    param(
        [AllowNull()][object]$Baselines,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $Baselines) {
        return $null
    }

    if ($Baselines.PSObject.Properties.Name -contains $Name) {
        return $Baselines.$Name
    }

    return $null
}

function Get-AiOsDailyAutomationSnapshot {
    param([string]$RepoRoot)

    $snapshotScript = Join-Path $RepoRoot 'automation\orchestration\daily_snapshot\New-AiOsDailyAutomationSnapshot.DRY_RUN.ps1'
    if (-not (Test-Path -LiteralPath $snapshotScript -PathType Leaf)) {
        throw "Daily snapshot script not found: $snapshotScript"
    }

    $snapshotOutput = @(& powershell -ExecutionPolicy Bypass -File $snapshotScript -Json 2>$null)
    if ($LASTEXITCODE -ne 0 -and $snapshotOutput.Count -eq 0) {
        throw "Daily snapshot script failed: $snapshotScript"
    }

    $snapshotJson = ($snapshotOutput -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($snapshotJson)) {
        throw "Daily snapshot script produced no JSON: $snapshotScript"
    }

    return $snapshotJson | ConvertFrom-Json
}

function New-AiOsPostMainBackupPlan {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][string]$CurrentCommit,
        [AllowNull()][string]$LastBackedUpCommit,
        [Parameter(Mandatory = $true)][bool]$BackupRequired,
        [Parameter(Mandatory = $true)][string]$RecommendedBackupPath,
        [Parameter(Mandatory = $true)][string]$RobocopyPreview,
        [Parameter(Mandatory = $true)][string]$NextSafeAction,
        [AllowNull()][string]$StateReadStatus
    )

    return [pscustomobject]@{
        schema = "AIOS_POST_MAIN_UPDATE_BACKUP_PLAN.v1"
        mode = "DRY_RUN"
        status = $Status
        backup_timeslot_label = $backupWorkDelta.backup_timeslot_label
        backup_timeslot_local = $backupWorkDelta.backup_timeslot_local
        backup_window_start = $backupWorkDelta.backup_window_start
        backup_window_end = $backupWorkDelta.backup_window_end
        current_commit = $CurrentCommit
        last_backed_up_commit = $LastBackedUpCommit
        last_successful_backup_commit = $backupWorkDelta.last_successful_backup_commit
        backup_required = $BackupRequired
        recommended_backup_path = $RecommendedBackupPath
        robocopy_preview = $RobocopyPreview
        writes_performed = 0
        state_file_path = ConvertTo-AiOsRelativePath -Root $normalizedSource -Path $resolvedStateFilePath
        state_read_status = $StateReadStatus
        excluded_paths = @($excludedDirs)
        excluded_secret_patterns = @($excludedSecretPatterns)
        backup_copied_metrics = $backupCopiedMetrics
        dev_work_delta_metrics = $backupWorkDelta.dev_work_delta_metrics
        daily_work_metrics = $backupWorkDelta.daily_work_metrics
        timeslot_work_metrics = $backupWorkDelta.timeslot_work_metrics
        courtesy_sos = $courtesySos
        state_update_preview = $stateUpdatePreview
        blocked_capabilities = @(
            "robocopy_execution",
            "backup_snapshot_creation",
            "state_file_write",
            "scheduler_registration",
            "repo_mutation",
            "git_mutation",
            "delete_or_mirror_behavior"
        )
        daily_data_snapshot_label = "DAILY DATA SNAPSHOT"
        daily_data_snapshot = $dailySnapshot
        next_safe_action = $NextSafeAction
        generated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    }
}

$expectedSource = "C:\Dev\Ai.Os"
$expectedBackupRoot = "D:\T9_FOB"
$normalizedSource = ConvertTo-AiOsFullPath -Path $SourceRepo
$normalizedBackupRoot = ConvertTo-AiOsFullPath -Path $BackupRoot

if ($normalizedSource -ne $expectedSource) {
    throw "Source repo must be exactly $expectedSource."
}

if ($normalizedBackupRoot -ne $expectedBackupRoot) {
    throw "Backup root must be exactly $expectedBackupRoot."
}

if (-not (Test-Path -LiteralPath $normalizedSource -PathType Container)) {
    throw "Source repo does not exist: $normalizedSource"
}

$resolvedStateFilePath = if ([System.IO.Path]::IsPathRooted($StateFilePath)) {
    ConvertTo-AiOsFullPath -Path $StateFilePath
}
else {
    ConvertTo-AiOsFullPath -Path (Join-Path $normalizedSource $StateFilePath)
}

$stateRoot = ConvertTo-AiOsFullPath -Path (Join-Path $normalizedSource "telemetry\backup_reports")
if (-not $resolvedStateFilePath.StartsWith($stateRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "State file path must stay under telemetry\backup_reports."
}

$currentCommit = Get-AiOsBackupGitHead -RepoRoot $normalizedSource
if ([string]::IsNullOrWhiteSpace([string]$currentCommit)) {
    throw "Unable to read current main commit with git rev-parse HEAD."
}

$currentCommit = [string]$currentCommit
$shortCommit = if ($currentCommit.Length -ge 7) { $currentCommit.Substring(0, 7) } else { $currentCommit }
$state = Read-AiOsBackupState -Path $resolvedStateFilePath
$dailySnapshot = Get-AiOsDailyAutomationSnapshot -RepoRoot $normalizedSource
$stateReadStatus = if ($null -eq $state) { "MISSING" } elseif ($state.PSObject.Properties.Name -contains "parse_error") { "PARSE_ERROR" } else { "READ" }
$lastSuccessfulBackupCommit = Get-AiOsObjectPropertyValue -Object $state -Name "last_successful_backup_commit" -Default $null
if ([string]::IsNullOrWhiteSpace([string]$lastSuccessfulBackupCommit)) {
    $lastSuccessfulBackupCommit = Get-AiOsObjectPropertyValue -Object $state -Name "last_backed_up_commit" -Default $null
}
$lastBackedUpCommit = if ([string]::IsNullOrWhiteSpace([string]$lastSuccessfulBackupCommit)) { $null } else { [string]$lastSuccessfulBackupCommit }

$timeslotBaselines = Get-AiOsObjectPropertyValue -Object $state -Name "timeslot_baselines" -Default $null
$dailyBaselines = Get-AiOsObjectPropertyValue -Object $state -Name "daily_baselines" -Default $null
$timeslotBaseline = Get-AiOsNamedBaseline -Baselines $timeslotBaselines -Name $BackupTimeslotLabel
$todayKey = (Get-Date).Date.ToString("yyyy-MM-dd")
$dailyBaseline = Get-AiOsNamedBaseline -Baselines $dailyBaselines -Name $todayKey
$timeslotBaseCommit = Get-AiOsObjectPropertyValue -Object $timeslotBaseline -Name "last_successful_backup_commit" -Default $null
if ([string]::IsNullOrWhiteSpace([string]$timeslotBaseCommit)) {
    $timeslotBaseCommit = Get-AiOsObjectPropertyValue -Object $timeslotBaseline -Name "commit" -Default $lastBackedUpCommit
}
$dayStartCommit = Get-AiOsObjectPropertyValue -Object $dailyBaseline -Name "day_start_commit" -Default $null

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$destinationName = "AIOS_BACKUP_POST_MAIN_${timestamp}_$shortCommit"
$recommendedBackupPath = [System.IO.Path]::Combine($normalizedBackupRoot, $destinationName)
$excludedDirs = @(".git", ".codex_backups", "node_modules", "__pycache__", ".venv", "dist", "build")
$excludedSecretPatterns = @(".env", "*.env", ".env.*", "*.pem", "*.key", "id_rsa", "id_ed25519", "*.pfx", "*.p12", "*secret*", "*secrets*")
$robocopyPreview = @(
    "robocopy",
    "`"$normalizedSource`"",
    "`"$recommendedBackupPath`"",
    "/E",
    "/XD"
) + ($excludedDirs | ForEach-Object { "`"$_`"" }) + @(
    "/XF"
) + ($excludedSecretPatterns | ForEach-Object { "`"$_`"" }) + @(
    "/R:2",
    "/W:2",
    "/COPY:DAT",
    "/DCOPY:DAT",
    "/NP",
    "/TEE"
)

$backupWorkDelta = Get-AiOsBackupWorkDeltaReport -RepoRoot $normalizedSource `
    -BaseCommit $lastBackedUpCommit `
    -CurrentCommit $currentCommit `
    -TimeslotLabel $BackupTimeslotLabel `
    -WindowStartLocal $BackupWindowStart `
    -WindowEndLocal $BackupWindowEnd `
    -DayStartCommit $dayStartCommit `
    -TimeslotBaseCommit $timeslotBaseCommit `
    -LastSuccessfulBackupCommit $lastBackedUpCommit
$backupCopiedMetrics = New-AiOsBackupCopiedMetrics -BackupMode "DRY_RUN_POST_MAIN_PREVIEW" `
    -BackupRoot $normalizedBackupRoot `
    -Destination $recommendedBackupPath `
    -CopiedFilesCount 0 `
    -CopiedBytes 0 `
    -ExcludedPaths $excludedDirs `
    -ExcludedSecretPatterns $excludedSecretPatterns `
    -FullSnapshotOrIncremental "FULL_SNAPSHOT_PREVIEW"
$timeslotBaselinePreview = [ordered]@{}
$timeslotBaselinePreview[$BackupTimeslotLabel] = [ordered]@{
    last_successful_backup_commit = $currentCommit
    last_successful_backup_timestamp = (Get-Date).ToString("o")
    last_successful_backup_path = $recommendedBackupPath
}
$dailyBaselinePreview = [ordered]@{}
$dailyBaselinePreview[$todayKey] = [ordered]@{
    day_start_commit = $backupWorkDelta.daily_work_metrics.day_start_commit
    current_commit = $currentCommit
    last_successful_backup_timestamp = (Get-Date).ToString("o")
}
$stateUpdatePreview = [pscustomobject][ordered]@{
    schema = "AIOS_POST_MAIN_UPDATE_BACKUP_STATE_PREVIEW.v1"
    dry_run_only = $true
    writes_performed = 0
    last_successful_backup_commit = $currentCommit
    last_successful_backup_timestamp = (Get-Date).ToString("o")
    last_successful_backup_path = $recommendedBackupPath
    timeslot_baselines = $timeslotBaselinePreview
    daily_baselines = $dailyBaselinePreview
}

$baselineMissing = -not $backupWorkDelta.dev_work_delta_metrics.available
$backupRequired = -not ($lastBackedUpCommit -and $lastBackedUpCommit -eq $currentCommit)
$status = if ($baselineMissing) { "BASELINE_UNKNOWN" } elseif ($backupRequired) { "BACKUP_RECOMMENDED" } else { "SKIP_BACKUP" }
$nextSafeAction = if ($baselineMissing) {
    "Establish the first successful backup baseline commit, then compare future reports against that commit."
}
elseif ($backupRequired) {
    "Approve the exact destination path before running any backup command."
}
else {
    "No backup needed for this commit unless the Human Owner requests a fresh snapshot."
}
$courtesySos = New-AiOsBackupCourtesySos -Status $status `
    -TimeslotLabel $backupWorkDelta.backup_timeslot_label `
    -CopiedMetrics $backupCopiedMetrics `
    -DevWorkDeltaMetrics $backupWorkDelta.dev_work_delta_metrics `
    -DailyWorkMetrics $backupWorkDelta.daily_work_metrics `
    -BaseCommit $backupWorkDelta.dev_work_delta_metrics.base_commit `
    -CurrentCommit $currentCommit `
    -Destination $recommendedBackupPath `
    -LogPath ""

$plan = New-AiOsPostMainBackupPlan -Status $status `
    -CurrentCommit $currentCommit `
    -LastBackedUpCommit $lastBackedUpCommit `
    -BackupRequired $backupRequired `
    -RecommendedBackupPath $recommendedBackupPath `
    -RobocopyPreview ($robocopyPreview -join " ") `
    -NextSafeAction $nextSafeAction `
    -StateReadStatus $stateReadStatus

if ($OutputJson) {
    $plan | ConvertTo-Json -Depth 6
}
else {
    $plan | ConvertTo-Json -Depth 6
}
