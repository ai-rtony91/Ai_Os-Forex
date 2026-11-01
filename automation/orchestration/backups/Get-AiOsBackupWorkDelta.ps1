Set-StrictMode -Version Latest

function ConvertTo-AiOsBackupMetricSize {
    param([Parameter(Mandatory = $true)][int64]$Bytes)

    return [pscustomobject][ordered]@{
        bytes = [int64]$Bytes
        kb = [math]::Round($Bytes / 1KB, 2)
        mb = [math]::Round($Bytes / 1MB, 4)
    }
}

function Get-AiOsRobocopyStatus {
    param([AllowNull()][object]$RobocopyExit)

    if ($null -eq $RobocopyExit) {
        return "NOT_RUN_DRY_RUN"
    }

    $exit = [int]$RobocopyExit
    if ($exit -ge 0 -and $exit -lt 8) {
        return "OK"
    }

    return "FAILED"
}

function New-AiOsBackupCopiedMetrics {
    param(
        [Parameter(Mandatory = $true)][string]$BackupMode,
        [AllowEmptyString()][string]$BackupRoot,
        [AllowEmptyString()][string]$Destination,
        [AllowNull()][object]$RobocopyExit = $null,
        [int]$CopiedFilesCount = 0,
        [int64]$CopiedBytes = 0,
        [int]$FailedFilesCount = 0,
        [int]$FailedDirsCount = 0,
        [string[]]$ExcludedPaths = @(),
        [string[]]$ExcludedSecretPatterns = @(),
        [string]$FullSnapshotOrIncremental = "DRY_RUN_PREVIEW"
    )

    $size = ConvertTo-AiOsBackupMetricSize -Bytes $CopiedBytes
    return [pscustomobject][ordered]@{
        backup_mode = $BackupMode
        backup_root = $BackupRoot
        destination = $Destination
        robocopy_exit = if ($null -eq $RobocopyExit) { $null } else { [int]$RobocopyExit }
        robocopy_status = Get-AiOsRobocopyStatus -RobocopyExit $RobocopyExit
        copied_files_count = [int]$CopiedFilesCount
        copied_bytes = [int64]$CopiedBytes
        copied_kb = $size.kb
        copied_mb = $size.mb
        failed_files_count = [int]$FailedFilesCount
        failed_dirs_count = [int]$FailedDirsCount
        excluded_paths = @($ExcludedPaths)
        excluded_secret_patterns = @($ExcludedSecretPatterns)
        full_snapshot_or_incremental = $FullSnapshotOrIncremental
    }
}

function Invoke-AiOsBackupGit {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $lines = @(& git -C $RepoRoot @Arguments 2>$null)
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference

    return [pscustomobject]@{
        exit_code = [int]$exitCode
        lines = @($lines | ForEach-Object { [string]$_ })
    }
}

function Test-AiOsBackupGitCommit {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [AllowNull()][string]$Commit
    )

    if ([string]::IsNullOrWhiteSpace($Commit)) {
        return $false
    }

    $result = Invoke-AiOsBackupGit -RepoRoot $RepoRoot -Arguments @("cat-file", "-e", "$Commit^{commit}")
    return ($result.exit_code -eq 0)
}

function Get-AiOsBackupGitHead {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    $result = Invoke-AiOsBackupGit -RepoRoot $RepoRoot -Arguments @("rev-parse", "HEAD")
    if ($result.exit_code -ne 0 -or @($result.lines).Count -eq 0) {
        return ""
    }

    return [string]$result.lines[0]
}

function Get-AiOsBackupPrNumbers {
    param([AllowEmptyCollection()][string[]]$Onelines = @())

    $numbers = New-Object System.Collections.Generic.List[string]
    foreach ($line in $Onelines) {
        foreach ($match in [regex]::Matches([string]$line, '(?i)(?:#|PR\s*#?)(\d+)')) {
            $numbers.Add([string]$match.Groups[1].Value) | Out-Null
        }
    }

    return @($numbers | Sort-Object -Unique)
}

function Get-AiOsBackupPatchDeltaBytes {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Range
    )

    $result = Invoke-AiOsBackupGit -RepoRoot $RepoRoot -Arguments @("diff", "--binary", "--no-ext-diff", $Range)
    if ($result.exit_code -ne 0 -or @($result.lines).Count -eq 0) {
        return 0L
    }

    $text = @($result.lines) -join [Environment]::NewLine
    return [int64][System.Text.Encoding]::UTF8.GetByteCount($text)
}

function Get-AiOsBackupTouchedFileBytes {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [AllowEmptyCollection()][string[]]$ChangedFiles = @()
    )

    $total = [int64]0
    foreach ($relativePath in $ChangedFiles) {
        if ([string]::IsNullOrWhiteSpace($relativePath)) {
            continue
        }

        $fullPath = Join-Path $RepoRoot $relativePath
        if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
            $total += [int64](Get-Item -LiteralPath $fullPath).Length
        }
    }

    return $total
}

