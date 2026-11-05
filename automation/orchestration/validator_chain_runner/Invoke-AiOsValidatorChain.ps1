<#
.SYNOPSIS
AI_OS Validator Chain Runner -- runs all VALIDATOR_CHAIN_001 checks for a given packet.

.DESCRIPTION
Replaces the 12-step manual validator invocation process with a single command.
Runs all required checks defined in VALIDATOR_CHAIN_001.json plus the two always-required
identity and collision validators.

Returns: PASS | REVIEW | BLOCKED per check and an overall result.

Does NOT approve APPLY, commit, push, or any protected action.
Validator output is evidence only.

.PARAMETER AllowedPaths
Paths the packet is allowed to modify. Used for allowed_path_check and blocked_path_check.

.PARAMETER BlockedPaths
Paths the packet must not touch. Defaults to the standard AI_OS blocked set.

.PARAMETER PacketId
Optional packet ID for audit trail output.

.PARAMETER SkipIdentitySpine
Skip the Test-AiOsIdentitySpine check (use only when spine has already been verified this session).

.PARAMETER SkipClaimCollision
Skip the Test-WorkerClaimCollision check.

.PARAMETER Json
Output results as structured JSON.

.EXAMPLE
.\automation\orchestration\validator_chain_runner\Invoke-AiOsValidatorChain.ps1 `
    -PacketId "PKT-WEST-APPLY-005" `
    -AllowedPaths @("automation/orchestration/", ".claude/")

.EXAMPLE
.\automation\orchestration\validator_chain_runner\Invoke-AiOsValidatorChain.ps1 `
    -AllowedPaths @("docs/specs/") `
    -Json
#>

[CmdletBinding()]
param(
    [string[]]$AllowedPaths  = @(),
    [string[]]$BlockedPaths  = @(
        "secrets/", ".env", "keys/", "credentials/", "private/",
        "trading/", "broker/", "oanda/", "live_order/",
        "automation/agent_runtime/", "services/"
    ),
    [string]$PacketId        = "UNKNOWN",
    [switch]$SkipIdentitySpine,
    [switch]$SkipClaimCollision,
    [switch]$Json
)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

$repoRoot   = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) { $repoRoot = "C:\Dev\Ai.Os" }
$repoRoot   = $repoRoot.Trim() -replace "/", "\"
$valDir     = Join-Path $repoRoot "automation\orchestration\validators"
$timestamp  = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$results    = [System.Collections.Generic.List[object]]::new()
$overallResult = "PASS"

function Add-Result {
    param(
        [string]$CheckId,
        [ValidateSet("PASS","REVIEW","BLOCKED")][string]$Result,
        [string]$Message,
        [string[]]$Evidence = @()
    )
    $results.Add([pscustomobject]@{
        check_id  = $CheckId
        result    = $Result
        message   = $Message
        evidence  = @($Evidence)
    }) | Out-Null
    if ($Result -eq "BLOCKED") {
        $script:overallResult = "BLOCKED"
    } elseif ($Result -eq "REVIEW" -and $script:overallResult -ne "BLOCKED") {
        $script:overallResult = "REVIEW"
    }
    if (-not $Json) {
        $color = switch ($Result) { "PASS" {"Green"} "REVIEW" {"Yellow"} "BLOCKED" {"Red"} }
        Write-Host ("  [{0,-8}]  {1}" -f $Result, $CheckId) -ForegroundColor $color
        if ($Message) { Write-Host "             $Message" -ForegroundColor DarkGray }
    }
}

function Invoke-Safe {
    param([scriptblock]$Block)
    try { & $Block } catch { "ERROR: $_" }
}

if (-not $Json) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host "  AI_OS VALIDATOR CHAIN -- VALIDATOR_CHAIN_001" -ForegroundColor Cyan
    Write-Host ("  Packet: " + $PacketId + "   at   " + $timestamp) -ForegroundColor DarkGray
    Write-Host ("=" * 72) -ForegroundColor DarkGray
}

# ---------- CHECK 1: execution_registry_guard --------------------------------

