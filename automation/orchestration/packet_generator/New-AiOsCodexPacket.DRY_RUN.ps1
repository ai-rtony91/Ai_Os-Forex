param(
    [string]$MissionId = "", [string]$MissionName = "",
    [string]$ProgramId = "", [string]$ProgramName = "",
    [string]$EpicId = "", [string]$EpicName = "",
    [string]$BucketId = "", [string]$BucketName = "",
    [string]$PacketId = "", [string]$PacketName = "",
    [string]$IdentityMarker = "", [string]$SupervisorIdentity = "",
    [string]$WorkerIdentity = "", [string]$LockIdentity = "",
    [string]$Mode = "", [string]$Zone = "", [string]$Lane = "",
    [string]$Worktree = "", [string]$Branch = "",
    [string]$ApprovalAuthority = "",
    [string[]]$AllowedPaths = @(), [string[]]$ForbiddenPaths = @(),
    [string[]]$Preflight = @(), [string[]]$Validators = @(),
    [string]$StopPoint = "", [string[]]$FinalReportFormat = @(),
    [string]$StagingAuthority = "", [string]$CommitAuthority = "",
    [string]$PushAuthority = "", [string]$PullRequestAuthority = "",
    [string]$MergeAuthority = "",
    [switch]$OutputJson, [switch]$AsPromptBlock,
    # Legacy values are translated below; missing v2 safety context stays blocked.
    [string[]]$AllowedMutationFiles = @(), [string]$StartBranch = "",
    [string[]]$ReadFirst = @(), [string]$Mission = "",
    [switch]$FromContinuationPlan, [string]$ContinuationPlanScript = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "AiOsCodexPacketContract.ps1")
$contract = Get-AiOsCodexPacketContract

function Format-List([string[]]$Values) {
    return (@($Values | ForEach-Object { if (-not [string]::IsNullOrWhiteSpace($_)) { "- $_" } }) -join "`n")
}

function Test-Placeholder([string]$Value) {
    foreach ($pattern in @($contract.unresolved_placeholder_patterns)) {
        if ($Value -match $pattern) { return $true }
    }
    return $false
}

function Invoke-ContinuationPlan([string]$ScriptPath) {
    if ([string]::IsNullOrWhiteSpace($ScriptPath) -or -not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
        return $null
    }
    try {
        # Preserve cross-host compatibility: reuse the current PowerShell
        # process rather than assuming either powershell.exe or pwsh exists.
        $powerShellHost = (Get-Process -Id $PID).Path
        $raw = & $powerShellHost -NoProfile -ExecutionPolicy Bypass -File $ScriptPath -OutputJson
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        return $raw | ConvertFrom-Json
    }
    catch { return $null }
}

$aliasDefects = @()
if (@($AllowedMutationFiles).Count -gt 0) {
    if (@($AllowedPaths).Count -gt 0 -and (($AllowedPaths -join "`n") -cne ($AllowedMutationFiles -join "`n"))) {
        $aliasDefects += "conflicting_alias:AllowedMutationFiles"
    }
    elseif (@($AllowedPaths).Count -eq 0) { $AllowedPaths = @($AllowedMutationFiles) }
}
if ([string]::IsNullOrWhiteSpace($Branch)) { $Branch = $StartBranch }
if ([string]::IsNullOrWhiteSpace($MissionName)) { $MissionName = $Mission }
if ([string]::IsNullOrWhiteSpace($Mission)) { $Mission = $MissionName }
if ($FromContinuationPlan -or -not [string]::IsNullOrWhiteSpace($ContinuationPlanScript)) {
    $aliasDefects += "continuation_requires_explicit_v2_inputs"
}

$scalars = [ordered]@{
    "MISSION ID"=$MissionId; "MISSION NAME"=$MissionName
    "PROGRAM ID"=$ProgramId; "PROGRAM NAME"=$ProgramName
    "EPIC ID"=$EpicId; "EPIC NAME"=$EpicName
    "BUCKET ID"=$BucketId; "BUCKET NAME"=$BucketName
    "PACKET ID"=$PacketId; "PACKET NAME"=$PacketName
    "IDENTITY MARKER"=$IdentityMarker; "SUPERVISOR IDENTITY"=$SupervisorIdentity
    "WORKER IDENTITY"=$WorkerIdentity; "LOCK IDENTITY"=$LockIdentity
    "MODE"=$Mode; "ZONE"=$Zone; "LANE"=$Lane; "WORKTREE"=$Worktree
    "BRANCH"=$Branch; "APPROVAL AUTHORITY"=$ApprovalAuthority; "STOP POINT"=$StopPoint
}
$lists = [ordered]@{
    "ALLOWED PATHS"=@($AllowedPaths); "FORBIDDEN PATHS"=@($ForbiddenPaths)
    "PREFLIGHT"=@($Preflight); "VALIDATOR CHAIN"=@($Validators)
    "FINAL REPORT FORMAT"=@($FinalReportFormat)
}
$protected = [ordered]@{
    "STAGING AUTHORITY"=$StagingAuthority; "COMMIT AUTHORITY"=$CommitAuthority
    "PUSH AUTHORITY"=$PushAuthority; "PULL REQUEST AUTHORITY"=$PullRequestAuthority
    "MERGE AUTHORITY"=$MergeAuthority
}

