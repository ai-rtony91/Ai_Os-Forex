<#
.SYNOPSIS
AI_OS Morning Brief -- single-command situational awareness for any worker or operator.

.DESCRIPTION
Produces a structured battle-map: repo state, open PRs, active packets,
approval inbox, validator status, and next-safe-action.

Run at session start, after Stop hook fires, or any time you need a status reset.
Does NOT write files (beyond LAST_SESSION_STATE.json), stage, commit, push, or mutate anything.

.PARAMETER NoStateFile
Skip writing the LAST_SESSION_STATE.json snapshot.

.PARAMETER Json
Output the brief as structured JSON.

.EXAMPLE
.\automation\orchestration\Invoke-AiOsMorningBrief.ps1

.EXAMPLE
.\automation\orchestration\Invoke-AiOsMorningBrief.ps1 -Json
#>

[CmdletBinding()]
param(
    [switch]$NoStateFile,
    [switch]$Json
)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

$repoRoot  = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$brief     = [ordered]@{}

function Invoke-Safe {
    param([scriptblock]$Block)
    try { & $Block } catch { "ERROR: $_" }
}

function Write-Banner {
    param([string]$Text, [string]$Color = "Cyan")
    if (-not $Json) {
        Write-Host ""
        Write-Host ("=" * 68) -ForegroundColor DarkGray
        Write-Host "  $Text" -ForegroundColor $Color
        Write-Host ("=" * 68) -ForegroundColor DarkGray
    }
}

function Write-Field {
    param([string]$Label, [string]$Value, [string]$Color = "White")
    if (-not $Json) {
        Write-Host ("  {0,-28} {1}" -f $Label, $Value) -ForegroundColor $Color
    }
}

# ---------- 1. REPO STATE ----------------------------------------------------

Write-Banner "REPO STATE" "Cyan"

$branch    = Invoke-Safe { git -C $repoRoot branch --show-current 2>&1 }
$statusOut = Invoke-Safe { git -C $repoRoot status --short 2>&1 }
$logOut    = Invoke-Safe { git -C $repoRoot log --oneline -5 2>&1 }

$remoteSync = Invoke-Safe {
    $ahead  = (git -C $repoRoot rev-list "@{u}..HEAD" 2>&1 | Measure-Object -Line).Lines
    $behind = (git -C $repoRoot rev-list "HEAD..@{u}" 2>&1 | Measure-Object -Line).Lines
    if ($ahead -gt 0 -and $behind -gt 0) { "DIVERGED ($ahead ahead, $behind behind)" }
    elseif ($ahead -gt 0)  { "$ahead commit(s) AHEAD of origin" }
    elseif ($behind -gt 0) { "$behind commit(s) BEHIND origin -- pull needed" }
    else { "SYNCED with origin" }
}

$dirtyFiles     = @($statusOut | Where-Object { $_ -and (-not $_.StartsWith("??")) })
$untrackedFiles = @($statusOut | Where-Object { $_ -and $_.StartsWith("??") })
$repoClean      = ($dirtyFiles.Count -eq 0)
$statusLabel    = if ($repoClean) { "CLEAN" } else { "$($dirtyFiles.Count) modified, $($untrackedFiles.Count) untracked" }
$statusColor    = if ($repoClean) { "Green" } else { "Yellow" }

Write-Field "Branch:"        ([string]$branch)
Write-Field "Remote:"        ([string]$remoteSync)
Write-Field "Working tree:"  $statusLabel -Color $statusColor
Write-Field "Last 5 commits:" ""
$logOut | ForEach-Object { Write-Field "" ([string]$_) }

$brief.repo = [ordered]@{
    branch          = [string]$branch
    remote_sync     = [string]$remoteSync
    clean           = $repoClean
    dirty_count     = $dirtyFiles.Count
    untracked_count = $untrackedFiles.Count
    last_commits    = @($logOut)
}

# ---------- 2. OPEN PULL REQUESTS --------------------------------------------

Write-Banner "OPEN PULL REQUESTS" "Cyan"

$prJson = Invoke-Safe {
    gh pr list --state open --json number,title,headRefName,mergeable --limit 10 2>&1
}
$prs = @()
try { $prs = ($prJson | Out-String) | ConvertFrom-Json -ErrorAction Stop } catch { $prs = @() }

if ($prs.Count -eq 0) {
    Write-Field "Open PRs:" "None" -Color "Green"
} else {
    foreach ($pr in $prs) {
        $mColor = if ($pr.mergeable -eq "CONFLICTING") { "Red" } else { "Green" }
        Write-Field "PR #$($pr.number):" $pr.title -Color $mColor
        Write-Field "" "  Branch: $($pr.headRefName)  Mergeable: $($pr.mergeable)"
    }
}

$brief.open_prs = @($prs | ForEach-Object {
    [ordered]@{ number = $_.number; title = $_.title; branch = $_.headRefName; mergeable = $_.mergeable }
})

# ---------- 3. ACTIVE PACKETS ------------------------------------------------

Write-Banner "ACTIVE PACKETS" "Cyan"

$activePacketDir = Join-Path $repoRoot "automation\orchestration\work_packets\active"
$activePackets   = @()

