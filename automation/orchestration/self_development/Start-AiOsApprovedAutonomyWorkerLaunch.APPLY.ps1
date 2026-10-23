[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$ExpectedBranch = "main",
    [switch]$OutputJson,
    [ValidateSet("DRY_RUN", "APPLY")]
    [string]$Mode = "DRY_RUN",
    [string]$HumanOwnerWorkerLaunchApproval = "",
    [ValidateSet("READ_ONLY_VALIDATOR_CREW", "PACKET_PREVIEW_CREW", "SUPERVISED_DAY_CREW_12H", "SUPERVISED_DAY_NIGHT_CREW_24H", "WEEKEND_LOW_TOUCH_CREW", "VACATION_EMERGENCY_ONLY_CREW", "FULL_AUTONOMY_SUPERVISED_CREW")]
    [string]$WorkerPosture = "READ_ONLY_VALIDATOR_CREW",
    [string]$OperatingProfile = "24H_SUPERVISED",
    [ValidateRange(0, 10)]
    [int]$WorkerCount = 1,
    [ValidateRange(0, 10)]
    [int]$MaxParallelWorkers = 2,
    [string[]]$AllowedLanes = @("validator", "self_audit"),
    [ValidateRange(1, 1440)]
    [int]$TimeboxMinutes = 30,
    [bool]$StopOnFirstFailure = $true,
    [string]$IdentitySpineStatus = "UNKNOWN",
    [string]$ValidatorChainStatus = "UNKNOWN",
    [string]$ApprovalSosStatus = "UNKNOWN",
    [string]$PreflightDecision = "UNKNOWN",
    [string]$LaunchGuardDecision = "UNKNOWN",
    [string]$ResearchPlan = "",
    [string]$OutputRoot = "automation/orchestration/self_development/run_ledger",
    [string]$NowUtc = "",
    [bool]$FailOnDirtyWorktree = $true,
    [ValidateRange(1, 300)]
    [int]$TimeoutSeconds = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    param([string]$PathHint)
    if (-not [string]::IsNullOrWhiteSpace($PathHint)) {
        return (Resolve-Path -LiteralPath $PathHint).Path
    }
    $root = & git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($root)) {
        throw "Unable to resolve repository root."
    }
    return $root.Trim()
}