function Get-AiOsBackupGitDeltaSummary {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [AllowNull()][string]$BaseCommit,
        [AllowNull()][string]$CurrentCommit = ""
    )

    $empty = [pscustomobject][ordered]@{
        available = $false
        baseline_note = "baseline commit missing"
        commits = 0
        onelines = @()
        prs = @()
        changed_files = @()
        insertions = 0
        deletions = 0
        patch_bytes = 0L
        touched_bytes = 0L
    }

    if (-not (Test-AiOsBackupGitCommit -RepoRoot $RepoRoot -Commit $BaseCommit)) {
        return $empty
    }

    if ([string]::IsNullOrWhiteSpace($CurrentCommit)) {
        $empty.baseline_note = "current commit missing"
        return $empty
    }

    if (-not (Test-AiOsBackupGitCommit -RepoRoot $RepoRoot -Commit $CurrentCommit)) {
        $empty.baseline_note = "current commit missing"
        return $empty
    }

    if ($BaseCommit -eq $CurrentCommit) {
        $empty.available = $true
        $empty.baseline_note = "base commit equals current commit"
        return $empty
    }

    $range = "{0}..{1}" -f $BaseCommit, $CurrentCommit
    $logResult = Invoke-AiOsBackupGit -RepoRoot $RepoRoot -Arguments @("log", "--oneline", $range)
    $nameResult = Invoke-AiOsBackupGit -RepoRoot $RepoRoot -Arguments @("diff", "--name-only", $range)
    $numstatResult = Invoke-AiOsBackupGit -RepoRoot $RepoRoot -Arguments @("diff", "--numstat", $range)

    if ($logResult.exit_code -ne 0 -or $nameResult.exit_code -ne 0 -or $numstatResult.exit_code -ne 0) {
        $empty.baseline_note = "git delta command failed"
        return $empty
    }

    $insertions = 0
    $deletions = 0
    foreach ($line in $numstatResult.lines) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $parts = [string]$line -split "`t"
        if ($parts.Count -lt 3) {
            continue
        }

        if ($parts[0] -match '^\d+$') {
            $insertions += [int]$parts[0]
        }

        if ($parts[1] -match '^\d+$') {
            $deletions += [int]$parts[1]
        }
    }

    $changedFiles = @($nameResult.lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $patchBytes = Get-AiOsBackupPatchDeltaBytes -RepoRoot $RepoRoot -Range $range
    $touchedBytes = Get-AiOsBackupTouchedFileBytes -RepoRoot $RepoRoot -ChangedFiles $changedFiles

    return [pscustomobject][ordered]@{
        available = $true
        baseline_note = "available"
        commits = [int]@($logResult.lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
        onelines = @($logResult.lines)
        prs = @(Get-AiOsBackupPrNumbers -Onelines $logResult.lines)
        changed_files = @($changedFiles)
        insertions = [int]$insertions
        deletions = [int]$deletions
        patch_bytes = [int64]$patchBytes
        touched_bytes = [int64]$touchedBytes
    }
}

function New-AiOsDevWorkDeltaMetrics {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [AllowNull()][string]$BaseCommit,
        [AllowNull()][string]$CurrentCommit = ""
    )

    $summary = Get-AiOsBackupGitDeltaSummary -RepoRoot $RepoRoot -BaseCommit $BaseCommit -CurrentCommit $CurrentCommit
    $patchSize = ConvertTo-AiOsBackupMetricSize -Bytes ([int64]$summary.patch_bytes)
    $touchedSize = ConvertTo-AiOsBackupMetricSize -Bytes ([int64]$summary.touched_bytes)

    return [pscustomobject][ordered]@{
        available = [bool]$summary.available
        baseline_note = [string]$summary.baseline_note
        base_commit = if ([string]::IsNullOrWhiteSpace($BaseCommit)) { $null } else { [string]$BaseCommit }
        current_commit = $CurrentCommit
        commits_included_count = [int]$summary.commits
        commits_included_oneline = @($summary.onelines)
        pr_numbers_detected = @($summary.prs)
        changed_files_count = [int]@($summary.changed_files).Count
        insertions = [int]$summary.insertions
        deletions = [int]$summary.deletions
        patch_delta_bytes = [int64]$summary.patch_bytes
        patch_delta_kb = $patchSize.kb
        patch_delta_mb = $patchSize.mb
        touched_changed_file_bytes = [int64]$summary.touched_bytes
        touched_changed_file_kb = $touchedSize.kb
        touched_changed_file_mb = $touchedSize.mb
    }
}

function Get-AiOsBackupDayStartCommit {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [datetime]$DayStart = (Get-Date).Date
    )

    $before = $DayStart.ToString("yyyy-MM-ddTHH:mm:ssK")
    $result = Invoke-AiOsBackupGit -RepoRoot $RepoRoot -Arguments @("rev-list", "-1", "--before=$before", "HEAD")
    if ($result.exit_code -ne 0 -or @($result.lines).Count -eq 0) {
        return ""
    }

    return [string]$result.lines[0]
}

function New-AiOsDailyWorkMetrics {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [AllowNull()][string]$CurrentCommit = "",
        [AllowNull()][string]$DayStartCommit = "",
        [datetime]$LocalDate = (Get-Date).Date
    )

    $base = if ([string]::IsNullOrWhiteSpace($DayStartCommit)) {
        Get-AiOsBackupDayStartCommit -RepoRoot $RepoRoot -DayStart $LocalDate
    } else {
        [string]$DayStartCommit
    }

    $summary = Get-AiOsBackupGitDeltaSummary -RepoRoot $RepoRoot -BaseCommit $base -CurrentCommit $CurrentCommit
    $patchSize = ConvertTo-AiOsBackupMetricSize -Bytes ([int64]$summary.patch_bytes)
    $touchedSize = ConvertTo-AiOsBackupMetricSize -Bytes ([int64]$summary.touched_bytes)

    return [pscustomobject][ordered]@{
        available = [bool]$summary.available
        baseline_note = [string]$summary.baseline_note
        local_date = $LocalDate.ToString("yyyy-MM-dd")
        day_start_commit = if ([string]::IsNullOrWhiteSpace($base)) { $null } else { $base }
        current_commit = $CurrentCommit
        commits_today_count = [int]$summary.commits
        prs_today_detected = @($summary.prs)
        changed_files_today_count = [int]@($summary.changed_files).Count
        insertions_today = [int]$summary.insertions
        deletions_today = [int]$summary.deletions
        patch_delta_today_kb = $patchSize.kb
        patch_delta_today_mb = $patchSize.mb
        touched_changed_file_today_kb = $touchedSize.kb
        touched_changed_file_today_mb = $touchedSize.mb
    }
}

