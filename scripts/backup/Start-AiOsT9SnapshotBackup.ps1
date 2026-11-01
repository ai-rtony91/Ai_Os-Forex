[CmdletBinding()]
param(
    [string]$SourceRepo = "C:\Dev\Ai.Os",
    [string]$BackupRoot = "D:\T9_FOB",
    [ValidateSet("Auto", "Full", "Delta", "ManifestOnly")][string]$BackupMode = "Auto",
    [switch]$Preview,
    [switch]$OutputJson,
    [switch]$AllowDirty,
    [switch]$RetentionPreview,
    [string[]]$SavedWorkFiles = @(),
    [string]$ExpectedVolumeUniqueId = "",
    [string]$VerifiedScopeCheckpointPath = "",
    [string]$VerifiedArchiveManifestPath = "",
    [string]$IncrementalStateRoot = "",
    [string]$VerifiedPolicyReceiptPath = "",
    [string]$BackupTimeslotLabel = "manual",
    [string]$BackupWindowStart = "",
    [string]$BackupWindowEnd = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$aiosBackupHelperRoot = if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    Join-Path (Get-Location).Path "automation\orchestration\backups"
} else {
    Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path "automation\orchestration\backups"
}
. (Join-Path $aiosBackupHelperRoot "Get-AiOsBackupWorkDelta.ps1")
. (Join-Path $aiosBackupHelperRoot "New-AiOsBackupCourtesySos.ps1")

function ConvertTo-AiOsFullPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    return [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
}

function Add-AiOsTrailingSeparator {
    param([Parameter(Mandatory = $true)][string]$Path)

    $separator = [System.IO.Path]::DirectorySeparatorChar
    if ($Path.EndsWith([string]$separator)) {
        return $Path
    }

    return "$Path$separator"
}

function Test-AiOsPathEqual {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )

    return [System.StringComparer]::OrdinalIgnoreCase.Equals($Left, $Right)
}

function Test-AiOsPathInside {
    param(
        [Parameter(Mandatory = $true)][string]$ChildPath,
        [Parameter(Mandatory = $true)][string]$ParentPath
    )

    if (Test-AiOsPathEqual -Left $ChildPath -Right $ParentPath) {
        return $false
    }

    $childWithSeparator = Add-AiOsTrailingSeparator -Path $ChildPath
    $parentWithSeparator = Add-AiOsTrailingSeparator -Path $ParentPath
    return $childWithSeparator.StartsWith($parentWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)
}

function Resolve-AiOsBackupReportRoot {
    param(
        [Parameter(Mandatory = $true)][string]$PreferredRoot,
        [Parameter(Mandatory = $true)][string]$FallbackRoot,
        [Parameter(Mandatory = $true)][string]$SourceRoot
    )

    foreach ($candidate in @($PreferredRoot, $FallbackRoot)) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }

        $candidateFullPath = ConvertTo-AiOsFullPath -Path $candidate
        if ((Test-AiOsPathEqual -Left $candidateFullPath -Right $SourceRoot) -or
            (Test-AiOsPathInside -ChildPath $candidateFullPath -ParentPath $SourceRoot)) {
            continue
        }

        return $candidateFullPath
    }

    throw "BACKUP_REPORT_ROOT_UNSAFE: no backup report root outside SourceRepo was available."
}

function Test-AiOsPathContainsBackupPattern {
    param([Parameter(Mandatory = $true)][string]$Path)

    $segments = @($Path -split '[\\/]' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    foreach ($segment in $segments) {
        if ($segment -like "AIOS_BACKUP*" -or
            $segment -ieq "current_mirror" -or
            $segment -ieq "snapshots" -or
            $segment -ieq "T9_FOB" -or
            $segment -ieq "AI_OS backup mirror") {
            return $true
        }
    }

    return $false
}

function Test-AiOsBackupRecursionGuard {
    param(
        [Parameter(Mandatory = $true)][string]$SourceFullPath,
        [Parameter(Mandatory = $true)][string]$BackupRootFullPath,
        [Parameter(Mandatory = $true)][string]$SnapshotPathFullPath,
        [Parameter(Mandatory = $true)][string]$ApprovedBackupRootFullPath,
        [AllowEmptyCollection()][string[]]$CandidateCopySourcePaths = @(),
        [AllowEmptyCollection()][string[]]$ExcludedFolderNames = @()
    )

    $sourceEqualsBackupRoot = Test-AiOsPathEqual -Left $SourceFullPath -Right $BackupRootFullPath
    $sourceEqualsSnapshotPath = Test-AiOsPathEqual -Left $SourceFullPath -Right $SnapshotPathFullPath
    $backupRootInsideSource = Test-AiOsPathInside -ChildPath $BackupRootFullPath -ParentPath $SourceFullPath
    $sourceInsideBackupRoot = Test-AiOsPathInside -ChildPath $SourceFullPath -ParentPath $BackupRootFullPath
    $snapshotInsideSource = Test-AiOsPathInside -ChildPath $SnapshotPathFullPath -ParentPath $SourceFullPath
    $backupRootApproved = Test-AiOsPathEqual -Left $BackupRootFullPath -Right $ApprovedBackupRootFullPath
    $candidateCopySourceContainsBackupRoot = $false
    $candidateCopySourceContainsBackupPattern = $false

    foreach ($candidate in $CandidateCopySourcePaths) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }

        $candidateFullPath = ConvertTo-AiOsFullPath -Path $candidate
        if ((Test-AiOsPathEqual -Left $candidateFullPath -Right $BackupRootFullPath) -or
            (Test-AiOsPathInside -ChildPath $candidateFullPath -ParentPath $BackupRootFullPath) -or
            (Test-AiOsPathInside -ChildPath $BackupRootFullPath -ParentPath $candidateFullPath)) {
            $candidateCopySourceContainsBackupRoot = $true
        }

        if (Test-AiOsPathContainsBackupPattern -Path $candidateFullPath) {
            $candidateCopySourceContainsBackupPattern = $true
        }
    }

    $reasons = New-Object System.Collections.Generic.List[string]
    if ($sourceEqualsBackupRoot) { $reasons.Add("SourceRepo path equals BackupRoot.") }
    if ($sourceEqualsSnapshotPath) { $reasons.Add("SourceRepo path equals SnapshotPath.") }
    if ($backupRootInsideSource) { $reasons.Add("BackupRoot is inside SourceRepo.") }
    if ($sourceInsideBackupRoot) { $reasons.Add("SourceRepo is inside BackupRoot.") }
    if ($snapshotInsideSource) { $reasons.Add("SnapshotPath is inside SourceRepo.") }
    if (-not $backupRootApproved) { $reasons.Add("BackupRoot resolves outside the approved T9 backup layout.") }
    if ($candidateCopySourceContainsBackupRoot) { $reasons.Add("A candidate copy source path contains the backup root.") }
    if ($candidateCopySourceContainsBackupPattern) { $reasons.Add("A candidate copy source path contains a known backup folder pattern.") }

    $recursiveBackupDetected = ($reasons.Count -gt 0)
    return [pscustomobject]@{
        recursion_guard_enabled = $true
        source_full_path = $SourceFullPath
        backup_root_full_path = $BackupRootFullPath
        snapshot_path_full_path = $SnapshotPathFullPath
        excluded_folder_names = @($ExcludedFolderNames)
        backup_root_inside_source = [bool]$backupRootInsideSource
        source_inside_backup_root = [bool]$sourceInsideBackupRoot
        snapshot_inside_source = [bool]$snapshotInsideSource
        recursive_backup_detected = [bool]$recursiveBackupDetected
        recursive_backup_reason = if ($recursiveBackupDetected) { ($reasons -join " ") } else { "NONE" }
        safe_to_copy = (-not $recursiveBackupDetected)
        source_equals_backup_root = [bool]$sourceEqualsBackupRoot
        source_equals_snapshot_path = [bool]$sourceEqualsSnapshotPath
        backup_root_approved = [bool]$backupRootApproved
        candidate_copy_source_contains_backup_root = [bool]$candidateCopySourceContainsBackupRoot
        candidate_copy_source_contains_backup_pattern = [bool]$candidateCopySourceContainsBackupPattern
    }
}

function Test-AiOsRelativePathExcluded {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [string[]]$ExcludedFolderNames = @(),
        [string[]]$ExcludedFilePatterns = @()
    )

    $segments = @($RelativePath -split '[\\/]' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    foreach ($name in $ExcludedFolderNames) {
        if (@($segments | Where-Object { $_ -like $name }).Count -gt 0) {
            return $true
        }
    }

    $leafName = if ($segments.Count -gt 0) { $segments[-1] } else { $RelativePath }
    foreach ($pattern in $ExcludedFilePatterns) {
        if ($leafName -like $pattern) {
            return $true
        }
    }

    return $false
}

function Format-AiOsBytes {
    param([Parameter(Mandatory = $true)][double]$Bytes)

    if ($Bytes -lt 0) { return 'UNKNOWN' }

    $units = @("B", "KB", "MB", "GB", "TB", "PB")
    $value = $Bytes
    $index = 0
    while ($value -ge 1024 -and $index -lt ($units.Count - 1)) {
        $value = $value / 1024
        $index++
    }

    return ("{0:N2} {1}" -f $value, $units[$index])
}

function Get-AiOsDirectorySize {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string[]]$ExcludeNames = @(),
        [string[]]$ExcludeFilePatterns = @()
    )

    $total = [double]0
    $files = Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue
    foreach ($file in $files) {
        $segments = $file.FullName.Split([System.IO.Path]::DirectorySeparatorChar)
        $leafName = Split-Path -Leaf $file.FullName
        $skip = $false
        foreach ($name in $ExcludeNames) {
            if (@($segments | Where-Object { $_ -like $name }).Count -gt 0) {
                $skip = $true
                break
            }
        }
        foreach ($pattern in $ExcludeFilePatterns) {
            if ($leafName -like $pattern) {
                $skip = $true
                break
            }
        }
        if (-not $skip) {
            $total += $file.Length
        }
    }

    return $total
}

function Get-AiOsGitStatus {
    param([Parameter(Mandatory = $true)][string]$Path)

    $statusLines = @(git -C $Path status --short --branch)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read git status for source repo: $Path"
    }

    return [pscustomobject]@{
        lines = $statusLines
        is_clean = (@($statusLines | Select-Object -Skip 1).Count -eq 0)
    }
}

function Test-AiOsBackupSelfValidationDirtyState {
    param([Parameter(Mandatory = $true)][object]$GitStatus)

    $allowedDirtyPaths = @(
        "scripts/backup/Start-AiOsT9SnapshotBackup.ps1",
        "tests/backup/test_t9_snapshot_backup_noninterference.py"
    )
    $dirtyLines = @($GitStatus.lines | Select-Object -Skip 1 | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($dirtyLines.Count -eq 0) {
        return $false
    }

    foreach ($line in $dirtyLines) {
        $pathText = if ($line.Length -gt 3) { $line.Substring(3).Trim() } else { $line.Trim() }
        $paths = @($pathText -split '\s+->\s+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        foreach ($path in $paths) {
            $normalizedPath = $path.Replace("\", "/")
            $allowed = @($allowedDirtyPaths | Where-Object {
                [System.StringComparer]::OrdinalIgnoreCase.Equals($_, $normalizedPath)
            })
            if ($allowed.Count -eq 0) {
                return $false
            }
        }
    }

    return $true
}

function Get-AiOsGitInfo {
    param([Parameter(Mandatory = $true)][string]$Path)

    $branch = (git -C $Path branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read git branch for source repo: $Path"
    }

    $commitHash = (git -C $Path rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read git commit for source repo: $Path"
    }

    $commitShort = (git -C $Path rev-parse --short HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read short git commit for source repo: $Path"
    }

    return [pscustomobject]@{
        branch = $branch
        commit_hash = $commitHash
        commit_short = $commitShort
    }
}

function Get-AiOsProtectedActionLocks {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$BackupReportRoot,
        [Parameter(Mandatory = $true)][string]$BackupLockPath
    )

    $lockRoots = @(
        (Join-Path $RepoRoot "automation\orchestration\locks"),
        $BackupReportRoot
    )
    $protectedPattern = "protected|git|commit|push|merge|stage|staging|reset|clean|branch|\bpr\b|pull request"
    $locks = @()

    foreach ($root in $lockRoots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) {
            continue
        }

        $candidates = @(Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -like "*.lock" -or $_.Name -like "*.lock.json"
        })

        foreach ($candidate in $candidates) {
            if ($candidate.FullName -ieq $BackupLockPath) {
                continue
            }

            $nameMatch = $candidate.Name -match $protectedPattern
            $contentMatch = $false
            try {
                $contentMatch = [bool](Select-String -LiteralPath $candidate.FullName -Pattern $protectedPattern -Quiet -ErrorAction Stop)
            } catch {
                $contentMatch = $false
            }

            if ($nameMatch -or $contentMatch) {
                $locks += [pscustomobject]@{
                    path = $candidate.FullName
                    reason = "protected-action-or-git-lock"
                }
            }
        }
    }

    return @($locks)
}

