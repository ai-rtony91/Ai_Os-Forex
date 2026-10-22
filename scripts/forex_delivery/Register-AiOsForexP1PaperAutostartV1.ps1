param(
    [datetime]$StartAt = [datetime]::Parse("2026-08-16T17:05:00"),
    [string]$RepoRoot = "C:\Dev\Ai.Os",
    [int]$Cycles = 288,
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$taskName = "AIOS-Forex-P1-Supertrend-Paper-Autostart-V1"
$launcher = Join-Path $RepoRoot "automation\forex_engine\forex_p1_paper_autostart_v1.py"
$python = (Get-Command python.exe -ErrorAction Stop).Source

if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "AUTOSTART_LAUNCHER_MISSING:$launcher"
}
if ($Cycles -lt 1 -or $Cycles -gt 288) {
    throw "CYCLES_OUT_OF_RANGE"
}
$userToken = [Environment]::GetEnvironmentVariable("OANDA_API_TOKEN", "User")
$userAccount = [Environment]::GetEnvironmentVariable("OANDA_ACCOUNT_ID", "User")
if (-not $userToken) {
    throw "USER_OANDA_API_TOKEN_MISSING"
}
if (-not $userAccount) {
    throw "USER_OANDA_ACCOUNT_ID_MISSING"
}

# Read credentials into this process without printing or persisting their values.
$env:OANDA_API_TOKEN = $userToken
$env:OANDA_ACCOUNT_ID = $userAccount
& $python $launcher --repo-root $RepoRoot --cycles $Cycles --preflight-only
if ($LASTEXITCODE -ne 0) {
    throw "AUTOSTART_PREFLIGHT_FAILED"
}

$arguments = @(
    '"' + $launcher + '"',
    "--repo-root", '"' + $RepoRoot + '"',
    "--cycles", $Cycles.ToString()
)
if ($PreflightOnly) {
    $arguments += "--preflight-only"
}

$action = New-ScheduledTaskAction `
    -Execute $python `
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
    -Description "One-time AIOS Supertrend PAPER-only 30-trade evidence campaign startup." `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Output "TASK_REGISTERED:$($task.TaskName)"
Write-Output "TASK_STATE:$($task.State)"
Write-Output "NEXT_RUN_TIME:$($info.NextRunTime.ToString('o'))"
Write-Output "PAPER_ONLY:TRUE"
Write-Output "LIVE_EXECUTION_ALLOWED:FALSE"