$guardScript = Join-Path $valDir "Invoke-AiOsExecutionRegistryGuard.ps1"
if (Test-Path -LiteralPath $guardScript) {
    $guardOut = Invoke-Safe { powershell -ExecutionPolicy Bypass -File $guardScript 2>&1 }
    $guardStr = ($guardOut | Out-String)
    # Guard is a report-only tool; findings are informational about the whole repo.
    # BLOCKED only on hard ERROR (script crash). REVIEW if guard reports STOP findings.
    if ($guardStr -cmatch "\bERROR\b" -and $guardStr -notmatch "Findings:") {
        Add-Result "execution_registry_guard" "BLOCKED" "Execution registry guard script errored." @($guardStr -split "`n" | Select-Object -First 5)
    } elseif ($guardStr -match "Findings:\s*0") {
        Add-Result "execution_registry_guard" "PASS" "Guard passed -- 0 findings."
    } elseif ($guardStr -match "Findings:\s*(\d+)") {
        $fCount = $Matches[1]
        Add-Result "execution_registry_guard" "REVIEW" "Guard found $fCount pre-existing finding(s) in repo (report-only, not related to this packet)."
    } else {
        Add-Result "execution_registry_guard" "REVIEW" "Guard output unclear -- review manually."
    }
} else {
    Add-Result "execution_registry_guard" "REVIEW" "Guard script not found -- skipping."
}

# ---------- CHECK 2: git_status_clean_before_work ----------------------------

$statusOut    = Invoke-Safe { git -C $repoRoot status --short 2>&1 }
$dirtyLines   = @($statusOut | Where-Object { $_ -and -not $_.StartsWith("??") })
$trackedDirty = @($dirtyLines | Where-Object { $_ -match "^[MADRCU]" })

if ($trackedDirty.Count -gt 0) {
    Add-Result "git_status_clean_before_work" "REVIEW" "$($trackedDirty.Count) tracked file(s) modified -- review before staging." @($trackedDirty)
} else {
    Add-Result "git_status_clean_before_work" "PASS" "No unexpected tracked modifications."
}

# ---------- CHECK 3: allowed_path_check --------------------------------------

$changedFiles = Invoke-Safe { git -C $repoRoot diff --name-only HEAD 2>&1 }
$untracked    = Invoke-Safe { git -C $repoRoot ls-files --others --exclude-standard 2>&1 }
$allChanged   = @($changedFiles) + @($untracked) | Where-Object { $_ }

if ($AllowedPaths.Count -eq 0) {
    Add-Result "allowed_path_check" "REVIEW" "No AllowedPaths specified -- cannot verify scope. Pass -AllowedPaths to enable this check."
} else {
    $violations = @()
    foreach ($file in $allChanged) {
        $inside = $false
        foreach ($allowed in $AllowedPaths) {
            if ($file -like "$allowed*" -or $file.StartsWith($allowed)) { $inside = $true; break }
        }
        if (-not $inside) { $violations += $file }
    }
    if ($violations.Count -gt 0) {
        Add-Result "allowed_path_check" "BLOCKED" "$($violations.Count) file(s) outside AllowedPaths." @($violations)
    } else {
        Add-Result "allowed_path_check" "PASS" "All $($allChanged.Count) changed file(s) within AllowedPaths."
    }
}

# ---------- CHECK 4: blocked_path_check --------------------------------------

$blockedHits = @()
foreach ($file in $allChanged) {
    foreach ($blocked in $BlockedPaths) {
        if ($file -like "*$blocked*" -or $file.StartsWith($blocked)) {
            $blockedHits += "$file (matches blocked: $blocked)"
        }
    }
}
if ($blockedHits.Count -gt 0) {
    Add-Result "blocked_path_check" "BLOCKED" "$($blockedHits.Count) file(s) touch blocked path(s)." @($blockedHits)
} else {
    Add-Result "blocked_path_check" "PASS" "No files touch blocked paths."
}

# ---------- CHECK 5: json_parse_check ----------------------------------------

$jsonFiles = @($allChanged | Where-Object { $_ -match "\.json$" })
$jsonFails = @()
foreach ($jf in $jsonFiles) {
    $fullPath = Join-Path $repoRoot ($jf -replace "/", "\")
    if (Test-Path -LiteralPath $fullPath) {
        try { Get-Content -LiteralPath $fullPath -Raw | ConvertFrom-Json | Out-Null }
        catch { $jsonFails += "$jf -- $_" }
    }
}
if ($jsonFails.Count -gt 0) {
    Add-Result "json_parse_check" "BLOCKED" "$($jsonFails.Count) JSON file(s) failed to parse." @($jsonFails)
} else {
    $msg = if ($jsonFiles.Count -eq 0) { "No JSON files changed." } else { "All $($jsonFiles.Count) JSON file(s) parse cleanly." }
    Add-Result "json_parse_check" "PASS" $msg
}

# ---------- CHECK 6: markdown_file_exists_check ------------------------------

$requiredMd = @("AGENTS.md", "README.md")
$mdMissing  = @()
foreach ($md in $requiredMd) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $md))) { $mdMissing += $md }
}
if ($mdMissing.Count -gt 0) {
    Add-Result "markdown_file_exists_check" "BLOCKED" "Required Markdown file(s) missing." @($mdMissing)
} else {
    Add-Result "markdown_file_exists_check" "PASS" "Required Markdown files exist."
}

