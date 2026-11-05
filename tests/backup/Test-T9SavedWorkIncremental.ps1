$ErrorActionPreference='Stop'
$helper=Join-Path $PSScriptRoot '../../scripts/backup/Start-AiOsT9SnapshotBackup.ps1'
$parseErrors=$null;$tokens=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($helper,[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count){throw 'Backup helper does not parse.'}
foreach($definition in $ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){
    . ([scriptblock]::Create($definition.Extent.Text))
}
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('AIOS-saved-work-test-'+[guid]::NewGuid().ToString('N'))
$source=Join-Path $fixture 'source';$destination=Join-Path $fixture 'copy'
[IO.Directory]::CreateDirectory($source)|Out-Null
[IO.Directory]::CreateDirectory($destination)|Out-Null
function Assert-True([bool]$Condition,[string]$Reason){if(-not $Condition){throw $Reason}}
function Assert-Refused([scriptblock]$Action,[string]$Reason){$refused=$false;try{& $Action|Out-Null}catch{$refused=$true};Assert-True $refused $Reason}
$volume=[pscustomobject]@{FileSystemLabel='T9_FOB';UniqueId='synthetic-approved-volume'}
Assert-AiOsBackupVolume -BackupRoot 'T:\AIOS_BACKUPS' -Volume $volume -ExpectedUniqueId 'synthetic-approved-volume'
Assert-Refused {Assert-AiOsBackupVolume -BackupRoot 'T:\AIOS_BACKUPS' -Volume $volume -ExpectedUniqueId 'different-volume'} 'Wrong volume identity accepted.'
Assert-Refused {Assert-AiOsBackupVolume -BackupRoot 'T:\AIOS_BACKUPS' -Volume $volume} 'Missing exact volume identity accepted.'
Assert-Refused {Assert-AiOsBackupVolume -BackupRoot 'D:\T9_FOB' -Volume $volume} 'D: label alone was accepted without the approved volume identity.'
Assert-Refused {Assert-AiOsBackupVolume -BackupRoot 'D:\T9_FOB' -Volume $volume -ExpectedUniqueId 'different-volume'} 'Wrong D: volume identity accepted.'
Assert-AiOsBackupVolume -BackupRoot 'D:\T9_FOB' -Volume $volume -ExpectedUniqueId 'synthetic-approved-volume'
$checkpointBlocked=$false
try { & $helper -SourceRepo $source -BackupRoot 'T:\AIOS_BACKUPS' -BackupMode Delta -SavedWorkFiles @('changed.txt') -Preview -OutputJson } catch { $checkpointBlocked=$_.Exception.Message -eq 'SAVED_WORK_ARCHIVE_CHECKPOINT_REQUIRED' }
Assert-True $checkpointBlocked 'Uncheckpointed saved-file route was accepted instead of requiring archive recovery state.'
$modeBlocked=$false
try { & $helper -SourceRepo $source -BackupRoot 'T:\AIOS_BACKUPS' -BackupMode Auto -SavedWorkFiles @('changed.txt') -Preview -OutputJson } catch { $modeBlocked=$_.Exception.Message -eq 'SAVED_WORK_REQUIRES_EXPLICIT_DELTA_NO_FULL_FALLBACK' }
Assert-True $modeBlocked 'Saved work did not refuse Auto before capture.'
[IO.File]::WriteAllText((Join-Path $source 'changed.txt'),'before')
[IO.File]::WriteAllText((Join-Path $source 'same.txt'),'same')
$baseline=@{'changed.txt'=(Get-FileHash (Join-Path $source 'changed.txt')).Hash;'same.txt'=(Get-FileHash (Join-Path $source 'same.txt')).Hash}
[IO.File]::WriteAllText((Join-Path $source 'changed.txt'),'after saved edit')
[IO.File]::WriteAllText((Join-Path $source 'new.txt'),'new saved file')
$scope=@('changed.txt','same.txt','new.txt')
$plan=Get-AiOsSavedWorkDelta -RepoRoot $source -RelativePaths $scope -PreviousHashes $baseline
Assert-True (@($plan.copy_files).Count -eq 2) 'Saved dirty/new work was not selected independently of Git HEAD.'
Assert-True ('same.txt' -notin $plan.copy_files) 'Unchanged saved file would be recopied.'
Copy-AiOsDeltaFiles -RepoRoot $source -DestinationRoot $destination -RelativePaths $plan.copy_files -ExpectedHashes $plan.file_hashes
foreach($file in $plan.copy_files){Assert-True ((Get-FileHash (Join-Path $destination $file)).Hash -eq $plan.file_hashes[$file]) 'Copied bytes did not verify.'}
$second=Get-AiOsSavedWorkDelta -RepoRoot $source -RelativePaths $scope -PreviousHashes $plan.file_hashes
Assert-True (@($second.copy_files).Count -eq 0) 'Equivalent saved checkpoint was copied again.'
Assert-Refused {Get-AiOsSavedWorkDelta -RepoRoot $source -RelativePaths @('../outside.txt')} 'Traversal accepted.'
Assert-Refused {Get-AiOsSavedWorkDelta -RepoRoot $source -RelativePaths @('.env')} 'Secret path accepted.'
Assert-Refused {Get-AiOsSavedWorkDelta -RepoRoot $source -RelativePaths @('nested')} 'Unresolved directory/file scope accepted.'
[IO.File]::WriteAllText((Join-Path $source 'changed.txt'),'changed after planning')
$other=Join-Path $fixture 'other';[IO.Directory]::CreateDirectory($other)|Out-Null
Assert-Refused {Copy-AiOsDeltaFiles -RepoRoot $source -DestinationRoot $other -RelativePaths @('changed.txt') -ExpectedHashes $plan.file_hashes} 'Changed source accepted against old plan.'
Assert-True (-not(Test-Path (Join-Path $other 'changed.txt'))) 'Changed source was copied before validation.'
[IO.File]::WriteAllText((Join-Path $destination 'keep.txt'),'preserve original')
[IO.File]::WriteAllText((Join-Path $source 'keep.txt'),'different')
Assert-Refused {Copy-AiOsDeltaFiles -RepoRoot $source -DestinationRoot $destination -RelativePaths @('keep.txt')} 'Existing destination overwritten.'
Assert-True ([IO.File]::ReadAllText((Join-Path $destination 'keep.txt')) -eq 'preserve original') 'Destination original lost.'
$pending=Join-Path $fixture 'pending.json'
Write-AiOsPendingBackupDrive -Path $pending -EventId 'synthetic-event' -BackupRoot 'T:\AIOS_BACKUPS'|Out-Null
$pendingHash=(Get-FileHash $pending).Hash
Write-AiOsPendingBackupDrive -Path $pending -EventId 'synthetic-event' -BackupRoot 'T:\AIOS_BACKUPS'|Out-Null
Assert-True ((Get-FileHash $pending).Hash -eq $pendingHash) 'Identical missing-drive event repeated/mutated.'
$record=Get-Content $pending -Raw|ConvertFrom-Json
Assert-True ($record.status -eq 'PENDING_DRIVE' -and -not $record.delivery_confirmed) 'Pending event pretended delivery/completion.'
Assert-Refused {Complete-AiOsPendingBackupDrive -Path $pending -EventId 'synthetic-event' -ManifestPath (Join-Path $fixture 'missing-manifest.json')} 'Unverified pending completion accepted.'
Assert-True ((Get-FileHash $pending).Hash -eq $pendingHash) 'Failed verification lost pending state.'
$proof=Join-Path $fixture 'verified-manifest.json'
$checkpoint=@([pscustomobject]@{relative_path='new.txt';sha256=$plan.file_hashes['new.txt'];backup_file=(Join-Path $destination 'new.txt')})
[IO.File]::WriteAllText($proof,([ordered]@{status='SUCCESS';saved_work_checkpoint=$checkpoint}|ConvertTo-Json -Depth 5))
Complete-AiOsPendingBackupDrive -Path $pending -EventId 'synthetic-event' -ManifestPath $proof
$completed=Get-Content $pending -Raw|ConvertFrom-Json
Assert-True ($completed.status -eq 'COMPLETED' -and $completed.verified_manifest -eq $proof) 'Verified checkpoint did not clear pending state.'
Write-AiOsPendingBackupDrive -Path $pending -EventId 'synthetic-event' -BackupRoot 'T:\AIOS_BACKUPS'|Out-Null
$again=Get-Content $pending -Raw|ConvertFrom-Json
Assert-True ($again.status -eq 'PENDING_DRIVE' -and $again.revision -eq 2) 'Next drive-absence event could not resume after a completed checkpoint.'
$beforeCorruptionCheck=(Get-FileHash $pending).Hash
[IO.File]::WriteAllText((Join-Path $destination 'new.txt'),'corrupt copied proof')
Assert-Refused {Complete-AiOsPendingBackupDrive -Path $pending -EventId 'synthetic-event' -ManifestPath $proof} 'Corrupt backup was accepted as a checkpoint.'
Assert-True ((Get-FileHash $pending).Hash -eq $beforeCorruptionCheck) 'Corrupt proof advanced pending state.'
$lockDefinition=($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'New-AiOsBackupLock'},$false)|Select-Object -First 1).Extent.Text
$barrier=[Threading.Barrier]::new(2)
$firstWriter=[Threading.ManualResetEventSlim]::new($false)
$lockPath=Join-Path $fixture 'contended.lock'
$contender={
    param($definition,$barrier,$firstWriter,$index,$lockPath,$fixture)
    function Test-Path {
        param([string]$LiteralPath,[string]$PathType)
        $options=@{LiteralPath=$LiteralPath};if($PathType){$options.PathType=$PathType}
        $present=Microsoft.PowerShell.Management\Test-Path @options
        if($LiteralPath -eq $lockPath){if(-not $barrier.SignalAndWait(5000)){throw 'Synthetic lock barrier expired.'}}
        return $present
    }
    function Set-Content {
        param([Parameter(ValueFromPipeline=$true)]$Value,[string]$LiteralPath,[string]$Encoding)
        process {
            if($index -eq 1 -and -not $firstWriter.Wait(5000)){throw 'Synthetic writer ordering expired.'}
            $Value|Microsoft.PowerShell.Management\Set-Content -LiteralPath $LiteralPath -Encoding $Encoding
            if($index -eq 0){$firstWriter.Set()}
        }
    }
    . ([scriptblock]::Create($definition))
    try {New-AiOsBackupLock -BackupReportRoot $fixture -BackupLockPath $lockPath -SourcePath 'synthetic-source' -SnapshotPath ('synthetic-'+$index);'ACQUIRED'}catch{'REFUSED'}
}
$runs=@();$handles=@()
foreach($index in @(0,1)){$run=[PowerShell]::Create();[void]$run.AddScript($contender).AddArgument($lockDefinition).AddArgument($barrier).AddArgument($firstWriter).AddArgument($index).AddArgument($lockPath).AddArgument($fixture);$runs+=$run;$handles+=$run.BeginInvoke()}
$outcomes=@();for($index=0;$index -lt 2;$index++){try{$outcomes+=@($runs[$index].EndInvoke($handles[$index]))}finally{$runs[$index].Dispose()}}
$barrier.Dispose();$firstWriter.Dispose()
Assert-True (@($outcomes|Where-Object {$_ -eq 'ACQUIRED'}).Count -eq 1) 'Competing jobs both acquired the backup lock.'
Write-Host 'PASS: approved volume, saved edits/new files, dedup, path/secret refusals, verified copy, changed-input refusal, original preservation, pending-drive dedup.'
Write-Host ('Synthetic fixture retained: '+$fixture)