function Resolve-AiOsBackupTimeslotWindow {
    param(
        [string]$TimeslotLabel = "manual",
        [AllowNull()][string]$WindowStartLocal = "",
        [AllowNull()][string]$WindowEndLocal = "",
        [datetime]$Now = (Get-Date)
    )

    $label = if ([string]::IsNullOrWhiteSpace($TimeslotLabel)) { "manual" } else { $TimeslotLabel.Trim() }
    $localDate = $Now.Date
    $parsedEnd = $null
    $normalizedLabel = $label -replace '\s+', ''

    if ($normalizedLabel -match '^(?<hour>\d{1,2})(:(?<minute>\d{2}))?(?<ampm>am|pm)$') {
        $hour = [int]$Matches.hour
        $minute = if (-not $Matches.ContainsKey("minute") -or [string]::IsNullOrWhiteSpace($Matches["minute"])) { 0 } else { [int]$Matches["minute"] }
        $ampm = $Matches.ampm.ToLowerInvariant()
        if ($ampm -eq "pm" -and $hour -lt 12) { $hour += 12 }
        if ($ampm -eq "am" -and $hour -eq 12) { $hour = 0 }
        $parsedEnd = $localDate.AddHours($hour).AddMinutes($minute)
    }

    $windowEnd = if (-not [string]::IsNullOrWhiteSpace($WindowEndLocal)) {
        [datetime]::Parse($WindowEndLocal)
    } elseif ($null -ne $parsedEnd) {
        $parsedEnd
    } else {
        $Now
    }

    $defaultStart = if ($label -match '^(?i)10\s*PM$') {
        $localDate.AddHours(15)
    } else {
        $localDate
    }

    $windowStart = if (-not [string]::IsNullOrWhiteSpace($WindowStartLocal)) {
        [datetime]::Parse($WindowStartLocal)
    } else {
        $defaultStart
    }

    return [pscustomobject][ordered]@{
        timeslot_label = $label
        timeslot_local = $windowEnd.ToString("yyyy-MM-dd HH:mm:ss K")
        window_start_local = $windowStart.ToString("yyyy-MM-dd HH:mm:ss K")
        window_end_local = $windowEnd.ToString("yyyy-MM-dd HH:mm:ss K")
    }
}

function New-AiOsTimeslotWorkMetrics {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [AllowNull()][string]$CurrentCommit = "",
        [Parameter(Mandatory = $true)][string]$TimeslotLabel,
        [Parameter(Mandatory = $true)][string]$WindowStartLocal,
        [Parameter(Mandatory = $true)][string]$WindowEndLocal,
        [AllowNull()][string]$BaseCommit = ""
    )

    $summary = Get-AiOsBackupGitDeltaSummary -RepoRoot $RepoRoot -BaseCommit $BaseCommit -CurrentCommit $CurrentCommit
    $patchSize = ConvertTo-AiOsBackupMetricSize -Bytes ([int64]$summary.patch_bytes)
    $touchedSize = ConvertTo-AiOsBackupMetricSize -Bytes ([int64]$summary.touched_bytes)

    return [pscustomobject][ordered]@{
        available = [bool]$summary.available
        baseline_note = [string]$summary.baseline_note
        timeslot_label = $TimeslotLabel
        window_start_local = $WindowStartLocal
        window_end_local = $WindowEndLocal
        base_commit = if ([string]::IsNullOrWhiteSpace($BaseCommit)) { $null } else { [string]$BaseCommit }
        current_commit = $CurrentCommit
        commits_in_window_count = [int]$summary.commits
        prs_in_window_detected = @($summary.prs)
        changed_files_in_window_count = [int]@($summary.changed_files).Count
        insertions_in_window = [int]$summary.insertions
        deletions_in_window = [int]$summary.deletions
        patch_delta_window_kb = $patchSize.kb
        patch_delta_window_mb = $patchSize.mb
        touched_changed_file_window_kb = $touchedSize.kb
        touched_changed_file_window_mb = $touchedSize.mb
    }
}

