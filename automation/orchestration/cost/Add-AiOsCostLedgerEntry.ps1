[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$CycleId,
    [decimal]$Cost=0, [int]$InputTokens=0, [int]$OutputTokens=0,
    [string]$PacketId='', [string]$Worker='', [bool]$Estimated=$false, [string]$EstimateReason='',
    [string]$RepoRoot='', [string]$RelayRoot='', [string]$LedgerPath='', [object]$CampaignBinding=$null
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'

function Resolve-AiOsCostLocalPath {
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
        $base=Resolve-AiOsCostLocalPath -Path $Under
        if (-not $full.StartsWith($base.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Path escapes selected root.' }
    }
    return $full
}

function Get-AiOsCostBinding {
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

function Write-AiOsCostBoundLine {
    param([string]$Path,[string]$RelayRoot,[string]$Line)
    $target=Resolve-AiOsCostLocalPath -Path $Path -Under $RelayRoot
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
    $target=Resolve-AiOsCostLocalPath -Path $target -Under $RelayRoot
    $stream=[IO.File]::Open($target,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try { $bytes=[Text.UTF8Encoding]::new($false).GetBytes($Line+[Environment]::NewLine); $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) }
    finally { $stream.Dispose() }
}

function Add-AiOsCostLedgerEntry {
    [CmdletBinding()]
    param(
    [Parameter(Mandatory=$true)][string]$CycleId,
    [decimal]$Cost=0, [int]$InputTokens=0, [int]$OutputTokens=0,
    [string]$PacketId='', [string]$Worker='', [bool]$Estimated=$false, [string]$EstimateReason='',
    [string]$RepoRoot='', [string]$RelayRoot='', [string]$LedgerPath='', [object]$CampaignBinding=$null
    )
    $campaign=@(@('RepoRoot','RelayRoot','LedgerPath','CampaignBinding') | Where-Object { $PSBoundParameters.ContainsKey($_) }).Count -gt 0
    if (-not $campaign) {
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$ledger = Join-Path $repoRoot "control\mode\cost_ledger.jsonl"
$entry = [ordered]@{
    utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    date_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
    cycle_id = $CycleId
    packet_id = $PacketId
    worker = $Worker
    cost_usd = [decimal]$Cost
    input_tokens = $InputTokens
    output_tokens = $OutputTokens
    estimated = [bool]$Estimated
    estimate_reason = $EstimateReason
}

$dir = Split-Path -Parent $ledger
if (-not (Test-Path -LiteralPath $dir -PathType Container)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
Add-Content -LiteralPath $ledger -Value (($entry | ConvertTo-Json -Compress -Depth 5))
return [pscustomobject]$entry

    }

    $binding=$null
    try {
        $binding=Get-AiOsCostBinding $CampaignBinding
        $root=Resolve-AiOsCostLocalPath $RepoRoot
        if (-not [IO.Directory]::Exists($root)) { throw 'Repository root missing.' }
        $relay=Resolve-AiOsCostLocalPath $RelayRoot -Under $root
        $ledger=Resolve-AiOsCostLocalPath $LedgerPath -Under $relay
        if($PacketId -cne $binding.packet_id -or $Cost -lt 0 -or $InputTokens -lt 0 -or $OutputTokens -lt 0 -or ($Estimated -and $Cost -le 0)) { throw 'Invalid bound cost or nonzero estimate required.' }
        $entry=[pscustomobject]@{utc=[datetime]::UtcNow.ToString('o');date_utc=[datetime]::UtcNow.ToString('yyyy-MM-dd');cycle_id=$CycleId;packet_id=$PacketId;worker=$Worker;cost_usd=[decimal]$Cost;input_tokens=[int]$InputTokens;output_tokens=[int]$OutputTokens;estimated=[bool]$Estimated;estimate_reason=$EstimateReason;binding=$binding;authority_granted=$false;ok=$true}
        Write-AiOsCostBoundLine $ledger $relay ($entry | ConvertTo-Json -Compress -Depth 5)
        return $entry
    } catch {
        return [pscustomobject]@{ok=$false;binding=$binding;authority_granted=$false;reason='HELPER_INPUT_OR_IO_REJECTED';detail=$_.Exception.Message}
    }

}
Add-AiOsCostLedgerEntry @PSBoundParameters
