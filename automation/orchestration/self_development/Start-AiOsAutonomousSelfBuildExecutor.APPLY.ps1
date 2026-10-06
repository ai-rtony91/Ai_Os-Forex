[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$ExpectedBranch = "main",
    [switch]$OutputJson,
    [ValidateSet("DRY_RUN", "APPLY")]
    [string]$Mode = "DRY_RUN",
    [string]$HumanOwnerSelfBuildApproval = "",
    [ValidateSet("PLAN_ONLY", "SELECT_NEXT_CANDIDATE", "BUILD_EXECUTION_PACKET", "VALIDATE_AND_REPAIR_STUB", "FULL_LOCAL_SELF_BUILD_STUB")]
    [string]$SupervisorMode = "PLAN_ONLY",
    [ValidateRange(1, 20)]
    [int]$MaxSupervisorCycles = 1,
    [ValidateRange(0, 5)]
    [int]$MaxRepairAttempts = 2,
    [ValidateRange(5, 240)]
    [int]$MaxRuntimeMinutes = 60,
    [bool]$StopOnFirstFailure = $true,
    [bool]$AllowLocalCommit = $false,
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
            throw "AIOS autonomous self-build executor timed out."
        }
        $rawText = $stdoutTask.Result.Trim()
        $errorText = $stderrTask.Result.Trim()
        if ([string]::IsNullOrWhiteSpace($rawText)) {
            throw "AIOS autonomous self-build executor returned no JSON. $errorText"
        }
        return $rawText | ConvertFrom-Json -ErrorAction Stop
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
    }
}

function Write-ConsoleReport {
    param([object]$Result)
    Write-Host "AIOS Autonomous Self-Build Executor"
    Write-Host "Mode: $($Result.mode)"
    Write-Host "supervisor_mode: $($Result.supervisor_mode)"
    Write-Host "candidate_id: $($Result.selected_candidate.candidate_id)"
    Write-Host "candidate_lane: $($Result.selected_candidate.candidate_lane)"
    Write-Host "repair_status: $($Result.validation_repair_result.status)"
    Write-Host "ledger_written: $($Result.run_ledger.written)"
    Write-Host "executed_autonomously: $($Result.executed_autonomously)"
    Write-Host "safety_status: $($Result.safety.status)"
    Write-Host "next_safe_action: $($Result.next_safe_action)"
}

$resolvedRepoRoot = Get-RepoRoot -PathHint $RepoRoot
$logicPath = Join-Path $PSScriptRoot "aios_autonomous_self_build_executor.py"
$generatedUtc = if ([string]::IsNullOrWhiteSpace($NowUtc)) { (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") } else { $NowUtc }
$statusLines = @(& git -C $resolvedRepoRoot status --short --branch --untracked-files=all 2>$null)
$branch = (& git -C $resolvedRepoRoot branch --show-current 2>$null).Trim()
$dirtyEntries = @($statusLines | Where-Object { $_ -notlike "##*" })
$repoState = [ordered]@{
    repo_root = $resolvedRepoRoot
    branch = $branch
    expected_branch = $ExpectedBranch
    branch_matches_expected = ([string]$branch -eq [string]$ExpectedBranch)
    dirty = ($dirtyEntries.Count -gt 0)
    fail_on_dirty_worktree = [bool]$FailOnDirtyWorktree
    status_lines = @($statusLines)
}

$payload = [ordered]@{
    repo_root = $resolvedRepoRoot
    generated_utc = $generatedUtc
    repo_state = $repoState
    mode = $Mode
    human_owner_self_build_approval = $HumanOwnerSelfBuildApproval
    supervisor_mode = $SupervisorMode
    max_supervisor_cycles = $MaxSupervisorCycles
    max_repair_attempts = $MaxRepairAttempts
    max_runtime_minutes = $MaxRuntimeMinutes
    stop_on_first_failure = $StopOnFirstFailure
    allow_local_commit = $AllowLocalCommit
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

if ([string]$result.safety.status -eq "PASS") { exit 0 }
exit 1