function Get-ChangedPathFromStatusLine {
    param([string]$Line)
    if ([string]::IsNullOrWhiteSpace($Line) -or $Line -like "##*") { return $null }
    if ($Line.Length -lt 4) { return $null }
    $path = $Line.Substring(3).Trim()
    if ($path -match " -> ") {
        $pathParts = $path -split " -> "
        if ($null -ne $pathParts -and $pathParts.Length -gt 0) {
            $path = $pathParts[$pathParts.Length - 1].Trim()
        }
    }
    return $path.Replace("\", "/")
}

function Test-ApprovedAutonomyDirtyState {
    param([string[]]$StatusLines)
    $allowedExact = @(
        "automation/orchestration/self_development/aios_approved_autonomy_worker_launch_controller.py",
        "automation/orchestration/self_development/Start-AiOsApprovedAutonomyWorkerLaunch.APPLY.ps1",
        "schemas/aios/orchestration/AIOS_APPROVED_AUTONOMY_WORKER_LAUNCH_RESULT.v1.schema.json",
        "tests/orchestration/test_aios_approved_autonomy_worker_launch_controller.py",
        "tests/orchestration/test_aios_approved_autonomy_worker_launch_runner.py",
        "automation/orchestration/self_development/aios_autonomy_run_ledger.py",
        "schemas/aios/orchestration/AIOS_AUTONOMY_RUN_LEDGER_RECORD.v1.schema.json",
        "tests/orchestration/test_aios_autonomy_run_ledger.py",
        "automation/orchestration/self_development/aios_autonomous_forex_research_pipeline.py",
        "automation/orchestration/self_development/Start-AiOsAutonomousForexResearchRun.APPLY.ps1",
        "schemas/aios/orchestration/AIOS_AUTONOMOUS_FOREX_RESEARCH_RUN_RESULT.v1.schema.json",
        "tests/orchestration/test_aios_autonomous_forex_research_pipeline.py",
        "tests/orchestration/test_aios_autonomous_forex_research_runner.py",
        "automation/orchestration/self_development/aios_minimal_sos_wake_policy.py",
        "schemas/aios/orchestration/AIOS_MINIMAL_SOS_WAKE_POLICY_RESULT.v1.schema.json",
        "tests/orchestration/test_aios_minimal_sos_wake_policy.py",
        "automation/orchestration/recommendations/Get-AiOsActionRecommendation.DRY_RUN.ps1",
        "schemas/aios/orchestration/ORCHESTRATION_SCHEMA_INDEX.json"
    )
    $changed = @($StatusLines | ForEach-Object { Get-ChangedPathFromStatusLine -Line ([string]$_) } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($changed.Count -eq 0) { return $false }
    foreach ($path in $changed) {
        if (-not ($allowedExact -contains $path)) { return $false }
    }
    return $true
}

function Invoke-PythonJsonLogic {
    param([string]$LogicPath, [object]$Payload, [int]$TimeoutSecondsValue)
    $payloadJson = $Payload | ConvertTo-Json -Depth 90
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = "python"
    $psi.Arguments = ('"{0}"' -f ($LogicPath -replace '"', '\"'))
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.WorkingDirectory = $resolvedRepoRoot
    $previousPythonPath = [System.Environment]::GetEnvironmentVariable("PYTHONPATH")
    if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
        $env:PYTHONPATH = $resolvedRepoRoot
    }
    else {
        $env:PYTHONPATH = "$resolvedRepoRoot$([System.IO.Path]::PathSeparator)$previousPythonPath"
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    try {
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.StandardInput.Write($payloadJson)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit($TimeoutSecondsValue * 1000)) {
            $process.Kill()
            throw "AIOS approved autonomy worker launch controller timed out."
        }
        $rawText = $stdoutTask.Result.Trim()
        $errorText = $stderrTask.Result.Trim()
        if ([string]::IsNullOrWhiteSpace($rawText)) {
            throw "AIOS approved autonomy worker launch controller returned no JSON. $errorText"
        }
        return $rawText | ConvertFrom-Json -ErrorAction Stop
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
    }
}

function Write-ConsoleReport {
    param([object]$Result)
    Write-Host "AIOS Approved Autonomy Worker Launch Controller"
    Write-Host "Mode: $($Result.mode)"
    Write-Host "Schema: $($Result.schema)"
    Write-Host ""
    Write-Host "LAUNCH DECISION"
    Write-Host "launch_decision: $($Result.launch_decision)"
    Write-Host "worker_posture: $($Result.worker_posture)"
    Write-Host "worker_count: $($Result.worker_count)"
    Write-Host "allowed_lanes: $(@($Result.allowed_lanes) -join ', ')"
    Write-Host "executed_task_count: $($Result.executed_task_count)"
    Write-Host "ledger_written: $($Result.run_ledger.written)"
    Write-Host ""
    Write-Host "SAFETY"
    Write-Host "starts_runtime: $($Result.safety.starts_runtime)"
    Write-Host "launches_workers: $($Result.safety.launches_workers)"
    Write-Host "enables_scheduler: $($Result.safety.enables_scheduler)"
    Write-Host "starts_daemon: $($Result.safety.starts_daemon)"
    Write-Host "broker_or_live_trading: $($Result.safety.broker_or_live_trading)"
    Write-Host ""
    Write-Host "NEXT SAFE ACTION"
    Write-Host $Result.next_safe_action
    Write-Host ""
    Write-Host "STATUS: $($Result.safety.status)"
}

$resolvedRepoRoot = Get-RepoRoot -PathHint $RepoRoot
$logicPath = Join-Path $PSScriptRoot "aios_approved_autonomy_worker_launch_controller.py"
$generatedUtc = if ([string]::IsNullOrWhiteSpace($NowUtc)) { (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") } else { $NowUtc }
$statusLines = @(& git -C $resolvedRepoRoot status --short --branch --untracked-files=all 2>$null)
$branch = (& git -C $resolvedRepoRoot branch --show-current 2>$null).Trim()
$dirtyEntries = @($statusLines | Where-Object { $_ -notlike "##*" })
$dirtyAllowed = Test-ApprovedAutonomyDirtyState -StatusLines $statusLines

$repoState = [ordered]@{
    repo_root = $resolvedRepoRoot
    branch = $branch
    expected_branch = $ExpectedBranch
    branch_matches_expected = ([string]$branch -eq [string]$ExpectedBranch)
    dirty = ($dirtyEntries.Count -gt 0)
    dirty_allowed_for_approved_autonomy_worker_launch_validation = [bool]$dirtyAllowed
    fail_on_dirty_worktree = [bool]$FailOnDirtyWorktree
    status_lines = @($statusLines)
}

$payload = [ordered]@{
    repo_root = $resolvedRepoRoot
    generated_utc = $generatedUtc
    repo_state = $repoState
    mode = $Mode
    human_owner_worker_launch_approval = $HumanOwnerWorkerLaunchApproval
    worker_posture = $WorkerPosture
    operating_profile = $OperatingProfile
    worker_count = $WorkerCount
    max_parallel_workers = $MaxParallelWorkers
    allowed_lanes = @($AllowedLanes)
    timebox_minutes = $TimeboxMinutes
    stop_on_first_failure = $StopOnFirstFailure
    identity_spine_status = $IdentitySpineStatus
    validator_chain_status = $ValidatorChainStatus
    approval_sos_status = $ApprovalSosStatus
    preflight_decision = $PreflightDecision
    launch_guard_decision = $LaunchGuardDecision
    research_plan = $ResearchPlan
    output_root = $OutputRoot
    write_ledger = ([string]$Mode -eq "APPLY")
}

$result = Invoke-PythonJsonLogic -LogicPath $logicPath -Payload $payload -TimeoutSecondsValue $TimeoutSeconds

if ($OutputJson) {
    $result | ConvertTo-Json -Depth 90
}
else {
    Write-ConsoleReport -Result $result
}

if ([string]$result.safety.status -in @("PASS", "REVIEW_REQUIRED")) { exit 0 }
exit 1
