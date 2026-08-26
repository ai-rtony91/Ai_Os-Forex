param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Body,
    [string]$HeadBranch = "",
    [string]$BaseBranch = "main",
    [string]$GitCommand = "git",
    [string]$BodyFile = "",
    [switch]$WatchChecks,
    [switch]$AnthonyReviewed,
    [Alias("MergeAfterChecks")]
    [switch]$AnthonyApprovedMerge,
    [switch]$DeleteBranch,
    [switch]$OutputJson,
    [string]$RepoRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $AnthonyReviewed) {
    $blocked = [ordered]@{
        schema = "AIOS_CHATGPT_REVIEWED_PR_LIFECYCLE.v1"
        mode = "DRY_RUN_READ_ONLY"
        branch = ""
        base_branch = $BaseBranch
        head_branch = ""
        working_tree_clean = $false
        ahead_of_base = $false
        pushed = $false
        pr_created = $false
        pr_reused = $false
        pr_number = ""
        pr_url = ""
        checks_status = "BLOCKED_NO_ANTHONY_REVIEW"
        merge_requested = $false
        merge_allowed = $false
        merged = $false
        deleted_branch = $false
        synced_main = $false
        aios_status_ran = $false
        continuation_plan_ran = $false
        continuation_bridge_ran = $false
        next_packet_candidate = ""
        execution_allowed = $false
        human_approval_required = $true
        requires_anthony_for_merge = $true
        blocked_actions = @("AnthonyReviewed flag missing", "branch state and PR checks blocked")
        exact_next_safe_action = "Paste a reviewed command from ChatGPT in Anthony channel, include -AnthonyReviewed, then rerun."
        reason = "Blocked because Anthony Reviewed guard is required."
        anthony_reviewed = $false
    }
    if ($OutputJson) {
        $blocked | ConvertTo-Json -Depth 20
        exit 0
    }
    Write-Output ($blocked | ConvertTo-Json -Depth 20)
    exit 0
}

function Resolve-RepoRoot {
    param([string]$CandidateRoot)
    if (-not [string]::IsNullOrWhiteSpace($CandidateRoot)) {
        return (Resolve-Path -LiteralPath $CandidateRoot -ErrorAction Stop).Path
    }

    $gitRootResult = Invoke-GitCommandCapture -Arguments @("rev-parse", "--show-toplevel") -RepoRootPath (Get-Location).Path
    if ($gitRootResult.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($gitRootResult.Stdout)) {
        return $gitRootResult.Stdout.Trim()
    }

    return (Get-Location).Path
}

function Resolve-HeadBranch {
    param(
        [string]$InputBranch,
        [string]$RepoRootPath
    )
    if (-not [string]::IsNullOrWhiteSpace($InputBranch)) {
        return $InputBranch
    }

    $currentResult = Invoke-GitCommandCapture -Arguments @("branch", "--show-current") -RepoRootPath $RepoRootPath
    $current = $currentResult.Stdout.TrimEnd("`r","`n")
    if ($currentResult.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($current)) {
        throw "Current branch is empty."
    }
    return $current
}

function Invoke-CommandCapture {
    param([string[]]$Arguments, [string]$Command = "git")
    $output = & $Command @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{
        Output = @($output | ForEach-Object { [string]$_ })
        ExitCode = $exitCode
    }
}

function Invoke-GitCommandCapture {
    param([string[]]$Arguments, [string]$RepoRootPath)
    $escapedArgs = @("-C", $RepoRootPath) + $Arguments
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    if ($GitCommand.ToLowerInvariant().EndsWith(".ps1")) {
        $psi.FileName = "powershell"
        $psi.Arguments = @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $GitCommand
        ) + $escapedArgs | ForEach-Object { "`"$($_.Replace('"','`"'))`"" }
        $psi.Arguments = [string]::Join(" ", $psi.Arguments)
    }
    else {
        $psi.FileName = $GitCommand
        $psi.Arguments = [string]::Join(" ", ($escapedArgs | ForEach-Object { "`"$($_.Replace('"','`"'))`"" }))
    }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    $null = $process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    $exitCode = $process.ExitCode
    $process.Dispose()

    $combined = @($stdout, $stderr) | Where-Object { $_ } | ForEach-Object { [string]$_ }

    return [pscustomobject]@{
        exit_code = $exitCode
        stdout = if ($stdout) { [string]$stdout.TrimEnd("`r","`n") } else { "" }
        stderr = if ($stderr) { [string]$stderr.TrimEnd("`r","`n") } else { "" }
        combined_output = $combined -join "`n"
        Output = @($combined)
        ExitCode = $exitCode
    }
}