if (Test-Path -LiteralPath $activePacketDir) {
    $packetFiles = Get-ChildItem -LiteralPath $activePacketDir -File -Filter "*.json" -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending
    foreach ($pf in $packetFiles) {
        try {
            $p      = Get-Content -LiteralPath $pf.FullName -Raw | ConvertFrom-Json
            $id     = if ($p.packet_id) { [string]$p.packet_id } else { $pf.BaseName }
            $title  = if ($p.title)     { [string]$p.title }     elseif ($p.goal) { [string]$p.goal } else { "(no title)" }
            $status = if ($p.status)    { [string]$p.status }    else { "UNKNOWN" }
            $next   = if ($p.next_action) { [string]$p.next_action } else { "" }
            $sColor = switch ($status) {
                "DONE"              { "Green" }
                "BLOCKED"           { "Red" }
                "awaiting_approval" { "Yellow" }
                default             { "White" }
            }
            Write-Field "Packet:" "$id  [$status]" -Color $sColor
            if ($title) { Write-Field "" "  $title" }
            if ($next)  { Write-Field "" "  Next: $next" }
            $activePackets += [ordered]@{ packet_id = $id; title = $title; status = $status; next_action = $next }
        } catch { }
    }
}

if ($activePackets.Count -eq 0) { Write-Field "Active packets:" "None" }
$brief.active_packets = $activePackets

# ---------- 4. APPROVAL INBOX ------------------------------------------------

Write-Banner "APPROVAL INBOX" "Cyan"

$approvalDir  = Join-Path $repoRoot "automation\orchestration\approval_inbox"
$pendingItems = @()

if (Test-Path -LiteralPath $approvalDir) {
    $approvalFiles = Get-ChildItem -LiteralPath $approvalDir -File -Filter "*.json" -ErrorAction SilentlyContinue
    foreach ($af in $approvalFiles) {
        try {
            $a = Get-Content -LiteralPath $af.FullName -Raw | ConvertFrom-Json
            $aStatus = if ($a.approval_status) { [string]$a.approval_status }
                       elseif ($a.approved_by_human -eq $false) { "pending" }
                       else { "approved" }
            if ($aStatus -notin @("approved","APPROVED","DONE","COMPLETE")) {
                $iColor = if ($aStatus -in @("blocked","BLOCKED")) { "Red" } else { "Yellow" }
                $id     = if ($a.approval_gate_id) { [string]$a.approval_gate_id } else { $af.BaseName }
                $action = if ($a.requested_action) { [string]$a.requested_action } else { "" }
                Write-Field "Pending:" "$id  [$aStatus]" -Color $iColor
                if ($action) { Write-Field "" "  Action: $action" }
                $pendingItems += [ordered]@{ id = $id; status = $aStatus; action = $action }
            }
        } catch { }
    }
}

if ($pendingItems.Count -eq 0) {
    Write-Field "Approval inbox:" "Clear -- no pending items" -Color "Green"
}
$brief.approval_inbox = $pendingItems

# ---------- 5. VALIDATOR STATUS (quick) --------------------------------------

Write-Banner "VALIDATOR STATUS" "Cyan"

$spineScript = Join-Path $repoRoot "automation\orchestration\validators\Test-AiOsIdentitySpine.DRY_RUN.ps1"
$spineResult = "SKIPPED"
if (Test-Path -LiteralPath $spineScript) {
    $spineOut = Invoke-Safe { powershell -ExecutionPolicy Bypass -File $spineScript 2>&1 }
    $spineStr = $spineOut | Out-String
    if ($spineStr -match '"overall_result":\s*"(\w+)"') { $spineResult = $Matches[1] }
}
$spineColor = if ($spineResult -eq "PASS") { "Green" } else { "Yellow" }
Write-Field "Identity spine:" $spineResult -Color $spineColor

$chainPath   = Join-Path $repoRoot "automation\orchestration\validators\VALIDATOR_CHAIN_001.json"
$chainStatus = "NOT_FOUND"
if (Test-Path -LiteralPath $chainPath) {
    try {
        $chain       = Get-Content -LiteralPath $chainPath -Raw | ConvertFrom-Json
        $checkCount  = $chain.required_checks.Count
        $chainStatus = "LOADED -- $checkCount checks defined"
    } catch { $chainStatus = "JSON_PARSE_ERROR" }
}
Write-Field "Validator chain:" $chainStatus

$brief.validators = [ordered]@{ identity_spine = $spineResult; chain_status = $chainStatus }

# ---------- 6. NEXT SAFE ACTION ----------------------------------------------

Write-Banner "NEXT SAFE ACTION" "Yellow"

$nextAction = if ($pendingItems.Count -gt 0) {
    "Review $($pendingItems.Count) pending approval inbox item(s) before any APPLY."
} elseif (-not $repoClean) {
    "Repo has unstaged changes. Run git status and classify before starting new work."
} elseif ($prs.Count -gt 0) {
    $prNums = ($prs | ForEach-Object { "#$($_.number)" }) -join ", "
    "Review open PR(s): $prNums. Merge when CI passes."
} elseif ($activePackets.Count -gt 0) {
    "Active packet found. Resume from packet next_action above."
} else {
    "Repo is clean. No pending approvals. Ready for next packet."
}

if (-not $Json) {
    Write-Host ""
    Write-Host "  >> $nextAction" -ForegroundColor Yellow
    Write-Host ""
}

$brief.next_safe_action = $nextAction
$brief.generated_at     = $timestamp

# ---------- 7. WRITE STATE FILE ----------------------------------------------

if (-not $NoStateFile) {
    $stateDir  = Join-Path $repoRoot "automation\orchestration\session"
    $stateFile = Join-Path $stateDir "LAST_SESSION_STATE.json"
    try {
        if (-not (Test-Path -LiteralPath $stateDir)) {
            New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
        }
        $brief | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $stateFile -Encoding UTF8
        if (-not $Json) {
            $rel = $stateFile -replace [regex]::Escape($repoRoot + "\"), ""
            Write-Host "  State saved: $rel" -ForegroundColor DarkGray
        }
    } catch {
        if (-not $Json) { Write-Host "  (Could not write state file: $_)" -ForegroundColor DarkGray }
    }
}

# ---------- 8. JSON OUTPUT ---------------------------------------------------

if ($Json) {
    $brief | ConvertTo-Json -Depth 6
}
