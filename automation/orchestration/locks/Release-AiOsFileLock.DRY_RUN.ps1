param(
    [string]$WorkerId = "AIOS-WORKER-DRY-RUN",
    [string]$LockId = "",
    [string]$Path = "",
    [string]$Reason = "Operator-approved lock release",
    [string]$RegistryPath = (Join-Path $PSScriptRoot "FILE_LOCK_REGISTRY.json"),
    [switch]$Apply,
    [switch]$OutputJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-AiOsUtcNow {
    return [DateTime]::UtcNow
}

function ConvertTo-AiOsUtcString {
    param([DateTime]$Value)
    return $Value.ToUniversalTime().ToString("o")
}

function Read-AiOsJsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "LOCK_REGISTRY_FAIL_CLOSED: Registry file not found: $Path"
    }

    try {
        return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    }
    catch {
        throw "LOCK_REGISTRY_FAIL_CLOSED: Registry JSON could not be parsed: $($_.Exception.Message)"
    }
}

function Write-AiOsJsonAtomic {
    param(
        [Parameter(Mandatory = $true)]$Data,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $directory = Split-Path -Parent $Path
    if ([string]::IsNullOrWhiteSpace($directory)) {
        $directory = "."
    }
    $leaf = Split-Path -Leaf $Path
    $tempPath = Join-Path $directory (".{0}.{1}.tmp" -f $leaf, [Guid]::NewGuid().ToString("N"))

    try {
        $json = $Data | ConvertTo-Json -Depth 20
        $encoding = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($tempPath, $json, $encoding)
        [void](Get-Content -Raw -LiteralPath $tempPath | ConvertFrom-Json)
        Move-Item -LiteralPath $tempPath -Destination $Path -Force
    }
    catch {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force
        }
        throw "LOCK_REGISTRY_ATOMIC_WRITE_FAILED: $($_.Exception.Message)"
    }
}