function Invoke-CommandCaptureText {
    param([string]$Command, [string]$ArgsString)
    $output = Invoke-Expression "$Command $ArgsString"
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{
        Output = @($output | ForEach-Object { [string]$_ })
        ExitCode = $exitCode
    }
}

function Has-Command {
    param([string]$Command)
    return $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

function Assert-MandatoryPrBody {
    param([string]$Text, [string]$FilePath)
    if (-not [string]::IsNullOrWhiteSpace($FilePath)) {
        if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
            throw "BodyFile not found: $FilePath"
        }
        return Get-Content -LiteralPath $FilePath -Raw
    }
    return $Text
}

function Test-GitRefExists {
    param(
        [string]$RepoRootPath,
        [string]$Ref
    )
    $probeResult = Invoke-GitCommandCapture -Arguments @("rev-parse", "--verify", $Ref) -RepoRootPath $RepoRootPath
    return ($probeResult.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($probeResult.stdout))
}

$repoRoot = Resolve-RepoRoot -CandidateRoot $RepoRoot
$headBranch = Resolve-HeadBranch -InputBranch $HeadBranch -RepoRootPath $repoRoot
$bodyText = Assert-MandatoryPrBody -Text $Body -FilePath $BodyFile

$gitStatusResult = Invoke-GitCommandCapture -Arguments @("status", "--short") -RepoRootPath $repoRoot
$gitStatus = if ($gitStatusResult.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($gitStatusResult.Stdout)) { @($gitStatusResult.Stdout -split "`n" | Where-Object { $_ }) } else { @() }
$dirtyOrUntrackedCount = @($gitStatus).Count
$workingTreeClean = ($dirtyOrUntrackedCount -eq 0)
$branchResult = Invoke-GitCommandCapture -Arguments @("branch", "--show-current") -RepoRootPath $repoRoot
$branch = $branchResult.Stdout.TrimEnd("`r","`n")
if ([string]::IsNullOrWhiteSpace($branch)) { $branch = "UNKNOWN" }

$result = [ordered]@{
    schema = "AIOS_CHATGPT_REVIEWED_PR_LIFECYCLE.v1"
    mode = "DRY_RUN_READ_ONLY"
    anthony_reviewed = $true
    repo_root = $repoRoot
    branch = $branch
    base_branch = $BaseBranch
    head_branch = $headBranch
    working_tree_clean = $false
    ahead_of_base = $false
    pushed = $false
    pr_created = $false
    pr_reused = $false
    pr_number = ""
    pr_url = ""
    checks_status = "NOT_RUN"
    merge_requested = $false
    merge_allowed = $false
    merged = $false
    deleted_branch = $false
    synced_main = $false
    aios_status_ran = $false
    continuation_plan_ran = $false
    continuation_bridge_ran = $false
    next_packet_candidate = ""
    execution_allowed = $false
    human_approval_required = $true
    requires_anthony_for_merge = $true
    blocked_actions = @(
        "never run on main",
        "clean tree required",
        "branch must be ahead of base before PR push",
        "no force push",
        "no merge without explicit merge flag",
        "no commit creation",
        "no runtime/queue/locks/telemetry/report mutation"
    )
    exact_next_safe_action = "Paste and rerun with required approvals."
    reason = ""
}

if (-not (Has-Command -Command "git")) {
    $result.reason = "Blocked: git command unavailable."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}
if (-not (Has-Command -Command "gh")) {
    $result.blocked_actions += "gh CLI missing"
    $result.reason = "Blocked: gh CLI is required for reviewed PR lifecycle."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}

