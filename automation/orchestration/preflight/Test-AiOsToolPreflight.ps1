[CmdletBinding()]
param(
    [string[]]$Tools=@('codex','claude','gh','git'),
    [ValidateRange(1,300)][int]$VersionTimeoutSec=10,
    [string]$RepoRoot='', [string]$RelayRoot='', [string]$LogPath='', [object]$CampaignBinding=$null
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'

function Resolve-AiOsPreflightLocalPath {
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
        $base=Resolve-AiOsPreflightLocalPath -Path $Under
        if (-not $full.StartsWith($base.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Path escapes selected root.' }
    }
    return $full
}

function Get-AiOsPreflightBinding {
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

function Write-AiOsPreflightBoundLine {
    param([string]$Path,[string]$RelayRoot,[string]$Line)
    $target=Resolve-AiOsPreflightLocalPath -Path $Path -Under $RelayRoot
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
    $target=Resolve-AiOsPreflightLocalPath -Path $target -Under $RelayRoot
    $stream=[IO.File]::Open($target,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try { $bytes=[Text.UTF8Encoding]::new($false).GetBytes($Line+[Environment]::NewLine); $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) }
    finally { $stream.Dispose() }
}

function Test-AiOsToolPreflight {
    [CmdletBinding()]
    param(
    [string[]]$Tools=@('codex','claude','gh','git'),
    [ValidateRange(1,300)][int]$VersionTimeoutSec=10,
    [string]$RepoRoot='', [string]$RelayRoot='', [string]$LogPath='', [object]$CampaignBinding=$null
    )
    $campaign=@(@('RepoRoot','RelayRoot','LogPath','CampaignBinding') | Where-Object { $PSBoundParameters.ContainsKey($_) }).Count -gt 0
    if (-not $campaign) {
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$logPath = Join-Path $repoRoot "relay\logs\preflight.log"
$timeoutHelper = Join-Path $PSScriptRoot "..\timeout\Invoke-AiOsCliWithTimeout.ps1"
$missing = New-Object System.Collections.Generic.List[string]
$unauth = New-Object System.Collections.Generic.List[string]

foreach ($tool in $Tools) {
    $cmd = Get-Command $tool -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        $missing.Add($tool)
        continue
    }

    $result = & $timeoutHelper -FilePath $cmd.Source -ArgumentList @("--version") -TimeoutSec $VersionTimeoutSec -WorkingDirectory $repoRoot
    if ([string]$result.exit_code -ne "0") {
        $unauth.Add($tool)
    }
}

$payload = [ordered]@{
    ok = ($missing.Count -eq 0 -and $unauth.Count -eq 0)
    missing = @($missing)
    unauth = @($unauth)
    checked_at_utc = (Get-Date).ToUniversalTime()
}

$logDir = Split-Path -Parent $logPath
if (-not (Test-Path -LiteralPath $logDir -PathType Container)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
Add-Content -LiteralPath $logPath -Value (($payload | ConvertTo-Json -Compress -Depth 5))

return [pscustomobject]$payload

    }

    $binding=$null
    try {
        $binding=Get-AiOsPreflightBinding $CampaignBinding
        $root=Resolve-AiOsPreflightLocalPath $RepoRoot
        if (-not [IO.Directory]::Exists($root)) { throw 'Repository root missing.' }
        $relay=Resolve-AiOsPreflightLocalPath $RelayRoot -Under $root
        $log=Resolve-AiOsPreflightLocalPath $LogPath -Under $relay
        if (-not $PSBoundParameters.ContainsKey('Tools') -or $Tools.Count -lt 1 -or $Tools.Count -gt 8) { throw 'Select one to eight required tools explicitly.' }
        $timeoutPath=Join-Path $PSScriptRoot '../timeout/Invoke-AiOsCliWithTimeout.ps1'
        $tokens=$null; $errors=$null
        $ast=[Management.Automation.Language.Parser]::ParseFile($timeoutPath,[ref]$tokens,[ref]$errors)
        if($errors.Count) { throw 'Accepted timeout source does not parse.' }
        foreach($name in @('Import-AiOsCliProcessPrimitive','Invoke-AiOsCliProcess')) {
            $nodes=@($ast.EndBlock.Statements | Where-Object { $_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq $name })
            if ($nodes.Count -ne 1) { throw 'Accepted timeout source definition missing.' }
            Set-Item -LiteralPath ('Function:'+$name) -Value $nodes[0].Body.GetScriptBlock()
        }
        $missing=@(); $failed=@(); $checks=@()
        foreach($tool in $Tools) {
            $command=Get-Command -Name $tool -CommandType Application,ExternalScript -ErrorAction SilentlyContinue | Select-Object -First 1
            if($null -eq $command) { $missing+=([string]$tool); continue }
            $run=Invoke-AiOsCliProcess -FilePath $command.Source -ArgumentList @('--version') -TimeoutSec $VersionTimeoutSec -WorkingDirectory $root
            $clean=($run.cleanup_state -ceq 'CONFIRMED' -and $run.root_exit_confirmed -is [bool] -and $run.root_exit_confirmed -and $run.tree_exit_confirmed -is [bool] -and $run.tree_exit_confirmed -and $run.drains_completed -is [bool] -and $run.drains_completed -and $run.stdin_writer_joined -is [bool] -and $run.stdin_writer_joined)
            $check=[pscustomobject]@{tool=[string]$tool;executable=[string]$command.Source;exit_code=[string]$run.exit_code;cleanup_state=[string]$run.cleanup_state;root_exit_confirmed=[bool]$run.root_exit_confirmed;tree_exit_confirmed=[bool]$run.tree_exit_confirmed;drains_completed=[bool]$run.drains_completed;stdin_writer_joined=[bool]$run.stdin_writer_joined;timed_out=[bool]$run.timed_out}
            $checks+=$check
            if (-not $clean -or [string]$run.exit_code -cne '0') { $failed+=([string]$tool) }
            if (-not $clean) { break }
        }
        $payload=[pscustomobject]@{ok=($missing.Count -eq 0 -and $failed.Count -eq 0);binding=$binding;authority_granted=$false;missing=@($missing);version_failed=@($failed);unauth=@();authentication_checked=$false;checks=@($checks);checked_at_utc=[datetime]::UtcNow.ToString('o');reason=''}
        Write-AiOsPreflightBoundLine $log $relay ($payload | ConvertTo-Json -Compress -Depth 6)
        return $payload
    } catch {
        return [pscustomobject]@{ok=$false;binding=$binding;authority_granted=$false;missing=@();version_failed=@();unauth=@();authentication_checked=$false;checks=@();reason='HELPER_INPUT_OR_IO_REJECTED';detail=$_.Exception.Message}
    }

}
Test-AiOsToolPreflight @PSBoundParameters