function New-AiOsBackupLock {
    param(
        [Parameter(Mandatory = $true)][string]$BackupReportRoot,
        [Parameter(Mandatory = $true)][string]$BackupLockPath,
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$SnapshotPath
    )

    if (-not (Test-Path -LiteralPath $BackupReportRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $BackupReportRoot | Out-Null
    }

    $stream = [IO.File]::Open($BackupLockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try {
    if ($stream.Length -gt 0) {
        $buffer = New-Object byte[] ([int]$stream.Length)
        [void]$stream.Read($buffer,0,$buffer.Length)
        $prior = [Text.Encoding]::UTF8.GetString($buffer).TrimStart([char]0xFEFF) | ConvertFrom-Json -ErrorAction Stop
        if ($prior.status -ne 'RELEASED') {
            if ($prior.PSObject.Properties.Name -notcontains 'process_started_utc') { throw 'BACKUP_LOCK_OWNER_IDENTITY_UNKNOWN' }
            $owner = $null
            try { $owner = [Diagnostics.Process]::GetProcessById([int]$prior.process_id) } catch [ArgumentException] { }
            if ($null -ne $owner -and $owner.StartTime.ToUniversalTime().ToString('o') -eq $prior.process_started_utc) { throw 'BACKUP_LOCK_OWNER_STILL_LIVE' }
        }
    }
    $lock = [ordered]@{
        schema = "AIOS_BACKUP_LOCK.v1"
        status = "IN_PROGRESS"
        created_at = (Get-Date).ToString("o")
        source_path = $SourcePath
        snapshot_path = $SnapshotPath
        process_id = $PID
        process_started_utc = ([Diagnostics.Process]::GetCurrentProcess()).StartTime.ToUniversalTime().ToString('o')
    }

    $bytes = [Text.Encoding]::UTF8.GetBytes(($lock | ConvertTo-Json -Depth 4)+"`n")
    $stream.Position=0;$stream.SetLength(0);$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)
    if (-not (Get-Variable aiosBackupOwnedStreams -Scope Script -ErrorAction SilentlyContinue)) { $script:aiosBackupOwnedStreams=@{} }
    $script:aiosBackupOwnedStreams[$BackupLockPath]=$stream
    } catch { $stream.Dispose(); throw }
}

function Remove-AiOsBackupLock {
    param([Parameter(Mandatory = $true)][string]$BackupLockPath)

    if (-not (Get-Variable aiosBackupOwnedStreams -Scope Script -ErrorAction SilentlyContinue) -or -not $script:aiosBackupOwnedStreams.ContainsKey($BackupLockPath)) { throw 'BACKUP_LOCK_NOT_OWNED' }
    $stream=$script:aiosBackupOwnedStreams[$BackupLockPath]
    try { $bytes=[Text.Encoding]::UTF8.GetBytes('{"status":"RELEASED"}');$stream.Position=0;$stream.SetLength(0);$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true) } finally {$stream.Dispose();$script:aiosBackupOwnedStreams.Remove($BackupLockPath)}
}

function Get-AiOsRobocopyCounts {
    # Robocopy still prints its summary table under /NFL /NDL. Parse the
    # "Files :" row for Copied and Skipped counts. Columns are:
    # Total Copied Skipped Mismatch FAILED Extras
    param([AllowEmptyCollection()][AllowNull()][string[]]$Output = @())

    $counts = [pscustomobject]@{
        files_copied = -1
        files_skipped = -1
    }

    if ($null -eq $Output -or @($Output).Count -eq 0) {
        return $counts
    }

    foreach ($line in $Output) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        if ($line -match '^\s*Files\s*:\s+(\d+)\s+(\d+)\s+(\d+)') {
            $counts.files_copied = [int]$Matches[2]
            $counts.files_skipped = [int]$Matches[3]
            break
        }
    }

    return $counts
}

function Get-AiOsPreviousBackupManifest {
    param(
        [Parameter(Mandatory = $true)][string]$BackupRoot,
        [Parameter(Mandatory = $true)][string]$CurrentSnapshotPath,
        [Nullable[datetime]]$BeforeLocalTime = $null
    )

    if (-not (Test-Path -LiteralPath $BackupRoot -PathType Container)) {
        return $null
    }

    $manifests = @(Get-ChildItem -LiteralPath $BackupRoot -Directory -Filter "AIOS_BACKUP*" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -ine $CurrentSnapshotPath } |
        ForEach-Object {
            $candidate = Join-Path $_.FullName "AIOS_BACKUP_MANIFEST.json"
            if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { return }
            try {
                $manifest = Get-Content -Raw -LiteralPath $candidate | ConvertFrom-Json
                $status = if ($null -ne $manifest.status) { [string]$manifest.status } else { "" }
                if ($status -ne "SUCCESS") { return }
                $createdAt = if ($null -ne $manifest.created_at) { [datetime]$manifest.created_at } else { $_.LastWriteTime }
                if ($null -ne $BeforeLocalTime -and $createdAt -ge $BeforeLocalTime.Value) { return }
                [pscustomobject]@{
                    path = $candidate
                    manifest = $manifest
                    created_at = $createdAt
                }
            } catch {
                return
            }
        } |
        Sort-Object created_at -Descending)

    if (@($manifests).Count -eq 0) { return $null }
    return $manifests[0]
}

function Test-AiOsSuccessfulBackupToday {
    param([Parameter(Mandatory = $true)][string]$BackupRoot)

    if (-not (Test-Path -LiteralPath $BackupRoot -PathType Container)) {
        return $false
    }

    $today = (Get-Date).Date
    $match = @(Get-ChildItem -LiteralPath $BackupRoot -Directory -Filter "AIOS_BACKUP*" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $candidate = Join-Path $_.FullName "AIOS_BACKUP_MANIFEST.json"
            if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { return }
            try {
                $manifest = Get-Content -Raw -LiteralPath $candidate | ConvertFrom-Json
                $status = if ($null -ne $manifest.status) { [string]$manifest.status } else { "" }
                if ($status -ne "SUCCESS") { return }
                $createdAt = if ($null -ne $manifest.created_at) { [datetime]$manifest.created_at } else { $_.LastWriteTime }
                if ($createdAt -ge $today) { $_.FullName }
            } catch {
                return
            }
        } | Select-Object -First 1)

    return (@($match).Count -gt 0)
}

function Assert-AiOsBackupVolume {
    param([string]$BackupRoot, [object]$Volume, [string]$ExpectedUniqueId = "")
    $root = ConvertTo-AiOsFullPath -Path $BackupRoot
    if ($root -notin @('D:\T9_FOB','T:\AIOS_BACKUPS')) { throw 'BACKUP_ROOT_NOT_APPROVED' }
    if ($null -eq $Volume -or $Volume.FileSystemLabel -ne 'T9_FOB') { throw 'BACKUP_VOLUME_IDENTITY_UNVERIFIED' }
    if ($root -eq 'T:\AIOS_BACKUPS' -and [string]::IsNullOrWhiteSpace($ExpectedUniqueId)) { throw 'BACKUP_VOLUME_UNIQUE_ID_REQUIRED' }
    if ($ExpectedUniqueId -and $Volume.UniqueId -cne $ExpectedUniqueId) { throw 'BACKUP_VOLUME_IDENTITY_MISMATCH' }
}

function Get-AiOsSavedWorkDelta {
    param([string]$RepoRoot, [Parameter(Mandatory=$true)][string[]]$RelativePaths, [hashtable]$PreviousHashes = @{})
    $root = ConvertTo-AiOsFullPath -Path $RepoRoot
    $copy = New-Object System.Collections.Generic.List[string]
    $deleted = New-Object System.Collections.Generic.List[string]
    $hashes = @{}
    $seen = @{}
    foreach ($relative in $RelativePaths) {
        $key = $relative.Replace('\','/')
        if ([string]::IsNullOrWhiteSpace($key) -or [IO.Path]::IsPathRooted($key) -or $key -match '(^|/)\.\.(/|$)' -or $seen.ContainsKey($key)) { throw 'SAVED_WORK_SCOPE_INVALID' }
        $seen[$key] = $true
        if (Test-AiOsRelativePathExcluded -RelativePath $key -ExcludedFolderNames @('.git','.aios','.codex','.agents','.venv','venv','node_modules','snapshots','current_mirror','AIOS_BACKUP*','secrets','credentials') -ExcludedFilePatterns @('.env','*.env','.env.*','*.local.json','*secret*','*credential*','*.key','*.pem','*.pfx','*.p12','id_rsa','id_ed25519')) { throw 'SAVED_WORK_PATH_EXCLUDED' }
        $full = ConvertTo-AiOsFullPath -Path (Join-Path $root $key)
        if (-not (Test-AiOsPathInside -ChildPath $full -ParentPath $root)) { throw 'SAVED_WORK_PATH_ESCAPED' }
        $cursor = $full
        while ($cursor -and $cursor -ne $root) {
            if ((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'SAVED_WORK_REPARSE_POINT' }
            $cursor = [IO.Path]::GetDirectoryName($cursor)
        }
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
            if ($PreviousHashes.ContainsKey($key) -and -not (Test-Path -LiteralPath $full)) { $deleted.Add($key); continue }
            throw 'SAVED_WORK_FILE_SCOPE_UNRESOLVED'
        }
        $hash = (Get-FileHash -LiteralPath $full -Algorithm SHA256 -ErrorAction Stop).Hash
        $hashes[$key] = $hash
        if (-not $PreviousHashes.ContainsKey($key) -or $PreviousHashes[$key] -cne $hash) { $copy.Add($key) }
    }
    return [pscustomobject]@{ copy_files=@($copy); deleted_files=@($deleted); file_hashes=$hashes }
}

function Write-AiOsPendingBackupDrive {
    param([string]$Path, [string]$EventId, [string]$BackupRoot)
    if ([string]::IsNullOrWhiteSpace($EventId)) { throw 'PENDING_BACKUP_EVENT_ID_REQUIRED' }
    $revision = 1
    if (Test-Path -LiteralPath $Path) {
        $existing = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -ErrorAction Stop
        if ($existing.event_id -eq $EventId -and $existing.status -eq 'PENDING_DRIVE') { return $existing }
        if ($existing.event_id -ne $EventId -or $existing.status -ne 'COMPLETED') { throw 'PENDING_BACKUP_EVENT_REQUIRES_RECONCILIATION' }
        $revision = [int]$existing.revision + 1
    }
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path)) | Out-Null
    $record = [ordered]@{schema='AIOS_BACKUP_PENDING_DRIVE.v1';event_id=$EventId;revision=$revision;status='PENDING_DRIVE';backup_root=$BackupRoot;created_utc=[DateTime]::UtcNow.ToString('o');delivery_confirmed=$false;next_action='Connect and verify the approved T9; retain the last successful checkpoint.'}
    $bytes = [Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json)+"`n")
    $temporary = $Path + '.' + [guid]::NewGuid().ToString('N') + '.pending'
    $stream = [IO.File]::Open($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporary,$Path,[NullString]::Value) } else { [IO.File]::Move($temporary,$Path) }
    return [pscustomobject]$record
}

