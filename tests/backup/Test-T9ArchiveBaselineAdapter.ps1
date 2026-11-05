$ErrorActionPreference='Stop'
foreach($path in @((Join-Path $PSScriptRoot '../../scripts/backup/Start-AiOsT9SnapshotBackup.ps1'),(Join-Path $PSScriptRoot '../../automation/orchestration/backups/Get-AiOsBackupWorkDelta.ps1'))){
 $errors=$null;$tokens=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)
 if($errors.Count){throw 'Adapter source parse failed.'}
 foreach($f in $ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){. ([scriptblock]::Create($f.Extent.Text))}
}
function Check([bool]$ok,[string]$reason){if(-not $ok){throw $reason}}
function Refused([scriptblock]$action){$failed=$false;try{&$action|Out-Null}catch{$failed=$true};Check $failed 'Unsafe input was accepted.'}
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('AIOS-archive-adapter-'+[guid]::NewGuid().ToString('N'))
$root=Join-Path $fixture 'source';$nested=Join-Path $root 'owned-child'
[IO.Directory]::CreateDirectory($nested)|Out-Null
$path=Join-Path $root 'saved ü.txt';[IO.File]::WriteAllText($path,'same')
$child=Join-Path $nested 'child.txt';[IO.File]::WriteAllText($child,'child')
$manifest=Join-Path $fixture 'synthetic.manifest.tsv'
$rows=@(foreach($file in @($path,$child)){
 $f=Get-Item $file;$relative='FILES/'+$file.Replace(':','').TrimStart('\').Replace('\','/')
 'F'+"`t"+[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($relative))+"`t"+$f.Length+"`t"+$f.LastWriteTimeUtc.Ticks+"`t"+(Get-FileHash $file).Hash+"`t32"
})
[IO.File]::WriteAllLines($manifest,$rows,[Text.UTF8Encoding]::new($false))
$index=Read-AiOsArchiveBaseline -ManifestPath $manifest -Roots @($root,$nested) -ArchivePath 'synthetic-verified.zip'
Check ($index.Count -eq 2 -and $index.ContainsKey($path)) 'Base64/FILES prefix mapping failed.'
$item=Get-Item $path;$file=[pscustomobject]@{source=$path;relative=$item.Name;bytes=$item.Length;ticks=$item.LastWriteTimeUtc.Ticks}
$handle=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try{$same=Get-AiOsArchiveChange -File $file -Baseline $index[$path];Check (-not $same.copy -and -not $same.observation_changed) 'Unchanged verified metadata read/recopied content.'}finally{$handle.Dispose()}
[IO.File]::SetLastWriteTimeUtc($path,$item.LastWriteTimeUtc.AddSeconds(2))
$item=Get-Item $path;$file.bytes=$item.Length;$file.ticks=$item.LastWriteTimeUtc.Ticks
$timeOnly=Get-AiOsArchiveChange -File $file -Baseline $index[$path]
Check (-not $timeOnly.copy -and $timeOnly.observation_changed -and $timeOnly.entry.reference -like 'synthetic-verified.zip!*') 'Hash-equal timestamp exception caused recopy.'
[IO.File]::WriteAllText($path,'changed saved content')
$item=Get-Item $path;$file.bytes=$item.Length;$file.ticks=$item.LastWriteTimeUtc.Ticks
Check (Get-AiOsArchiveChange -File $file -Baseline $index[$path]).copy 'Changed saved bytes not captured.'
$known=@{(Get-FileHash $path).Hash='synthetic-verified-policy-copy'}
$reconciled=Get-AiOsArchiveChange -File $file -Baseline $index[$path] -VerifiedAdditionalReferences $known
Check (-not $reconciled.copy -and $reconciled.entry.reference -eq 'synthetic-verified-policy-copy') 'Already verified later policy increment would be duplicated.'
[IO.File]::WriteAllText((Join-Path $root 'future-new.txt'),'new')
[IO.File]::WriteAllText((Join-Path $root '.env'),'synthetic excluded text')
$outer=@(Get-AiOsScopedSavedFiles -Root $root -AllRoots @($root,$nested) -DeadlineUtc ([DateTime]::UtcNow.AddMinutes(1)))
Check (@($outer|Where-Object {$_.source -eq $child}).Count -eq 0) 'Nested approved root duplicated.'
Check (@($outer|Where-Object {$_.relative -eq 'future-new.txt'}).Count -eq 1) 'Future new file not discovered.'
Check (@($outer|Where-Object {$_.relative -eq '.env'}).Count -eq 0) 'Credential-pattern file discovered for capture.'
Refused {Get-AiOsScopedSavedFiles -Root $root -AllRoots @($root) -DeadlineUtc ([DateTime]::UtcNow.AddSeconds(-1))}
Refused {Read-AiOsArchiveBaseline -ManifestPath $manifest -Roots @($root) -ArchivePath 'synthetic' -DeadlineUtc ([DateTime]::UtcNow.AddSeconds(-1))}
[IO.File]::AppendAllText($manifest,"`n"+$rows[0])
Refused {Read-AiOsArchiveBaseline -ManifestPath $manifest -Roots @($root) -ArchivePath 'synthetic'}
$state=[pscustomobject]@{schema='AIOS_ARCHIVE_INCREMENTAL_STATE.v1';scope_sha256='synthetic';next_root=0;completed_roots=@();snapshot='AIOS_BACKUP_20261031_200000_SAVED_WORK';status='STARTED'}
Assert-AiOsArchiveRunState -State $state -ScopeHash 'synthetic' -Roots @($root,$nested) -BackupRoot $fixture
$state.next_root=60
Refused {Assert-AiOsArchiveRunState -State $state -ScopeHash 'synthetic' -Roots @($root,$nested) -BackupRoot $fixture}
$state.next_root=0;$state.snapshot='../escape'
Refused {Assert-AiOsArchiveRunState -State $state -ScopeHash 'synthetic' -Roots @($root,$nested) -BackupRoot $fixture}
$saved=Join-Path $fixture 'saved.txt';[IO.File]::WriteAllText($saved,'verified')
$entry=[pscustomobject]@{reference=$saved;sha256=(Get-FileHash $saved).Hash;bytes=8}
Assert-AiOsArchiveJournalReference -Entry $entry -Original $null -BackupRoot $fixture
[IO.File]::WriteAllText($saved,'corrupt')
Refused {Assert-AiOsArchiveJournalReference -Entry $entry -Original $null -BackupRoot $fixture}
$entry.reference=Join-Path $fixture 'absent.txt'
Refused {Assert-AiOsArchiveJournalReference -Entry $entry -Original $null -BackupRoot $fixture}
[IO.Directory]::CreateDirectory((Join-Path $root '.codex'))|Out-Null
[IO.File]::WriteAllText((Join-Path $root '.codex/auth.json'),'synthetic credential exclusion fixture')
$checked=@(Get-AiOsScopedSavedFiles -Root $root -AllRoots @($root,$nested) -DeadlineUtc ([DateTime]::UtcNow.AddMinutes(1)))
Check (@($checked|Where-Object {$_.source -like '*auth.json'}).Count -eq 0) 'Authentication state entered saved-work discovery.'
$lock=Join-Path $fixture 'stale.lock'
[IO.File]::WriteAllText($lock,'{"status":"IN_PROGRESS","process_id":2147483647,"process_started_utc":"2000-01-01T00:00:00.0000000Z"}')
New-AiOsBackupLock -BackupReportRoot $fixture -BackupLockPath $lock -SourcePath 'fixture' -SnapshotPath 'fixture'
Remove-AiOsBackupLock -BackupLockPath $lock
Check ((Get-Content $lock -Raw|ConvertFrom-Json).status -eq 'RELEASED') 'Verified dead-owner recovery did not release its own lease.'
# An interrupted attempt may already contain an older, verified version of this same path.
$snapshot=Join-Path $fixture 'AIOS_BACKUP_20261031_200000_SAVED_WORK'
$firstHash=(Get-FileHash $path).Hash
$firstDestination=Get-AiOsArchiveVersionDestination -Snapshot $snapshot -Root $root -Sha256 $firstHash
[IO.Directory]::CreateDirectory($firstDestination)|Out-Null
Copy-AiOsDeltaFiles -RepoRoot $root -DestinationRoot $firstDestination -RelativePaths @($file.relative) -ExpectedHashes @{$file.relative.Replace('\','/')=$firstHash}
$firstCopy=Join-Path $firstDestination $file.relative
[IO.File]::WriteAllText($path,'edited between interrupted attempts')
$secondHash=(Get-FileHash $path).Hash
$secondDestination=Get-AiOsArchiveVersionDestination -Snapshot $snapshot -Root $root -Sha256 $secondHash
Check ($firstDestination -cne $secondDestination) 'Resumed changed content collided with its prior version.'
[IO.Directory]::CreateDirectory($secondDestination)|Out-Null
Copy-AiOsDeltaFiles -RepoRoot $root -DestinationRoot $secondDestination -RelativePaths @($file.relative) -ExpectedHashes @{$file.relative.Replace('\','/')=$secondHash}
Check ((Get-FileHash $firstCopy).Hash -ceq $firstHash) 'Prior verified version was changed.'
Check ((Get-FileHash (Join-Path $secondDestination $file.relative)).Hash -ceq $secondHash -and (Get-FileHash $path).Hash -ceq $secondHash) 'New copy or live source was lost.'
Refused {Get-AiOsArchiveVersionDestination -Snapshot $snapshot -Root $root -Sha256 '../escape'}

$journal=Join-Path $fixture 'verified-file-updates.jsonl'
$record=([ordered]@{source=$path;bytes=(Get-Item $path).Length;ticks=(Get-Item $path).LastWriteTimeUtc.Ticks;sha256=$secondHash;reference=(Join-Path $secondDestination $file.relative)}|ConvertTo-Json -Compress)
$prefix=[Text.Encoding]::UTF8.GetBytes($record+"`n")
# Include a torn multibyte tail. It is preserved as bytes, never decoded as a committed record.
$torn=[byte[]]($prefix+[Text.Encoding]::UTF8.GetBytes('{"source":')+@(195))
[IO.File]::WriteAllBytes($journal,$torn)
$before=(Get-FileHash $journal).Hash
$replay=@(Read-AiOsArchiveJournal -Path $journal)
$summary=$replay[-1]
Check (@($replay|Where-Object {$_.kind -eq 'ENTRY'}).Count -eq 1 -and $summary.committed_bytes -eq $prefix.Length -and $summary.tail_bytes -eq ($torn.Length-$prefix.Length)) 'Torn-tail prefix boundary was not preserved.'
Assert-AiOsArchiveJournalReference -Entry $replay[0].entry -Original $null -BackupRoot $fixture
Check ($summary.sha256 -ceq $before -and (Get-FileHash $journal).Hash -ceq $before) 'Reader modified or misidentified the preserved journal.'
$segment='verified-file-updates.'+('a'*32)+'.jsonl'
$journalState=[pscustomobject]@{journal_files=@('verified-file-updates.jsonl',$segment);journal_reconciliations=@([pscustomobject]@{file='verified-file-updates.jsonl';sha256=$summary.sha256;file_bytes=$summary.file_bytes;committed_bytes=$summary.committed_bytes;tail_bytes=$summary.tail_bytes;reason='UNTERMINATED_FINAL_APPEND';original_retained=$true})}
Assert-AiOsArchiveJournalState -State $journalState
$journalState.journal_files[1]='../escape.jsonl'
Refused {Assert-AiOsArchiveJournalState -State $journalState}
$journalState.journal_files[1]=$segment
$journalState.journal_reconciliations[0].original_retained=$false
Refused {Assert-AiOsArchiveJournalState -State $journalState}
$completeWithoutLf=Join-Path $fixture 'uncommitted-final.jsonl'
[IO.File]::WriteAllText($completeWithoutLf,$record,[Text.UTF8Encoding]::new($false))
$uncommitted=@(Read-AiOsArchiveJournal -Path $completeWithoutLf)
Check ($uncommitted.Count -eq 1 -and $uncommitted[0].committed_bytes -eq 0 -and $uncommitted[0].tail_bytes -gt 0) 'Unterminated valid JSON was incorrectly treated as committed.'
$bad=Join-Path $fixture 'invalid-interior.jsonl'
[IO.File]::WriteAllText($bad,"{broken}`n"+$record+"`n",[Text.UTF8Encoding]::new($false))
Refused {Read-AiOsArchiveJournal -Path $bad}
[IO.File]::WriteAllText($bad,$record+"`n{broken}`n",[Text.UTF8Encoding]::new($false))
Refused {Read-AiOsArchiveJournal -Path $bad}
Refused {Read-AiOsArchiveJournal -Path $journal -DeadlineUtc ([DateTime]::UtcNow.AddSeconds(-1))}
# A root checkpoint cannot outlive the journal proof on which it depends.
$boundaryJournal=Join-Path $fixture 'checkpoint-journal'
[IO.Directory]::CreateDirectory($boundaryJournal)|Out-Null
$boundaryPath=Join-Path $boundaryJournal 'verified-file-updates.jsonl'
[IO.File]::WriteAllBytes($boundaryPath,([byte[]]($prefix+$prefix)))
$boundaryState=[pscustomobject]@{next_root=1;journal_files=@('verified-file-updates.jsonl');journal_checkpoint=@([pscustomobject]@{file='verified-file-updates.jsonl';minimum_bytes=[long]($prefix.Length*2)})}
Assert-AiOsArchiveJournalCheckpoint -State $boundaryState -StateRoot $boundaryJournal
[IO.File]::AppendAllText($boundaryPath,$record+"`n",[Text.UTF8Encoding]::new($false))
Assert-AiOsArchiveJournalCheckpoint -State $boundaryState -StateRoot $boundaryJournal
[IO.File]::WriteAllBytes($boundaryPath,$prefix)
Refused {Assert-AiOsArchiveJournalCheckpoint -State $boundaryState -StateRoot $boundaryJournal}
[IO.File]::WriteAllBytes($boundaryPath,(New-Object byte[] 0))
Refused {Assert-AiOsArchiveJournalCheckpoint -State $boundaryState -StateRoot $boundaryJournal}
$missingRoot=Join-Path $fixture 'missing-journal'
[IO.Directory]::CreateDirectory($missingRoot)|Out-Null
Refused {Assert-AiOsArchiveJournalCheckpoint -State $boundaryState -StateRoot $missingRoot}
Check (-not(Test-Path (Join-Path $missingRoot 'verified-file-updates.jsonl'))) 'Missing journal proof was recreated.'
$legacy=[pscustomobject]@{next_root=1;journal_files=@('verified-file-updates.jsonl')}
Refused {Assert-AiOsArchiveJournalCheckpoint -State $legacy -StateRoot $boundaryJournal}
$legacy.next_root=0
Assert-AiOsArchiveJournalCheckpoint -State $legacy -StateRoot $boundaryJournal
$boundaryState.journal_checkpoint[0].minimum_bytes=-1
Refused {Assert-AiOsArchiveJournalCheckpoint -State $boundaryState -StateRoot $boundaryJournal}
# Exercise the real archive entry path using tiny local files. Only the physical
# volume/archive observations are synthetic; no real T9 or large archive is read.
& {
    Set-StrictMode -Version Latest
    $entryRoot=Join-Path $fixture 'entry-path'
    $backup=Join-Path $entryRoot 'backup';$liveState=Join-Path $entryRoot 'state'
    [IO.Directory]::CreateDirectory($backup)|Out-Null
    $scopePath=Join-Path $entryRoot 'scope.json'
    $manifestPath=Join-Path $entryRoot 'synthetic.manifest.tsv'
    $archivePath=Join-Path $entryRoot 'synthetic-baseline.zip'
    $mirror=[IO.Path]::Combine([IO.Path]::GetPathRoot($backup),'AIOS_VERIFIED_ARCHIVES_20261031','synthetic-baseline.zip')
    $checks=@(foreach($number in 1..59){
        $sourceRoot=Join-Path $entryRoot ('root-'+$number)
        [IO.Directory]::CreateDirectory($sourceRoot)|Out-Null
        [pscustomobject]@{Index=$number;Status='PASS';Source=$sourceRoot}
    })
    [IO.File]::WriteAllText($scopePath,([pscustomobject]@{Status='PASSED_59_CHECKS';Checks=$checks}|ConvertTo-Json -Depth 4))
    [IO.File]::WriteAllText($manifestPath,'synthetic archive identity sentinel')
    $receipt=[pscustomobject]@{Status='CONTENTS_HASH_VERIFIED';Manifest=$manifestPath;ManifestSHA256='12E9119132F01919FF2413F067F1DFEB463F7DAFBF1DEDF4041912DA4700F5AE';ArchiveBytes=179473954947L;Archive=$archivePath}
    [IO.File]::WriteAllText(($manifestPath -replace '\.manifest\.tsv$','.VERIFIED.json'),($receipt|ConvertTo-Json))
    function Get-Volume { [CmdletBinding()]param([string]$DriveLetter) [pscustomobject]@{FileSystemLabel='T9_FOB';UniqueId='fixture-volume'} }
    function Assert-AiOsBackupVolume {
        param($BackupRoot,$Volume,$ExpectedUniqueId)
        Check ($BackupRoot -ceq $backup -and $ExpectedUniqueId -ceq 'fixture-volume') 'Entry fixture escaped its synthetic destination.'
    }
    function Get-Item {
        [CmdletBinding()]param([Parameter(Position=0)][string]$LiteralPath,[switch]$Force)
        if($LiteralPath -ceq $manifestPath){return [pscustomobject]@{Length=432773522L;LastWriteTimeUtc=[datetime]'2026-01-01'}}
        if($LiteralPath -ceq $archivePath -or $LiteralPath -ceq $mirror){return [pscustomobject]@{Length=179473954947L}}
        Microsoft.PowerShell.Management\Get-Item @PSBoundParameters
    }
    function Read-AiOsArchiveBaseline {
        param($ManifestPath,$Roots,$ArchivePath,$DeadlineUtc)
        return ,(New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::OrdinalIgnoreCase))
    }
    $call=@{ScopeCheckpoint=$scopePath;ArchiveManifest=$manifestPath;BackupRoot=$backup;VolumeUniqueId='fixture-volume'}
    $fresh=Invoke-AiOsVerifiedArchiveIncremental @call -StateRoot $liveState
    Check ($fresh.status -eq 'SUCCESS') 'Fresh empty-scope entry fixture did not complete.'
    $saved=Get-Content (Join-Path $liveState 'archive-incremental-state.json') -Raw|ConvertFrom-Json
    Check ($saved.next_root -eq 59 -and $saved.journal_checkpoint.Count -eq 1 -and (Test-Path (Join-Path $liveState 'verified-file-updates.jsonl'))) 'Checkpoint was published without its empty journal/boundary.'
    $scopeIdentity=(Get-FileHash $scopePath).Hash
    foreach($fault in @('missing','truncated')){
        $faultRoot=Join-Path $entryRoot $fault
        [IO.Directory]::CreateDirectory($faultRoot)|Out-Null
        $saved.status='STARTED';$saved.journal_checkpoint[0].minimum_bytes=2L
        $stateFile=Join-Path $faultRoot 'archive-incremental-state.json'
        [IO.File]::WriteAllText($stateFile,($saved|ConvertTo-Json -Depth 5))
        $pendingFile=Join-Path $faultRoot 'pending-drive.json'
        Write-AiOsPendingBackupDrive -Path $pendingFile -EventId $scopeIdentity -BackupRoot $backup|Out-Null
        if($fault -eq 'truncated'){[IO.File]::WriteAllBytes((Join-Path $faultRoot 'verified-file-updates.jsonl'),(New-Object byte[] 0))}
        $stateBefore=(Get-FileHash $stateFile).Hash;$pendingBefore=(Get-FileHash $pendingFile).Hash
        $reason=''
        try{Invoke-AiOsVerifiedArchiveIncremental @call -StateRoot $faultRoot|Out-Null}catch{$reason=$_.Exception.Message}
        $expected=if($fault -eq 'missing'){'INCREMENTAL_JOURNAL_SEGMENT_MISSING'}else{'INCREMENTAL_JOURNAL_TRUNCATED'}
        Check ($reason -ceq $expected) ('Entry-path refusal mismatch: '+$reason)
        Check ((Get-FileHash $stateFile).Hash -ceq $stateBefore -and (Get-FileHash $pendingFile).Hash -ceq $pendingBefore) 'Failed resume advanced checkpoint or cleared pending work.'
    }
}
Write-Host 'PASS: archive entry refuses missing/truncated proof without clearing pending work.'

Write-Host 'PASS: archive mapping/reuse, saved-change discovery, exclusions, recovery leases, immutable resumed versions, preserved torn journal prefix, strict complete-record refusal and deadlines.'
Write-Host ('Synthetic fixture retained: '+$fixture)
