param(
    [Parameter(Mandatory = $true)][string]$PacketPath,
    [string]$TargetState = "",
    [string]$Worker = "human_operator",
    [switch]$AdvanceToNext,
    [switch]$Apply
)

Set-StrictMode -Off
$ErrorActionPreference = "Stop"

$allowedTransitions = @{
    "active"              = @("routed")
    "new"                 = @("routed")
    "routed"              = @("dry_run_done", "blocked")
    "dry_run_done"        = @("awaiting_approval", "blocked")
    "awaiting_approval"   = @("approved", "blocked")
    "approved"            = @("applying", "blocked")
    "applying"            = @("validated", "failed")
    "validated"           = @("complete")
    "blocked"             = @("routed")
    "failed"              = @("routed")
    "complete"            = @()
}

$applyProtectedStates = @("approved", "applying", "validated", "complete")
$approvedStatuses = @("approved", "approved_for_apply", "apply_approved", "completed")
$passingStatuses = @("PASS", "pass", "passed", "validation_passed")
$hardBlockedTerms = @(
    "broker",
    "oanda",
    "live_trading",
    "api_key",
    "webhook",
    "startup_task",
    "scheduled_task"
)

function Test-AiOsTruthy {
    param([object]$Value)
    return ($Value -eq $true -or [string]$Value -match "^(?i:true|yes|approved|approved_for_apply|apply_approved)$")
}

function Test-AiOsMidnightPlaceholder {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }
    if ($Value -eq "2026-06-08T00:00:00Z" -or $Value -eq "2026-06-02T00:00:00Z") {
        return $true
    }
    return ($Value -match "T00:00:00Z$")
}

function Get-AiOsPacketField {
    param(
        [object]$Packet,
        [string[]]$Names
    )

    foreach ($name in $Names) {
        if ($Packet.PSObject.Properties.Name -contains $name) {
            return $Packet.$name
        }
    }

    return $null
}

function Assert-AiOsNoHardBlockedAction {
    param([object]$Packet)

    $values = @()
    foreach ($property in @("blocked_actions", "requested_actions", "actions", "command", "goal", "title")) {
        if ($Packet.PSObject.Properties.Name -contains $property) {
            $values += @($Packet.$property)
        }
    }

    $joined = ($values | ForEach-Object { [string]$_ }) -join " "
    foreach ($term in $hardBlockedTerms) {
        if ($joined -match "(?i)$term") {
            throw "APPLY blocked: packet references hard-blocked action term '$term'."
        }
    }
}

function Assert-AiOsApplyGate {
    param(
        [object]$Packet,
        [string]$CurrentState,
        [string]$TargetState
    )

    Assert-AiOsNoHardBlockedAction -Packet $Packet

    if ($TargetState -notin $applyProtectedStates) {
        return
    }

    $packetMode = [string](Get-AiOsPacketField -Packet $Packet -Names @("mode", "requested_mode"))
    if ($packetMode -eq "DRY_RUN" -and $TargetState -in @("applying", "validated", "complete")) {
        throw "APPLY blocked: DRY_RUN packet cannot advance into $TargetState."
    }

    $approvalRequired = Get-AiOsPacketField -Packet $Packet -Names @("approval_required", "requiresApproval")
    $approvedByHuman = Get-AiOsPacketField -Packet $Packet -Names @("approved_by_human", "human_approved")
    $approvalStatus = [string](Get-AiOsPacketField -Packet $Packet -Names @("approval_status", "approval_state", "approval"))
    $approvalEvidenceStatus = [string](Get-AiOsPacketField -Packet $Packet -Names @("approval_evidence_status", "hardened_approval_status"))
    $approvalEvidenceType = [string](Get-AiOsPacketField -Packet $Packet -Names @("approval_evidence_type", "hardened_approval_type"))
    $approvalHmac = [string](Get-AiOsPacketField -Packet $Packet -Names @("approval_hmac_sha256", "hardened_approval_hmac_sha256"))
    $approvalTimestamp = [string](Get-AiOsPacketField -Packet $Packet -Names @("approval_timestamp_utc", "approval_timestamp", "bound_at"))
    $hasHardenedEvidence = (
        $approvalEvidenceStatus -eq "VERIFIED" -and
        $approvalEvidenceType -eq "HMAC_SHA256" -and
        -not [string]::IsNullOrWhiteSpace($approvalHmac) -and
        -not [string]::IsNullOrWhiteSpace($approvalTimestamp) -and
        -not (Test-AiOsMidnightPlaceholder -Value $approvalTimestamp)
    )

    if (($approvalRequired -eq $true -or $TargetState -in @("applying", "validated", "complete")) -and
        -not (Test-AiOsTruthy -Value $approvedByHuman) -and
        $approvalStatus -notin $approvedStatuses) {
        throw "APPLY blocked: packet lacks human approval for protected transition $CurrentState -> $TargetState."
    }

    if ($TargetState -in @("applying", "validated", "complete") -and -not $hasHardenedEvidence) {
        Write-Host "raw approved_by_human is not sufficient"
        throw "APPLY blocked: protected transition $CurrentState -> $TargetState requires hardened Human Owner approval evidence; raw approved_by_human is not sufficient."
    }

    if ($TargetState -in @("validated", "complete")) {
        $validatorStatus = [string](Get-AiOsPacketField -Packet $Packet -Names @("validator_chain_status", "validation_status", "validator_status"))
        if ($validatorStatus -notin $passingStatuses) {
            throw "APPLY blocked: validator status is not passing for transition $CurrentState -> $TargetState."
        }
    }

    if ($TargetState -eq "complete") {
        $proofStatus = [string](Get-AiOsPacketField -Packet $Packet -Names @("proof_status", "proof_gate_status"))
        if (-not [string]::IsNullOrWhiteSpace($proofStatus) -and $proofStatus -notin $passingStatuses) {
            throw "APPLY blocked: proof status is not passing for completion."
        }
    }
}