function Complete-AiOsPendingBackupDrive {
    param([string]$Path, [string]$EventId, [string]$ManifestPath, [string]$AllowedBackupRoot = "")
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $pending = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -ErrorAction Stop
    if ($pending.event_id -ne $EventId -or $pending.status -notin @('PENDING_DRIVE','COMPLETED')) { throw 'PENDING_BACKUP_EVENT_REQUIRES_RECONCILIATION' }
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ($manifest.status -ne 'SUCCESS' -or @($manifest.saved_work_checkpoint).Count -eq 0) { throw 'SAVED_WORK_PROOF_MISSING' }
    if (-not $AllowedBackupRoot) { $AllowedBackupRoot = [IO.Path]::GetDirectoryName($ManifestPath) }
    foreach ($entry in $manifest.saved_work_checkpoint) {
        if (-not (Test-AiOsPathInside -ChildPath (ConvertTo-AiOsFullPath $entry.backup_file) -ParentPath (ConvertTo-AiOsFullPath $AllowedBackupRoot)) -or (Get-FileHash -LiteralPath $entry.backup_file -Algorithm SHA256 -ErrorAction Stop).Hash -cne $entry.sha256) { throw 'SAVED_WORK_PROOF_INVALID' }
    }
    if ($pending.status -eq 'COMPLETED') { return }
    $pending.status = 'COMPLETED'
    $pending | Add-Member -NotePropertyName verified_manifest -NotePropertyValue $ManifestPath
    $bytes = [Text.Encoding]::UTF8.GetBytes(($pending | ConvertTo-Json)+"`n")
    $temporary = $Path + '.' + [guid]::NewGuid().ToString('N') + '.complete'
    [IO.File]::WriteAllBytes($temporary,$bytes)
    [IO.File]::Replace($temporary,$Path,[NullString]::Value)
}

function Get-AiOsGitDeltaFiles {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$PreviousCommit,
        [Parameter(Mandatory = $true)][string]$CurrentCommit
    )

    $empty = [pscustomobject]@{
        source_range = ""
        changed_files = @()
        deleted_files = @()
        copy_files = @()
    }

    if ([string]::IsNullOrWhiteSpace($PreviousCommit) -or [string]::IsNullOrWhiteSpace($CurrentCommit) -or $PreviousCommit -eq $CurrentCommit) {
        return $empty
    }

    $range = "{0}..{1}" -f $PreviousCommit, $CurrentCommit
    $nameStatusLines = @(git -C $RepoRoot diff --name-status $range)
    if ($LASTEXITCODE -ne 0) {
        return $empty
    }

    $changed = New-Object System.Collections.Generic.List[string]
    $deleted = New-Object System.Collections.Generic.List[string]
    $copy = New-Object System.Collections.Generic.List[string]

    foreach ($line in $nameStatusLines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split "`t"
        $status = [string]$parts[0]
        $relPath = if ($status.StartsWith("R") -and $parts.Count -ge 3) { [string]$parts[2] } elseif ($parts.Count -ge 2) { [string]$parts[1] } else { "" }
        if ([string]::IsNullOrWhiteSpace($relPath)) { continue }
        $relPath = $relPath.Replace("/", "\")

        if ($status -eq "D") {
            $deleted.Add($relPath)
            continue
        }

        $tracked = @(git -C $RepoRoot ls-files -- $relPath)
        if ($LASTEXITCODE -eq 0 -and @($tracked).Count -gt 0) {
            $changed.Add($relPath)
            $fullPath = Join-Path $RepoRoot $relPath
            if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
                $copy.Add($relPath)
            }
        }
    }

    return [pscustomobject]@{
        source_range = $range
        changed_files = @($changed)
        deleted_files = @($deleted)
        copy_files = @($copy)
    }
}

function Select-AiOsBackupMode {
    param(
        [Parameter(Mandatory = $true)][string]$RequestedMode,
        [AllowNull()]$PreviousManifest,
        [Parameter(Mandatory = $true)][bool]$HasSuccessfulBackupToday,
        [Parameter(Mandatory = $true)][object]$GitInfo,
        [Parameter(Mandatory = $true)][object]$ProductivityDelta
    )

    if ($RequestedMode -ne "Auto") {
        return [pscustomobject]@{
            mode = $RequestedMode
            reason = "Operator requested $RequestedMode mode."
        }
    }

    if ($null -eq $PreviousManifest) {
        return [pscustomobject]@{ mode = "Full"; reason = "No prior successful backup manifest found." }
    }

    if (-not $HasSuccessfulBackupToday) {
        return [pscustomobject]@{ mode = "Full"; reason = "First successful backup of the local day." }
    }

    if ([string]$ProductivityDelta.previous_backup_commit_hash -eq [string]$GitInfo.commit_hash) {
        return [pscustomobject]@{ mode = "ManifestOnly"; reason = "Current commit already matches the previous backup commit." }
    }

    if ([int]$ProductivityDelta.productivity_delta_files -gt 0 -and [int64]$ProductivityDelta.productivity_delta_bytes -le 52428800) {
        return [pscustomobject]@{ mode = "Delta"; reason = "Productive delta exists and is below the 50 MB delta threshold." }
    }

    return [pscustomobject]@{ mode = "Full"; reason = "Productive delta is large or cannot be safely represented as a small delta." }
}

function Get-AiOsRetentionPreviewCandidates {
    param([Parameter(Mandatory = $true)][string]$BackupRoot)

    if (-not (Test-Path -LiteralPath $BackupRoot -PathType Container)) {
        return @()
    }

    $records = @(Get-ChildItem -LiteralPath $BackupRoot -Directory -Filter "AIOS_BACKUP*" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $manifestPath = Join-Path $_.FullName "AIOS_BACKUP_MANIFEST.json"
            if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { return }
            try {
                $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
                if ([string]$manifest.status -ne "SUCCESS") { return }
                $mode = if ($manifest.PSObject.Properties.Name -contains "backup_mode") { [string]$manifest.backup_mode } else { "Full" }
                $createdAt = if ($null -ne $manifest.created_at) { [datetime]$manifest.created_at } else { $_.LastWriteTime }
                [pscustomobject]@{
                    backup_id = if ($null -ne $manifest.backup_id) { [string]$manifest.backup_id } else { $_.Name }
                    path = $_.FullName
                    manifest_path = $manifestPath
                    backup_mode = $mode
                    created_at = $createdAt
                    local_date = $createdAt.ToString("yyyy-MM-dd")
                }
            } catch {
                return
            }
        } | Sort-Object created_at -Descending)

    $fullBackups = @($records | Where-Object { $_.backup_mode -eq "Full" })
    $keep = New-Object System.Collections.Generic.HashSet[string]
    @($fullBackups | Select-Object -First 3) | ForEach-Object { [void]$keep.Add($_.backup_id) }
    $fullBackups | Group-Object local_date | ForEach-Object {
        $firstOfDay = @($_.Group | Sort-Object created_at | Select-Object -First 1)
        if (@($firstOfDay).Count -gt 0) { [void]$keep.Add($firstOfDay[0].backup_id) }
    }

    return @($fullBackups | Where-Object { -not $keep.Contains($_.backup_id) } | ForEach-Object {
        [pscustomobject]@{
            backup_id = $_.backup_id
            path = $_.path
            reason = "Older duplicate full snapshot; retention preview only."
        }
    })
}

function Copy-AiOsDeltaFiles {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$DestinationRoot,
        [Parameter(Mandatory = $true)][string[]]$RelativePaths,
        [hashtable]$ExpectedHashes = @{}
    )

    foreach ($relPath in $RelativePaths) {
        $source = Join-Path $RepoRoot $relPath
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'DELTA_SOURCE_MISSING' }
        $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256 -ErrorAction Stop).Hash
        $key = $relPath.Replace('\','/')
        if ($ExpectedHashes.Count -gt 0 -and (-not $ExpectedHashes.ContainsKey($key) -or $ExpectedHashes[$key] -cne $sourceHash)) { throw 'DELTA_SOURCE_CHANGED_AFTER_PLAN' }
        $destination = Join-Path $DestinationRoot $relPath
        if (Test-Path -LiteralPath $destination) { throw 'DELTA_DESTINATION_EXISTS' }
        $destinationParent = Split-Path -Parent $destination
        if (-not (Test-Path -LiteralPath $destinationParent -PathType Container)) {
            New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
        }
        $staging=$destination+'.partial.'+[guid]::NewGuid().ToString('N')
        Copy-Item -LiteralPath $source -Destination $staging -ErrorAction Stop
        if ((Get-FileHash -LiteralPath $staging -Algorithm SHA256).Hash -cne $sourceHash -or (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -cne $sourceHash) { throw 'DELTA_COPY_HASH_MISMATCH' }
        [IO.File]::Move($staging,$destination)
    }
}

function Get-AiOsGitDeltaStats {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$PreviousCommit,
        [Parameter(Mandatory = $true)][string]$CurrentCommit
    )

    $empty = [pscustomobject]@{
        files = 0
        new_files = 0
        changed_files = 0
        deleted_files = 0
        bytes = 0L
        commits = 0
        pr_merges = 0
        pr_merge_subjects = @()
    }
    if ([string]::IsNullOrWhiteSpace($PreviousCommit) -or [string]::IsNullOrWhiteSpace($CurrentCommit) -or $PreviousCommit -eq $CurrentCommit) {
        return $empty
    }

    $range = "{0}..{1}" -f $PreviousCommit, $CurrentCommit
    $commitCountText = (git -C $RepoRoot rev-list --count $range).Trim()
    if ($LASTEXITCODE -ne 0) { return $empty }

    $mergeSubjects = @(git -C $RepoRoot log --merges --grep "Merge pull request" --format=%s $range)
    if ($LASTEXITCODE -ne 0) { $mergeSubjects = @() }

    $nameStatusLines = @(git -C $RepoRoot diff --name-status $range)
    if ($LASTEXITCODE -ne 0) { return $empty }

    $newFiles = 0
    $changedFiles = 0
    $deletedFiles = 0
    $deltaBytes = [int64]0
    foreach ($line in $nameStatusLines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split "`t"
        $status = [string]$parts[0]
        $currentRelPath = if ($status.StartsWith("R") -and $parts.Count -ge 3) { [string]$parts[2] } elseif ($parts.Count -ge 2) { [string]$parts[1] } else { "" }

        if ($status -eq "D") {
            $deletedFiles++
            continue
        } elseif ($status -eq "A") {
            $newFiles++
        } else {
            $changedFiles++
        }

        if (-not [string]::IsNullOrWhiteSpace($currentRelPath)) {
            $fullPath = Join-Path $RepoRoot $currentRelPath
            if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
                $deltaBytes += (Get-Item -LiteralPath $fullPath).Length
            }
        }
    }

    return [pscustomobject]@{
        files = @($nameStatusLines).Count
        new_files = $newFiles
        changed_files = $changedFiles
        deleted_files = $deletedFiles
        bytes = $deltaBytes
        commits = [int]$commitCountText
        pr_merges = @($mergeSubjects).Count
        pr_merge_subjects = @($mergeSubjects)
    }
}