# ---------- CHECK 7: no_secrets_check ----------------------------------------

$secretPatterns   = @("password\s*[:=]", "api_key\s*[:=]", "apikey\s*[:=]", "secret\s*[:=]", "bearer\s+[A-Za-z0-9]", "private_key", "-----BEGIN")
$secretExclusions = @("docs/", "schemas/", "AGENTS.md", "README.md", ".md", "validator_chain_runner/")
$secretHits       = @()

foreach ($file in $allChanged) {
    $skip = $false
    foreach ($excl in $secretExclusions) { if ($file -like "*$excl*") { $skip = $true; break } }
    if ($skip) { continue }
    $fullPath = Join-Path $repoRoot ($file -replace "/", "\")
    if (-not (Test-Path -LiteralPath $fullPath) -or (Test-Path -LiteralPath $fullPath -PathType Container)) { continue }
    $content  = Get-Content -LiteralPath $fullPath -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }
    foreach ($pat in $secretPatterns) {
        if ($content -match $pat) { $secretHits += "$file -- matches pattern: $pat"; break }
    }
}
if ($secretHits.Count -gt 0) {
    Add-Result "no_secrets_check" "BLOCKED" "Potential secret pattern detected." @($secretHits)
} else {
    Add-Result "no_secrets_check" "PASS" "No secret patterns detected in changed files."
}

# ---------- CHECK 8: no_broker_live_trading_enablement_check -----------------

$tradingPatterns    = @("oanda", "live_order", "broker_connect", "place_order", "execute_trade", "live_trading\s*=\s*true")
$tradingExclusions  = @("\.md$", "AGENTS\.md", "README", "validator_chain_runner/")
$tradingHits        = @()