$baseRefExists = Test-GitRefExists -RepoRootPath $repoRoot -Ref $BaseBranch
$headRefExists = Test-GitRefExists -RepoRootPath $repoRoot -Ref $headBranch
if (-not $baseRefExists -or -not $headRefExists) {
    $result.blocked_actions += "base or head ref missing"
    $result.reason = "Blocked: no commits ahead of base."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}

if ($branch -eq $BaseBranch) {
    $result.reason = "Blocked: cannot run reviewed PR lifecycle on base branch '$BaseBranch'."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}
if (-not $workingTreeClean) {
    $result.reason = "Blocked: working tree is dirty."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}

$countResultRaw = Invoke-GitCommandCapture -Arguments @("rev-list", "--count", "$BaseBranch..$headBranch") -RepoRootPath $repoRoot
if ($countResultRaw.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($countResultRaw.stdout)) {
    $result.reason = "Blocked: no commits ahead of base."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}

$countResult = @($countResultRaw.stdout.Trim())
$ahead = [int]$countResult[0]
$result.ahead_of_base = ($ahead -gt 0)
if (-not $result.ahead_of_base) {
    $result.reason = "Blocked: no commits ahead of base."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}

$result.working_tree_clean = $true

if ($branch -ne $headBranch) {
    $gitCheckoutHead = Invoke-GitCommandCapture -Arguments @("checkout", $headBranch) -RepoRootPath $repoRoot
    if ($gitCheckoutHead.ExitCode -ne 0) {
        $result.reason = "Blocked: unable to checkout head branch."
        if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
        Write-Output ($result | ConvertTo-Json -Depth 20)
        exit 0
    }
}

$pushResult = Invoke-GitCommandCapture -Arguments @("push", "-u", "origin", $headBranch) -RepoRootPath $repoRoot
if ($pushResult.ExitCode -ne 0) {
    $result.reason = "Blocked: push failed."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}
$result.pushed = $true

$existing = Invoke-CommandCapture -Arguments @("pr", "list", "--head", $headBranch, "--base", $BaseBranch, "--state", "open", "--json", "number,url") -Command "gh"
if ($existing.ExitCode -eq 0 -and (@($existing.Output)).Count -gt 0) {
    try {
        $json = $existing.Output -join [Environment]::NewLine | ConvertFrom-Json
        $jsonItems = @($json)
        if ((@($jsonItems)).Count -gt 0) {
            $result.pr_reused = $true
            $first = $jsonItems[0]
            $result.pr_number = [string]$first.number
            $result.pr_url = [string]$first.url
        }
    }
    catch {
        # keep pr_reused false
    }
}

if (-not $result.pr_reused) {
    $createResult = Invoke-CommandCapture -Arguments @(
        "pr", "create",
        "--base", $BaseBranch,
        "--head", $headBranch,
        "--title", $Title,
        "--body", $bodyText
    ) -Command "gh"
    if ($createResult.ExitCode -ne 0) {
        $result.reason = "Blocked: PR create failed."
        if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
        Write-Output ($result | ConvertTo-Json -Depth 20)
        exit 0
    }
    $result.pr_created = $true
    $result.pr_url = if ((@($createResult.Output)).Count -gt 0) { [string]$createResult.Output[0] } else { "" }
    if (-not [string]::IsNullOrWhiteSpace($result.pr_url) -and $result.pr_url -match "/pull/(\\d+)") {
        $result.pr_number = $Matches[1]
    }
}

if (-not $result.pr_number) {
    $result.pr_number = if ([string]::IsNullOrWhiteSpace($result.pr_url)) { "" } else { $result.pr_url.Split("/")[-1] }
}

$checksWanted = [bool]$WatchChecks -or [bool]$AnthonyApprovedMerge
if ($checksWanted) {
    $prForChecks = if ($result.pr_number) { $result.pr_number } else { "HEAD" }
    $checkResult = Invoke-CommandCapture -Arguments @("pr", "checks", $prForChecks, "--watch") -Command "gh"
    if ($checkResult.ExitCode -ne 0) {
        $result.checks_status = "FAIL"
        $result.reason = "Blocked: PR checks failed."
        if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
        Write-Output ($result | ConvertTo-Json -Depth 20)
        exit 0
    }
    $result.checks_status = "PASS"
}
else {
    $result.checks_status = "NOT_WATCHED"
}