function Get-AiOsBackupProductivityDelta {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$BackupRoot,
        [Parameter(Mandatory = $true)][string]$CurrentSnapshotPath,
        [Parameter(Mandatory = $true)][object]$GitInfo,
        [Parameter(Mandatory = $true)][string[]]$ExcludedDirs
    )

    $previous = Get-AiOsPreviousBackupManifest -BackupRoot $BackupRoot -CurrentSnapshotPath $CurrentSnapshotPath
    $todayBase = Get-AiOsPreviousBackupManifest -BackupRoot $BackupRoot -CurrentSnapshotPath $CurrentSnapshotPath -BeforeLocalTime (Get-Date).Date
    $previousCommit = if ($null -ne $previous -and $null -ne $previous.manifest.commit_hash) { [string]$previous.manifest.commit_hash } else { "" }
    $todayCommit = if ($null -ne $todayBase -and $null -ne $todayBase.manifest.commit_hash) { [string]$todayBase.manifest.commit_hash } else { "" }

    $delta = Get-AiOsGitDeltaStats -RepoRoot $RepoRoot -PreviousCommit $previousCommit -CurrentCommit ([string]$GitInfo.commit_hash)
    $todayDelta = if ([string]::IsNullOrWhiteSpace($todayCommit)) { $null } else { Get-AiOsGitDeltaStats -RepoRoot $RepoRoot -PreviousCommit $todayCommit -CurrentCommit ([string]$GitInfo.commit_hash) }
    $signal = Get-AiOsBackupProductivitySignal -HasPreviousBackup ($null -ne $previous) `
        -Commits ([int]$delta.commits) `
        -Files ([int]$delta.files) `
        -Bytes ([int64]$delta.bytes) `
        -PrMerges ([int]$delta.pr_merges)
    $runtimeNames = @("relay\logs", "relay\running", "relay\done", "relay\error", "telemetry", "Reports")
    $runtimeExcluded = @($runtimeNames | Where-Object {
        $runtimeName = $_
        @($ExcludedDirs | Where-Object { $_ -like "*$runtimeName*" }).Count -gt 0
    }).Count -eq $runtimeNames.Count

    return [pscustomobject]@{
        previous_backup_manifest_path = if ($null -ne $previous) { [string]$previous.path } else { "" }
        previous_backup_id = if ($null -ne $previous -and $null -ne $previous.manifest.backup_id) { [string]$previous.manifest.backup_id } else { "" }
        previous_backup_commit_hash = $previousCommit
        productivity_delta_files = [int]$delta.files
        productivity_delta_new_files = [int]$delta.new_files
        productivity_delta_changed_files = [int]$delta.changed_files
        productivity_delta_deleted_files = [int]$delta.deleted_files
        productivity_delta_bytes = [int64]$delta.bytes
        productivity_delta_human = Format-AiOsBytes -Bytes ([double]$delta.bytes)
        productivity_delta_commits = [int]$delta.commits
        productivity_delta_pr_merges = [int]$delta.pr_merges
        productivity_delta_pr_merge_subjects = @($delta.pr_merge_subjects)
        productivity_delta_today_files = if ($null -eq $todayDelta) { "UNKNOWN" } else { [int]$todayDelta.files }
        productivity_delta_today_bytes = if ($null -eq $todayDelta) { "UNKNOWN" } else { [int64]$todayDelta.bytes }
        productivity_delta_today_human = if ($null -eq $todayDelta) { "UNKNOWN" } else { Format-AiOsBytes -Bytes ([double]$todayDelta.bytes) }
        runtime_files_excluded = [bool]$runtimeExcluded
        runtime_exclusion_status = if ($runtimeExcluded) { "FULL" } else { "PARTIAL" }
        productivity_delta_signal_score = $signal.score
        productivity_delta_progress_bar = $signal.bar
        productivity_delta_progress_label = $signal.label
        productivity_delta_summary = "Productivity delta: $($delta.files) files / $(Format-AiOsBytes -Bytes ([double]$delta.bytes)) / $($delta.commits) commits since last backup."
    }
}

function Get-AiOsBackupProductivitySignal {
    param(
        [Parameter(Mandatory = $true)][bool]$HasPreviousBackup,
        [Parameter(Mandatory = $true)][int]$Commits,
        [Parameter(Mandatory = $true)][int]$Files,
        [Parameter(Mandatory = $true)][int64]$Bytes,
        [Parameter(Mandatory = $true)][int]$PrMerges
    )

    if (-not $HasPreviousBackup) {
        return [pscustomobject]@{
            score = "UNKNOWN"
            bar = "UNKNOWN"
            label = "UNKNOWN"
        }
    }

    $signals = 0
    if ($Commits -gt 0) { $signals++ }
    if ($Files -gt 0) { $signals++ }
    if ($Bytes -gt 0) { $signals++ }
    if ($PrMerges -gt 0) { $signals++ }

    $score = [Math]::Min(100, $signals * 25)
    $filled = [Math]::Min(10, [int]($score / 10))
    $empty = 10 - $filled
    $bar = ("█" * $filled) + ("░" * $empty)

    return [pscustomobject]@{
        score = $score
        bar = $bar
        label = "$score%"
    }
}

function Add-AiOsProductivityFields {
    param(
        [Parameter(Mandatory = $true)][object]$Target,
        [Parameter(Mandatory = $true)][object]$ProductivityDelta
    )

    foreach ($property in $ProductivityDelta.PSObject.Properties) {
        $Target | Add-Member -NotePropertyName $property.Name -NotePropertyValue $property.Value -Force
    }
}

function Write-AiOsBackupProductivityOutput {
    param(
        [Parameter(Mandatory = $true)][object]$ProductivityDelta,
        [Parameter(Mandatory = $true)][string]$CopiedHuman,
        [int]$ChangedCopied = 0,
        [int]$DeletedRecorded = 0,
        [bool]$RestoreRequiresFullBackup = $false,
        [int]$RetentionCandidateCount = 0
    )

    if ([string]$ProductivityDelta.productivity_delta_progress_label -eq "UNKNOWN") {
        Write-Host "Backup productivity bar: UNKNOWN"
    } else {
        Write-Host "Backup productivity bar: $($ProductivityDelta.productivity_delta_progress_bar) $($ProductivityDelta.productivity_delta_progress_label)"
    }
    Write-Host "Backup total copied: $CopiedHuman"
    Write-Host $ProductivityDelta.productivity_delta_summary
    Write-Host "Changed files copied: $ChangedCopied"
    Write-Host "Deleted files recorded: $DeletedRecorded"
    Write-Host "Restore requires full backup: $(if ($RestoreRequiresFullBackup) { 'YES' } else { 'NO' })"
    if ($RetentionPreview) {
        Write-Host "Retention preview candidates: $RetentionCandidateCount"
    }
    Write-Host "PR merges included: $($ProductivityDelta.productivity_delta_pr_merges)"
    Write-Host "Runtime exclusion status: $($ProductivityDelta.runtime_exclusion_status)"
}

function New-AiOsBackupResult {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][string]$Message,
        [int]$RobocopyExitCode = -1,
        [int]$ExitCode = 0,
        [int64]$CopiedBytes = 0,
        [int]$CopiedFilesCount = 0,
        [int]$FailedFilesCount = 0,
        [int]$FailedDirsCount = 0,
        [string]$FullSnapshotOrIncremental = ""
    )

    $workDelta = if ($null -eq $script:backupWorkDelta) {
        Get-AiOsBackupWorkDeltaReport -RepoRoot $normalizedSource -BaseCommit "" -CurrentCommit "" -TimeslotLabel $BackupTimeslotLabel -WindowStartLocal $BackupWindowStart -WindowEndLocal $BackupWindowEnd
    } else {
        $script:backupWorkDelta
    }
    $robocopyExitForMetrics = if ($RobocopyExitCode -lt 0) { $null } else { [int]$RobocopyExitCode }
    $snapshotKind = if ([string]::IsNullOrWhiteSpace($FullSnapshotOrIncremental)) { $retentionClass } else { $FullSnapshotOrIncremental }
    $copiedMetrics = New-AiOsBackupCopiedMetrics -BackupMode $selectedBackupMode `
        -BackupRoot $normalizedBackupRoot `
        -Destination $snapshotPath `
        -RobocopyExit $robocopyExitForMetrics `
        -CopiedFilesCount $CopiedFilesCount `
        -CopiedBytes $CopiedBytes `
        -FailedFilesCount $FailedFilesCount `
        -FailedDirsCount $FailedDirsCount `
        -ExcludedPaths $excludedDirs `
        -ExcludedSecretPatterns $excludedFilePatterns `
        -FullSnapshotOrIncremental $snapshotKind
    $courtesySos = New-AiOsBackupCourtesySos -Status $Status `
        -TimeslotLabel $workDelta.backup_timeslot_label `
        -CopiedMetrics $copiedMetrics `
        -DevWorkDeltaMetrics $workDelta.dev_work_delta_metrics `
        -DailyWorkMetrics $workDelta.daily_work_metrics `
        -BaseCommit $workDelta.dev_work_delta_metrics.base_commit `
        -CurrentCommit $workDelta.current_commit `
        -Destination $snapshotPath `
        -RobocopyExit $robocopyExitForMetrics `
        -FailedFilesCount $FailedFilesCount `
        -FailedDirsCount $FailedDirsCount `
        -LogPath $robocopyLogPath `
        -Failure:($Status -match '^(FAILED|FAILURE|ERROR|BLOCKED)$')

    return [pscustomobject]@{
        schema = "AIOS_T9_SNAPSHOT_BACKUP.v1"
        mode = if ($Preview) { "PREVIEW" } else { "APPLY" }
        status = $Status
        message = $Message
        backup_timeslot_label = $workDelta.backup_timeslot_label
        backup_timeslot_local = $workDelta.backup_timeslot_local
        backup_window_start = $workDelta.backup_window_start
        backup_window_end = $workDelta.backup_window_end
        last_successful_backup_commit = $workDelta.last_successful_backup_commit
        current_commit = $workDelta.current_commit
        source_repo = $normalizedSource
        backup_root = $normalizedBackupRoot
        snapshot_name = $snapshotName
        snapshot_path = $snapshotPath
        recursion_guard_enabled = [bool]$recursionGuard.recursion_guard_enabled
        source_full_path = $recursionGuard.source_full_path
        backup_root_full_path = $recursionGuard.backup_root_full_path
        snapshot_path_full_path = $recursionGuard.snapshot_path_full_path
        excluded_folder_names = @($recursionGuard.excluded_folder_names)
        backup_root_inside_source = [bool]$recursionGuard.backup_root_inside_source
        source_inside_backup_root = [bool]$recursionGuard.source_inside_backup_root
        snapshot_inside_source = [bool]$recursionGuard.snapshot_inside_source
        recursive_backup_detected = [bool]$recursionGuard.recursive_backup_detected
        recursive_backup_reason = $recursionGuard.recursive_backup_reason
        safe_to_copy = [bool]$recursionGuard.safe_to_copy
        backup_mode = $selectedBackupMode
        requested_backup_mode = $BackupMode
        selected_backup_mode_reason = $selectedBackupModeReason
        excluded_paths = $excludedDirs
        excluded_file_patterns = $excludedFilePatterns
        robocopy_exit_code = $RobocopyExitCode
        exit_code = $ExitCode
        mutation_scope = if ($Preview) { "NONE" } elseif ($selectedBackupMode -eq "ManifestOnly") { "BACKUP_MANIFEST_ONLY" } else { "BACKUP_SNAPSHOT_ONLY" }
        active_repo_mutation = "NO"
        scheduler_behavior = "NO"
        runtime_mutation = if ($Preview) { "NO" } else { "BACKUP_DESTINATION_ONLY" }
        allow_dirty = [bool]$AllowDirty
        self_validation_dirty_allowed = [bool]$backupSelfValidationDirtyAllowed
        backup_report_root = $backupReportRoot
        lock_path = $backupLockPath
        backup_lock_path = $backupLockPath
        robocopy_log_path = $robocopyLogPath
        manifest_path = $manifestPath
        base_backup_id = $baseBackupId
        base_backup_commit_hash = $baseBackupCommitHash
        changed_files = @($changedFiles)
        deleted_files = @($deletedFiles)
        file_count_copied = [int]$fileCountCopied
        delta_source_range = $deltaSourceRange
        restore_requires_full_backup = [bool]$restoreRequiresFullBackup
        retention_class = $retentionClass
        retention_preview_candidates = @($retentionPreviewCandidates)
        backup_copied_metrics = $copiedMetrics
        dev_work_delta_metrics = $workDelta.dev_work_delta_metrics
        daily_work_metrics = $workDelta.daily_work_metrics
        timeslot_work_metrics = $workDelta.timeslot_work_metrics
        courtesy_sos = $courtesySos
        generated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    }
}