$missing = @()
$defects = @($aliasDefects)
foreach ($entry in $scalars.GetEnumerator()) {
    if ([string]::IsNullOrWhiteSpace([string]$entry.Value)) { $missing += $entry.Key }
    elseif ([string]$entry.Value -match "[\r\n\x00]") { $defects += "multiline_field:$($entry.Key)" }
    elseif (Test-Placeholder ([string]$entry.Value)) { $defects += "unresolved_placeholder:$($entry.Key)" }
}
foreach ($entry in $lists.GetEnumerator()) {
    $items = @($entry.Value | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    if ($items.Count -eq 0) { $missing += $entry.Key }
    elseif ($items.Count -ne @($entry.Value).Count -or @($items | Where-Object { $_ -match "[\r\n\x00]" }).Count -gt 0) { $defects += "malformed_list:$($entry.Key)" }
    elseif (Test-Placeholder ($items -join "`n")) { $defects += "unresolved_placeholder:$($entry.Key)" }
}
foreach ($entry in $protected.GetEnumerator()) {
    if ([string]::IsNullOrWhiteSpace([string]$entry.Value)) { $missing += $entry.Key }
    elseif ([string]$entry.Value -match "[\r\n\x00]") { $defects += "multiline_field:$($entry.Key)" }
    elseif (Test-Placeholder ([string]$entry.Value)) { $defects += "unresolved_placeholder:$($entry.Key)" }
    elseif ([string]$entry.Value -notmatch $contract.protected_authority_pattern) { $defects += "malformed_protected_authority:$($entry.Key)" }
}
foreach ($value in @($ReadFirst) + @($StartBranch, $Mission)) {
    if ($value -match "[\r\n\x00]" -or (Test-Placeholder $value)) { $defects += "invalid_legacy_value" }
}
if ($Mode -notin @("DRY_RUN", "APPLY")) { $defects += "invalid_mode" }
foreach ($command in @($contract.required_repository_state_commands)) {
    if ($Preflight -notcontains $command) { $defects += "missing_preflight_command:$command" }
}

$text = @"
CODEX-ONLY PROMPT
AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

$($contract.required_bootstrap_lines -join "`n")

MISSION ID:
$MissionId
MISSION NAME:
$MissionName
PROGRAM ID:
$ProgramId
PROGRAM NAME:
$ProgramName
EPIC ID:
$EpicId
EPIC NAME:
$EpicName
BUCKET ID:
$BucketId
BUCKET NAME:
$BucketName
PACKET ID:
$PacketId
PACKET NAME:
$PacketName

IDENTITY MARKER:
$IdentityMarker
SUPERVISOR IDENTITY:
$SupervisorIdentity
WORKER IDENTITY:
$WorkerIdentity
LOCK IDENTITY:
$LockIdentity
MODE:
$Mode
ZONE:
$Zone
LANE:
$Lane
WORKTREE:
$Worktree
BRANCH:
$Branch
START_BRANCH:
$StartBranch
MISSION:
$Mission
READ FIRST:
$(Format-List $ReadFirst)
APPROVAL AUTHORITY:
$ApprovalAuthority

ALLOWED PATHS:
$(Format-List $AllowedPaths)
FORBIDDEN PATHS:
$(Format-List $ForbiddenPaths)
PREFLIGHT:
$(Format-List $Preflight)
VALIDATOR CHAIN:
$(Format-List $Validators)
STOP POINT:
$StopPoint
FINAL REPORT FORMAT:
$(Format-List $FinalReportFormat)

STAGING AUTHORITY:
$StagingAuthority
COMMIT AUTHORITY:
$CommitAuthority
PUSH AUTHORITY:
$PushAuthority
PULL REQUEST AUTHORITY:
$PullRequestAuthority
MERGE AUTHORITY:
$MergeAuthority

execution_allowed=false
can_continue_without_anthony=false
writes_files=false
"@

# The serialized packet must also pass the same validator used by consumers.
try {
    $checked = & (Join-Path $PSScriptRoot "Test-AiOsCodexPacket.DRY_RUN.ps1") -PacketText $text -OutputJson | ConvertFrom-Json -ErrorAction Stop
    if (-not (Test-AiOsCodexPacketReport -Report $checked -ExpectedSchema "AIOS_CODEX_PACKET_VALIDATOR.v2")) {
        $missing += @($checked.missing_required_fields)
        $defects += @($checked.validation_defects)
        $defects += "serialized_packet_rejected"
    }
}
catch { $defects += "validator_invocation_error" }
$valid = ($missing.Count -eq 0 -and $defects.Count -eq 0)
if (-not $valid) { $text = "" }

$result = [ordered]@{
    schema="AIOS_CODEX_PACKET_GENERATOR.v2"; contract_schema=$contract.schema
    generated_packet_text=$text; packet_valid=$valid
    missing_required_fields=@($missing); validation_defects=@($defects)
    writes_files=$false; execution_allowed=$false; can_continue_without_anthony=$false
}
if ($OutputJson) { $result | ConvertTo-Json -Depth 20 }
elseif ($valid) { Write-Output $text }
else { Write-Output "WHAT FAILED: Packet validation.
WHY IT FAILED: Missing or invalid safety context.
WHAT IS MISSING: $($missing -join ', '); $($defects -join ', ')
SAFE NEXT ACTION: Supply explicit valid inputs.
STATUS: BLOCKED" }
exit 0