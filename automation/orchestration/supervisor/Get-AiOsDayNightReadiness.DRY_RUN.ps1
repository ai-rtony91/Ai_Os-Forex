[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$ExpectedBranch = "main",
    [switch]$OutputJson,
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

function ConvertTo-RelativePath {
    param([string]$Root, [string]$Path)
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd("\", "/")
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    if ($pathFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $pathFull.Substring($rootFull.Length).TrimStart("\", "/").Replace("\", "/")
    }
    return $pathFull.Replace("\", "/")
}

function New-MetadataHash {
    param([object[]]$Items)
    $text = ($Items | Sort-Object -Property relative_path | ConvertTo-Json -Depth 6 -Compress)
    if ([string]::IsNullOrWhiteSpace($text)) {
        $text = "[]"
    }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
}

function Get-PathFingerprint {
    param([string]$Root, [string]$RelativePath)
    $target = Join-Path $Root $RelativePath
    if (-not (Test-Path -LiteralPath $target)) {
        return [ordered]@{
            path = $RelativePath.Replace("\", "/")
            exists = $false
            file_count = 0
            total_bytes = 0
            metadata_hash = New-MetadataHash -Items @()
        }
    }
    $files = @(Get-ChildItem -LiteralPath $target -File -Recurse -Force -ErrorAction SilentlyContinue)
    $items = @($files | ForEach-Object {
        [ordered]@{
            relative_path = ConvertTo-RelativePath -Root $Root -Path $_.FullName
            length = [int64]$_.Length
            last_write_utc_ticks = [int64]$_.LastWriteTimeUtc.Ticks
        }
    })
    $totalBytes = 0
    foreach ($file in $files) {
        $totalBytes += [int64]$file.Length
    }
    return [ordered]@{
        path = $RelativePath.Replace("\", "/")
        exists = $true
        file_count = $files.Count
        total_bytes = $totalBytes
        metadata_hash = New-MetadataHash -Items $items
    }
}

function Get-EnvFingerprint {
    param([string]$Root)
    $files = @(Get-ChildItem -LiteralPath $Root -File -Force -Recurse -Filter ".env*" -ErrorAction SilentlyContinue)
    $items = @($files | ForEach-Object {
        [ordered]@{
            relative_path = ConvertTo-RelativePath -Root $Root -Path $_.FullName
            length = [int64]$_.Length
            last_write_utc_ticks = [int64]$_.LastWriteTimeUtc.Ticks
        }
    })
    $totalBytes = 0
    foreach ($file in $files) {
        $totalBytes += [int64]$file.Length
    }
    return [ordered]@{
        path = ".env*"
        exists = ($files.Count -gt 0)
        file_count = $files.Count
        total_bytes = [int64]$totalBytes
        metadata_hash = New-MetadataHash -Items $items
    }
}

function Get-NoWriteState {
    param([string]$Root)
    Push-Location -LiteralPath $Root
    try {
        $oldErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $statusLines = @(& git status --short --branch --untracked-files=all 2>$null)
        $statusExitCode = $LASTEXITCODE
        $diffNames = @(& git diff --name-only 2>$null)
        $diffExitCode = $LASTEXITCODE
        $branch = (& git branch --show-current 2>$null).Trim()
        $branchExitCode = $LASTEXITCODE
        $ErrorActionPreference = $oldErrorActionPreference
        if ($statusExitCode -ne 0) { throw "git status failed." }
        if ($diffExitCode -ne 0) { throw "git diff --name-only failed." }
        if ($branchExitCode -ne 0) { throw "git branch --show-current failed." }
    }
    finally {
        if ($null -ne $oldErrorActionPreference) {
            $ErrorActionPreference = $oldErrorActionPreference
        }
        Pop-Location
    }

    $untracked = @($statusLines | Where-Object { $_ -match "^\?\? " } | ForEach-Object { $_.Substring(3).Trim().Replace("\", "/") })
    $changed = @($statusLines | Where-Object { $_ -notlike "##*" })
    $forbiddenRoots = @(
        "Reports",
        "telemetry",
        "automation/orchestration/work_packets",
        "control/relay_bus/messages",
        "control/review_bridge/codex_reports",
        "automation/orchestration/queue",
        "automation/orchestration/command_queue",
        "automation/orchestration/locks",
        "automation/orchestration/approval_inbox",
        "automation/orchestration/runtime",
        "automation/orchestration/workers/inbox",
        "control"
    )
    $fingerprints = [ordered]@{}
    foreach ($relative in $forbiddenRoots) {
        $fingerprints[$relative] = Get-PathFingerprint -Root $Root -RelativePath $relative
    }
    $fingerprints[".env*"] = Get-EnvFingerprint -Root $Root

    return [ordered]@{
        branch = $branch
        status_lines = $statusLines
        diff_name_only = $diffNames
        untracked_files = $untracked
        changed_entries = $changed
        dirty = ($changed.Count -gt 0)
        forbidden_fingerprints = $fingerprints
    }
}

function Get-ChangedPathFromStatusLine {
    param([string]$Line)
    if ([string]::IsNullOrWhiteSpace($Line) -or $Line -like "##*") {
        return $null
    }
    if ($Line.Length -lt 4) {
        return $null
    }
    $path = $Line.Substring(3).Trim()
    if ($path -match " -> ") {
        $path = ($path -split " -> ")[-1].Trim()
    }
    return $path.Replace("\", "/")
}

function Test-DayNightReadinessDirtyState {
    param([object]$State)
    $allowedExact = @(
        "automation/orchestration/supervisor/Get-AiOsDayNightReadiness.DRY_RUN.ps1",
        "automation/orchestration/supervisor/aios_day_night_readiness.py",
        "schemas/aios/orchestration/AIOS_DAY_NIGHT_READINESS_RESULT.v1.schema.json",
        "schemas/aios/orchestration/ORCHESTRATION_SCHEMA_INDEX.json",
        "tests/orchestration/test_aios_day_night_readiness.py",
        "tests/orchestration/test_aios_day_night_readiness_runner.py",
        "automation/orchestration/self_audit/Get-AiOsSelfDevelopmentPacketRouter.DRY_RUN.ps1",
        "automation/orchestration/self_audit/Invoke-AiOsSelfAuditLoop.DRY_RUN.ps1",
        "automation/orchestration/validators/Get-AiOsValidatorEvidenceRouter.DRY_RUN.ps1",
        "automation/orchestration/self_development/Invoke-AiOsGovernedSelfDevelopmentLoop.DRY_RUN.ps1",
        "automation/orchestration/self_development/aios_governed_self_development_loop.py",
        "schemas/aios/orchestration/AIOS_GOVERNED_SELF_DEVELOPMENT_LOOP_RESULT.v1.schema.json",
        "tests/orchestration/test_aios_governed_self_development_loop.py",
        "tests/orchestration/test_aios_governed_self_development_loop_runner.py",
        "tests/orchestration/test_aios_self_audit_runner.py",
        "tests/orchestration/test_aios_self_development_packet_router_runner.py",
        "tests/orchestration/test_aios_validator_evidence_router_runner.py",
        "automation/orchestration/operator_control/Test-AiOsApprovalSosHardGate.DRY_RUN.ps1",
        "automation/orchestration/operator_control/aios_approval_sos_hard_gate.py",
        "schemas/aios/orchestration/AIOS_APPROVAL_SOS_HARD_GATE_RESULT.v1.schema.json",
        "tests/orchestration/test_aios_approval_sos_hard_gate.py",
        "tests/orchestration/test_aios_approval_sos_hard_gate_runner.py",
        "automation/orchestration/self_development/Test-AiOsGovernedSelfDevelopmentSoak.DRY_RUN.ps1",
        "automation/orchestration/self_development/aios_governed_self_development_soak.py",
        "schemas/aios/orchestration/AIOS_GOVERNED_SELF_DEVELOPMENT_SOAK_RESULT.v1.schema.json",
        "tests/orchestration/test_aios_governed_self_development_soak.py",
        "tests/orchestration/test_aios_governed_self_development_soak_runner.py"
    )
    $changedPaths = @($State.changed_entries | ForEach-Object { Get-ChangedPathFromStatusLine -Line ([string]$_) } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($changedPaths.Count -eq 0) {
        return $false
    }
    foreach ($path in $changedPaths) {
        if (-not ($allowedExact -contains $path)) {
            return $false
        }
    }
    return $true
}

function ConvertTo-StableJson {
    param([object]$Value)
    return ($Value | ConvertTo-Json -Depth 30 -Compress)
}

function Compare-NoWriteState {
    param([object]$Before, [object]$After)
    $gitChanged = (ConvertTo-StableJson -Value $Before.status_lines) -ne (ConvertTo-StableJson -Value $After.status_lines) -or
        (ConvertTo-StableJson -Value $Before.diff_name_only) -ne (ConvertTo-StableJson -Value $After.diff_name_only)
    $forbiddenChanged = (ConvertTo-StableJson -Value $Before.forbidden_fingerprints) -ne (ConvertTo-StableJson -Value $After.forbidden_fingerprints)
    return [ordered]@{
        changed = [bool]($gitChanged -or $forbiddenChanged)
        git_state_changed = [bool]$gitChanged
        forbidden_surface_changed = [bool]$forbiddenChanged
        before_dirty = [bool]$Before.dirty
        after_dirty = [bool]$After.dirty
        before_changed_entries = @($Before.changed_entries)
        after_changed_entries = @($After.changed_entries)
        before_untracked_files = @($Before.untracked_files)
        after_untracked_files = @($After.untracked_files)
    }
}

function Read-AuthorityContext {
    param([string]$Root)
    $files = @(
        "AGENTS.md",
        "README.md",
        "RISK_POLICY.md",
        "docs/AI_OS/autonomy/AIOS_SELF_AUDIT_LOOP_CONTRACT_V1.md",
        "docs/governance/aios-identity-and-lane-governance.md",
        "docs/governance/AI_OS_REPO_MEMORY.md"
    )
    $items = @()
    foreach ($relative in $files) {
        $path = Join-Path $Root $relative
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $text = Get-Content -LiteralPath $path -Raw
            $items += [ordered]@{
                path = $relative
                exists = $true
                bytes = [System.Text.Encoding]::UTF8.GetByteCount($text)
            }
        }
        else {
            $items += [ordered]@{
                path = $relative
                exists = $false
                bytes = 0
            }
        }
    }
    return [ordered]@{
        files = $items
        all_required_loaded = [bool](-not @($items | Where-Object { -not $_.exists }))
    }
}

function Invoke-JsonSurface {
    param([string]$Root, [string]$RelativeScript, [int]$TimeoutSeconds, [string]$ExpectedBranchValue = $ExpectedBranch)
    $scriptPath = Join-Path $Root $RelativeScript
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        return [ordered]@{
            available = $false
            ok = $false
            error = "surface_missing"
            data = $null
        }
    }
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = "powershell"
    $safePath = $scriptPath -replace '"', '\"'
    $safeRoot = $Root -replace '"', '\"'
    $safeExpectedBranch = $ExpectedBranchValue -replace '"', '\"'
    $branchAwareScripts = @(
        "automation/orchestration/self_audit/Invoke-AiOsSelfAuditLoop.DRY_RUN.ps1",
        "automation/orchestration/self_audit/Get-AiOsSelfDevelopmentPacketRouter.DRY_RUN.ps1",
        "automation/orchestration/validators/Get-AiOsValidatorEvidenceRouter.DRY_RUN.ps1"
    )
    $normalizedRelativeScript = $RelativeScript -replace "\\", "/"
    if ($branchAwareScripts -contains $normalizedRelativeScript) {
        $psi.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -RepoRoot "{1}" -ExpectedBranch "{2}" -OutputJson -TimeoutSeconds {3}' -f $safePath, $safeRoot, $safeExpectedBranch, $TimeoutSeconds
    } else {
        $psi.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -OutputJson' -f $safePath
    }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.WorkingDirectory = $Root
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $process.Kill()
        return [ordered]@{
            available = $true
            ok = $false
            error = "surface_timeout"
            data = $null
        }
    }
    $rawText = $stdoutTask.Result.Trim()
    if ($process.ExitCode -ne 0) {
        return [ordered]@{
            available = $true
            ok = $false
            error = "surface_exit_$($process.ExitCode)"
            data = $null
        }
    }
    try {
        return [ordered]@{
            available = $true
            ok = $true
            error = ""
            data = ($rawText | ConvertFrom-Json -ErrorAction Stop)
        }
    }
    catch {
        $null = $stderrTask.Result
        return [ordered]@{
            available = $true
            ok = $false
            error = "surface_json_parse_failed"
            data = $null
        }
    }
}

function Invoke-PythonReadinessLogic {
    param([string]$Root, [string]$LogicPath, [object]$Payload, [int]$TimeoutSeconds)
    if (-not (Test-Path -LiteralPath $LogicPath -PathType Leaf)) {
        throw "Python day/night readiness logic module missing: $LogicPath"
    }
    $payloadJson = $Payload | ConvertTo-Json -Depth 70
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = "python"
    $psi.Arguments = ('"{0}"' -f ($LogicPath -replace '"', '\"'))
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.WorkingDirectory = $Root
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.StandardInput.Write($payloadJson)
    $process.StandardInput.Close()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $process.Kill()
        throw "Python day/night readiness logic timed out."
    }
    $rawText = $stdoutTask.Result.Trim()
    $errorText = $stderrTask.Result.Trim()
    if ([string]::IsNullOrWhiteSpace($rawText)) {
        throw "Python day/night readiness logic returned no JSON. $errorText"
    }
    return $rawText | ConvertFrom-Json -ErrorAction Stop
}

function Write-ConsoleReport {
    param([object]$Result)
    Write-Host "AIOS Day Night Readiness"
    Write-Host "Mode: $($Result.mode)"
    Write-Host "Schema: $($Result.schema)"
    Write-Host ""
    Write-Host "CURRENT STATE"
    Write-Host "branch: $($Result.repo_state.branch)"
    Write-Host "dirty: $($Result.repo_state.dirty)"
    Write-Host "expected_branch: $($Result.repo_state.expected_branch)"
    Write-Host "branch_matches_expected: $($Result.repo_state.branch_matches_expected)"
    Write-Host ""
    Write-Host "READINESS"
    Write-Host "classification: $($Result.readiness.classification)"
    Write-Host "recommendation_allowed: $($Result.readiness.recommendation_allowed)"
    Write-Host "execution_allowed: $($Result.readiness.execution_allowed)"
    Write-Host ""
    Write-Host "OPERATOR MODES"
    Write-Host "allowed: $(@($Result.allowed_operator_modes) -join ', ')"
    Write-Host "blocked: $(@($Result.blocked_operator_modes) -join ', ')"
    Write-Host ""
    Write-Host "EVIDENCE SOURCES"
    foreach ($source in @($Result.evidence_sources)) {
        Write-Host "- $($source.name): $($source.status)"
    }
    Write-Host ""
    Write-Host "VALIDATOR STATUS"
    Write-Host "status: $($Result.validator_status.status)"
    Write-Host "unsafe_flags: $(@($Result.validator_status.unsafe_flags) -join ', ')"
    Write-Host ""
    Write-Host "APPROVAL STATE"
    Write-Host "status: $($Result.approval_state.status)"
    Write-Host "approval_required: $($Result.approval_state.approval_required)"
    Write-Host ""
    Write-Host "RUNTIME WORKER STATE"
    Write-Host "status: $($Result.runtime_worker_state.status)"
    Write-Host ""
    Write-Host "BACKUP INTERFERENCE"
    Write-Host "status: $($Result.backup_interference_state.status)"
    Write-Host ""
    Write-Host "NO-WRITE PROOF"
    Write-Host "changed: $($Result.no_write_proof.changed)"
    Write-Host "git_state_changed: $($Result.no_write_proof.git_state_changed)"
    Write-Host "forbidden_surface_changed: $($Result.no_write_proof.forbidden_surface_changed)"
    Write-Host ""
    Write-Host "STOP CONDITIONS"
    if (@($Result.stop_conditions).Count -eq 0) {
        Write-Host "- none"
    }
    else {
        foreach ($condition in @($Result.stop_conditions)) {
            Write-Host "- $condition"
        }
    }
    Write-Host ""
    Write-Host "NEXT SAFE ACTION"
    Write-Host $Result.next_safe_action
    Write-Host ""
    Write-Host "STATUS: $($Result.safety.status)"
}

$resolvedRepoRoot = Get-RepoRoot -PathHint $RepoRoot
$logicPath = Join-Path $PSScriptRoot "aios_day_night_readiness.py"
$generatedUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$authorityContext = Read-AuthorityContext -Root $resolvedRepoRoot
$beforeState = Get-NoWriteState -Root $resolvedRepoRoot
$dirtyAllowedForValidation = Test-DayNightReadinessDirtyState -State $beforeState
$skipSurfaceCalls = (-not $authorityContext.all_required_loaded) -or ([bool]$beforeState.dirty -and $FailOnDirtyWorktree -and (-not $dirtyAllowedForValidation))

$surfaceResults = [ordered]@{
    self_audit_result = $null
    packet_router_result = $null
    validator_evidence_router_result = $null
    campaign_no_ready = $null
    campaign_next_task = $null
    action_recommendation = $null
    approval_inbox_summary = $null
    lock_status = $null
    worker_inbox = $null
}

if (-not $skipSurfaceCalls) {
    $surfaces = [ordered]@{
        self_audit_result = "automation/orchestration/self_audit/Invoke-AiOsSelfAuditLoop.DRY_RUN.ps1"
        packet_router_result = "automation/orchestration/self_audit/Get-AiOsSelfDevelopmentPacketRouter.DRY_RUN.ps1"
        validator_evidence_router_result = "automation/orchestration/validators/Get-AiOsValidatorEvidenceRouter.DRY_RUN.ps1"
        campaign_no_ready = "automation/orchestration/campaign_registry/Get-AiOsCampaignNoReadyStageDiscovery.DRY_RUN.ps1"
        campaign_next_task = "automation/orchestration/campaign_registry/Get-AiOsCampaignNextTask.DRY_RUN.ps1"
        action_recommendation = "automation/orchestration/recommendations/Get-AiOsActionRecommendation.DRY_RUN.ps1"
        approval_inbox_summary = "automation/orchestration/approval_inbox/Get-AiOsApprovalInboxSummary.DRY_RUN.ps1"
        lock_status = "automation/orchestration/locks/Get-AiOsWorkerLockStatus.DRY_RUN.ps1"
        worker_inbox = "automation/orchestration/workers/inbox/Get-AiOsWorkerInbox.DRY_RUN.ps1"
    }
    foreach ($entry in $surfaces.GetEnumerator()) {
        $surfaceResult = Invoke-JsonSurface -Root $resolvedRepoRoot -RelativeScript $entry.Value -TimeoutSeconds $TimeoutSeconds
        if ($surfaceResult.ok) {
            $surfaceResults[$entry.Key] = $surfaceResult.data
        }
    }
}

$afterState = Get-NoWriteState -Root $resolvedRepoRoot
$noWriteProof = Compare-NoWriteState -Before $beforeState -After $afterState

$repoState = [ordered]@{
    repo_root = $resolvedRepoRoot
    branch = $beforeState.branch
    expected_branch = $ExpectedBranch
    branch_matches_expected = ([string]$beforeState.branch -eq [string]$ExpectedBranch)
    dirty = [bool]$beforeState.dirty
    dirty_allowed_for_day_night_readiness_validation = [bool]$dirtyAllowedForValidation
    fail_on_dirty_worktree = [bool]$FailOnDirtyWorktree
    status_lines = @($beforeState.status_lines)
    diff_name_only = @($beforeState.diff_name_only)
    untracked_files = @($beforeState.untracked_files)
}

$payload = [ordered]@{
    generated_utc = $generatedUtc
    repo_state = $repoState
    authority_context = $authorityContext
    self_audit_result = $surfaceResults.self_audit_result
    packet_router_result = $surfaceResults.packet_router_result
    validator_evidence_router_result = $surfaceResults.validator_evidence_router_result
    campaign_no_ready = $surfaceResults.campaign_no_ready
    campaign_next_task = $surfaceResults.campaign_next_task
    action_recommendation = $surfaceResults.action_recommendation
    approval_inbox_summary = $surfaceResults.approval_inbox_summary
    lock_status = $surfaceResults.lock_status
    worker_inbox = $surfaceResults.worker_inbox
    runtime_worker_state = [ordered]@{
        runtime_risk_detected = $false
        worker_launch_detected = $false
        scheduler_or_daemon_detected = $false
        runtime_state_source = "read_only_evidence"
    }
    backup_interference_state = [ordered]@{
        interference_detected = $false
        repo_local_backup_lock_present = $false
        backup_in_progress = $false
        snapshot_restore_candidate_present = $false
    }
    no_write_proof = $noWriteProof
}

$result = Invoke-PythonReadinessLogic -Root $resolvedRepoRoot -LogicPath $logicPath -Payload $payload -TimeoutSeconds $TimeoutSeconds

if ($OutputJson) {
    $result | ConvertTo-Json -Depth 70
}
else {
    Write-ConsoleReport -Result $result
}

if ([string]$result.safety.status -eq "PASS") {
    exit 0
}
exit 1