Write-Host ("COPY START " + [char]0x2014 + " Move-AiOsPacketState.ps1")
Write-Host "AI_OS Packet State Transition" -ForegroundColor Cyan
Write-Host "Mode: $(if ($Apply) { 'APPLY' } else { 'DRY_RUN' })"

if (-not (Test-Path -LiteralPath $PacketPath -PathType Leaf)) {
    throw "Packet not found: $PacketPath"
}

$packet = Get-Content -LiteralPath $PacketPath -Raw | ConvertFrom-Json
$currentState = $packet.status

if (-not ($allowedTransitions.ContainsKey($currentState))) {
    throw "Unknown current state: $currentState"
}

if ($AdvanceToNext) {
    $nextStates = @($allowedTransitions[$currentState])
    if ($nextStates.Count -eq 0) {
        Write-Host ""
        Write-Host "Packet: $($packet.packet_id)"
        Write-Host "Current state: $currentState"
        Write-Host "Target state: NONE"
        throw "No legal automatic transition exists from current state: $currentState"
    }

    $TargetState = $nextStates[0]
}

if ([string]::IsNullOrWhiteSpace($TargetState)) {
    throw "TargetState is required unless AdvanceToNext is used."
}

Write-Host ""
Write-Host "Packet: $($packet.packet_id)"
Write-Host "Current state: $currentState"
Write-Host "Target state: $TargetState"
Write-Host "Worker: $Worker"

if ($allowedTransitions[$currentState] -notcontains $TargetState) {
    throw "Illegal transition: $currentState -> $TargetState"
}

if ($Apply) {
    Assert-AiOsApplyGate -Packet $packet -CurrentState $currentState -TargetState $TargetState
}

$utcNow = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

if (-not ($packet.PSObject.Properties.Name -contains "history")) {
    $packet | Add-Member -MemberType NoteProperty -Name history -Value @()
}

$historyEntry = [pscustomobject]@{
    from_state = $currentState
    to_state = $TargetState
    utc = $utcNow
    worker = $Worker
    apply = [bool]$Apply
}

Write-Host ""
Write-Host "Transition allowed." -ForegroundColor Green

if ($Apply) {
    $packet.status = $TargetState
    $packet.updated_utc = $utcNow
    $packet.history = @($packet.history) + $historyEntry
    $packet | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $PacketPath -Encoding UTF8
    Write-Host "Packet updated: YES" -ForegroundColor Green
} else {
    Write-Host "Packet updated: NO"
}

Write-Host ""
Write-Host "Commit performed: NO"
Write-Host "Push performed: NO"
Write-Host ("COPY END " + [char]0x2014 + " Move-AiOsPacketState.ps1")
