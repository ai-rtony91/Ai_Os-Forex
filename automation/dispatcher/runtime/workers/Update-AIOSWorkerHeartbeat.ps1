[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^AIOS-(0[1-9]|10)$')]
    [string]$WorkerId,

    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "IDLE",
        "ASSIGNED",
        "DRY_RUN_STARTED",
        "DRY_RUN_COMPLETE",
        "WAITING_APPROVAL",
        "APPLY_RUNNING",
        "VALIDATING",
        "VALIDATED",
        "STALE",
        "BLOCKED",
        "FAILED",
        "REVIEW_REQUIRED",
        "STOPPED"
    )]
    [string]$CurrentState,

    [string]$AssignedRole,
    [string]$AssignedPacketId,
    [string]$LaunchSessionId,
    [string]$TerminalWindowName,
    [string]$NextSafeAction = "Worker heartbeat registered. Continue DRY_RUN only until packet assignment and approval are confirmed.",
    [string]$WorkerStateRoot
)

$ErrorActionPreference = "Stop"

function Get-AIOSRepoRoot {
    $root = & git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($root)) {
        throw "Unable to find git repository root."
    }
    return $root.Trim()
}

function Fail-AIOSReviewRequired {
    param([string]$Message)

    [Console]::Error.WriteLine($Message)
    exit 1
}

function Read-AIOSJson {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        Fail-AIOSReviewRequired "REVIEW_REQUIRED: Missing required worker-state file: $Path"
    }

    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    }
    catch {
        Fail-AIOSReviewRequired "REVIEW_REQUIRED: Malformed worker-state JSON: $Path. $($_.Exception.Message)"
    }
}

function Write-AIOSJson {
    param(
        [string]$Path,
        [object]$Data
    )

    $targetDir = Split-Path -Parent $Path
    if ([string]::IsNullOrWhiteSpace($targetDir)) {
        Fail-AIOSReviewRequired "REVIEW_REQUIRED: Worker-state target directory could not be resolved for $Path"
    }
    if (-not (Test-Path -LiteralPath $targetDir)) {
        Fail-AIOSReviewRequired "REVIEW_REQUIRED: Worker-state target directory is missing: $targetDir"
    }

    $tmpPath = Join-Path $targetDir ("{0}.{1}.tmp" -f ([IO.Path]::GetFileName($Path)), ([guid]::NewGuid().ToString("N")))
    $json = $Data | ConvertTo-Json -Depth 30
    try {
        Set-Content -LiteralPath $tmpPath -Value $json -Encoding UTF8
        $null = Get-Content -LiteralPath $tmpPath -Raw | ConvertFrom-Json
        Move-Item -LiteralPath $tmpPath -Destination $Path -Force
    }
    catch {
        if (Test-Path -LiteralPath $tmpPath) {
            Remove-Item -LiteralPath $tmpPath -Force
        }
        Fail-AIOSReviewRequired "REVIEW_REQUIRED: Atomic worker-state write failed for $Path. $($_.Exception.Message)"
    }
}

function Get-AIOSSingleRecord {
    param(
        [object[]]$Records,
        [string]$WorkerId,
        [string]$RecordName
    )

    $matches = @($Records | Where-Object { $_.worker_id -eq $WorkerId })
    if ($matches.Count -ne 1) {
        throw "Expected exactly one $RecordName record for $WorkerId, found $($matches.Count)."
    }
    return $matches[0]
}

function Set-AIOSPropertyIfValue {
    param(
        [object]$Object,
        [string]$Name,
        [object]$Value
    )

    if ($null -ne $Value -and -not [string]::IsNullOrWhiteSpace([string]$Value)) {
        $Object.$Name = $Value
    }
}

$repoRoot = Get-AIOSRepoRoot
Set-Location -LiteralPath $repoRoot

if ([string]::IsNullOrWhiteSpace($WorkerStateRoot)) {
    $workerDir = Join-Path $repoRoot "Reports/dispatcher/runtime/workers"
}
else {
    $workerDir = $WorkerStateRoot
}
$activePath = Join-Path $workerDir "active_worker_table.json"
$heartbeatPath = Join-Path $workerDir "worker_heartbeat_table.json"
$ledgerPath = Join-Path $workerDir "worker_session_ledger.json"
$registrationPath = Join-Path $workerDir "worker_registration_status.json"

$activeTable = Read-AIOSJson -Path $activePath
$heartbeatTable = Read-AIOSJson -Path $heartbeatPath
$sessionLedger = Read-AIOSJson -Path $ledgerPath
$registrationStatus = Read-AIOSJson -Path $registrationPath

