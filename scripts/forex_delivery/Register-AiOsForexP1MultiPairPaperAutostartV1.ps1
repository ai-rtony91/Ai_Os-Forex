param(
    [datetime]$StartAt = [datetime]::Parse("2026-08-27T17:00:00"),
    [string]$RepoRoot = "C:\Dev\Ai.Os",
    [int]$Cycles = 288,
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$taskName = "AIOS-Forex-P1-MultiPair-Paper-Autostart-V1"
$launcher = Join-Path $RepoRoot "scripts\forex_delivery\Start-AiOsForexP1MultiPairPaperCampaignV1.ps1"
$powershell = (Get-Command powershell.exe -ErrorAction Stop).Source

if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "MULTIPAIR_LAUNCHER_MISSING:$launcher"
}
if ($Cycles -lt 1 -or $Cycles -gt 288) {
    throw "CYCLES_OUT_OF_RANGE"
}

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", '"' + $launcher + '"',
    "-RepoRoot", '"' + $RepoRoot + '"',
    "-Cycles", $Cycles.ToString()
)
if ($PreflightOnly) {
    $arguments += "-PreflightOnly"
}

$action = New-ScheduledTaskAction `
    -Execute $powershell `
    -Argument ($arguments -join " ") `
    -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Once -At $StartAt
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 25)
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "One-time AIOS multipair PAPER-only bounded campaign startup." `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Output "TASK_REGISTERED:$($task.TaskName)"
Write-Output "TASK_STATE:$($task.State)"
Write-Output "NEXT_RUN_TIME:$($info.NextRunTime.ToString('o'))"
Write-Output "PAPER_ONLY:TRUE"
Write-Output "LIVE_EXECUTION_ALLOWED:FALSE"