$result.merge_requested = [bool]$AnthonyApprovedMerge
$result.merge_allowed = [bool]$AnthonyApprovedMerge
$result.human_approval_required = -not [bool]$AnthonyApprovedMerge
if ([bool]$AnthonyApprovedMerge -eq $false) {
    $result.requires_anthony_for_merge = $true
    $result.exact_next_safe_action = "Checks can pass, but Anthony merge flag is required before merge."
    $result.reason = "Blocked: merge requires -AnthonyReviewed with explicit merge flag."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}

$result.requires_anthony_for_merge = $false
$result.reason = "Merge flag present. Running merge and post-merge proof."
$mergeResult = Invoke-CommandCapture -Arguments @("pr", "merge", $result.pr_number, "--merge") -Command "gh"
if ($mergeResult.ExitCode -ne 0) {
    $result.reason = "Blocked: merge failed."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}
$result.merged = $true

if ($checksWanted -and $result.checks_status -ne "PASS") {
    $result.reason = "Blocked: checks not passed."
    $result.merged = $false
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}

$checkoutBaseResult = Invoke-GitCommandCapture -Arguments @("checkout", $BaseBranch) -RepoRootPath $repoRoot
if ($checkoutBaseResult.ExitCode -ne 0) {
    $result.reason = "Blocked: unable to checkout base branch."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}
$pullMainResult = Invoke-GitCommandCapture -Arguments @("pull", "--ff-only", "origin", $BaseBranch) -RepoRootPath $repoRoot
if ($pullMainResult.ExitCode -ne 0) {
    $result.reason = "Blocked: unable to sync base branch."
    if ($OutputJson) { $result | ConvertTo-Json -Depth 20; exit 0 }
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
}
$result.synced_main = $true

$aiosStatus = Invoke-CommandCaptureText -Command "powershell" -ArgsString "-NoProfile -ExecutionPolicy Bypass -File .\\aios.ps1 -Mode status"
$result.aios_status_ran = ($LASTEXITCODE -eq 0)

$continuationPlan = Invoke-CommandCaptureText -Command "powershell" -ArgsString "-NoProfile -ExecutionPolicy Bypass -File automation/orchestration/continuation/Get-AiOsSupervisedContinuationPlan.DRY_RUN.ps1 -OutputJson"
$result.continuation_plan_ran = ($LASTEXITCODE -eq 0)
if ($continuationPlan.ExitCode -eq 0) {
    try {
        $jsonPlan = $continuationPlan.Output -join [Environment]::NewLine | ConvertFrom-Json
        if ($jsonPlan -and $jsonPlan.PSObject.Properties.Name -contains "recommended_next_packet_id") {
            $result.next_packet_candidate = [string]$jsonPlan.recommended_next_packet_id
        }
    }
    catch {
        $result.next_packet_candidate = ""
    }
}

$bridge = Invoke-CommandCaptureText -Command "powershell" -ArgsString "-NoProfile -ExecutionPolicy Bypass -File automation/orchestration/continuation/Convert-AiOsContinuationPlanToProposedPacket.DRY_RUN.ps1 -OutputJson"
$result.continuation_bridge_ran = ($LASTEXITCODE -eq 0)

if ($DeleteBranch) {
    $deleteResult = Invoke-GitCommandCapture -Arguments @("branch", "-d", $headBranch) -RepoRootPath $repoRoot
    $result.deleted_branch = ($deleteResult.ExitCode -eq 0)
}

$result.reason = "Completed reviewed PR lifecycle run with explicit merge."
$result.exact_next_safe_action = "Workflow complete for this packet; wait for next recommended packet."

if ($OutputJson) {
    $result | ConvertTo-Json -Depth 20
    exit 0
}

Write-Output ($result | ConvertTo-Json -Depth 20)
