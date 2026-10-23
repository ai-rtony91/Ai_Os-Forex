[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$PacketId,
    [Parameter(Mandatory=$true)][string[]]$AllowedPaths,
    [datetime]$RunStartUtc=[datetime]::MinValue,
    [string]$RepoRoot='C:\Dev\Ai.Os', [string]$RelayRoot='', [string]$LogPath='', [object]$CampaignBinding=$null,
    [object]$BeforeManifest=$null, [string[]]$ControllerMetadataPaths=@(),
    [object]$ChangedPathsEvidence=$null, [string]$ExpectedStatusParserSha256='',
    [switch]$Apply
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'

function Resolve-AiOsOutputLocalPath {
    param([string]$Path,[string]$Under='')
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -notmatch '^[A-Za-z]:[\\/]' -or $Path.Substring(2).Contains(':') -or $Path -match '[\x00-\x1f]' -or $Path -match '(?:^|[\\/])\.{1,2}(?:[\\/]|$)') { throw 'Absolute local canonical path required.' }
    $full=[IO.Path]::GetFullPath($Path)
    if (-not [string]::Equals($full.TrimEnd('\'),$Path.TrimEnd('\'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Noncanonical path rejected.' }
    foreach($segment in $full.Substring(3).Split([char]'\')) {
        if ($segment -ne $segment.TrimEnd(' ','.') -or $segment -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') { throw 'Ambiguous Windows path rejected.' }
    }
    $cursor=$full
    while($cursor) {
        try {
            if (([IO.File]::GetAttributes($cursor) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse path rejected.' }
        } catch {
            $failure=$_.Exception.GetBaseException()
            if ($failure -isnot [IO.FileNotFoundException] -and $failure -isnot [IO.DirectoryNotFoundException]) { throw }
        }
        $parent=[IO.Path]::GetDirectoryName($cursor)
        if ($parent -eq $cursor) { break }; $cursor=$parent
    }
    if ($Under) {
        $base=Resolve-AiOsOutputLocalPath -Path $Under
        if (-not $full.StartsWith($base.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Path escapes selected root.' }
    }
    return $full
}

function Get-AiOsOutputBinding {
    param([object]$Value)
    $fields=@('request_sha256','task_id','packet_id','attempt_id','attempt_number','claim_task_id','claim_acquired_at','claim_identity_sha256','campaign_id')
    if ($null -eq $Value -or $Value -is [string] -or $Value -is [array]) { throw 'CampaignBinding object required.' }
    $keys=if($Value -is [Collections.IDictionary]) { @($Value.Keys) } else { @($Value.PSObject.Properties.Name) }
    if ($keys.Count -ne 9 -or @($keys | Where-Object { $_ -cnotin $fields }).Count) { throw 'CampaignBinding shape mismatch.' }
    $copy=[ordered]@{}
    foreach($name in $fields) {
        if($Value -is [Collections.IDictionary]) { $item=$Value[$name] }
        else { $item=$Value.PSObject.Properties[$name].Value }
        if ($name -eq 'attempt_number') {
            if (($item -isnot [int] -and $item -isnot [long]) -or $item -lt 0 -or $item -gt 2147483647) { throw 'Attempt number must be a nonnegative integer.' }
            $copy[$name]=[int]$item; continue
        }
        if ($item -isnot [string] -or [string]::IsNullOrWhiteSpace($item)) { throw 'CampaignBinding scalar string required.' }
        if ($name -in @('request_sha256','claim_identity_sha256')) {
            if ($item -cnotmatch '^[0-9a-f]{64}$') { throw 'CampaignBinding SHA256 must be lowercase hex.' }
        } elseif($name -eq 'claim_acquired_at') {
            $date=[datetimeoffset]::MinValue
            if ($item -notmatch '^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,7})?(?:Z|\+00:00)$' -or -not [datetimeoffset]::TryParse($item,[ref]$date)) { throw 'Claim acquisition must be explicit UTC ISO8601.' }
        } elseif($item -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$') { throw 'CampaignBinding identifier invalid.' }
        $copy[$name]=[string]::new($item.ToCharArray())
    }
    return [pscustomobject]$copy
}

function Write-AiOsOutputBoundLine {
    param([string]$Path,[string]$RelayRoot,[string]$Line,[object]$DiagnosticWriteChoice=$false,[object]$OutputWriteState='')
    if($DiagnosticWriteChoice -isnot [bool] -or -not $DiagnosticWriteChoice -or $OutputWriteState -isnot [string] -or $OutputWriteState -cne 'READY_TO_WRITE_DIAGNOSTIC') { throw 'DIAGNOSTIC_WRITE_GATE_REQUIRED' }
    $target=Resolve-AiOsOutputLocalPath -Path $Path -Under $RelayRoot
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
    $target=Resolve-AiOsOutputLocalPath -Path $target -Under $RelayRoot
    $stream=[IO.File]::Open($target,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try { $bytes=[Text.UTF8Encoding]::new($false).GetBytes($Line+[Environment]::NewLine); $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) }
    finally { $stream.Dispose() }
}

function Write-AiOsOutputLegacyLine {
    param([string]$Path,[string]$RepoRoot,[string]$Line,[object]$DiagnosticWriteChoice=$false,[object]$OutputWriteState='')
    if($DiagnosticWriteChoice -isnot [bool] -or -not $DiagnosticWriteChoice -or $OutputWriteState -isnot [string] -or $OutputWriteState -cne 'READY_TO_WRITE_DIAGNOSTIC') { throw 'DIAGNOSTIC_WRITE_GATE_REQUIRED' }
    $target=Resolve-AiOsOutputLocalPath -Path $Path -Under $RepoRoot
    $logDir=Split-Path -Parent $target
    if (-not (Test-Path -LiteralPath $logDir -PathType Container)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    $target=Resolve-AiOsOutputLocalPath -Path $target -Under $RepoRoot
    Add-Content -LiteralPath $target -Value $Line
}

function Resolve-AiOsOutputRelativeFile {
    param([string]$RepoRoot,[string]$RelativePath)
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or [IO.Path]::IsPathRooted($RelativePath) -or $RelativePath.Contains('\') -or $RelativePath.Contains(':') -or $RelativePath -match '(^|/)\.{1,2}(/|$)' -or $RelativePath.Contains('//') -or $RelativePath.EndsWith('/')) { throw 'Exact canonical relative file required.' }
    if ($RelativePath -match '(?i)(^|/)(\.git|\.aws|\.codex|approvals?|secrets?|credentials?|private)(/|$)' -or $RelativePath -match '(?i)^(control|runtime)/' -or $RelativePath -match '(?i)(^|/)\.env(?:\.|$)' -or $RelativePath -match '(?i)\.(pem|pfx|p12|key)$') { throw 'Private payload inventory prohibited.' }
    return Resolve-AiOsOutputLocalPath (Join-Path $RepoRoot $RelativePath) -Under $RepoRoot
}

function Get-AiOsWorkerOutputManifest {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$RepoRoot,[Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$SourcePaths)
    $root=Resolve-AiOsOutputLocalPath $RepoRoot
    if (-not [IO.Directory]::Exists($root)) { throw 'Repository root missing.' }
    $manifest=@{}
    foreach($relative in $SourcePaths) {
        if ($manifest.ContainsKey($relative)) { throw 'Duplicate inventory path.' }
        $full=Resolve-AiOsOutputRelativeFile $root $relative
        if([IO.Directory]::Exists($full)) { throw 'Inventory is files only.' }
        if(-not [IO.File]::Exists($full)) { $manifest[$relative]=$null; continue }
        if(([IO.FileInfo]$full).Length -gt 16777216) { throw 'Inventory file exceeds bounded inspection.' }
        $stream=[IO.File]::OpenRead($full); $hasher=[Security.Cryptography.SHA256]::Create()
        try { $manifest[$relative]=([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
        finally { $hasher.Dispose(); $stream.Dispose() }
    }
    return $manifest
}

function Test-AiOsWorkerOutput {
    [CmdletBinding()]
    param(
    [Parameter(Mandatory=$true)][string]$PacketId,
    [Parameter(Mandatory=$true)][string[]]$AllowedPaths,
    [datetime]$RunStartUtc=[datetime]::MinValue,
    [string]$RepoRoot='C:\Dev\Ai.Os', [string]$RelayRoot='', [string]$LogPath='', [object]$CampaignBinding=$null,
    [object]$BeforeManifest=$null, [string[]]$ControllerMetadataPaths=@(),
    [object]$ChangedPathsEvidence=$null, [string]$ExpectedStatusParserSha256='',
    [object]$DiagnosticWriteChoice=$false
    )
    # The named API never inherits ambient Apply or coerces raw aliases.
    $Apply=$false
    $OutputWriteState=''
    if($DiagnosticWriteChoice -isnot [bool]) {
        return [pscustomobject]@{pass=$false;ok=$false;authority_granted=$false;packet_id=$PacketId;violation_reason='DIAGNOSTIC_WRITE_CHOICE_REJECTED';diagnostic_write_requested=$false;diagnostic_write_completed=$false;diagnostic_write_error='';requirement_acceptance=$false}
    }
    $Apply=$DiagnosticWriteChoice
    $campaign=@(@('RelayRoot','LogPath','CampaignBinding','BeforeManifest','ControllerMetadataPaths','ChangedPathsEvidence','ExpectedStatusParserSha256') | Where-Object { $PSBoundParameters.ContainsKey($_) }).Count -gt 0
    if (-not $campaign) {
        if(-not $PSBoundParameters.ContainsKey('RunStartUtc')) { throw 'RunStartUtc required for legacy profile.' }
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRootResolved = (Resolve-Path -LiteralPath $RepoRoot).Path
$logPath = Join-Path $repoRootResolved "relay\logs\output_validator.log"
$protectedPaths = @("RISK_POLICY.md", "AGENTS.md", "README.md", "CLAUDE.md", ".git/", ".codex_backups/")

function Convert-ToRelativePath {
    param([string]$Path)
    $base = $repoRootResolved.TrimEnd("\") + "\"
    return $Path.Substring($base.Length).Replace("\", "/")
}

function Test-UnderPattern {
    param([string]$RelativePath, [string[]]$Patterns)
    foreach ($pattern in $Patterns) {
        $clean = ([string]$pattern).Replace("\", "/").TrimStart("./")
        if ([string]::IsNullOrWhiteSpace($clean)) { continue }
        if ($RelativePath.Equals($clean, [StringComparison]::OrdinalIgnoreCase) -or
            $RelativePath.StartsWith($clean.TrimEnd("/") + "/", [StringComparison]::OrdinalIgnoreCase) -or
            ($clean.EndsWith("/") -and $RelativePath.StartsWith($clean, [StringComparison]::OrdinalIgnoreCase))) {
            return $true
        }
    }
    return $false
}

$protectedAllowed = @($AllowedPaths | Where-Object { Test-UnderPattern -RelativePath $_ -Patterns $protectedPaths })
$touched = @(Get-ChildItem -LiteralPath $repoRootResolved -Recurse -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\.git\\" -and $_.LastWriteTimeUtc -ge $RunStartUtc.ToUniversalTime() } |
    ForEach-Object { Convert-ToRelativePath -Path $_.FullName })

$violations = @($touched | Where-Object { -not (Test-UnderPattern -RelativePath $_ -Patterns $AllowedPaths) })
$protectedViolations = @($touched | Where-Object { Test-UnderPattern -RelativePath $_ -Patterns $protectedPaths })

$payload = [ordered]@{
    pass = ($protectedAllowed.Count -eq 0 -and $violations.Count -eq 0 -and $protectedViolations.Count -eq 0)
    packet_id = $PacketId
    touched = @($touched)
    violations = @($violations)
    protected_violations = @($protectedViolations + $protectedAllowed)
    violation_reason = if (($protectedViolations.Count + $protectedAllowed.Count) -gt 0) { "PROTECTED_PATH_TOUCHED" } elseif ($violations.Count -gt 0) { "OUTPUT_OUTSIDE_ALLOWED_PATHS" } else { "" }
    checked_at_utc = (Get-Date).ToUniversalTime()
    authority_granted = $false
    requirement_acceptance = $false
    diagnostic_write_requested = $Apply
    diagnostic_write_completed = $false
    diagnostic_write_error = ''
}

$OutputWriteState='READY_TO_WRITE_DIAGNOSTIC'
if ($Apply -and $OutputWriteState -ceq 'READY_TO_WRITE_DIAGNOSTIC') {
    try {
        Write-AiOsOutputLegacyLine -Path $logPath -RepoRoot $repoRootResolved -Line ($payload | ConvertTo-Json -Compress -Depth 8) -DiagnosticWriteChoice $Apply -OutputWriteState $OutputWriteState
        $payload['diagnostic_write_completed']=$true
    } catch { $payload['diagnostic_write_error']=[string]::new($_.Exception.Message.ToCharArray()) }
}

return [pscustomobject]$payload

    }

    $binding=$null
    try {
        $binding=Get-AiOsOutputBinding $CampaignBinding
        if($PacketId -cne $binding.packet_id) { throw 'Packet identity mismatch.' }
        $root=Resolve-AiOsOutputLocalPath $RepoRoot
        if(-not [IO.Directory]::Exists($root)) { throw 'Repository root missing.' }
        $relay=Resolve-AiOsOutputLocalPath $RelayRoot -Under $root
        $log=Resolve-AiOsOutputLocalPath $LogPath -Under $relay
        if($null -eq $BeforeManifest -or $BeforeManifest -is [string] -or $BeforeManifest -is [array]) { throw 'BeforeManifest object required.' }
        $keys=if($BeforeManifest -is [Collections.IDictionary]) { @($BeforeManifest.Keys) } else { @($BeforeManifest.PSObject.Properties.Name) }
        $before=@{}
        foreach($name in $keys) {
            [void](Resolve-AiOsOutputRelativeFile $root $name)
            if($before.ContainsKey($name)) { throw 'Duplicate manifest path.' }
            if($BeforeManifest -is [Collections.IDictionary]) { $value=$BeforeManifest[$name] }
            else { $value=$BeforeManifest.PSObject.Properties[$name].Value }
            if($null -ne $value -and ($value -isnot [string] -or $value -cnotmatch '^[0-9a-f]{64}$')) { throw 'Manifest value must be SHA256 or null.' }
            $before[$name]=$value
        }
        foreach($path in @($AllowedPaths)+@($ControllerMetadataPaths)) {
            [void](Resolve-AiOsOutputRelativeFile $root $path)
            if(-not $before.ContainsKey($path)) { throw 'Allowed/metadata path not covered by before manifest.' }
        }
        if ($null -eq $ChangedPathsEvidence -or $ChangedPathsEvidence -is [string] -or $ChangedPathsEvidence -is [array]) { throw 'Changed paths evidence object required.' }
        if($ChangedPathsEvidence -is [Collections.IDictionary]) {
            $evidenceCopy=[ordered]@{}
            foreach($key in $ChangedPathsEvidence.Keys) { $evidenceCopy[$key]=$ChangedPathsEvidence[$key] }
            $ChangedPathsEvidence=[pscustomobject]$evidenceCopy
        }
        foreach($field in @('complete','repo_root','parser_source_sha256','before_paths','after_paths','errors')) {
            if(-not $ChangedPathsEvidence.PSObject.Properties[$field]) { throw 'Changed paths evidence field missing.' }
        }
        if($ChangedPathsEvidence.complete -isnot [bool] -or -not $ChangedPathsEvidence.complete -or $ChangedPathsEvidence.errors -isnot [array] -or @($ChangedPathsEvidence.errors).Count -ne 0) { throw 'Changed paths evidence incomplete.' }
        if($ChangedPathsEvidence.repo_root -isnot [string] -or -not [string]::Equals((Resolve-AiOsOutputLocalPath $ChangedPathsEvidence.repo_root),$root,[StringComparison]::OrdinalIgnoreCase)) { throw 'Changed paths repository mismatch.' }
        if($ExpectedStatusParserSha256 -cnotmatch '^[0-9a-f]{64}$' -or $ChangedPathsEvidence.parser_source_sha256 -isnot [string] -or $ChangedPathsEvidence.parser_source_sha256 -cne $ExpectedStatusParserSha256) { throw 'Changed paths parser source mismatch.' }
        if($ChangedPathsEvidence.before_paths -isnot [array] -or $ChangedPathsEvidence.after_paths -isnot [array]) { throw 'Raw parser endpoint arrays required.' }
        foreach($endpoint in @($ChangedPathsEvidence.before_paths)+@($ChangedPathsEvidence.after_paths)) {
            if($endpoint -isnot [string]) { throw 'Raw parser endpoint string required.' }
            [void](Resolve-AiOsOutputRelativeFile $root $endpoint)
            if(-not $before.ContainsKey($endpoint)) { throw 'Changed endpoint outside covered inventory.' }
        }
        $after=Get-AiOsWorkerOutputManifest -RepoRoot $root -SourcePaths @($keys)
        $touched=@($keys | Where-Object { $before[$_] -cne $after[$_] })
        $protected=@('AGENTS.md','README.md','RISK_POLICY.md','CLAUDE.md')
        $protectedViolations=@($touched | Where-Object { $_ -in $protected })+@($AllowedPaths | Where-Object { $_ -in $protected })
        $metadataViolations=@($touched | Where-Object { $_ -in $ControllerMetadataPaths })
        $violations=@($touched | Where-Object { $_ -notin $AllowedPaths -or $_ -in $ControllerMetadataPaths })
        $reason=if($protectedViolations.Count) { 'PROTECTED_PATH_TOUCHED' } elseif($metadataViolations.Count) { 'CONTROLLER_METADATA_CHANGED_BY_PROVIDER' } elseif($violations.Count) { 'OUTPUT_OUTSIDE_ALLOWED_PATHS' } else { '' }
        $payload=[pscustomobject]@{pass=($reason -eq '');ok=($reason -eq '');binding=$binding;authority_granted=$false;packet_id=$PacketId;touched=@($touched);violations=@($violations);protected_violations=@($protectedViolations);controller_metadata_violations=@($metadataViolations);violation_reason=$reason;checked_at_utc=[datetime]::UtcNow.ToString('o');coverage='EXPLICIT_NONPRIVATE_INVENTORY_AND_VERIFIED_RAW_STATUS_ENDPOINTS';requirement_acceptance=$false;diagnostic_write_requested=$Apply;diagnostic_write_completed=$false;diagnostic_write_error=''}
        $OutputWriteState='READY_TO_WRITE_DIAGNOSTIC'
        if ($Apply -and $OutputWriteState -ceq 'READY_TO_WRITE_DIAGNOSTIC') {
            try {
                Write-AiOsOutputBoundLine -Path $log -RelayRoot $relay -Line ($payload | ConvertTo-Json -Compress -Depth 6) -DiagnosticWriteChoice $Apply -OutputWriteState $OutputWriteState
                $payload.diagnostic_write_completed=$true
            } catch { $payload.diagnostic_write_error=[string]::new($_.Exception.Message.ToCharArray()) }
        }
        return $payload
    } catch {
        return [pscustomobject]@{pass=$false;ok=$false;binding=$binding;authority_granted=$false;packet_id=$PacketId;touched=@();violations=@();protected_violations=@();violation_reason='OUTPUT_EVIDENCE_OR_IO_REJECTED';detail=$_.Exception.Message;requirement_acceptance=$false;diagnostic_write_requested=$Apply;diagnostic_write_completed=$false;diagnostic_write_error=''}
    }

}
# Translate the sole direct-entry switch into the named API's raw bool choice.
$arguments=@{}
foreach($name in $PSBoundParameters.Keys) { if($name -cne 'Apply') { $arguments[$name]=$PSBoundParameters[$name] } }
Test-AiOsWorkerOutput @arguments -DiagnosticWriteChoice ([bool]$Apply.IsPresent)