foreach ($file in $allChanged) {
    $skip = $false
    foreach ($texcl in $tradingExclusions) { if ($file -match $texcl) { $skip = $true; break } }
    if ($skip) { continue }
    $fullPath = Join-Path $repoRoot ($file -replace "/", "\")
    if (-not (Test-Path -LiteralPath $fullPath) -or (Test-Path -LiteralPath $fullPath -PathType Container)) { continue }
    $raw      = Get-Content -LiteralPath $fullPath -Raw -ErrorAction SilentlyContinue
    if (-not $raw) { continue }
    $content  = $raw.ToLower()
    foreach ($pat in $tradingPatterns) {
        if ($content -match $pat) { $tradingHits += "$file -- matches: $pat"; break }
    }
}
if ($tradingHits.Count -gt 0) {
    Add-Result "no_broker_live_trading_enablement_check" "BLOCKED" "Live trading/broker pattern detected." @($tradingHits)
} else {
    Add-Result "no_broker_live_trading_enablement_check" "PASS" "No live trading or broker enablement detected."
}

# ---------- CHECK 9: commit_package_review_check -----------------------------

$staged      = Invoke-Safe { git -C $repoRoot diff --cached --name-only 2>&1 }
$stagedFiles = @($staged | Where-Object { $_ })

if ($stagedFiles.Count -eq 0) {
    Add-Result "commit_package_review_check" "REVIEW" "No files currently staged. Stage exact files before commit."
} else {
    if ($AllowedPaths.Count -gt 0) {
        $stagedViolations = @()
        foreach ($sf in $stagedFiles) {
            $inside = $false
            foreach ($allowed in $AllowedPaths) {
                if ($sf.StartsWith($allowed) -or $sf -like "$allowed*") { $inside = $true; break }
            }
            if (-not $inside) { $stagedViolations += $sf }
        }
        if ($stagedViolations.Count -gt 0) {
            Add-Result "commit_package_review_check" "BLOCKED" "$($stagedViolations.Count) staged file(s) outside AllowedPaths." @($stagedViolations)
        } else {
            Add-Result "commit_package_review_check" "PASS" "$($stagedFiles.Count) staged file(s) all within AllowedPaths."
        }
    } else {
        Add-Result "commit_package_review_check" "REVIEW" "$($stagedFiles.Count) file(s) staged. Verify all are within packet scope." @($stagedFiles)
    }
}

# ---------- CHECK 10: final_git_status_check ---------------------------------

$finalStatus = Invoke-Safe { git -C $repoRoot status --short 2>&1 }
$finalLines  = @($finalStatus | Where-Object { $_ })
Add-Result "final_git_status_check" "PASS" "$($finalLines.Count) line(s) in working tree." @($finalLines | Select-Object -First 10)

# ---------- BONUS: Test-AiOsIdentitySpine ------------------------------------

if (-not $SkipIdentitySpine) {
    $spineScript = Join-Path $valDir "Test-AiOsIdentitySpine.DRY_RUN.ps1"
    if (Test-Path -LiteralPath $spineScript) {
        $spineOut = Invoke-Safe { powershell -ExecutionPolicy Bypass -File $spineScript 2>&1 }
        $spineStr = ($spineOut | Out-String)
        $spineResultMatch = $spineStr | Select-String '"overall_result":\s*"(\w+)"'
        $spineResult = if ($spineResultMatch) { $spineResultMatch.Matches[0].Groups[1].Value } else { "UNKNOWN" }
        $resultLevel = switch ($spineResult) { "PASS" {"PASS"} "FAIL" {"BLOCKED"} default {"REVIEW"} }
        Add-Result "identity_spine" $resultLevel "Test-AiOsIdentitySpine result: $spineResult"
    } else {
        Add-Result "identity_spine" "REVIEW" "Test-AiOsIdentitySpine.DRY_RUN.ps1 not found."
    }
}

# ---------- BONUS: Test-WorkerClaimCollision ----------------------------------

if (-not $SkipClaimCollision) {
    $claimScript = Join-Path $valDir "Test-WorkerClaimCollision.DRY_RUN.ps1"
    if (Test-Path -LiteralPath $claimScript) {
        $claimOut = Invoke-Safe { powershell -ExecutionPolicy Bypass -File $claimScript 2>&1 }
        $claimStr = ($claimOut | Out-String)
        if ($claimStr -match "REVIEW_REQUIRED") {
            Add-Result "worker_claim_collision" "REVIEW" "REVIEW_REQUIRED -- check claim registry for PACKET_ID_PLACEHOLDER (pre-existing placeholder, verify no real collision)."
        } elseif ($claimStr -match "BLOCKED|FAIL") {
            Add-Result "worker_claim_collision" "BLOCKED" "Worker claim collision detected." @($claimStr -split "`n" | Select-Object -First 5)
        } else {
            Add-Result "worker_claim_collision" "PASS" "No worker claim collisions."
        }
    } else {
        Add-Result "worker_claim_collision" "REVIEW" "Test-WorkerClaimCollision.DRY_RUN.ps1 not found."
    }
}

# ---------- SUMMARY ----------------------------------------------------------

$passCount    = ($results | Where-Object { $_.result -eq "PASS"    }).Count
$reviewCount  = ($results | Where-Object { $_.result -eq "REVIEW"  }).Count
$blockedCount = ($results | Where-Object { $_.result -eq "BLOCKED" }).Count

$nextSafeAction = switch ($overallResult) {
    "PASS"    { "All checks passed. Human Owner approval still required before APPLY, commit, or push." }
    "REVIEW"  { "Review flagged items above. Resolve REVIEW items before APPLY. Human Owner approval still required." }
    "BLOCKED" { "BLOCKED -- do not proceed with APPLY or commit until all BLOCKED checks are resolved." }
}

$output = [ordered]@{
    schema           = "AIOS_VALIDATOR_CHAIN_RESULT.v1"
    packet_id        = $PacketId
    timestamp        = $timestamp
    overall_result   = $overallResult
    pass_count       = $passCount
    review_count     = $reviewCount
    blocked_count    = $blockedCount
    checks           = @($results)
    next_safe_action = $nextSafeAction
}

if (-not $Json) {
    $overallColor = switch ($overallResult) { "PASS" {"Green"} "REVIEW" {"Yellow"} "BLOCKED" {"Red"} }
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host ("  OVERALL: {0,-12}  PASS:{1}  REVIEW:{2}  BLOCKED:{3}" -f $overallResult, $passCount, $reviewCount, $blockedCount) -ForegroundColor $overallColor
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host ("  >> " + $nextSafeAction) -ForegroundColor Yellow
    Write-Host ""
} else {
    $output | ConvertTo-Json -Depth 6
}