function ConvertTo-AiOsPathKey {
    param([AllowNull()][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ""
    }

    $key = $Path.Replace("\", "/").Trim()
    while ($key.StartsWith("./")) {
        $key = $key.Substring(2)
    }
    return $key.TrimEnd("/")
}

function Test-AiOsPathContained {
    param(
        [string]$RequestedPath,
        [string]$ClaimedPath
    )

    $requested = ConvertTo-AiOsPathKey -Path $RequestedPath
    $claimed = ConvertTo-AiOsPathKey -Path $ClaimedPath

    if ([string]::IsNullOrWhiteSpace($requested) -or [string]::IsNullOrWhiteSpace($claimed)) {
        return $false
    }

    return ($requested -eq $claimed -or $requested.StartsWith("$claimed/"))
}

function Get-AiOsLockPaths {
    param($Lock)

    if ($Lock.PSObject.Properties.Name -contains "claimed_paths") {
        return @($Lock.claimed_paths)
    }
    if ($Lock.PSObject.Properties.Name -contains "locked_paths") {
        return @($Lock.locked_paths)
    }
    if ($Lock.PSObject.Properties.Name -contains "paths") {
        return @($Lock.paths)
    }
    return @()
}

$registry = Read-AiOsJsonFile -Path $RegistryPath
$locks = @($registry.locks)
$normalizedPath = ConvertTo-AiOsPathKey -Path $Path
$reviewRequired = @()

if ([string]::IsNullOrWhiteSpace($LockId)) {
    $reviewRequired += [pscustomobject]@{
        risk_type = "MISSING_LOCK_ID"
        recommendation = "Release requires an exact lock_id."
    }
}

if ([string]::IsNullOrWhiteSpace($WorkerId)) {
    $reviewRequired += [pscustomobject]@{
        risk_type = "MISSING_WORKER_ID"
        recommendation = "Release requires an exact worker_id."
    }
}

$ownerMatches = @($locks | Where-Object { $_.lock_id -eq $LockId -and $_.worker_id -eq $WorkerId })
$matches = @($ownerMatches | Where-Object { $_.status -eq "ACTIVE" })
$releaseStatus = "BLOCKED"

if ($reviewRequired.Count -gt 0) {
    $releaseStatus = "REVIEW_REQUIRED"
}
elseif ($matches.Count -eq 0) {
    if ($ownerMatches.Count -gt 0) {
        $releaseStatus = "REVIEW_REQUIRED"
        $reviewRequired += [pscustomobject]@{
            risk_type = "NON_ACTIVE_LOCK_RELEASE_REVIEW"
            recommendation = "Do not mutate terminal lock history when no matching ACTIVE record exists."
        }
    }
    else {
        $releaseStatus = "BLOCKED"
        $reviewRequired += [pscustomobject]@{
            risk_type = "NO_EXACT_LOCK_OWNER_MATCH"
            recommendation = "Do not release any lock without exact lock_id and worker_id ownership."
        }
    }
}
elseif ($matches.Count -gt 1) {
    $releaseStatus = "REVIEW_REQUIRED"
    $reviewRequired += [pscustomobject]@{
        risk_type = "MULTIPLE_EXACT_LOCK_OWNER_MATCHES"
        recommendation = "Registry integrity review is required before release."
    }
}
else {
    $match = $matches[0]
    if ($match.status -ne "ACTIVE") {
        $releaseStatus = "REVIEW_REQUIRED"
        $reviewRequired += [pscustomobject]@{
            lock_id = $match.lock_id
            current_status = $match.status
            risk_type = "NON_ACTIVE_LOCK_RELEASE_REVIEW"
            recommendation = "Do not mutate non-active locks without review."
        }
    }
    elseif (-not [string]::IsNullOrWhiteSpace($normalizedPath)) {
        $pathAllowed = $false
        foreach ($claimedPath in (Get-AiOsLockPaths -Lock $match)) {
            if (Test-AiOsPathContained -RequestedPath $normalizedPath -ClaimedPath $claimedPath) {
                $pathAllowed = $true
            }
        }

        if ($pathAllowed) {
            $releaseStatus = "READY_TO_RELEASE"
        }
        else {
            $releaseStatus = "BLOCKED"
            $reviewRequired += [pscustomobject]@{
                requested_path = $normalizedPath
                lock_id = $match.lock_id
                risk_type = "RELEASE_PATH_NOT_OWNED_BY_LOCK"
                recommendation = "Optional path narrowing cannot release a path outside the matching lock."
            }
        }
    }
    else {
        $releaseStatus = "READY_TO_RELEASE"
    }
}

$releasePreview = @()
foreach ($match in $matches) {
    $releasePreview += [pscustomobject]@{
        lock_id = $match.lock_id
        worker_id = $match.worker_id
        packet_id = $match.packet_id
        current_status = $match.status
        next_status = "RELEASED"
        released_at_utc = ConvertTo-AiOsUtcString -Value (Get-AiOsUtcNow)
        release_reason = $Reason
    }
}

$writesPerformed = 0
if ($Apply -and $releaseStatus -eq "READY_TO_RELEASE") {
    $now = ConvertTo-AiOsUtcString -Value (Get-AiOsUtcNow)
    foreach ($lock in $registry.locks) {
        if ($lock.lock_id -eq $LockId -and $lock.worker_id -eq $WorkerId -and $lock.status -eq "ACTIVE") {
            $lock.status = "RELEASED"
            $lock.updated_at_utc = $now
            $lock | Add-Member -NotePropertyName "released_at_utc" -NotePropertyValue $now -Force
            $lock | Add-Member -NotePropertyName "release_reason" -NotePropertyValue $Reason -Force
        }
    }
    Write-AiOsJsonAtomic -Data $registry -Path $RegistryPath
    $writesPerformed = 1
}

$result = [pscustomobject]@{
    task = "AI_OS file lock release"
    mode = $(if ($Apply) { "APPLY" } else { "DRY_RUN" })
    registry_path = $RegistryPath
    release_status = $releaseStatus
    writes_performed = $writesPerformed
    match_count = $matches.Count
    release_preview = $releasePreview
    review_required = $reviewRequired
    safety = [pscustomobject]@{
        commits_performed = 0
        pushes_performed = 0
        broker_or_live_api_work = "NO"
    }
    next_safe_action = "Proceed only when release_status is READY_TO_RELEASE and the operator approved the exact APPLY lock release."
}

if ($OutputJson) {
    $result | ConvertTo-Json -Depth 10
    exit 0
}

Write-Host "AI_OS File Lock Release"
Write-Host "Mode: $($result.mode)"
Write-Host "Worker: $WorkerId"
Write-Host "LockId: $LockId"
Write-Host "Path: $normalizedPath"
Write-Host "Result: $releaseStatus"
Write-Host "Writes performed: $writesPerformed"
Write-Host ""

if ($matches.Count -eq 0) {
    Write-Host "No exact matching lock owner was found."
} else {
    Write-Host "Matched locks:"
    foreach ($preview in $releasePreview) {
        Write-Host "  - $($preview.lock_id): $($preview.current_status) -> $($preview.next_status)"
    }
}

Write-Host ""
Write-Host "Next safe action: $($result.next_safe_action)"