$activeWorker = Get-AIOSSingleRecord -Records @($activeTable.workers) -WorkerId $WorkerId -RecordName "active worker"
$heartbeat = Get-AIOSSingleRecord -Records @($heartbeatTable.heartbeats) -WorkerId $WorkerId -RecordName "heartbeat"
$registrations = @($registrationStatus.registrations | Where-Object { $_.worker_id -eq $WorkerId })
if ($registrations.Count -gt 1) {
    throw "Expected zero or one registration record for $WorkerId, found $($registrations.Count)."
}
$registration = if ($registrations.Count -eq 1) { $registrations[0] } else { $null }

if ($CurrentState -eq "APPLY_RUNNING") {
    $approvalState = [string]$activeWorker.approval_state
    if ($approvalState -notin @("APPROVED", "APPLY_APPROVED")) {
        throw "APPLY_RUNNING is blocked for $WorkerId because approval_state is '$approvalState'."
    }
}

$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$effectiveLaunchSessionId = $LaunchSessionId
if ([string]::IsNullOrWhiteSpace($effectiveLaunchSessionId)) {
    $effectiveLaunchSessionId = [string]$activeWorker.launch_session_id
}
if ([string]::IsNullOrWhiteSpace($effectiveLaunchSessionId)) {
    $effectiveLaunchSessionId = "MANUAL-$WorkerId-$((Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss'))"
}

$previousState = [string]$activeWorker.current_state
$previousHeartbeatTime = $activeWorker.heartbeat_time

$activeTable.generated_at = $now
$activeWorker.current_state = $CurrentState
$activeWorker.heartbeat_time = $now
$activeWorker.heartbeat_age_seconds = 0
$activeWorker.launch_session_id = $effectiveLaunchSessionId
$activeWorker.next_safe_action = $NextSafeAction
Set-AIOSPropertyIfValue -Object $activeWorker -Name "assigned_role" -Value $AssignedRole
Set-AIOSPropertyIfValue -Object $activeWorker -Name "assigned_packet_id" -Value $AssignedPacketId
Set-AIOSPropertyIfValue -Object $activeWorker -Name "terminal_window_name" -Value $TerminalWindowName

$heartbeatTable.generated_at = $now
$heartbeat.current_state = $CurrentState
$heartbeat.heartbeat_time = $now
$heartbeat.heartbeat_age_seconds = 0
$heartbeat.stale_status = "CURRENT"
$heartbeat.launch_session_id = $effectiveLaunchSessionId
$heartbeat.next_safe_action = $NextSafeAction
Set-AIOSPropertyIfValue -Object $heartbeat -Name "assigned_packet_id" -Value $AssignedPacketId
Set-AIOSPropertyIfValue -Object $heartbeat -Name "terminal_window_name" -Value $TerminalWindowName

$registrationUpdated = $false
if ($null -ne $registration) {
    $registrationStatus.generated_at = $now
    $registration.registration_time = $now
    $registration.registration_status = "REGISTERED"
    $registration.duplicate_identity_status = "NOT_CHECKED"
    $registration.launch_session_id = $effectiveLaunchSessionId
    $registration.next_safe_action = $NextSafeAction
    Set-AIOSPropertyIfValue -Object $registration -Name "assigned_role" -Value $AssignedRole
    Set-AIOSPropertyIfValue -Object $registration -Name "terminal_window_name" -Value $TerminalWindowName
    $registrationUpdated = $true
}

$sessionLedger.generated_at = $now
$event = [pscustomobject]@{
    event_id = "WORKER-HEARTBEAT-$WorkerId-$((Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss'))"
    event_time = $now
    event_type = "HEARTBEAT_REGISTERED"
    worker_id = $WorkerId
    launch_session_id = $effectiveLaunchSessionId
    previous_state = $previousState
    new_state = $CurrentState
    previous_heartbeat_time = $previousHeartbeatTime
    heartbeat_time = $now
    assigned_packet_id = $activeWorker.assigned_packet_id
    assigned_role = $activeWorker.assigned_role
    terminal_window_name = $activeWorker.terminal_window_name
    stale_status = "CURRENT"
    startup_tasks_created = $false
    scheduled_tasks_created = $false
    auto_launch_created = $false
    apply_automation_created = $false
    commit_created = $false
    push_created = $false
    next_safe_action = $NextSafeAction
}
$sessionLedger.events = @($sessionLedger.events) + $event

Write-AIOSJson -Path $activePath -Data $activeTable
Write-AIOSJson -Path $heartbeatPath -Data $heartbeatTable
Write-AIOSJson -Path $registrationPath -Data $registrationStatus
Write-AIOSJson -Path $ledgerPath -Data $sessionLedger

Write-Host "AI_OS WORKER HEARTBEAT UPDATE"
Write-Host "Worker: $WorkerId"
Write-Host "State: $CurrentState"
Write-Host "Heartbeat UTC: $now"
Write-Host "Stale status: CURRENT"
Write-Host "Registration updated: $registrationUpdated"
Write-Host "Ledger event: $($event.event_id)"
Write-Host "Next safe action: $NextSafeAction"

