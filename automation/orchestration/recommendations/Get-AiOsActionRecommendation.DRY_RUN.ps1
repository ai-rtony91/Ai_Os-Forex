param(
    [switch]$QuietJson,
    [switch]$OutputJson
)

Set-StrictMode -Off
$ErrorActionPreference = "Stop"

function Get-RelayOperatorState {
    param([string]$RepoRoot)

    $relayOperatorStateScript = Join-Path $RepoRoot "automation/orchestration/review_bridge/Get-AiOsRelayOperatorState.DRY_RUN.ps1"
    if (-not (Test-Path -LiteralPath $relayOperatorStateScript -PathType Leaf)) {
        return $null
    }

    try {
        $rawOutput = powershell -NoProfile -ExecutionPolicy Bypass -File $relayOperatorStateScript -OutputJson 2>$null
        $rawText = ($rawOutput | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($rawText)) {
            return $null
        }

        return $rawText | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Get-CampaignNextTaskState {
    param([string]$RepoRoot)

    $campaignNextTaskScript = Join-Path $RepoRoot "automation/orchestration/campaign_registry/Get-AiOsCampaignNextTask.DRY_RUN.ps1"
    if (-not (Test-Path -LiteralPath $campaignNextTaskScript -PathType Leaf)) {
        return $null
    }

    try {
        $rawOutput = powershell -NoProfile -ExecutionPolicy Bypass -File $campaignNextTaskScript -OutputJson 2>$null
        $rawText = ($rawOutput | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($rawText)) {
            return $null
        }

        return $rawText | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Get-CampaignNoReadyStageDiscoveryState {
    param([string]$RepoRoot)

    $discoveryScript = Join-Path $RepoRoot "automation/orchestration/campaign_registry/Get-AiOsCampaignNoReadyStageDiscovery.DRY_RUN.ps1"
    if (-not (Test-Path -LiteralPath $discoveryScript -PathType Leaf)) {
        return $null
    }

    try {
        $rawOutput = powershell -NoProfile -ExecutionPolicy Bypass -File $discoveryScript -OutputJson 2>$null
        $rawText = ($rawOutput | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($rawText)) {
            return $null
        }

        return $rawText | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Get-FullAutonomyWorkerPostureBridgeState {
    param([string]$RepoRoot)

    $bridgeScript = Join-Path $RepoRoot "automation/orchestration/self_development/Get-AiOsFullAutonomyWorkerPostureBridge.DRY_RUN.ps1"
    $fallback = [pscustomobject]@{
        available = $false
        mode = "DRY_RUN_READ_ONLY"
        requested_level = "UNKNOWN"
        resolved_or_activation_status = "REVIEW_REQUIRED"
        operating_profile = "24H_SUPERVISED"
        worker_posture = "BLOCKED_BY_VALIDATION"
        worker_launch_allowed = $false
        human_wake_policy = "Review full-autonomy posture bridge availability before relying on worker guidance."
        next_safe_action = "Review full-autonomy worker posture bridge failure before autonomy posture escalation."
        starts_runtime = $false
        launches_workers = $false
        slow_nested_workers_started = $false
        source = "automation/orchestration/self_development/Get-AiOsFullAutonomyWorkerPostureBridge.DRY_RUN.ps1"
    }

    if (-not (Test-Path -LiteralPath $bridgeScript -PathType Leaf)) {
        return $fallback
    }

    try {
        $branch = (& git -C $RepoRoot branch --show-current 2>$null).Trim()
        if ([string]::IsNullOrWhiteSpace($branch)) {
            $branch = "main"
        }
        $rawOutput = powershell -NoProfile -ExecutionPolicy Bypass -File $bridgeScript -RepoRoot $RepoRoot -ExpectedBranch $branch -OutputJson -RequestedAutonomyLevel "LEVEL_4_CONDITIONAL_FULL_AUTONOMY" -OperatingProfile "24H_SUPERVISED" 2>$null
        $rawText = ($rawOutput | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($rawText)) {
            return $fallback
        }

        $data = $rawText | ConvertFrom-Json -ErrorAction Stop
        return [pscustomobject]@{
            available = $true
            mode = [string]$data.mode
            requested_level = [string]$data.activation_summary.requested_autonomy_level
            resolved_or_activation_status = [string]$data.activation_summary.activation_status
            operating_profile = [string]$data.activation_summary.operating_profile
            worker_posture = [string]$data.worker_posture
            worker_launch_allowed = [bool]$data.worker_launch_allowed
            human_wake_policy = [string]$data.human_wake_policy
            next_safe_action = [string]$data.next_safe_action
            starts_runtime = [bool]$data.safety.starts_runtime
            launches_workers = [bool]$data.safety.launches_workers
            slow_nested_workers_started = $false
            source = "automation/orchestration/self_development/Get-AiOsFullAutonomyWorkerPostureBridge.DRY_RUN.ps1"
        }
    }
    catch {
        return $fallback
    }
}

function Get-FullAutonomyWorkerLaunchAvailabilityState {
    param([string]$RepoRoot)

    $preflightScript = Join-Path $RepoRoot "automation/orchestration/self_development/Test-AiOsFullAutonomyWorkerLaunchPreflightGate.DRY_RUN.ps1"
    $commanderScript = Join-Path $RepoRoot "automation/orchestration/self_development/New-AiOsFullAutonomyWorkerLaunchCommand.DRY_RUN.ps1"
    $guardScript = Join-Path $RepoRoot "automation/orchestration/self_development/Test-AiOsFullAutonomyWorkerLaunchGuard.DRY_RUN.ps1"
    $controllerScript = Join-Path $RepoRoot "automation/orchestration/self_development/Start-AiOsApprovedAutonomyWorkerLaunch.APPLY.ps1"
    $controllerLogic = Join-Path $RepoRoot "automation/orchestration/self_development/aios_approved_autonomy_worker_launch_controller.py"
    $forexScript = Join-Path $RepoRoot "automation/orchestration/self_development/Start-AiOsAutonomousForexResearchRun.APPLY.ps1"
    $forexLogic = Join-Path $RepoRoot "automation/orchestration/self_development/aios_autonomous_forex_research_pipeline.py"

    $preflightAvailable = Test-Path -LiteralPath $preflightScript -PathType Leaf
    $commandGuardAvailable = (Test-Path -LiteralPath $commanderScript -PathType Leaf) -and (Test-Path -LiteralPath $guardScript -PathType Leaf)
    $controllerAvailable = (Test-Path -LiteralPath $controllerScript -PathType Leaf) -and (Test-Path -LiteralPath $controllerLogic -PathType Leaf)
    $forexAvailable = (Test-Path -LiteralPath $forexScript -PathType Leaf) -and (Test-Path -LiteralPath $forexLogic -PathType Leaf)

    return [pscustomobject]@{
        preflight = if ($preflightAvailable) { "available" } else { "missing" }
        command_guard = if ($commandGuardAvailable) { "available" } else { "missing" }
        approved_launch_controller = if ($controllerAvailable) { "available" } else { "missing" }
        forex_research_pipeline = if ($forexAvailable) { "available" } else { "missing" }
        worker_launch_allowed_now = $false
        starts_apply = $false
        writes_ledger = $false
        launches_workers = $false
        starts_runtime = $false
        enables_scheduler = $false
        starts_daemon = $false
        broker_or_live_trading = $false
        touches_secrets_or_env = $false
        next_safe_action = "Run approved local simulation workers only after Human Owner approval and current validation evidence are supplied."
    }
}

function Get-AutonomousSelfBuildAvailabilityState {
    param([string]$RepoRoot)

    $executorScript = Join-Path $RepoRoot "automation/orchestration/self_development/Start-AiOsAutonomousSelfBuildExecutor.APPLY.ps1"
    $executorLogic = Join-Path $RepoRoot "automation/orchestration/self_development/aios_autonomous_self_build_executor.py"
    $candidateSelector = Join-Path $RepoRoot "automation/orchestration/self_development/aios_self_build_candidate_selector.py"
    $executionPacket = Join-Path $RepoRoot "automation/orchestration/self_development/aios_self_build_execution_packet.py"
    $repairEngine = Join-Path $RepoRoot "automation/orchestration/self_development/aios_self_build_validator_repair_engine.py"
    $ledgerHelper = Join-Path $RepoRoot "automation/orchestration/self_development/aios_self_build_execution_ledger.py"

    $executorAvailable = (Test-Path -LiteralPath $executorScript -PathType Leaf) -and (Test-Path -LiteralPath $executorLogic -PathType Leaf)
    $selectorAvailable = Test-Path -LiteralPath $candidateSelector -PathType Leaf
    $packetAvailable = Test-Path -LiteralPath $executionPacket -PathType Leaf
    $repairAvailable = Test-Path -LiteralPath $repairEngine -PathType Leaf
    $ledgerAvailable = Test-Path -LiteralPath $ledgerHelper -PathType Leaf

    return [pscustomobject]@{
        executor = if ($executorAvailable) { "available" } else { "missing" }
        can_select_next_candidate = [bool]$selectorAvailable
        can_build_execution_packet = [bool]$packetAvailable
        can_validate_and_repair_stub = [bool]$repairAvailable
        can_apply_local_self_build = "requires Human Owner approval"
        can_commit = "requires separate Human Owner commit approval"
        push_pr_merge_allowed = $false
        starts_apply = $false
        writes_ledger = $false
        launches_workers = $false
        commits = $false
        pushes = $false
        creates_pr = $false
        merges = $false
        ledger_helper = if ($ledgerAvailable) { "available" } else { "missing" }
        next_safe_action = "Run autonomous self-build executor in DRY_RUN or approved local APPLY mode."
    }
}

$health = powershell -ExecutionPolicy Bypass -File automation/orchestration/health/Test-AiOsRuntimeHealth.DRY_RUN.ps1 -QuietJson | ConvertFrom-Json
$next = powershell -ExecutionPolicy Bypass -File automation/orchestration/next_step/Resolve-AiOsNextStep.DRY_RUN.ps1 -QuietJson | ConvertFrom-Json
$blocker = powershell -ExecutionPolicy Bypass -File automation/orchestration/blockers/Resolve-AiOsRuntimeBlocker.DRY_RUN.ps1 -QuietJson | ConvertFrom-Json
$approval = powershell -ExecutionPolicy Bypass -File automation/orchestration/approval_detection/Find-AiOsApprovalMatch.DRY_RUN.ps1 -QuietJson | ConvertFrom-Json
$gitStatus = @(git status --short)
$repoRoot = (Get-Location).Path
$fullAutonomyState = Get-FullAutonomyWorkerPostureBridgeState -RepoRoot $repoRoot
$fullAutonomyWorkerLaunch = Get-FullAutonomyWorkerLaunchAvailabilityState -RepoRoot $repoRoot
$autonomousSelfBuild = Get-AutonomousSelfBuildAvailabilityState -RepoRoot $repoRoot
$relayOperatorState = Get-RelayOperatorState -RepoRoot $repoRoot
$campaignNextTaskState = Get-CampaignNextTaskState -RepoRoot $repoRoot
$campaignOverallReadiness = if ($campaignNextTaskState -and $campaignNextTaskState.PSObject.Properties.Name -contains "overall_readiness") {
    [string]$campaignNextTaskState.overall_readiness
}
else {
    ""
}
$noReadyStageDiscoveryCommand = "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/campaign_registry/Get-AiOsCampaignNoReadyStageDiscovery.DRY_RUN.ps1 -OutputJson"
$campaignNoReadyStageDiscoveryState = if ($campaignOverallReadiness -eq "NO_READY_STAGE") {
    Get-CampaignNoReadyStageDiscoveryState -RepoRoot $repoRoot
}
else {
    $null
}
$noReadyStageClassification = if ($campaignNoReadyStageDiscoveryState -and $campaignNoReadyStageDiscoveryState.PSObject.Properties.Name -contains "no_ready_stage_classification") {
    [string]$campaignNoReadyStageDiscoveryState.no_ready_stage_classification
}
else {
    ""
}
$noReadyStageIdleAllowed = if ($campaignNoReadyStageDiscoveryState -and $campaignNoReadyStageDiscoveryState.PSObject.Properties.Name -contains "idle_allowed") {
    [bool]$campaignNoReadyStageDiscoveryState.idle_allowed
}
else {
    $false
}
$noReadyStagePlanningRequired = if ($campaignNoReadyStageDiscoveryState -and $campaignNoReadyStageDiscoveryState.PSObject.Properties.Name -contains "next_stage_planning_required") {
    [bool]$campaignNoReadyStageDiscoveryState.next_stage_planning_required
}
else {
    $false
}
$noReadyStageRegistryInconsistencyDetected = if ($campaignNoReadyStageDiscoveryState -and $campaignNoReadyStageDiscoveryState.PSObject.Properties.Name -contains "registry_inconsistency_detected") {
    [bool]$campaignNoReadyStageDiscoveryState.registry_inconsistency_detected
}
else {
    $false
}
$relaySosEscalationStatus = "NOT_APPLICABLE"
$relaySosAnthonyRequired = $false
$relaySosRoutineReviewAllowed = $false
$relaySosSafeNextAction = ""
$relaySosApplies = $false
$routineReviewContinuationAllowed = $false
$routineReviewContinuationReason = ""
$routineReviewNextAction = ""
$routineReviewResolverCommand = "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/relay_bus/Resolve-AiOsRelayHumanReview.DRY_RUN.ps1 -OutputJson"

if ($relayOperatorState -and [string]$relayOperatorState.actor_relay_bus_status -eq "NEEDS_HUMAN_REVIEW") {
    $relaySosApplies = $true
    if ($relayOperatorState.PSObject.Properties.Name -contains "sos_escalation_status") {
        $relaySosEscalationStatus = [string]$relayOperatorState.sos_escalation_status
    }
    if ($relayOperatorState.PSObject.Properties.Name -contains "sos_anthony_required") {
        $relaySosAnthonyRequired = [bool]$relayOperatorState.sos_anthony_required
    }
    if ($relayOperatorState.PSObject.Properties.Name -contains "sos_routine_review_allowed") {
        $relaySosRoutineReviewAllowed = [bool]$relayOperatorState.sos_routine_review_allowed
    }
    if ($relayOperatorState.PSObject.Properties.Name -contains "sos_safe_next_action") {
        $relaySosSafeNextAction = [string]$relayOperatorState.sos_safe_next_action
    }
    if ($relayOperatorState.PSObject.Properties.Name -contains "routine_review_continuation_allowed") {
        $routineReviewContinuationAllowed = [bool]$relayOperatorState.routine_review_continuation_allowed
    }
    else {
        $routineReviewContinuationAllowed = ($relaySosEscalationStatus -eq "ROUTINE_REVIEW" -and (-not $relaySosAnthonyRequired) -and $relaySosRoutineReviewAllowed)
    }
    if ($relayOperatorState.PSObject.Properties.Name -contains "routine_review_continuation_reason") {
        $routineReviewContinuationReason = [string]$relayOperatorState.routine_review_continuation_reason
    }
    if ($relayOperatorState.PSObject.Properties.Name -contains "routine_review_next_action") {
        $routineReviewNextAction = [string]$relayOperatorState.routine_review_next_action
    }
    if ($routineReviewContinuationAllowed -and [string]::IsNullOrWhiteSpace($routineReviewNextAction)) {
        $routineReviewNextAction = $routineReviewResolverCommand
    }
    if ($routineReviewContinuationAllowed -and [string]::IsNullOrWhiteSpace($routineReviewContinuationReason)) {
        $routineReviewContinuationReason = "Routine relay review may continue through resolver and SOS-governed review flow."
    }
}
$commitPackagePreview = $null
if ($gitStatus.Count -gt 0) {
    try {
        $commitPackagePreview = powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/commit_packages/New-AiOsCommitPackageRecommendation.DRY_RUN.ps1 -OutputJson | ConvertFrom-Json
    }
    catch {
        $commitPackagePreview = $null
    }
}

$recommendedCommand = "powershell -ExecutionPolicy Bypass -File automation/session/Start-AiOsSession.ps1"
$reason = "Default: start AIOS session."
$level5Validators = @(
    "git diff --check",
    "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/validators/Test-WorkerClaimCollision.DRY_RUN.ps1",
    "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/validators/Test-LockRegistryIntegrity.DRY_RUN.ps1",
    "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/validators/Test-AiOsIdentitySpine.DRY_RUN.ps1",
    "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1"
)

if ($approval.matches_found -gt 0) {
    $recommendedCommand = "No command recommended. Use separately approved APPLY helper for approval processing."
    $reason = "Approval exists for waiting packet; DRY_RUN cannot process approval."
}
elseif ($next.status -eq "awaiting_approval") {
    $recommendedCommand = "powershell -ExecutionPolicy Bypass -File automation/orchestration/approval_detection/Find-AiOsApprovalMatch.DRY_RUN.ps1"
    $reason = "Packet is waiting for approval."
}
elseif ($gitStatus.Count -gt 0 -and $commitPackagePreview -and $campaignOverallReadiness -ne "NO_READY_STAGE") {
    $recommendedCommand = "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/commit_packages/New-AiOsCommitPackageRecommendation.DRY_RUN.ps1 -OutputJson"
    $reason = "Working tree has changes; prepare an exact-file Level 5 commit package preview and stop before staging."
}
elseif ($health.health -ne "HEALTHY" -and $campaignOverallReadiness -ne "NO_READY_STAGE") {
    $recommendedCommand = "powershell -ExecutionPolicy Bypass -File automation/orchestration/health/Test-AiOsRuntimeHealth.DRY_RUN.ps1"
    $reason = "Health is not clean."
}
elseif ($next.status -eq "blocked" -or $next.status -eq "failed") {
    $recommendedCommand = "powershell -ExecutionPolicy Bypass -File automation/orchestration/blockers/Resolve-AiOsRuntimeBlocker.DRY_RUN.ps1"
    $reason = "Packet needs blocker/failure review."
}
elseif ($next.status -eq "campaign_ready") {
    $recommendedCommand = "powershell -ExecutionPolicy Bypass -File automation/orchestration/health/Test-AiOsRuntimeHealth.DRY_RUN.ps1"
    $reason = "No active packet is present; campaign registry has a READY packet candidate."
}
elseif ($next.status -eq "no_active_packet") {
    if ($campaignOverallReadiness -eq "NO_READY_STAGE") {
        $recommendedCommand = $noReadyStageDiscoveryCommand
        if ($noReadyStageClassification -eq "COMPLETE_IDLE") {
            $reason = "Campaign registry reports COMPLETE_IDLE; no selectable work is pending and AIOS may idle cleanly. Discovery remains available for read-only review."
        }
        elseif ($noReadyStageClassification -eq "BLOCKED_BY_REGISTRY_INCONSISTENCY") {
            $reason = "Campaign registry reports BLOCKED_BY_REGISTRY_INCONSISTENCY; review and repair registry bookkeeping before requesting a packet."
        }
        else {
            $reason = "Campaign registry reports NO_READY_STAGE; run read-only discovery to identify next-stage planning gaps."
        }
    }
    else {
        $recommendedCommand = "No command recommended. Review campaign registry statuses and approve one next packet candidate."
        $reason = "No active packet and no READY campaign stage are available for automatic advancement."
    }
}
else {
    $recommendedCommand = "powershell -ExecutionPolicy Bypass -File automation/orchestration/advancement/Invoke-AiOsPacketAdvancement.DRY_RUN.ps1"
    $reason = "Packet can continue normal advancement."
}

if ($relaySosApplies -and $routineReviewContinuationAllowed) {
    $recommendedCommand = if ($routineReviewNextAction) { $routineReviewNextAction } else { $routineReviewResolverCommand }
    $reason = if ($routineReviewContinuationReason) { $routineReviewContinuationReason } else { "Routine relay review may continue through resolver and SOS-governed review flow." }
}
elseif ($relaySosApplies -and ($relaySosEscalationStatus -eq "SOS_ESCALATION" -or $relaySosAnthonyRequired)) {
    $recommendedCommand = "No command recommended. STOP and request Anthony review before any continuation."
    $reason = "Relay SOS escalation requires Anthony; do not continue automatically."
}

$commitPackageChangedFiles = @()
$commitPackageRecommendedFiles = @()
$commitPackageRiskFlags = @()
if ($commitPackagePreview) {
    $commitPackageChangedFiles = @(
        @($commitPackagePreview.changed_files)
        @($commitPackagePreview.new_files)
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | Sort-Object -Unique
    $commitPackageRecommendedFiles = @($commitPackagePreview.recommended_files | ForEach-Object { [string]$_.path } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique)
    $commitPackageRiskFlags = @($commitPackagePreview.risks | ForEach-Object {
        if ($_.path -and $_.risk) {
            "$($_.path): $($_.risk)"
        } else {
            [string]$_
        }
    } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

$result = [pscustomobject]@{
    mode = "READ_ONLY"
    recommended_command = $recommendedCommand
    relay_sos_escalation_status = $relaySosEscalationStatus
    relay_sos_anthony_required = $relaySosAnthonyRequired
    relay_sos_routine_review_allowed = $relaySosRoutineReviewAllowed
    relay_sos_next_safe_action = if ($relaySosSafeNextAction) { $relaySosSafeNextAction } else { "" }
    routine_review_continuation_allowed = $routineReviewContinuationAllowed
    routine_review_continuation_reason = $routineReviewContinuationReason
    routine_review_next_action = $routineReviewNextAction
    campaign_overall_readiness = $campaignOverallReadiness
    no_ready_stage_discovery_command = $noReadyStageDiscoveryCommand
    no_ready_stage_classification = $noReadyStageClassification
    no_ready_stage_idle_allowed = $noReadyStageIdleAllowed
    no_ready_stage_planning_required = $noReadyStagePlanningRequired
    no_ready_stage_registry_inconsistency_detected = $noReadyStageRegistryInconsistencyDetected
    reason = $reason
    health = $health.health
    packet_id = $next.packet_id
    packet_status = $next.status
    approval_matches = $approval.matches_found
    blocker = $blocker.blocker
    full_autonomy_state = $fullAutonomyState
    full_autonomy_worker_launch = $fullAutonomyWorkerLaunch
    autonomous_self_build = $autonomousSelfBuild
    level5_commit_package_preview = [pscustomobject]@{
        available = [bool]($null -ne $commitPackagePreview)
        status = if ($commitPackagePreview -and $commitPackagePreview.orchestration_result_contract.status) { [string]$commitPackagePreview.orchestration_result_contract.status } elseif ($gitStatus.Count -gt 0) { "REVIEW" } else { "NOT_NEEDED" }
        command = "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/commit_packages/New-AiOsCommitPackageRecommendation.DRY_RUN.ps1 -OutputJson"
        exact_changed_files = @($commitPackageChangedFiles)
        recommended_files = @($commitPackageRecommendedFiles)
        suggested_validators = @($level5Validators)
        risk_flags = @($commitPackageRiskFlags)
        stop_before_staging = "STOP: preview only. Do not run git add, git commit, git push, PR, or merge without separate explicit approval."
    }
}

$approvalRequired = ($approval.matches_found -gt 0 -or $next.status -eq "awaiting_approval" -or ($commitPackagePreview -and (-not $routineReviewContinuationAllowed)))
if ($relaySosApplies -and ($relaySosEscalationStatus -eq "SOS_ESCALATION" -or $relaySosAnthonyRequired)) {
    $approvalRequired = $true
}
$blockedReason = if ($gitStatus.Count -gt 0 -and $commitPackagePreview) { "none" } elseif ($health.health -ne "HEALTHY") { "Runtime health is not clean." } elseif ($next.status -eq "blocked" -or $next.status -eq "failed") { "Packet is blocked or failed." } elseif ($next.status -eq "no_active_packet") { "No active packet or READY campaign stage is available." } else { "none" }
$status = if ($blockedReason -ne "none") { "BLOCKED" } elseif ($approvalRequired) { "REVIEW" } else { "READY" }
$nextSafeAction = $recommendedCommand
if ($next.status -eq "no_active_packet" -and $campaignOverallReadiness -eq "NO_READY_STAGE" -and (-not $relaySosApplies)) {
    if ($noReadyStageClassification -eq "COMPLETE_IDLE") {
        $nextSafeAction = "No READY stage is available and no blocker is detected. Idle cleanly or run read-only no-ready-stage discovery for review: $noReadyStageDiscoveryCommand"
    }
    elseif ($noReadyStageClassification -eq "BLOCKED_BY_REGISTRY_INCONSISTENCY") {
        $nextSafeAction = "Review and repair campaign registry inconsistencies before requesting a packet. Read-only evidence: $noReadyStageDiscoveryCommand"
    }
    else {
        $nextSafeAction = $noReadyStageDiscoveryCommand
    }
}
if ($relaySosApplies -and $routineReviewContinuationAllowed) {
    $routineReviewCommandForAction = if ($routineReviewNextAction) { $routineReviewNextAction } else { $routineReviewResolverCommand }
    $nextSafeAction = "Routine relay review may continue through resolver and SOS-governed review flow: $routineReviewCommandForAction"
}
elseif ($relaySosApplies -and ($relaySosEscalationStatus -eq "SOS_ESCALATION" -or $relaySosAnthonyRequired)) {
    $nextSafeAction = "STOP and request Anthony review before continuation."
}
$result | Add-Member -NotePropertyName orchestration_result_contract -NotePropertyValue ([pscustomobject]@{
    status = $status
    severity = if ($status -eq "BLOCKED") { "BLOCKED" } elseif ($status -eq "REVIEW") { "REVIEW" } else { "INFO" }
    packet_id = if ($next.packet_id) { [string]$next.packet_id } else { "UNKNOWN" }
    worker_identity = "UNKNOWN"
    validator_results = @()
    approval_required = $approvalRequired
    blocked_reason = $blockedReason
    escalation_reason = if ($approvalRequired) { "Approval evidence requires Human Owner review." } elseif ($blockedReason -ne "none") { $blockedReason } else { "none" }
    commit_candidate = [bool]($commitPackagePreview)
    next_safe_action = $nextSafeAction
    stop_condition = "REPORT_ONLY_NO_PACKET_ADVANCEMENT"
    runtime_notes = @(
        "READ_ONLY",
        "Recommendation only.",
        "No packet advancement, APPLY, commit, or push was performed."
    )
    evidence = [pscustomobject]@{
        health = $health.health
        packet_status = $next.status
        approval_matches = $approval.matches_found
        blocker = $blocker.blocker
        reason = $reason
        level5_commit_package_preview = $result.level5_commit_package_preview
        routine_review_continuation_allowed = $routineReviewContinuationAllowed
        routine_review_continuation_reason = $routineReviewContinuationReason
        routine_review_next_action = $routineReviewNextAction
        campaign_overall_readiness = $campaignOverallReadiness
        no_ready_stage_discovery_command = $noReadyStageDiscoveryCommand
        no_ready_stage_classification = $noReadyStageClassification
        no_ready_stage_idle_allowed = $noReadyStageIdleAllowed
        no_ready_stage_planning_required = $noReadyStagePlanningRequired
        no_ready_stage_registry_inconsistency_detected = $noReadyStageRegistryInconsistencyDetected
        full_autonomy_state = $fullAutonomyState
        full_autonomy_worker_launch = $fullAutonomyWorkerLaunch
        autonomous_self_build = $autonomousSelfBuild
    }
    generated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
})

if ($QuietJson -or $OutputJson) {
    $result | ConvertTo-Json -Depth 8
    exit 0
}

Write-Host "COPY START - Get-AiOsActionRecommendation.DRY_RUN.ps1"
Write-Host "AI_OS Action Recommendation" -ForegroundColor Cyan
Write-Host "health: $($result.health)"
Write-Host "packet_id: $($result.packet_id)"
Write-Host "packet_status: $($result.packet_status)"
Write-Host "approval_matches: $($result.approval_matches)"
Write-Host "reason: $($result.reason)"
Write-Host "routine_review_continuation_allowed: $($result.routine_review_continuation_allowed)"
Write-Host "level5_commit_package_preview: available=$($result.level5_commit_package_preview.available); status=$($result.level5_commit_package_preview.status)"
Write-Host "level5_stop: $($result.level5_commit_package_preview.stop_before_staging)"
Write-Host ""
Write-Host "FULL AUTONOMY STATE"
Write-Host "requested_level: $($result.full_autonomy_state.requested_level)"
Write-Host "resolved_or_activation_status: $($result.full_autonomy_state.resolved_or_activation_status)"
Write-Host "operating_profile: $($result.full_autonomy_state.operating_profile)"
Write-Host "worker_posture: $($result.full_autonomy_state.worker_posture)"
Write-Host "worker_launch_allowed: $($result.full_autonomy_state.worker_launch_allowed)"
Write-Host "human_wake_policy: $($result.full_autonomy_state.human_wake_policy)"
Write-Host "next_safe_action: $($result.full_autonomy_state.next_safe_action)"
Write-Host ""
Write-Host "FULL AUTONOMY WORKER LAUNCH"
Write-Host "preflight: $($result.full_autonomy_worker_launch.preflight)"
Write-Host "command_guard: $($result.full_autonomy_worker_launch.command_guard)"
Write-Host "approved_launch_controller: $($result.full_autonomy_worker_launch.approved_launch_controller)"
Write-Host "forex_research_pipeline: $($result.full_autonomy_worker_launch.forex_research_pipeline)"
Write-Host "worker_launch_allowed_now: $($result.full_autonomy_worker_launch.worker_launch_allowed_now)"
Write-Host "next_safe_action: $($result.full_autonomy_worker_launch.next_safe_action)"
Write-Host ""
Write-Host "AUTONOMOUS SELF-BUILD"
Write-Host "executor: $($result.autonomous_self_build.executor)"
Write-Host "can_select_next_candidate: $($result.autonomous_self_build.can_select_next_candidate)"
Write-Host "can_build_execution_packet: $($result.autonomous_self_build.can_build_execution_packet)"
Write-Host "can_validate_and_repair_stub: $($result.autonomous_self_build.can_validate_and_repair_stub)"
Write-Host "can_apply_local_self_build: $($result.autonomous_self_build.can_apply_local_self_build)"
Write-Host "can_commit: $($result.autonomous_self_build.can_commit)"
Write-Host "push_pr_merge_allowed: $($result.autonomous_self_build.push_pr_merge_allowed)"
Write-Host "next_safe_action: $($result.autonomous_self_build.next_safe_action)"
Write-Host ""
Write-Host "RECOMMENDED COMMAND:"
Write-Host $result.recommended_command
Write-Host ""
Write-Host "Commit performed: NO"
Write-Host "Push performed: NO"
Write-Host "COPY END - Get-AiOsActionRecommendation.DRY_RUN.ps1"
