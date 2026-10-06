param(
    [string]$InboxPath = ".aios/runtime/forex_institutional_data_breakthrough_v1/manual_drop_inbox",
    [string]$OutputPath = ".aios/runtime/forex_institutional_data_breakthrough_v1/manual_drop_manifest.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolvedInbox = Resolve-Path -LiteralPath $InboxPath -ErrorAction Stop
$allowedRoot = (Resolve-Path -LiteralPath ".aios/runtime/forex_institutional_data_breakthrough_v1").Path

if (-not $resolvedInbox.Path.StartsWith($allowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "MANUAL_DROP_IMPORT_BLOCKED: inbox must stay inside Packet 016 runtime root."
}

$allowedExtensions = @(".csv", ".zip", ".xlsx", ".json", ".txt", ".ics", ".html")
$files = Get-ChildItem -LiteralPath $resolvedInbox.Path -File | Sort-Object Name
$items = @()

foreach ($file in $files) {
    if ($allowedExtensions -notcontains $file.Extension.ToLowerInvariant()) {
        throw "MANUAL_DROP_IMPORT_BLOCKED: unsupported file type $($file.Extension)"
    }
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName
    $items += [pscustomobject]@{
        name = $file.Name
        extension = $file.Extension.ToLowerInvariant()
        length = $file.Length
        sha256 = $hash.Hash.ToLowerInvariant()
        provenance = "HUMAN_PLACED_PUBLIC_OFFICIAL_FILE_UNVERIFIED_BY_CODEX"
    }
}

$manifest = [pscustomobject]@{
    schema = "AIOS_FOREX_OFFICIAL_DATA_DROP_IMPORT_MANIFEST_V1"
    status = "IMPORTED_FOR_VALIDATION"
    inbox = $resolvedInbox.Path
    file_count = $items.Count
    files = $items
    credential_collection = $false
    network_automation = $false
}

$json = $manifest | ConvertTo-Json -Depth 8
$outDir = Split-Path -Parent $OutputPath
if (-not [string]::IsNullOrWhiteSpace($outDir)) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}
$json | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Write-Output $json