function Set-AiOsBackupWindow {
    # Shrink the console to just fit the banner/text, matching the other worker windows.
    try {
        $rawUi = $Host.UI.RawUI
        $targetWidth = 92
        $targetHeight = 34

        $buffer = $rawUi.BufferSize
        $buffer.Width = $targetWidth
        $buffer.Height = [Math]::Max(300, $buffer.Height)
        $rawUi.BufferSize = $buffer

        $window = $rawUi.WindowSize
        $window.Width = [Math]::Min($targetWidth, $rawUi.MaxWindowSize.Width)
        $window.Height = [Math]::Min($targetHeight, $rawUi.MaxWindowSize.Height)
        $rawUi.WindowSize = $window
    } catch {
        # Non-interactive hosts may reject sizing; the backup still runs.
    }
}

function Write-AiOsBackupManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][int]$RobocopyExitCode,
        [Parameter(Mandatory = $true)][object]$GitInfo,
        [Parameter(Mandatory = $true)][object]$GitStatus,
        [AllowEmptyCollection()][AllowNull()][object[]]$ProtectedLocks = @(),
        [Parameter(Mandatory = $true)][object]$ProductivityDelta,
        [int64]$CopiedBytes = 0,
        [string]$CopiedHuman = "0.00 B",
        [string[]]$ChangedFiles = @(),
        [string[]]$DeletedFiles = @(),
        [int]$FileCountCopied = 0,
        [string]$DeltaSourceRange = "",
        [string]$BaseBackupId = "",
        [string]$BaseBackupCommitHash = "",
        [bool]$RestoreRequiresFullBackup = $false,
        [string]$RetentionClass = "",
        [object[]]$RetentionPreviewCandidates = @(),
        [Parameter(Mandatory = $true)][string]$Message,
        [object[]]$SavedWorkCheckpoint = @()
    )

    $protectedLocksForManifest = if ($null -eq $ProtectedLocks) { @() } else { @($ProtectedLocks) }
    $workDelta = if ($null -eq $script:backupWorkDelta) {
        Get-AiOsBackupWorkDeltaReport -RepoRoot $normalizedSource -BaseCommit $BaseBackupCommitHash -CurrentCommit $GitInfo.commit_hash -TimeslotLabel $BackupTimeslotLabel -WindowStartLocal $BackupWindowStart -WindowEndLocal $BackupWindowEnd
    } else {
        $script:backupWorkDelta
    }
    $robocopyExitForMetrics = if ($RobocopyExitCode -lt 0) { $null } else { [int]$RobocopyExitCode }
    $copiedMetrics = New-AiOsBackupCopiedMetrics -BackupMode $selectedBackupMode `
        -BackupRoot $normalizedBackupRoot `
        -Destination $snapshotPath `
        -RobocopyExit $robocopyExitForMetrics `
        -CopiedFilesCount $FileCountCopied `
        -CopiedBytes $CopiedBytes `
        -FailedFilesCount $(if ($RobocopyExitCode -ge 8) { -1 } else { 0 }) `
        -FailedDirsCount 0 `
        -ExcludedPaths $excludedDirs `
        -ExcludedSecretPatterns $excludedFilePatterns `
        -FullSnapshotOrIncremental $RetentionClass
    $courtesySos = New-AiOsBackupCourtesySos -Status $Status `
        -TimeslotLabel $workDelta.backup_timeslot_label `
        -CopiedMetrics $copiedMetrics `
        -DevWorkDeltaMetrics $workDelta.dev_work_delta_metrics `
        -DailyWorkMetrics $workDelta.daily_work_metrics `
        -BaseCommit $workDelta.dev_work_delta_metrics.base_commit `
        -CurrentCommit $workDelta.current_commit `
        -Destination $snapshotPath `
        -RobocopyExit $robocopyExitForMetrics `
        -FailedFilesCount $(if ($RobocopyExitCode -ge 8) { -1 } else { 0 }) `
        -FailedDirsCount 0 `
        -LogPath $robocopyLogPath `
        -Failure:($Status -match '^(FAILED|FAILURE|ERROR|BLOCKED)$')

    $manifest = [ordered]@{
        schema = "AIOS_T9_SNAPSHOT_BACKUP_MANIFEST.v1"
        backup_id = $snapshotName
        created_at = (Get-Date).ToString("o")
        backup_timeslot_label = $workDelta.backup_timeslot_label
        backup_timeslot_local = $workDelta.backup_timeslot_local
        backup_window_start = $workDelta.backup_window_start
        backup_window_end = $workDelta.backup_window_end
        last_successful_backup_commit = $workDelta.last_successful_backup_commit
        current_commit = $workDelta.current_commit
        source_path = $normalizedSource
        destination_path = $snapshotPath
        branch = $GitInfo.branch
        commit_hash = $GitInfo.commit_hash
        commit_short = $GitInfo.commit_short
        git_status = @($GitStatus.lines)
        git_status_clean = [bool]$GitStatus.is_clean
        allow_dirty = [bool]$AllowDirty
        self_validation_dirty_allowed = [bool]$backupSelfValidationDirtyAllowed
        robocopy_exit_code = $RobocopyExitCode
        status = $Status
        message = $Message
        backup_mode = $selectedBackupMode
        requested_backup_mode = $BackupMode
        selected_backup_mode_reason = $selectedBackupModeReason
        base_backup_id = $BaseBackupId
        base_backup_commit_hash = $BaseBackupCommitHash
        changed_files = @($ChangedFiles)
        saved_work_checkpoint = @($SavedWorkCheckpoint)
        deleted_files = @($DeletedFiles)
        file_count_copied = $FileCountCopied
        delta_source_range = $DeltaSourceRange
        restore_requires_full_backup = [bool]$RestoreRequiresFullBackup
        retention_class = $RetentionClass
        retention_preview_candidates = @($RetentionPreviewCandidates)
        excluded_dirs = @($excludedDirs)
        excluded_file_patterns = @($excludedFilePatterns)
        recursion_guard = $recursionGuard
        robocopy_log_path = $robocopyLogPath
        backup_report_root = $backupReportRoot
        backup_lock_path = $backupLockPath
        protected_action_locks_found = $protectedLocksForManifest
        copied_bytes = $CopiedBytes
        copied_human = $CopiedHuman
        backup_copied_metrics = $copiedMetrics
        dev_work_delta_metrics = $workDelta.dev_work_delta_metrics
        daily_work_metrics = $workDelta.daily_work_metrics
        timeslot_work_metrics = $workDelta.timeslot_work_metrics
        courtesy_sos = $courtesySos
        operator = "Anthony"
        script = $PSCommandPath
    }
    foreach ($property in $ProductivityDelta.PSObject.Properties) {
        $manifest[$property.Name] = $property.Value
    }

    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}

