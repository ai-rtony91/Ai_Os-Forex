[CmdletBinding()]
param(
    [string]$LockRegistryPath = "automation/orchestration/locks/FILE_LOCK_REGISTRY.json"
)

$ErrorActionPreference = "Stop"

function Write-WarningLine {
    param([string]$Message)
    Write-Output ("REVIEW_REQUIRED: {0}" -f $Message)
}

if (-not (Test-Path -LiteralPath $LockRegistryPath)) {
    Write-WarningLine "Lock registry not found: $LockRegistryPath"
    return
}

try {
    $lockData = Get-Content -LiteralPath $LockRegistryPath -Raw | ConvertFrom-Json
}
catch {
    Write-WarningLine "Lock registry JSON could not be parsed."
    return
}

$locks = @()
if ($lockData.PSObject.Properties.Name -contains "locks") {
    $locks = @($lockData.locks)
}
else {
    $locks = @($lockData)
}

$warnings = New-Object System.Collections.Generic.List[string]

function Get-LockPaths {
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

function ConvertTo-PathKey {
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

function Test-PathOverlap {
    param(
        [string]$LeftPath,
        [string]$RightPath
    )

    $left = ConvertTo-PathKey -Path $LeftPath
    $right = ConvertTo-PathKey -Path $RightPath

    if ([string]::IsNullOrWhiteSpace($left) -or [string]::IsNullOrWhiteSpace($right)) {
        return $false
    }

    return ($left -eq $right -or $left.StartsWith("$right/") -or $right.StartsWith("$left/"))
}

$requiredActiveFields = @(
    "schema",
    "schema_version",
    "lock_id",
    "worker_id",
    "packet_id",
    "lane",
    "status",
    "claimed_paths",
    "created_at_utc",
    "updated_at_utc",
    "expires_at_utc",
    "release_condition",
    "approval_packet_id",
    "notes"
)

foreach ($lock in $locks) {
    $lockId = [string]$lock.lock_id
    $workerId = [string]$lock.worker_id
    $lockedPaths = @(Get-LockPaths -Lock $lock)

    if ([string]::IsNullOrWhiteSpace($lockId) -or $lockId -like "*PLACEHOLDER*") {
        $warnings.Add("Lock has malformed lock_id: $lockId") | Out-Null
    }
    if ([string]::IsNullOrWhiteSpace($workerId) -or $workerId -like "*PLACEHOLDER*") {
        $warnings.Add("Lock has missing worker_id.") | Out-Null
    }

    if ($lock.status -eq "ACTIVE") {
        foreach ($field in $requiredActiveFields) {
            if (-not ($lock.PSObject.Properties.Name -contains $field)) {
                $warnings.Add("ACTIVE lock missing required field ${field}: $lockId") | Out-Null
            }
        }
    }

    if ($lock.status -eq "ACTIVE" -and $lockedPaths.Count -eq 0) {
        $warnings.Add("ACTIVE lock has empty claimed_paths array: $lockId") | Out-Null
    }

    foreach ($lockedPath in $lockedPaths) {
        if ([string]::IsNullOrWhiteSpace((ConvertTo-PathKey -Path $lockedPath))) {
            $warnings.Add("Lock has empty claimed path: $lockId") | Out-Null
        }
    }
}

foreach ($group in @($locks | Group-Object lock_id)) {
    $records = @($group.Group)
    if ($records.Count -le 1 -or [string]::IsNullOrWhiteSpace([string]$group.Name)) {
        continue
    }

    $activeForId = @($records | Where-Object { $_.status -eq "ACTIVE" })
    $unresolvedForId = @($records | Where-Object { $_.status -notin @("ACTIVE", "RELEASED") })
    if ($activeForId.Count -gt 1) {
        $warnings.Add("Multiple ACTIVE records share canonical lock_id: $($group.Name)") | Out-Null
    }
    if ($unresolvedForId.Count -gt 0) {
        $warnings.Add("Repeated canonical lock_id has unresolved non-terminal history: $($group.Name)") | Out-Null
    }
}

$activeLocks = @($locks | Where-Object { $_.status -eq "ACTIVE" })
for ($i = 0; $i -lt $activeLocks.Count; $i++) {
    for ($j = $i + 1; $j -lt $activeLocks.Count; $j++) {
        foreach ($leftPath in @(Get-LockPaths -Lock $activeLocks[$i])) {
            foreach ($rightPath in @(Get-LockPaths -Lock $activeLocks[$j])) {
                if (Test-PathOverlap -LeftPath $leftPath -RightPath $rightPath) {
                    $warnings.Add("ACTIVE lock path overlap detected: $($activeLocks[$i].lock_id) and $($activeLocks[$j].lock_id)") | Out-Null
                }
            }
        }
    }
}

if ($warnings.Count -eq 0) {
    Write-Output "PASS: Lock registry integrity checks passed."
}
else {
    foreach ($warning in $warnings) {
        Write-WarningLine $warning
    }
}