function Get-AiOsBackupWorkDeltaReport {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [AllowNull()][string]$BaseCommit = "",
        [AllowNull()][string]$CurrentCommit = "",
        [string]$TimeslotLabel = "manual",
        [AllowNull()][string]$WindowStartLocal = "",
        [AllowNull()][string]$WindowEndLocal = "",
        [AllowNull()][string]$DayStartCommit = "",
        [AllowNull()][string]$TimeslotBaseCommit = "",
        [AllowNull()][string]$LastSuccessfulBackupCommit = ""
    )

    $head = if ([string]::IsNullOrWhiteSpace($CurrentCommit)) {
        Get-AiOsBackupGitHead -RepoRoot $RepoRoot
    } else {
        [string]$CurrentCommit
    }

    $window = Resolve-AiOsBackupTimeslotWindow -TimeslotLabel $TimeslotLabel -WindowStartLocal $WindowStartLocal -WindowEndLocal $WindowEndLocal
    $devMetrics = New-AiOsDevWorkDeltaMetrics -RepoRoot $RepoRoot -BaseCommit $BaseCommit -CurrentCommit $head
    $dailyMetrics = New-AiOsDailyWorkMetrics -RepoRoot $RepoRoot -CurrentCommit $head -DayStartCommit $DayStartCommit
    $slotBase = if ([string]::IsNullOrWhiteSpace($TimeslotBaseCommit)) { $BaseCommit } else { $TimeslotBaseCommit }
    $timeslotMetrics = New-AiOsTimeslotWorkMetrics -RepoRoot $RepoRoot -CurrentCommit $head -TimeslotLabel $window.timeslot_label -WindowStartLocal $window.window_start_local -WindowEndLocal $window.window_end_local -BaseCommit $slotBase

    return [pscustomobject][ordered]@{
        backup_timeslot_label = $window.timeslot_label
        backup_timeslot_local = $window.timeslot_local
        backup_window_start = $window.window_start_local
        backup_window_end = $window.window_end_local
        last_successful_backup_commit = if ([string]::IsNullOrWhiteSpace($LastSuccessfulBackupCommit)) { $BaseCommit } else { $LastSuccessfulBackupCommit }
        current_commit = $head
        dev_work_delta_metrics = $devMetrics
        daily_work_metrics = $dailyMetrics
        timeslot_work_metrics = $timeslotMetrics
    }
}
function Read-AiOsArchiveBaseline {
    param([string]$ManifestPath, [string[]]$Roots, [string]$ArchivePath, [datetime]$DeadlineUtc = [DateTime]::MaxValue)
    # Read metadata once; reuse the completed archive verification, not a new archive hash pass.
    $index = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::OrdinalIgnoreCase)
    $orderedRoots = @($Roots | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') } | Sort-Object Length -Descending)
    $reader = [IO.StreamReader]::new($ManifestPath)
    try {
        while ($null -ne ($line = $reader.ReadLine())) {
            if ([DateTime]::UtcNow -ge $DeadlineUtc) { throw 'BACKUP_RESOURCE_TIME_BOUNDARY' }
            $parts = $line.Split([char]9)
            if ($parts[0] -ne 'F') { continue }
            if ($parts.Count -ne 6 -or $parts[4] -notmatch '^[A-Fa-f0-9]{64}$') { throw 'ARCHIVE_MANIFEST_ROW_INVALID' }
            $relative = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($parts[1])).Replace('/','\')
            $mapping = [regex]::Match($relative,'^FILES\\([A-Za-z])\\(.+)$')
            if (-not $mapping.Success) { continue }
            if ($relative -match '(^|\\)\.\.($|\\)') { throw 'ARCHIVE_MANIFEST_TRAVERSAL' }
            $source = [IO.Path]::GetFullPath($mapping.Groups[1].Value+':\'+$mapping.Groups[2].Value)
            foreach ($root in $orderedRoots) {
                if ($source.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)) {
                    if ($index.ContainsKey($source)) { throw 'ARCHIVE_BASELINE_DUPLICATE_SOURCE' }
                    $index.Add($source,[pscustomobject]@{bytes=[long]$parts[2];ticks=[long]$parts[3];sha256=$parts[4].ToUpperInvariant();reference=$ArchivePath+'!payload/'+$relative.Replace('\','/')})
                    break
                }
            }
        }
    } finally { $reader.Dispose() }
    return ,$index
}

function Get-AiOsScopedSavedFiles {
    param([string]$Root, [string[]]$AllRoots, [datetime]$DeadlineUtc)
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if ((Get-Item -LiteralPath $rootPath -Force -ErrorAction Stop).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'SOURCE_ROOT_REPARSE_POINT' }
    $nested = @($AllRoots | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') } | Where-Object { $_ -ne $rootPath -and $_.StartsWith($rootPath+'\',[StringComparison]::OrdinalIgnoreCase) })
    $stack = New-Object 'System.Collections.Generic.Stack[string]'; $stack.Push($rootPath)
    while ($stack.Count) {
        if ([DateTime]::UtcNow -ge $DeadlineUtc) { throw 'BACKUP_RESOURCE_TIME_BOUNDARY' }
        $directory = $stack.Pop()
        foreach ($entry in [IO.Directory]::EnumerateFileSystemEntries($directory)) {
            if ([DateTime]::UtcNow -ge $DeadlineUtc) { throw 'BACKUP_RESOURCE_TIME_BOUNDARY' }
            $item = Get-Item -LiteralPath $entry -Force -ErrorAction Stop
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
            $relative = $item.FullName.Substring($rootPath.Length+1)
            if (Test-AiOsRelativePathExcluded -RelativePath $relative -ExcludedFolderNames @('.git','.ssh','.codex','.agents','.aios','.venv','venv','node_modules','__pycache__','.codex_backups','AIOS_BACKUP*','snapshots','current_mirror','T9_FOB','secrets','credentials') -ExcludedFilePatterns @('.env','*.env','.env.*','*.local.json','auth.json','*secret*','*credential*','*.key','*.pem','*.pfx','*.p12','id_rsa','id_ed25519','AIOS_DIRECT*.zip','AIOS_RECOVERY*.zip')) { continue }
            if ($item.PSIsContainer) { if ($item.FullName -notin $nested) { $stack.Push($item.FullName) }; continue }
            [pscustomobject]@{source=$item.FullName;relative=$relative;bytes=$item.Length;ticks=$item.LastWriteTimeUtc.Ticks}
        }
    }
}

function Get-AiOsArchiveChange {
    param([object]$File, [object]$Baseline, [hashtable]$VerifiedAdditionalReferences = @{})
    if ($null -ne $Baseline -and $Baseline.bytes -eq $File.bytes -and $Baseline.ticks -eq $File.ticks) {
        return [pscustomobject]@{copy=$false;observation_changed=$false;entry=$Baseline}
    }
    $hash = (Get-FileHash -LiteralPath $File.source -Algorithm SHA256 -ErrorAction Stop).Hash
    $after = Get-Item -LiteralPath $File.source -Force -ErrorAction Stop
    if ($after.Length -ne $File.bytes -or $after.LastWriteTimeUtc.Ticks -ne $File.ticks) { throw 'SOURCE_CHANGED_DURING_INCREMENTAL_HASH' }
    $same = $null -ne $Baseline -and $Baseline.sha256 -ceq $hash
    $known = $VerifiedAdditionalReferences.ContainsKey($hash)
    $entry = [pscustomobject]@{bytes=$File.bytes;ticks=$File.ticks;sha256=$hash;reference=$(if($same){$Baseline.reference}elseif($known){$VerifiedAdditionalReferences[$hash]}else{''})}
    return [pscustomobject]@{copy=(-not ($same -or $known));observation_changed=$true;entry=$entry}
}
function Invoke-AiOsVerifiedArchiveIncremental {
    param([string]$ScopeCheckpoint,[string]$ArchiveManifest,[string]$BackupRoot,[string]$VolumeUniqueId,[string]$StateRoot,[string]$PolicyReceipt='', [int]$MaximumMinutes=60,[switch]$Preview)
    $scope = Get-Content -LiteralPath $ScopeCheckpoint -Raw | ConvertFrom-Json
    if ($scope.Status -ne 'PASSED_59_CHECKS' -or @($scope.Checks).Count -ne 59 -or @($scope.Checks | Where-Object {$_.Status -ne 'PASS'}).Count) { throw 'VERIFIED_59_ROOT_SCOPE_REQUIRED' }
    $roots = @($scope.Checks | Sort-Object Index | ForEach-Object {[IO.Path]::GetFullPath($_.Source).TrimEnd('\')})
    if (@($roots | Sort-Object -Unique).Count -ne 59) { throw 'DUPLICATE_SCOPE_ROOT' }
    foreach($root in $roots){
        if ([IO.Path]::GetFileName($root) -in @('.codex','.agents','.aios','.ssh','secrets','credentials')) { throw 'PROTECTED_ROOT_REQUIRES_SCOPE_RECONCILIATION' }
        if ($root -eq [IO.Path]::GetPathRoot($root).TrimEnd('\') -or (Test-AiOsPathInside $BackupRoot $root) -or (Test-AiOsPathInside $StateRoot $root)) { throw 'BACKUP_SCOPE_RECURSION' }
    }
    $receiptPath=$ArchiveManifest -replace '\.manifest\.tsv$','.VERIFIED.json'
    if($receiptPath -eq $ArchiveManifest){throw 'ARCHIVE_MANIFEST_FILENAME_UNSUPPORTED'}
    $receipt=Get-Content -LiteralPath $receiptPath -Raw|ConvertFrom-Json
    if($receipt.Status -ne 'CONTENTS_HASH_VERIFIED' -or $receipt.Manifest -ine $ArchiveManifest -or $receipt.ManifestSHA256 -ne '12E9119132F01919FF2413F067F1DFEB463F7DAFBF1DEDF4041912DA4700F5AE' -or $receipt.ArchiveBytes -ne 179473954947L){throw 'ARCHIVE_VERIFICATION_REFERENCE_MISMATCH'}
    $manifestInfo=Get-Item -LiteralPath $ArchiveManifest
    if($manifestInfo.Length -ne 432773522L -or (Get-Item -LiteralPath $receipt.Archive).Length -ne $receipt.ArchiveBytes){throw 'ARCHIVE_METADATA_IDENTITY_CHANGED'}
    if($MaximumMinutes -lt 1 -or $MaximumMinutes -gt 120){throw 'BACKUP_TIME_BOUNDARY_INVALID'}
    if(Test-Path -LiteralPath ([IO.Path]::Combine($StateRoot,'MANUAL_STOP'))){throw 'OWNER_BACKUP_STOP_PRESERVED'}
    $scopeHash=(Get-FileHash -LiteralPath $ScopeCheckpoint).Hash
    if($Preview){return [pscustomobject]@{status='PREVIEW';roots=59;scope_sha256=$scopeHash;archive_hash_reused=$receipt.ManifestSHA256;capture_started=$false}}
    [IO.Directory]::CreateDirectory($StateRoot)|Out-Null
    $lockPath=[IO.Path]::Combine($StateRoot,'AIOS_BACKUP_IN_PROGRESS.lock')
    New-AiOsBackupLock -BackupReportRoot $StateRoot -BackupLockPath $lockPath -SourcePath 'VERIFIED_59_ROOT_SCOPE' -SnapshotPath $BackupRoot
    try {
        $pendingPath=[IO.Path]::Combine($StateRoot,'pending-drive.json')
        $volume=Get-Volume -DriveLetter ([IO.Path]::GetPathRoot($BackupRoot).Substring(0,1)) -ErrorAction SilentlyContinue
        if($null -eq $volume){
            $wasPending=$false
            if(Test-Path -LiteralPath $pendingPath){$wasPending=(Get-Content $pendingPath -Raw|ConvertFrom-Json).status -eq 'PENDING_DRIVE'}
            $pending=Write-AiOsPendingBackupDrive -Path $pendingPath -EventId $scopeHash -BackupRoot $BackupRoot
            # Receipt remains pending; no Telegram delivery or approval is claimed.
            return $pending
        }
        Assert-AiOsBackupVolume -BackupRoot $BackupRoot -Volume $volume -ExpectedUniqueId $VolumeUniqueId
        if(-not(Test-Path -LiteralPath $BackupRoot -PathType Container)){throw 'APPROVED_BACKUP_ROOT_MISSING'}
        $destinationLock=[IO.Path]::Combine($BackupRoot,'backup_reports','AIOS_BACKUP_IN_PROGRESS.lock')
        New-AiOsBackupLock -BackupReportRoot ([IO.Path]::GetDirectoryName($destinationLock)) -BackupLockPath $destinationLock -SourcePath 'VERIFIED_59_ROOT_SCOPE' -SnapshotPath $BackupRoot
        $statePath=[IO.Path]::Combine($StateRoot,'archive-incremental-state.json')
        $state=if(Test-Path -LiteralPath $statePath){Get-Content $statePath -Raw|ConvertFrom-Json}else{[pscustomobject]@{schema='AIOS_ARCHIVE_INCREMENTAL_STATE.v1';scope_sha256=$scopeHash;next_root=0;completed_roots=@();snapshot=('AIOS_BACKUP_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'_SAVED_WORK');status='STARTED'}}
        Assert-AiOsArchiveRunState -State $state -ScopeHash $scopeHash -Roots $roots -BackupRoot $BackupRoot
        if($state.status -eq 'SUCCESS'){$state.next_root=0;$state.completed_roots=@();$state.snapshot='AIOS_BACKUP_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'_SAVED_WORK';$state.status='STARTED'}
        $deadline=[DateTime]::UtcNow.AddMinutes($MaximumMinutes)
        $archiveMirror=[IO.Path]::Combine([IO.Path]::GetPathRoot($BackupRoot),'AIOS_VERIFIED_ARCHIVES_20261031',[IO.Path]::GetFileName($receipt.Archive))
        if((Get-Item -LiteralPath $archiveMirror -ErrorAction Stop).Length -ne $receipt.ArchiveBytes){throw 'VERIFIED_ARCHIVE_MIRROR_MISSING_OR_CHANGED'}
        $baseline=Read-AiOsArchiveBaseline -ManifestPath $ArchiveManifest -Roots $roots -ArchivePath $archiveMirror -DeadlineUtc $deadline
        if((Get-Item $ArchiveManifest).Length -ne $manifestInfo.Length -or (Get-Item $ArchiveManifest).LastWriteTimeUtc -ne $manifestInfo.LastWriteTimeUtc){throw 'ARCHIVE_MANIFEST_CHANGED_DURING_READ'}
        $additional=@{}
        if($PolicyReceipt){
            $policy=Get-Content -LiteralPath $PolicyReceipt -Raw|ConvertFrom-Json
            $policyManifestPath=[IO.Path]::Combine([IO.Path]::GetDirectoryName($PolicyReceipt),'package','MANIFEST.json')
            if($policy.status -ne 'VERIFIED' -or $policy.source_commit -ne '9261f8ca78c1c0250c51fb285c1bdcde3cb9c858' -or (Get-FileHash $policyManifestPath).Hash -cne $policy.manifest_sha256){throw 'POLICY_INCREMENTAL_REFERENCE_INVALID'}
            $policyManifest=Get-Content $policyManifestPath -Raw|ConvertFrom-Json
            foreach($entry in $policyManifest.files|Where-Object {$_.path -in @('AGENTS.md','docs/governance/aios-identity-and-lane-governance.md','docs/workflows/AI_OS_T9_BACKUP_WORKFLOW.md')}){
                $target=[IO.Path]::Combine($policy.destination,$entry.path)
                if(-not (Test-AiOsPathInside $target $BackupRoot) -or (Get-FileHash -LiteralPath $target).Hash -cne $entry.sha256){throw 'POLICY_INCREMENTAL_COPY_UNVERIFIED'}
                $additional[[IO.Path]::Combine('C:\Dev\Ai.Os',$entry.path)]=@{ $entry.sha256=$target }
            }
        }
        # Segments retain a torn append verbatim. Only LF-terminated records are committed.
        if(-not $state.PSObject.Properties['journal_files']){$state|Add-Member -NotePropertyName journal_files -NotePropertyValue @('verified-file-updates.jsonl')}
        if(-not $state.PSObject.Properties['journal_reconciliations']){$state|Add-Member -NotePropertyName journal_reconciliations -NotePropertyValue @()}
        Assert-AiOsArchiveJournalState -State $state
        $journalSources=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $archiveOriginals=@{}
        $rotateJournal=$false
        foreach($journalName in @($state.journal_files)){
            $journalPath=[IO.Path]::Combine($StateRoot,$journalName)
            $preserved=@($state.journal_reconciliations|Where-Object {$_.file -ceq $journalName})
            if(-not(Test-Path -LiteralPath $journalPath)){
                if($journalName -cne $state.journal_files[-1] -or $preserved.Count){throw 'INCREMENTAL_JOURNAL_SEGMENT_MISSING'}
                continue # Active segment may not have received its first append yet.
            }
            Read-AiOsArchiveJournal -Path $journalPath -DeadlineUtc $deadline | ForEach-Object {
                $record=$_
                if($record.kind -eq 'ENTRY'){
                    $update=$record.entry
                    if($update.sha256 -notmatch '^[A-F0-9]{64}$' -or $update.source -isnot [string] -or -not @($roots|Where-Object {$update.source.StartsWith($_+'\',[StringComparison]::OrdinalIgnoreCase)}).Count){throw 'INCREMENTAL_JOURNAL_INVALID'}
                    if($journalSources.Add($update.source) -and $baseline.ContainsKey($update.source)){$archiveOriginals[$update.source]=$baseline[$update.source]}
                    $baseline[$update.source]=$update
                }else{
                    if($preserved.Count){
                        $proof=$preserved[0]
                        if($record.sha256 -cne $proof.sha256 -or $record.file_bytes -ne $proof.file_bytes -or $record.committed_bytes -ne $proof.committed_bytes -or $record.tail_bytes -ne $proof.tail_bytes){throw 'PRESERVED_JOURNAL_CHANGED'}
                    }elseif($record.tail_bytes -gt 0){
                        if($journalName -cne $state.journal_files[-1]){throw 'UNRECONCILED_INTERIOR_JOURNAL_TAIL'}
                        $state.journal_reconciliations+= [pscustomobject]@{file=$journalName;sha256=$record.sha256;file_bytes=$record.file_bytes;committed_bytes=$record.committed_bytes;tail_bytes=$record.tail_bytes;reason='UNTERMINATED_FINAL_APPEND';original_retained=$true}
                        $rotateJournal=$true
                    }
                }
            }
        }
        foreach($source in $journalSources){$entry=$baseline[$source];Assert-AiOsArchiveJournalReference -Entry $entry -Original $(if($archiveOriginals.ContainsKey($source)){$archiveOriginals[$source]}else{$null}) -BackupRoot $BackupRoot}
        # Persist the verified-prefix reconciliation before any new append; never truncate/repair the old file.
        if($rotateJournal){$state.journal_files+= 'verified-file-updates.'+[guid]::NewGuid().ToString('N')+'.jsonl'}
        Assert-AiOsArchiveJournalState -State $state
        $journalPath=[IO.Path]::Combine($StateRoot,$state.journal_files[-1])
        $snapshot=[IO.Path]::Combine($BackupRoot,$state.snapshot)
        # Logical ready-bin proposal in the existing checkpoint, not a second queue or a deletion job.
        $state|Add-Member -NotePropertyName ready_bin -NotePropertyValue ([pscustomobject]@{kind='PROPOSED_STAGING_ONLY';task_id=$scopeHash;accepted_milestone_id=$null;capture_status='PENDING';capture_checkpoint=$statePath;restore_journals=@($state.journal_files);cleanup_authorized=$false;cleanup_implemented=$false;live_sources_retained=$true;restore_manifests_retained=$true}) -Force
        $copied=0;$observed=0
        $saveState={
            $temporary=$statePath+'.'+[guid]::NewGuid().ToString('N')
            [IO.File]::WriteAllText($temporary,($state|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
            if(Test-Path $statePath){[IO.File]::Replace($temporary,$statePath,[NullString]::Value)}else{[IO.File]::Move($temporary,$statePath)}
        }
        & $saveState
        for($i=[int]$state.next_root;$i -lt $roots.Count;$i++){
            $root=$roots[$i]
            Get-AiOsScopedSavedFiles -Root $root -AllRoots $roots -DeadlineUtc $deadline | ForEach-Object {
                $file=$_
                if([DateTime]::UtcNow -ge $deadline){throw 'BACKUP_RESOURCE_TIME_BOUNDARY'}
                $observed++
                $prior=if($baseline.ContainsKey($file.source)){$baseline[$file.source]}else{$null}
                $known=if($additional.ContainsKey($file.source)){$additional[$file.source]}else{@{}}
                $decision=Get-AiOsArchiveChange -File $file -Baseline $prior -VerifiedAdditionalReferences $known
                if(-not $decision.observation_changed){return}
                $entry=$decision.entry
                if($decision.copy){
                    # A changed source on resume gets a different immutable destination, preserving prior proof.
                    $destination=Get-AiOsArchiveVersionDestination -Snapshot $snapshot -Root $root -Sha256 $entry.sha256
                    $target=[IO.Path]::Combine($destination,$file.relative)
                    if(Test-Path -LiteralPath $target){if((Get-FileHash -LiteralPath $target).Hash -cne $entry.sha256){throw 'EXISTING_INCREMENTAL_COPY_CONFLICT'}}
                    else{[IO.Directory]::CreateDirectory($destination)|Out-Null;Copy-AiOsDeltaFiles -RepoRoot $root -DestinationRoot $destination -RelativePaths @($file.relative) -ExpectedHashes @{$file.relative.Replace('\','/')=$entry.sha256};$copied++}
                    $entry.reference=$target
                }
                $update=[ordered]@{source=$file.source;bytes=$entry.bytes;ticks=$entry.ticks;sha256=$entry.sha256;reference=$entry.reference}
                $bytes=[Text.Encoding]::UTF8.GetBytes(($update|ConvertTo-Json -Compress)+"`n")
                $stream=[IO.File]::Open($journalPath,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::Read)
                try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
                $baseline[$file.source]=[pscustomobject]$update
            }
            $state.completed_roots+= $root;$state.next_root=$i+1;& $saveState
        }
        $state.ready_bin.capture_status='VERIFIED';$state.status='SUCCESS';& $saveState
        if(Test-Path $pendingPath){$pending=Get-Content $pendingPath -Raw|ConvertFrom-Json;if($pending.event_id -ne $scopeHash){throw 'PENDING_SCOPE_CHANGED'};$pending.status='COMPLETED';$pending|Add-Member -NotePropertyName verified_checkpoint -NotePropertyValue $statePath -Force;$pending|ConvertTo-Json|Set-Content -LiteralPath $pendingPath -Encoding UTF8}
        return [pscustomobject]@{status='SUCCESS';roots_completed=59;files_observed=$observed;files_copied=$copied;checkpoint=$statePath;archive_rehashed=$false;deletion_performed=$false;ready_bin_cleanup_performed=$false;telegram_delivery_verified=$false;milestone_watcher_installed=$false}
    } finally {
        if(Get-Variable destinationLock -ErrorAction SilentlyContinue){if((Get-Variable aiosBackupOwnedStreams -Scope Script -ErrorAction SilentlyContinue) -and $script:aiosBackupOwnedStreams.ContainsKey($destinationLock)){Remove-AiOsBackupLock -BackupLockPath $destinationLock}}
        Remove-AiOsBackupLock -BackupLockPath $lockPath
    }
}

function Get-AiOsArchiveVersionDestination {
    param([string]$Snapshot,[string]$Root,[string]$Sha256)
    if($Sha256 -cnotmatch '^[A-F0-9]{64}$'){throw 'INCREMENTAL_VERSION_HASH_INVALID'}
    return [IO.Path]::Combine([IO.Path]::Combine($Snapshot,'VERSIONS',$Sha256),'FILES',$Root.Replace(':','').TrimStart('\'))
}

function Assert-AiOsArchiveJournalState {
    param([object]$State)
    if($State.journal_files -isnot [array] -or -not $State.journal_files.Count -or $State.journal_files[0] -cne 'verified-file-updates.jsonl' -or $State.journal_reconciliations -isnot [array]){throw 'INCREMENTAL_JOURNAL_STATE_INVALID'}
    $names=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach($name in $State.journal_files){
        if($name -isnot [string] -or $name -cnotmatch '^verified-file-updates(?:\.[a-f0-9]{32})?\.jsonl$' -or -not $names.Add($name)){throw 'INCREMENTAL_JOURNAL_SEGMENT_INVALID'}
    }
    $sealed=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach($proof in $State.journal_reconciliations){
        if(-not $names.Contains($proof.file) -or $proof.file -ceq $State.journal_files[-1] -or -not $sealed.Add($proof.file) -or $proof.sha256 -cnotmatch '^[A-F0-9]{64}$' -or $proof.file_bytes -le 0 -or $proof.committed_bytes -lt 0 -or $proof.tail_bytes -le 0 -or $proof.file_bytes -ne ($proof.committed_bytes+$proof.tail_bytes) -or $proof.reason -cne 'UNTERMINATED_FINAL_APPEND' -or $proof.original_retained -ne $true){throw 'INCREMENTAL_JOURNAL_RECONCILIATION_INVALID'}
    }
}

function Read-AiOsArchiveJournal {
    param([string]$Path,[datetime]$DeadlineUtc=[datetime]::MaxValue)
    if((Get-Item -LiteralPath $Path -Force -ErrorAction Stop).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'INCREMENTAL_JOURNAL_REPARSE_POINT'}
    $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $line=[IO.MemoryStream]::new();$hash=[Security.Cryptography.SHA256]::Create()
    $utf8=[Text.UTF8Encoding]::new($false,$true)
    $buffer=New-Object byte[] 65536
    $total=0L;$committed=0L
    try{
        while(($count=$stream.Read($buffer,0,$buffer.Length)) -gt 0){
            if([datetime]::UtcNow -ge $DeadlineUtc){throw 'BACKUP_RESOURCE_TIME_BOUNDARY'}
            $null=$hash.TransformBlock($buffer,0,$count,$buffer,0);$total+=$count
            $start=0
            while($start -lt $count){
                $end=[Array]::IndexOf($buffer,[byte]10,$start,$count-$start)
                $length=if($end -lt 0){$count-$start}else{$end-$start}
                if($line.Length+$length -gt 1048576){throw 'INCREMENTAL_JOURNAL_RECORD_TOO_LARGE'}
                $line.Write($buffer,$start,$length)
                if($end -lt 0){break}
                # Decode committed lines strictly. A malformed complete/interior record is never skipped.
                $text=$utf8.GetString($line.ToArray())
                if([string]::IsNullOrWhiteSpace($text)){throw 'INCREMENTAL_JOURNAL_EMPTY_RECORD'}
                $entry=$text|ConvertFrom-Json -ErrorAction Stop
                [pscustomobject]@{kind='ENTRY';entry=$entry}
                $committed+=$line.Length+1;$line.SetLength(0);$line.Position=0;$start=$end+1
            }
        }
        $null=$hash.TransformFinalBlock((New-Object byte[] 0),0,0)
        # Even syntactically valid JSON without LF is uncommitted. Keep those bytes untouched.
        [pscustomobject]@{kind='SUMMARY';sha256=([BitConverter]::ToString($hash.Hash).Replace('-',''));file_bytes=$total;committed_bytes=$committed;tail_bytes=$line.Length}
    }finally{$line.Dispose();$hash.Dispose();$stream.Dispose()}
}

function Assert-AiOsArchiveRunState {
    param([object]$State,[string]$ScopeHash,[string[]]$Roots,[string]$BackupRoot)
    if($State.schema -ne 'AIOS_ARCHIVE_INCREMENTAL_STATE.v1' -or $State.scope_sha256 -cne $ScopeHash -or $State.status -notin @('STARTED','SUCCESS') -or $State.next_root -isnot [int] -or $State.next_root -lt 0 -or $State.next_root -gt $Roots.Count -or $State.snapshot -notmatch '^AIOS_BACKUP_\d{8}_\d{6}_SAVED_WORK$' -or @($State.completed_roots).Count -ne $State.next_root){throw 'INCREMENTAL_CHECKPOINT_INVALID'}
    for($i=0;$i -lt $State.next_root;$i++){if($State.completed_roots[$i] -ine $Roots[$i]){throw 'INCREMENTAL_ROOT_RECEIPT_MISMATCH'}}
    if($State.status -eq 'SUCCESS' -and $State.next_root -ne $Roots.Count){throw 'INCREMENTAL_SUCCESS_WITHOUT_ALL_ROOTS'}
    if(-not (Test-AiOsPathInside ([IO.Path]::Combine($BackupRoot,$State.snapshot)) $BackupRoot)){throw 'INCREMENTAL_DESTINATION_ESCAPED'}
}

function Assert-AiOsArchiveJournalReference {
    param([object]$Entry,[object]$Original,[string]$BackupRoot)
    if($null -ne $Original -and $Entry.reference -ceq $Original.reference -and $Entry.sha256 -ceq $Original.sha256 -and $Entry.bytes -eq $Original.bytes){return}
    if(-not (Test-AiOsPathInside (ConvertTo-AiOsFullPath $Entry.reference) $BackupRoot) -or (Get-Item -LiteralPath $Entry.reference -Force -ErrorAction Stop).Attributes -band [IO.FileAttributes]::ReparsePoint -or (Get-FileHash -LiteralPath $Entry.reference -ErrorAction Stop).Hash -cne $Entry.sha256){throw 'INCREMENTAL_SAVED_REFERENCE_UNVERIFIED'}
}