if ($VerifiedScopeCheckpointPath -or $VerifiedArchiveManifestPath) {
    if ($BackupMode -ne 'Delta' -or -not $VerifiedScopeCheckpointPath -or -not $VerifiedArchiveManifestPath -or -not $IncrementalStateRoot -or -not $ExpectedVolumeUniqueId) { throw 'VERIFIED_ARCHIVE_DELTA_CONFIGURATION_REQUIRED' }
    $archiveResult = Invoke-AiOsVerifiedArchiveIncremental -ScopeCheckpoint $VerifiedScopeCheckpointPath -ArchiveManifest $VerifiedArchiveManifestPath -BackupRoot $BackupRoot -VolumeUniqueId $ExpectedVolumeUniqueId -StateRoot $IncrementalStateRoot -PolicyReceipt $VerifiedPolicyReceiptPath -Preview:$Preview
    $archiveResult | ConvertTo-Json -Depth 8
    if ($archiveResult.status -in @('SUCCESS','PREVIEW')) { exit 0 } else { exit 2 }
}
$expectedSource = "C:\Dev\Ai.Os"
$expectedBackupRoot = ConvertTo-AiOsFullPath -Path $BackupRoot
if ($expectedBackupRoot -notin @('D:\T9_FOB','T:\AIOS_BACKUPS')) { throw 'BACKUP_ROOT_NOT_APPROVED' }
$savedWorkMode = @($SavedWorkFiles).Count -gt 0
$SavedWorkFiles = @($SavedWorkFiles | ForEach-Object { $_.Replace('\','/') })
if ($savedWorkMode -and $BackupMode -ne 'Delta') { throw 'SAVED_WORK_REQUIRES_EXPLICIT_DELTA_NO_FULL_FALLBACK' }
$savedWorkPlan = $null
$savedWorkLocations = @{}
$savedWorkCheckpoint = @()
$normalizedSource = ConvertTo-AiOsFullPath -Path $SourceRepo
$normalizedBackupRoot = ConvertTo-AiOsFullPath -Path $BackupRoot
$backupWorkDelta = $null
$selectedBackupMode = $BackupMode
$selectedBackupModeReason = "not selected yet"
$baseBackupId = ""
$baseBackupCommitHash = ""
$changedFiles = @()
$deletedFiles = @()
$deltaSourceRange = ""
$restoreRequiresFullBackup = $false
$retentionClass = "UNKNOWN"
$retentionPreviewCandidates = @()
$fileCountCopied = 0
$sourceFullPath = $normalizedSource
$backupRootFullPath = $normalizedBackupRoot
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$snapshotName = "AIOS_BACKUP_$timestamp"
$snapshotPath = ConvertTo-AiOsFullPath -Path ([IO.Path]::Combine($normalizedBackupRoot,$snapshotName))
$snapshotPathFullPath = $snapshotPath
$preferredBackupReportRoot = [IO.Path]::Combine($normalizedBackupRoot,"backup_reports")
$fallbackBackupReportRoot = Join-Path ([System.IO.Path]::GetTempPath()) "AIOS_T9_BACKUP"
$backupReportRoot = Resolve-AiOsBackupReportRoot -PreferredRoot $preferredBackupReportRoot -FallbackRoot $fallbackBackupReportRoot -SourceRoot $normalizedSource
$backupLockPath = [IO.Path]::Combine($backupReportRoot,"AIOS_BACKUP_IN_PROGRESS.lock")
$robocopyLogPath = [IO.Path]::Combine($snapshotPath,"AIOS_BACKUP_ROBOCOPY.log")
$manifestPath = [IO.Path]::Combine($snapshotPath,"AIOS_BACKUP_MANIFEST.json")
$pendingDrivePath = [IO.Path]::Combine($fallbackBackupReportRoot,'PENDING_SAVED_WORK_BACKUP.json')
$pendingDriveEvent = $normalizedSource + '|' + $normalizedBackupRoot + '|' + (@($SavedWorkFiles | Sort-Object) -join '|')
$excludedFolderNames = @(
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".codex_backups",
    "current_mirror",
    "snapshots",
    "AIOS_BACKUP*",
    "T9_FOB",
    "AI_OS backup mirror",
    "secrets",
    "credentials"
)
$excludedFilePatterns = @(
    ".env",
    "*.env",
    ".env.*",
    "*secret*",
    "*secrets*",
    "*credential*",
    "*credentials*",
    "*.key",
    "*.pem",
    "id_rsa",
    "id_ed25519",
    "*.pfx",
    "*.p12"
)
$excludedDirs = @(
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".codex_backups",
    "current_mirror",
    "snapshots",
    "secrets",
    "credentials"
)
$recursionGuard = [pscustomobject]@{
    recursion_guard_enabled = $true
    source_full_path = $sourceFullPath
    backup_root_full_path = $backupRootFullPath
    snapshot_path_full_path = $snapshotPathFullPath
    excluded_folder_names = @($excludedFolderNames)
    backup_root_inside_source = $false
    source_inside_backup_root = $false
    snapshot_inside_source = $false
    recursive_backup_detected = $false
    recursive_backup_reason = "NOT_EVALUATED"
    safe_to_copy = $false
    source_equals_backup_root = $false
    source_equals_snapshot_path = $false
    backup_root_approved = $false
    candidate_copy_source_contains_backup_root = $false
    candidate_copy_source_contains_backup_pattern = $false
}
$selectedBackupMode = $BackupMode
$selectedBackupModeReason = "Mode has not been selected yet."
$baseBackupId = ""
$baseBackupCommitHash = ""
$changedFiles = @()
$deletedFiles = @()
$fileCountCopied = 0
$deltaSourceRange = ""
$restoreRequiresFullBackup = $false
$retentionClass = ""
$retentionPreviewCandidates = @()
$backupSelfValidationDirtyAllowed = $false

try {
    if (-not $OutputJson) {
        Set-AiOsBackupWindow
        $identityScript = Join-Path $PSScriptRoot "..\..\automation\window_identity\Set-AiOsWindowIdentity.ps1"
        if (Test-Path -LiteralPath $identityScript) {
            & $identityScript -Marker "T9 BACKUP"
        }
    }

    $recursionGuard = Test-AiOsBackupRecursionGuard -SourceFullPath $sourceFullPath `
        -BackupRootFullPath $backupRootFullPath `
        -SnapshotPathFullPath $snapshotPathFullPath `
        -ApprovedBackupRootFullPath $expectedBackupRoot `
        -CandidateCopySourcePaths @($sourceFullPath) `
        -ExcludedFolderNames $excludedFolderNames
    if (-not $recursionGuard.safe_to_copy) {
        throw "RECURSIVE_BACKUP_BLOCKED: $($recursionGuard.recursive_backup_reason)"
    }

    if ($normalizedSource -ne $expectedSource) {
        throw "Source repo must be exactly $expectedSource."
    }

    if ($normalizedBackupRoot -ne $expectedBackupRoot) {
        throw "Backup root must be exactly $expectedBackupRoot."
    }

    if (-not (Test-Path -LiteralPath $normalizedSource -PathType Container)) {
        throw "Source repo does not exist: $normalizedSource"
    }

    $driveLetter = [IO.Path]::GetPathRoot($normalizedBackupRoot).Substring(0,1)
    $volume = Get-Volume -DriveLetter $driveLetter -ErrorAction SilentlyContinue
    if ($null -eq $volume -and $savedWorkMode) {
        if ($Preview) { [pscustomobject]@{status='PENDING_DRIVE';mutation='NONE';telegram_delivery_verified=$false} | ConvertTo-Json; exit 2 }
        Write-AiOsPendingBackupDrive -Path $pendingDrivePath -EventId $pendingDriveEvent -BackupRoot $normalizedBackupRoot | ConvertTo-Json
        exit 2
    }
    Assert-AiOsBackupVolume -BackupRoot $normalizedBackupRoot -Volume $volume -ExpectedUniqueId $ExpectedVolumeUniqueId
    if (-not (Test-Path -LiteralPath $normalizedBackupRoot -PathType Container)) { throw "Backup root does not exist: $normalizedBackupRoot" }

    if (Test-Path -LiteralPath $snapshotPath) {
        throw "Snapshot destination already exists: $snapshotPath"
    }

    # New-AiOsBackupLock owns the OS handle and validates any persisted prior owner.

    $gitStatus = Get-AiOsGitStatus -Path $normalizedSource
    $gitInfo = Get-AiOsGitInfo -Path $normalizedSource
    $productivityDelta = Get-AiOsBackupProductivityDelta -RepoRoot $normalizedSource -BackupRoot $normalizedBackupRoot -CurrentSnapshotPath $snapshotPath -GitInfo $gitInfo -ExcludedDirs $excludedDirs
    $previousManifest = Get-AiOsPreviousBackupManifest -BackupRoot $normalizedBackupRoot -CurrentSnapshotPath $snapshotPath
    $hasSuccessfulBackupToday = Test-AiOsSuccessfulBackupToday -BackupRoot $normalizedBackupRoot
    if ($null -ne $previousManifest) {
        $baseBackupId = if ($null -ne $previousManifest.manifest.backup_id) { [string]$previousManifest.manifest.backup_id } else { "" }
        $baseBackupCommitHash = if ($null -ne $previousManifest.manifest.commit_hash) { [string]$previousManifest.manifest.commit_hash } else { "" }
    }
    $deltaInfo = if ($savedWorkMode) { [pscustomobject]@{copy_files=@();deleted_files=@();source_range='EXPLICIT_SAVED_WORK_HASH_SCOPE'} } else { Get-AiOsGitDeltaFiles -RepoRoot $normalizedSource -PreviousCommit $baseBackupCommitHash -CurrentCommit ([string]$gitInfo.commit_hash) }
    $changedFiles = @($deltaInfo.copy_files | Where-Object {
        -not (Test-AiOsRelativePathExcluded -RelativePath $_ -ExcludedFolderNames $excludedFolderNames -ExcludedFilePatterns $excludedFilePatterns)
    })
    $deletedFiles = @($deltaInfo.deleted_files)
    $deltaSourceRange = [string]$deltaInfo.source_range
    if ($savedWorkMode) {
        $baselineHashes = @{}
        if ($null -ne $previousManifest -and $previousManifest.manifest.PSObject.Properties.Name -contains 'saved_work_checkpoint') {
            foreach ($entry in @($previousManifest.manifest.saved_work_checkpoint)) {
                if ($entry.relative_path -notin $SavedWorkFiles) { continue }
                if (-not (Test-AiOsPathInside -ChildPath (ConvertTo-AiOsFullPath $entry.backup_file) -ParentPath $normalizedBackupRoot) -or (Get-FileHash -LiteralPath $entry.backup_file -Algorithm SHA256 -ErrorAction Stop).Hash -cne $entry.sha256) { throw 'SAVED_WORK_BASELINE_UNVERIFIED' }
                $baselineHashes[$entry.relative_path] = $entry.sha256
                $savedWorkLocations[$entry.relative_path] = $entry.backup_file
            }
        }
        $savedWorkPlan = Get-AiOsSavedWorkDelta -RepoRoot $normalizedSource -RelativePaths $SavedWorkFiles -PreviousHashes $baselineHashes
        $changedFiles = @($savedWorkPlan.copy_files)
        $deletedFiles = @($savedWorkPlan.deleted_files)
        $deltaSourceRange = 'EXPLICIT_SAVED_WORK_HASH_SCOPE'
        if ($changedFiles.Count -eq 0 -and $deletedFiles.Count -eq 0) {
            if (-not $Preview -and $null -ne $previousManifest) { Complete-AiOsPendingBackupDrive -Path $pendingDrivePath -EventId $pendingDriveEvent -ManifestPath $previousManifest.path -AllowedBackupRoot $normalizedBackupRoot }
            [pscustomobject]@{status='NO_CHANGES';backup_mode='Delta';files_copied=0;full_copy=$false} | ConvertTo-Json
            exit 0
        }
    }
    $backupWorkDelta = Get-AiOsBackupWorkDeltaReport -RepoRoot $normalizedSource `
        -BaseCommit $baseBackupCommitHash `
        -CurrentCommit ([string]$gitInfo.commit_hash) `
        -TimeslotLabel $BackupTimeslotLabel `
        -WindowStartLocal $BackupWindowStart `
        -WindowEndLocal $BackupWindowEnd `
        -TimeslotBaseCommit $baseBackupCommitHash `
        -LastSuccessfulBackupCommit $baseBackupCommitHash
    $selection = Select-AiOsBackupMode -RequestedMode $BackupMode -PreviousManifest $previousManifest -HasSuccessfulBackupToday $hasSuccessfulBackupToday -GitInfo $gitInfo -ProductivityDelta $productivityDelta
    $selectedBackupMode = [string]$selection.mode
    $selectedBackupModeReason = [string]$selection.reason
    $restoreRequiresFullBackup = ($selectedBackupMode -eq "Delta" -and -not $savedWorkMode)
    $retentionClass = if ($selectedBackupMode -eq "Full") { "FULL_SNAPSHOT" } elseif ($selectedBackupMode -eq "Delta") { "DELTA_SNAPSHOT" } else { "MANIFEST_ONLY" }
    $retentionPreviewCandidates = if ($RetentionPreview) { @(Get-AiOsRetentionPreviewCandidates -BackupRoot $normalizedBackupRoot) } else { @() }

    if ($selectedBackupMode -eq "Full") {
        $snapshotName = "AIOS_BACKUP_$timestamp"
    } else {
        $snapshotName = "AIOS_BACKUP_{0}_{1}" -f $timestamp, $selectedBackupMode.ToUpperInvariant()
    }
    $snapshotPath = ConvertTo-AiOsFullPath -Path (Join-Path $normalizedBackupRoot $snapshotName)
    $snapshotPathFullPath = $snapshotPath
    $robocopyLogPath = Join-Path $snapshotPath "AIOS_BACKUP_ROBOCOPY.log"
    $manifestPath = Join-Path $snapshotPath "AIOS_BACKUP_MANIFEST.json"

    $candidateCopySourcePaths = New-Object System.Collections.Generic.List[string]
    $candidateCopySourcePaths.Add($normalizedSource)
    foreach ($relPath in $changedFiles) {
        if (-not [string]::IsNullOrWhiteSpace($relPath)) {
            $candidateCopySourcePaths.Add((Join-Path $normalizedSource $relPath))
        }
    }
    $recursionGuard = Test-AiOsBackupRecursionGuard -SourceFullPath $sourceFullPath `
        -BackupRootFullPath $backupRootFullPath `
        -SnapshotPathFullPath $snapshotPathFullPath `
        -ApprovedBackupRootFullPath $expectedBackupRoot `
        -CandidateCopySourcePaths @($candidateCopySourcePaths) `
        -ExcludedFolderNames $excludedFolderNames
    if (-not $recursionGuard.safe_to_copy) {
        throw "RECURSIVE_BACKUP_BLOCKED: $($recursionGuard.recursive_backup_reason)"
    }

    if ($selectedBackupMode -eq "Delta" -and -not $savedWorkMode -and [string]::IsNullOrWhiteSpace($baseBackupCommitHash)) {
        throw "Delta mode requires a prior successful backup manifest with commit_hash."
    }

    $protectedLocks = @(Get-AiOsProtectedActionLocks -RepoRoot $normalizedSource -BackupReportRoot $backupReportRoot -BackupLockPath $backupLockPath)
    if (@($protectedLocks).Count -gt 0) {
        throw "PROTECTED_ACTION_LOCK_EXISTS: $($protectedLocks.path -join ', ')"
    }

    if (-not $Preview -and -not $AllowDirty -and -not $gitStatus.is_clean) {
        if (Test-AiOsBackupSelfValidationDirtyState -GitStatus $gitStatus) {
            $backupSelfValidationDirtyAllowed = $true
        } else {
            throw "DIRTY_REPO: Backup requires clean git status. Re-run with -AllowDirty only after explicit approval. Status: $($gitStatus.lines -join ' | ')"
        }
    }

    $plannedCommand = if ($selectedBackupMode -eq "ManifestOnly") {
        @("Write manifest only to `"$manifestPath`"")
    } elseif ($selectedBackupMode -eq "Delta") {
        @("Copy tracked changed files only to `"$snapshotPath`"", "range=$deltaSourceRange", "files=$(@($changedFiles).Count)")
    } else {
        @(
            "robocopy",
            "`"$normalizedSource`"",
            "`"$snapshotPath`"",
            "/E",
            "/XJ",
            "/R:1",
            "/W:1",
            "/NFL",
            "/NDL",
            "/NP",
            "/LOG:`"$robocopyLogPath`"",
            "/TEE",
            "/XD"
        ) + ($excludedDirs | ForEach-Object { "`"$_`"" }) + @("/XF") + ($excludedFilePatterns | ForEach-Object { "`"$_`"" })
    }

    $excludeNames = @($excludedFolderNames)

    if ($Preview) {
        $sourceBytes = Get-AiOsDirectorySize -Path $normalizedSource -ExcludeNames $excludeNames -ExcludeFilePatterns $excludedFilePatterns
        $destBytes = Get-AiOsDirectorySize -Path $normalizedBackupRoot

        $result = New-AiOsBackupResult -Status "PREVIEW" -Message "Preview only. No folder was created, no lock was created, and robocopy was not run." -CopiedBytes 0 -CopiedFilesCount 0 -FullSnapshotOrIncremental "PREVIEW_$retentionClass"
        $result | Add-Member -NotePropertyName planned_command -NotePropertyValue ($plannedCommand -join " ")
        $result | Add-Member -NotePropertyName source_bytes -NotePropertyValue ([long]$sourceBytes)
        $result | Add-Member -NotePropertyName dest_bytes -NotePropertyValue ([long]$destBytes)
        $result | Add-Member -NotePropertyName copied_bytes -NotePropertyValue 0
        $result | Add-Member -NotePropertyName copied_human -NotePropertyValue "0.00 B"
        $result | Add-Member -NotePropertyName source_human -NotePropertyValue (Format-AiOsBytes -Bytes $sourceBytes)
        $result | Add-Member -NotePropertyName dest_human -NotePropertyValue (Format-AiOsBytes -Bytes $destBytes)
        $result | Add-Member -NotePropertyName git_status_clean -NotePropertyValue ([bool]$gitStatus.is_clean)
        $result | Add-Member -NotePropertyName protected_action_lock_count -NotePropertyValue ([int]@($protectedLocks).Count)
        $result | Add-Member -NotePropertyName retention_preview_status -NotePropertyValue $(if ($RetentionPreview) { "RETENTION_PREVIEW_ONLY" } else { "NOT_REQUESTED" })
        Add-AiOsProductivityFields -Target $result -ProductivityDelta $productivityDelta
        if ($OutputJson) {
            $result | ConvertTo-Json -Depth 6
        }
        else {
            Write-Host "AI_OS T9 Snapshot Backup Preview"
            Write-Host "Backup mode: $selectedBackupMode"
            Write-Host "Selected reason: $selectedBackupModeReason"
            if ($RetentionPreview) { Write-Host "RETENTION_PREVIEW_ONLY" }
            Write-Host "Source: $normalizedSource"
            Write-Host "Backup root: $normalizedBackupRoot"
            Write-Host "Snapshot path: $snapshotPath"
            Write-Host "Backup lock path: $backupLockPath"
            Write-Host "Robocopy log path: $robocopyLogPath"
            Write-Host "Manifest path: $manifestPath"
            Write-Host "Git status clean: $($gitStatus.is_clean)"
            Write-Host "Protected-action locks found: $(@($protectedLocks).Count)"
            Write-Host "Recursion guard enabled: $($recursionGuard.recursion_guard_enabled)"
            Write-Host "Recursion guard passed: $($recursionGuard.safe_to_copy)"
            Write-Host "Recursive backup detected: $($recursionGuard.recursive_backup_detected)"
            Write-Host "Recursive backup reason: $($recursionGuard.recursive_backup_reason)"
            Write-Host "Excluded folder names:"
            $excludedFolderNames | ForEach-Object { Write-Host "  - $_" }
            Write-Host "Excluded paths:"
            $excludedDirs | ForEach-Object { Write-Host "  - $_" }
            Write-Host "Excluded file patterns:"
            $excludedFilePatterns | ForEach-Object { Write-Host "  - $_" }
            Write-Host ""
            Write-Host "Source data measured:        $(Format-AiOsBytes -Bytes $sourceBytes)"
            Write-Host "Current backup size (T9):    $(Format-AiOsBytes -Bytes $destBytes)"
            Write-Host "Copied this run:             0.00 B (preview - no copy run)"
            Write-Host "Skipped (already current):   pending (preview - robocopy not run)"
            Write-Host "Produced this backup session: 0.00 B (preview - no copy run)"
            Write-Host ""
            Write-AiOsBackupProductivityOutput -ProductivityDelta $productivityDelta -CopiedHuman "0.00 B" -ChangedCopied @($changedFiles).Count -DeletedRecorded @($deletedFiles).Count -RestoreRequiresFullBackup $restoreRequiresFullBackup -RetentionCandidateCount @($retentionPreviewCandidates).Count
            if ($productivityDelta.productivity_delta_today_files -eq "UNKNOWN") {
                Write-Host "Productivity delta today: UNKNOWN"
            } else {
                Write-Host "Productivity delta today: $($productivityDelta.productivity_delta_today_files) files / $($productivityDelta.productivity_delta_today_human)"
            }
            Write-Host ""
            Write-Host "Planned command:"
            Write-Host ($plannedCommand -join " ")
            Write-Host "No folder was created. No lock was created. Robocopy was not run."
        }
        exit 0
    }

    if ($selectedBackupMode -eq "ManifestOnly") {
        $lockCreated = $false
        try {
            New-AiOsBackupLock -BackupReportRoot $backupReportRoot -BackupLockPath $backupLockPath -SourcePath $normalizedSource -SnapshotPath $snapshotPath
            $lockCreated = $true
            New-Item -ItemType Directory -Path $snapshotPath | Out-Null
            $sourceBytes = Get-AiOsDirectorySize -Path $normalizedSource -ExcludeNames $excludeNames -ExcludeFilePatterns $excludedFilePatterns
            $destBytes = Get-AiOsDirectorySize -Path $normalizedBackupRoot
            $copiedHuman = "0.00 B"
            $manifestMessage = "Manifest-only checkpoint created. No files were copied."

            Write-AiOsBackupManifest -Path $manifestPath -Status "SUCCESS" -RobocopyExitCode 0 -GitInfo $gitInfo -GitStatus $gitStatus -ProtectedLocks $protectedLocks -ProductivityDelta $productivityDelta -CopiedBytes 0 -CopiedHuman $copiedHuman -ChangedFiles $changedFiles -DeletedFiles $deletedFiles -FileCountCopied 0 -DeltaSourceRange $deltaSourceRange -BaseBackupId $baseBackupId -BaseBackupCommitHash $baseBackupCommitHash -RestoreRequiresFullBackup $false -RetentionClass $retentionClass -RetentionPreviewCandidates $retentionPreviewCandidates -Message $manifestMessage

            $finalSnapshotBytes = Get-AiOsDirectorySize -Path $snapshotPath
            $result = New-AiOsBackupResult -Status "SUCCESS" -Message $manifestMessage -RobocopyExitCode 0 -ExitCode 0 -CopiedBytes 0 -CopiedFilesCount 0 -FullSnapshotOrIncremental $retentionClass
            $result | Add-Member -NotePropertyName source_bytes -NotePropertyValue ([long]$sourceBytes)
            $result | Add-Member -NotePropertyName dest_bytes -NotePropertyValue ([long]$destBytes)
            $result | Add-Member -NotePropertyName copied_bytes -NotePropertyValue 0
            $result | Add-Member -NotePropertyName final_snapshot_bytes -NotePropertyValue ([long]$finalSnapshotBytes)
            $result | Add-Member -NotePropertyName files_copied -NotePropertyValue 0
            $result | Add-Member -NotePropertyName files_skipped -NotePropertyValue -1
            $result | Add-Member -NotePropertyName source_human -NotePropertyValue (Format-AiOsBytes -Bytes $sourceBytes)
            $result | Add-Member -NotePropertyName dest_human -NotePropertyValue (Format-AiOsBytes -Bytes $destBytes)
            $result | Add-Member -NotePropertyName copied_human -NotePropertyValue $copiedHuman
            $result | Add-Member -NotePropertyName final_snapshot_human -NotePropertyValue (Format-AiOsBytes -Bytes $finalSnapshotBytes)
            Add-AiOsProductivityFields -Target $result -ProductivityDelta $productivityDelta

            if ($OutputJson) {
                $result | ConvertTo-Json -Depth 6
            } else {
                Write-Host "AI_OS T9 Snapshot Backup"
                Write-Host "Status: SUCCESS"
                Write-Host "Backup mode: $selectedBackupMode"
                Write-Host "Selected reason: $selectedBackupModeReason"
                Write-Host "Source size: $(Format-AiOsBytes -Bytes $sourceBytes)"
                Write-Host "Snapshot path: $snapshotPath"
                Write-Host "Robocopy exit code: 0"
                Write-Host "File count copied: 0"
                Write-Host "Byte count copied: 0"
                Write-Host "Final snapshot size: $(Format-AiOsBytes -Bytes $finalSnapshotBytes)"
                Write-Host "Manifest path: $manifestPath"
                Write-Host "Lock path: $backupLockPath"
                Write-AiOsBackupProductivityOutput -ProductivityDelta $productivityDelta -CopiedHuman $copiedHuman -ChangedCopied 0 -DeletedRecorded @($deletedFiles).Count -RestoreRequiresFullBackup $false -RetentionCandidateCount @($retentionPreviewCandidates).Count
                Write-Host "Active repo mutation: NO"
                Write-Host "active_repo_mutation = NO"
                Write-Host "Scheduler behavior: NO"
                Write-Host "Runtime mutation: BACKUP_DESTINATION_ONLY"
            }
            exit 0
        }
        finally {
            if ($lockCreated) {
                Remove-AiOsBackupLock -BackupLockPath $backupLockPath
            }
        }
    }

    if ($selectedBackupMode -eq "Delta") {
        $lockCreated = $false
        try {
            New-AiOsBackupLock -BackupReportRoot $backupReportRoot -BackupLockPath $backupLockPath -SourcePath $normalizedSource -SnapshotPath $snapshotPath
            $lockCreated = $true
            $sourceBytes = if ($savedWorkMode) { [long](($changedFiles | ForEach-Object { (Get-Item -LiteralPath (Join-Path $normalizedSource $_)).Length } | Measure-Object -Sum).Sum) } else { Get-AiOsDirectorySize -Path $normalizedSource -ExcludeNames $excludeNames -ExcludeFilePatterns $excludedFilePatterns }
            $destBytesBefore = if ($savedWorkMode) { -1L } else { Get-AiOsDirectorySize -Path $normalizedBackupRoot }
            New-Item -ItemType Directory -Path $snapshotPath | Out-Null
            $expectedHashes = if ($savedWorkMode) { $savedWorkPlan.file_hashes } else { @{} }
            Copy-AiOsDeltaFiles -RepoRoot $normalizedSource -DestinationRoot $snapshotPath -RelativePaths $changedFiles -ExpectedHashes $expectedHashes
            if ($savedWorkMode) {
                foreach ($file in $changedFiles) { $savedWorkLocations[$file] = Join-Path $snapshotPath $file }
                $savedWorkCheckpoint = @(foreach ($file in $savedWorkPlan.file_hashes.Keys | Sort-Object) { [pscustomobject]@{relative_path=$file;sha256=$savedWorkPlan.file_hashes[$file];backup_file=$savedWorkLocations[$file]} })
            }
            $copiedBytes = Get-AiOsDirectorySize -Path $snapshotPath
            $destBytesAfter = if ($savedWorkMode) { -1L } else { $destBytesBefore + $copiedBytes }
            $fileCountCopied = @($changedFiles).Count
            $copiedHuman = Format-AiOsBytes -Bytes $copiedBytes
            $manifestMessage = if ($savedWorkMode) { 'Explicit saved-work delta hash-verified; whole-project/destination sizes not scanned.' } else { 'Delta snapshot created from tracked changed files only.' }

            Write-AiOsBackupManifest -Path $manifestPath -Status "SUCCESS" -RobocopyExitCode 0 -GitInfo $gitInfo -GitStatus $gitStatus -ProtectedLocks $protectedLocks -ProductivityDelta $productivityDelta -CopiedBytes ([long]$copiedBytes) -CopiedHuman $copiedHuman -ChangedFiles $changedFiles -DeletedFiles $deletedFiles -FileCountCopied $fileCountCopied -DeltaSourceRange $deltaSourceRange -BaseBackupId $baseBackupId -BaseBackupCommitHash $baseBackupCommitHash -RestoreRequiresFullBackup (-not $savedWorkMode) -RetentionClass $retentionClass -RetentionPreviewCandidates $retentionPreviewCandidates -Message $manifestMessage -SavedWorkCheckpoint $savedWorkCheckpoint
            if ($savedWorkMode) { Complete-AiOsPendingBackupDrive -Path $pendingDrivePath -EventId $pendingDriveEvent -ManifestPath $manifestPath -AllowedBackupRoot $normalizedBackupRoot }

            $finalSnapshotBytes = Get-AiOsDirectorySize -Path $snapshotPath
            $result = New-AiOsBackupResult -Status "SUCCESS" -Message $manifestMessage -RobocopyExitCode 0 -ExitCode 0 -CopiedBytes ([long]$copiedBytes) -CopiedFilesCount $fileCountCopied -FullSnapshotOrIncremental $retentionClass
            $result | Add-Member -NotePropertyName source_bytes -NotePropertyValue ([long]$sourceBytes)
            $result | Add-Member -NotePropertyName dest_bytes -NotePropertyValue ([long]$destBytesAfter)
            $result | Add-Member -NotePropertyName copied_bytes -NotePropertyValue ([long]$copiedBytes)
            $result | Add-Member -NotePropertyName final_snapshot_bytes -NotePropertyValue ([long]$finalSnapshotBytes)
            $result | Add-Member -NotePropertyName files_copied -NotePropertyValue $fileCountCopied
            $result | Add-Member -NotePropertyName files_skipped -NotePropertyValue -1
            $result | Add-Member -NotePropertyName source_human -NotePropertyValue (Format-AiOsBytes -Bytes $sourceBytes)
            $result | Add-Member -NotePropertyName dest_human -NotePropertyValue (Format-AiOsBytes -Bytes $destBytesAfter)
            $result | Add-Member -NotePropertyName copied_human -NotePropertyValue $copiedHuman
            $result | Add-Member -NotePropertyName final_snapshot_human -NotePropertyValue (Format-AiOsBytes -Bytes $finalSnapshotBytes)
            Add-AiOsProductivityFields -Target $result -ProductivityDelta $productivityDelta

            if ($OutputJson) {
                $result | ConvertTo-Json -Depth 6
            } else {
                Write-Host "AI_OS T9 Snapshot Backup"
                Write-Host "Status: SUCCESS"
                Write-Host "Backup mode: $selectedBackupMode"
                Write-Host "Selected reason: $selectedBackupModeReason"
                Write-Host "Source size: $(Format-AiOsBytes -Bytes $sourceBytes)"
                Write-Host "Snapshot path: $snapshotPath"
                Write-Host "Robocopy exit code: 0"
                Write-Host "File count copied: $fileCountCopied"
                Write-Host "Byte count copied: $copiedBytes"
                Write-Host "Final snapshot size: $(Format-AiOsBytes -Bytes $finalSnapshotBytes)"
                Write-Host "Manifest path: $manifestPath"
                Write-Host "Lock path: $backupLockPath"
                Write-AiOsBackupProductivityOutput -ProductivityDelta $productivityDelta -CopiedHuman $copiedHuman -ChangedCopied @($changedFiles).Count -DeletedRecorded @($deletedFiles).Count -RestoreRequiresFullBackup $restoreRequiresFullBackup -RetentionCandidateCount @($retentionPreviewCandidates).Count
                Write-Host "Active repo mutation: NO"
                Write-Host "active_repo_mutation = NO"
                Write-Host "Scheduler behavior: NO"
                Write-Host "Runtime mutation: BACKUP_DESTINATION_ONLY"
            }
            exit 0
        }
        finally {
            if ($lockCreated) {
                Remove-AiOsBackupLock -BackupLockPath $backupLockPath
            }
        }
    }

    $lockCreated = $false
    try {
        New-AiOsBackupLock -BackupReportRoot $backupReportRoot -BackupLockPath $backupLockPath -SourcePath $normalizedSource -SnapshotPath $snapshotPath
        $lockCreated = $true

        # Measured before the snapshot is created so it reflects existing T9 backups.
        $sourceBytes = Get-AiOsDirectorySize -Path $normalizedSource -ExcludeNames $excludeNames -ExcludeFilePatterns $excludedFilePatterns
        $destBytesBefore = Get-AiOsDirectorySize -Path $normalizedBackupRoot

        New-Item -ItemType Directory -Path $snapshotPath | Out-Null

        Write-Host ""
        Write-Host "Source data measured:        $(Format-AiOsBytes -Bytes $sourceBytes)"
        Write-Host "Copying to: $snapshotPath"
        Write-Host ""

        $robocopyArgs = @(
            $normalizedSource,
            $snapshotPath,
            "/E",
            "/XJ",
            "/R:1",
            "/W:1",
            "/NFL",
            "/NDL",
            "/NP",
            "/LOG:$robocopyLogPath",
            "/TEE",
            "/XD"
        ) + $excludedDirs + @("/XF") + $excludedFilePatterns

        $robocopyOutput = @(& robocopy @robocopyArgs 2>&1)
        $robocopyExitCode = $LASTEXITCODE
        $robocopyOutput | ForEach-Object { Write-Host $_ }

        $robocopyLines = @($robocopyOutput | ForEach-Object {
            if ($null -eq $_) {
                ""
            } else {
                "$_"
            }
        })
        $counts = Get-AiOsRobocopyCounts -Output $robocopyLines
        $copiedBytes = Get-AiOsDirectorySize -Path $snapshotPath
        $destBytesAfter = $destBytesBefore + $copiedBytes

        $copiedCountText = if ($counts.files_copied -ge 0) { "{0:N0} files" -f $counts.files_copied } else { "count unavailable" }
        $skippedCountText = if ($counts.files_skipped -ge 0) { "{0:N0} files" -f $counts.files_skipped } else { "count unavailable" }
        $fileCountCopied = if ($counts.files_copied -ge 0) { [int]$counts.files_copied } else { 0 }

        Write-Host ""
        Write-Host "Source data measured:        $(Format-AiOsBytes -Bytes $sourceBytes)"
        Write-Host "Current backup size (T9):    $(Format-AiOsBytes -Bytes $destBytesAfter)"
        Write-Host "Copied this run:             $copiedCountText / $(Format-AiOsBytes -Bytes $copiedBytes)"
        Write-Host "Skipped (already current):   $skippedCountText"
        Write-Host "Produced this backup session: $(Format-AiOsBytes -Bytes $copiedBytes)"
        Write-Host ""
        $copiedHuman = Format-AiOsBytes -Bytes $copiedBytes
        Write-AiOsBackupProductivityOutput -ProductivityDelta $productivityDelta -CopiedHuman $copiedHuman -ChangedCopied $fileCountCopied -DeletedRecorded @($deletedFiles).Count -RestoreRequiresFullBackup $false -RetentionCandidateCount @($retentionPreviewCandidates).Count
        if ($productivityDelta.productivity_delta_today_files -eq "UNKNOWN") {
            Write-Host "Productivity delta today: UNKNOWN"
        } else {
            Write-Host "Productivity delta today: $($productivityDelta.productivity_delta_today_files) files / $($productivityDelta.productivity_delta_today_human)"
        }
        Write-Host ""

        $majorPaths = @(
            "automation\orchestration",
            "docs\workflows",
            "schemas\aios\orchestration",
            "services\python_supervisor",
            "telemetry"
        )

        $missingPaths = @($majorPaths | Where-Object {
            -not (Test-Path -LiteralPath (Join-Path $snapshotPath $_))
        })

        $manifestStatus = "SUCCESS"
        $manifestMessage = "Backup snapshot created and verified."
        $exitCode = 0
        if ($robocopyExitCode -lt 0 -or $robocopyExitCode -ge 8) {
            $manifestStatus = "FAILED"
            $manifestMessage = "Robocopy reported a failure."
            $exitCode = $robocopyExitCode
        } elseif (@($missingPaths).Count -gt 0) {
            $manifestStatus = "FAILED"
            $manifestMessage = "Snapshot verification failed. Missing expected paths: $($missingPaths -join ', ')."
            $exitCode = 9
        }

        Write-AiOsBackupManifest -Path $manifestPath -Status $manifestStatus -RobocopyExitCode $robocopyExitCode -GitInfo $gitInfo -GitStatus $gitStatus -ProtectedLocks $protectedLocks -ProductivityDelta $productivityDelta -CopiedBytes ([long]$copiedBytes) -CopiedHuman $copiedHuman -ChangedFiles $changedFiles -DeletedFiles $deletedFiles -FileCountCopied $fileCountCopied -DeltaSourceRange $deltaSourceRange -BaseBackupId $baseBackupId -BaseBackupCommitHash $baseBackupCommitHash -RestoreRequiresFullBackup $false -RetentionClass $retentionClass -RetentionPreviewCandidates $retentionPreviewCandidates -Message $manifestMessage

        $finalSnapshotBytes = Get-AiOsDirectorySize -Path $snapshotPath
        $result = New-AiOsBackupResult -Status $manifestStatus -Message $manifestMessage -RobocopyExitCode $robocopyExitCode -ExitCode $exitCode -CopiedBytes ([long]$copiedBytes) -CopiedFilesCount $fileCountCopied -FailedFilesCount $(if ($robocopyExitCode -ge 8) { -1 } else { 0 }) -FailedDirsCount 0 -FullSnapshotOrIncremental $retentionClass
        $result | Add-Member -NotePropertyName source_bytes -NotePropertyValue ([long]$sourceBytes)
        $result | Add-Member -NotePropertyName dest_bytes -NotePropertyValue ([long]$destBytesAfter)
        $result | Add-Member -NotePropertyName copied_bytes -NotePropertyValue ([long]$copiedBytes)
        $result | Add-Member -NotePropertyName final_snapshot_bytes -NotePropertyValue ([long]$finalSnapshotBytes)
        $result | Add-Member -NotePropertyName files_copied -NotePropertyValue $fileCountCopied
        $result | Add-Member -NotePropertyName files_skipped -NotePropertyValue ([int]$counts.files_skipped)
        $result | Add-Member -NotePropertyName source_human -NotePropertyValue (Format-AiOsBytes -Bytes $sourceBytes)
        $result | Add-Member -NotePropertyName dest_human -NotePropertyValue (Format-AiOsBytes -Bytes $destBytesAfter)
        $result | Add-Member -NotePropertyName copied_human -NotePropertyValue $copiedHuman
        $result | Add-Member -NotePropertyName final_snapshot_human -NotePropertyValue (Format-AiOsBytes -Bytes $finalSnapshotBytes)
        Add-AiOsProductivityFields -Target $result -ProductivityDelta $productivityDelta

        if ($OutputJson) {
            $result | ConvertTo-Json -Depth 6
        }
        else {
            Write-Host "AI_OS T9 Snapshot Backup"
            Write-Host "Status: $manifestStatus"
            Write-Host "Backup mode: $selectedBackupMode"
            Write-Host "Selected reason: $selectedBackupModeReason"
            Write-Host "Source size: $(Format-AiOsBytes -Bytes $sourceBytes)"
            Write-Host "Snapshot path: $snapshotPath"
            Write-Host "Robocopy log path: $robocopyLogPath"
            Write-Host "Manifest path: $manifestPath"
            Write-Host "Robocopy exit code: $robocopyExitCode"
            Write-Host "File count copied: $fileCountCopied"
            Write-Host "Byte count copied: $copiedBytes"
            Write-Host "Final snapshot size: $(Format-AiOsBytes -Bytes $finalSnapshotBytes)"
            Write-Host "Lock path: $backupLockPath"
            Write-Host "Active repo mutation: NO"
            Write-Host "active_repo_mutation = NO"
            Write-Host "Scheduler behavior: NO"
            Write-Host "Runtime mutation: BACKUP_DESTINATION_ONLY"
        }

        exit $exitCode
    }
    finally {
        if ($lockCreated) {
            Remove-AiOsBackupLock -BackupLockPath $backupLockPath
        }
    }
}
catch {
    $result = New-AiOsBackupResult -Status "FAILED" -Message $_.Exception.Message -ExitCode 1
    $result | ConvertTo-Json -Depth 6
    exit 1
}
