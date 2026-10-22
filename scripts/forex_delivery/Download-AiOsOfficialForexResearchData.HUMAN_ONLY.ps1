param(
    [string]$ManifestPath = "Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_HUMAN_DOWNLOAD_MANIFEST_V1.json",
    [string]$InboxPath = ".aios/runtime/forex_official_data_human_inbox",
    [int]$MaxAttemptsPerTransport = 3,
    [int]$ConnectTimeoutSeconds = 20,
    [int]$TotalTimeoutSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Enable-AiOsSafeTls {
    try {
        $protocols = [System.Net.SecurityProtocolType]::Tls12
        if ([Enum]::GetNames([System.Net.SecurityProtocolType]) -contains "Tls13") {
            $protocols = $protocols -bor [System.Net.SecurityProtocolType]::Tls13
        }
        [System.Net.ServicePointManager]::SecurityProtocol = $protocols
    }
    catch {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    }
}

function ConvertTo-AiOsSafeMessage {
    param([AllowNull()][string]$Message)
    if ([string]::IsNullOrWhiteSpace($Message)) {
        return "no message"
    }
    $safe = $Message -replace "[\r\n]+", " "
    if ($safe.Length -gt 280) {
        return $safe.Substring(0, 280)
    }
    return $safe
}

function Get-AiOsFailureClass {
    param([AllowNull()][string]$Message)
    $text = ([string]$Message).ToLowerInvariant()
    $transientMarkers = @(
        "underlying connection was closed",
        "unexpected error occurred on a receive",
        "connection reset",
        "timed out",
        "timeout",
        "temporarily",
        "name resolution",
        "could not resolve",
        "operation canceled",
        "operation cancelled",
        "http 408",
        "http 429",
        "http 500",
        "http 502",
        "http 503",
        "http 504"
    )
    foreach ($marker in $transientMarkers) {
        if ($text.Contains($marker)) {
            return "TRANSIENT"
        }
    }

    $permanentMarkers = @(
        "http 400",
        "http 401",
        "http 403",
        "http 404",
        "schema",
        "wrong official source",
        "hash mismatch"
    )
    foreach ($marker in $permanentMarkers) {
        if ($text.Contains($marker)) {
            return "PERMANENT"
        }
    }

    return "TRANSIENT"
}

function Assert-AiOsOfficialUri {
    param([Parameter(Mandatory = $true)][Uri]$Uri)
    if ($Uri.Scheme -ne "https") {
        throw "AIOS_OFFICIAL_DOWNLOAD_BLOCKED: only https official URLs are allowed"
    }
    $officialHost = $Uri.Host.ToLowerInvariant()
    $allowedHosts = @(
        "www.bankofengland.co.uk",
        "bankofengland.co.uk",
        "fred.stlouisfed.org",
        "www.cftc.gov",
        "cftc.gov",
        "www.bls.gov",
        "bls.gov"
    )
    if ($allowedHosts -notcontains $officialHost) {
        throw "AIOS_OFFICIAL_DOWNLOAD_BLOCKED: unapproved official host $officialHost"
    }
}

function Test-AiOsExpectedContent {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [AllowNull()][string]$ExpectedContentType,
        [AllowNull()][object]$ExpectedContentMarkers
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -le 0) {
        return $false
    }

    $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Path).Path)
    $length = [Math]::Min($bytes.Length, 65536)
    if ($length -le 0) {
        return $false
    }
    $prefix = [System.Text.Encoding]::UTF8.GetString($bytes, 0, $length)
    $prefixLower = $prefix.ToLowerInvariant()

    $htmlMisrouteMarkers = @(
        "<html",
        "<!doctype html",
        "access denied",
        "akamai",
        "bot activity",
        "robots",
        "consent",
        "captcha",
        "challenge"
    )
    foreach ($marker in $htmlMisrouteMarkers) {
        if ($prefixLower.Contains($marker)) {
            return $false
        }
    }

    $expected = ([string]$ExpectedContentType).ToLowerInvariant()
    if ($expected.Contains("html")) {
        return ($prefixLower.Contains("<html") -or $prefixLower.Contains("<!doctype") -or $prefixLower.Contains("<head") -or $prefixLower.Contains("<body"))
    }

    if ($expected.Contains("csv")) {
        if ($prefixLower.Contains("<html") -or -not $prefix.Contains(",")) {
            return $false
        }
    }
    elseif ($expected.Contains("zip")) {
        if ($bytes.Length -lt 4 -or $bytes[0] -ne 0x50 -or $bytes[1] -ne 0x4b) {
            return $false
        }
    }
    elseif ($expected.Contains("calendar") -or $expected.Contains("ics")) {
        if (-not $prefix.Contains("BEGIN:VCALENDAR")) {
            return $false
        }
    }

    if ($null -ne $ExpectedContentMarkers) {
        foreach ($marker in @($ExpectedContentMarkers)) {
            $markerText = [string]$marker
            if (-not [string]::IsNullOrWhiteSpace($markerText) -and -not $prefix.Contains($markerText)) {
                return $false
            }
        }
    }

    return $true
}

function Get-AiOsArtifactHash {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-AiOsOptionalProperty {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Expand-AiOsManifestItems {
    param([Parameter(Mandatory = $true)][object[]]$Items)
    $expanded = @()
    foreach ($item in $Items) {
        $yearStart = Get-AiOsOptionalProperty -Object $item -Name "artifact_year_start"
        $yearEnd = Get-AiOsOptionalProperty -Object $item -Name "artifact_year_end"
        $urlTemplate = Get-AiOsOptionalProperty -Object $item -Name "official_url_template"
        $destinationTemplate = Get-AiOsOptionalProperty -Object $item -Name "expected_destination_template"
        if ($null -ne $yearStart -and $null -ne $yearEnd -and -not [string]::IsNullOrWhiteSpace([string]$urlTemplate) -and -not [string]::IsNullOrWhiteSpace([string]$destinationTemplate)) {
            for ($year = [int]$yearStart; $year -le [int]$yearEnd; $year++) {
                $copy = [ordered]@{}
                foreach ($property in $item.PSObject.Properties) {
                    if (@("artifact_year_start", "artifact_year_end", "official_url_template", "expected_destination_template") -notcontains $property.Name) {
                        $copy[$property.Name] = $property.Value
                    }
                }
                $copy["artifact_id"] = "$($item.artifact_id)_$year"
                $copy["official_url"] = ([string]$urlTemplate).Replace("{year}", [string]$year)
                $copy["expected_destination_relative_path"] = ([string]$destinationTemplate).Replace("{year}", [string]$year)
                $copy["expected_time_period"] = [string]$year
                $expanded += [pscustomobject]$copy
            }
        }
        else {
            $expanded += $item
        }
    }
    return $expanded
}

function Invoke-AiOsIwrDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$TempPath,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )
    Invoke-WebRequest -Uri $Uri -Method Get -OutFile $TempPath -UseBasicParsing -MaximumRedirection 5 -TimeoutSec $TimeoutSeconds | Out-Null
}

function Invoke-AiOsCurlDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$TempPath,
        [Parameter(Mandatory = $true)][int]$ConnectTimeout,
        [Parameter(Mandatory = $true)][int]$MaxTime
    )
    $curl = Get-Command -Name "curl.exe" -ErrorAction SilentlyContinue
    if ($null -eq $curl) {
        throw "curl.exe unavailable"
    }
    $output = & $curl.Source --fail --location --silent --show-error --connect-timeout $ConnectTimeout --max-time $MaxTime --output $TempPath $Uri 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "curl.exe failed: $(ConvertTo-AiOsSafeMessage -Message ([string]$output))"
    }
}

function Invoke-AiOsHttpClientDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$TempPath,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )
    Add-Type -AssemblyName System.Net.Http
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $client = [System.Net.Http.HttpClient]::new($handler)
    try {
        $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
        $response = $client.GetAsync($Uri).GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            throw "HTTP $([int]$response.StatusCode)"
        }
        $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $file = [System.IO.File]::Create((Resolve-Path -LiteralPath (Split-Path -Parent $TempPath)).Path + [System.IO.Path]::DirectorySeparatorChar + (Split-Path -Leaf $TempPath))
        try {
            $stream.CopyTo($file)
        }
        finally {
            $file.Dispose()
            $stream.Dispose()
        }
    }
    finally {
        $client.Dispose()
        $handler.Dispose()
    }
}

function Invoke-AiOsOfficialDownload {
    param(
        [Parameter(Mandatory = $true)]$Item,
        [Parameter(Mandatory = $true)][int]$Index,
        [Parameter(Mandatory = $true)][int]$Total,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][int]$MaxAttempts,
        [Parameter(Mandatory = $true)][int]$ConnectTimeout,
        [Parameter(Mandatory = $true)][int]$MaxTime
    )

    $uri = [Uri]$Item.official_url
    Assert-AiOsOfficialUri -Uri $uri
    $expectedMarkers = Get-AiOsOptionalProperty -Object $Item -Name "expected_content_markers"

    if (Test-AiOsExpectedContent -Path $Destination -ExpectedContentType $Item.expected_content_type -ExpectedContentMarkers $expectedMarkers) {
        $hash = Get-AiOsArtifactHash -Path $Destination
        Write-Host "OFFICIAL_ITEM=$Index/$Total SOURCE_ID=$($Item.source_family_purpose) TRANSPORT=REUSE ATTEMPT=0/$MaxAttempts STATUS=COMPLETE"
        return [pscustomobject]@{
            source_id = $Item.source_family_purpose
            official_url = $uri.AbsoluteUri
            destination = $Destination
            transport_used = "REUSE"
            attempt_count = 0
            file_size = (Get-Item -LiteralPath $Destination).Length
            sha256 = $hash
            validation_result = "PASS"
            failure_classification = "NONE"
        }
    }

    $transports = @("IWR", "CURL", "HTTPCLIENT")
    $attemptTotal = 0
    $lastFailure = "not attempted"
    $lastClass = "TRANSIENT"

    foreach ($transport in $transports) {
        for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
            $attemptTotal += 1
            $leaf = Split-Path -Leaf $Destination
            $tempPath = Join-Path (Split-Path -Parent $Destination) (".$leaf.$([Guid]::NewGuid().ToString('N')).tmp")
            Write-Host "OFFICIAL_ITEM=$Index/$Total SOURCE_ID=$($Item.source_family_purpose) TRANSPORT=$transport ATTEMPT=$attempt/$MaxAttempts STATUS=DOWNLOADING"
            try {
                if ($transport -eq "IWR") {
                    Invoke-AiOsIwrDownload -Uri $uri.AbsoluteUri -TempPath $tempPath -TimeoutSeconds $MaxTime
                }
                elseif ($transport -eq "CURL") {
                    Invoke-AiOsCurlDownload -Uri $uri.AbsoluteUri -TempPath $tempPath -ConnectTimeout $ConnectTimeout -MaxTime $MaxTime
                }
                else {
                    Invoke-AiOsHttpClientDownload -Uri $uri.AbsoluteUri -TempPath $tempPath -TimeoutSeconds $MaxTime
                }

                Write-Host "OFFICIAL_ITEM=$Index/$Total SOURCE_ID=$($Item.source_family_purpose) TRANSPORT=$transport ATTEMPT=$attempt/$MaxAttempts STATUS=VALIDATING"
                if (-not (Test-AiOsExpectedContent -Path $tempPath -ExpectedContentType $Item.expected_content_type -ExpectedContentMarkers $expectedMarkers)) {
                    throw "schema validation failed for expected content type $($Item.expected_content_type)"
                }
                Move-Item -LiteralPath $tempPath -Destination $Destination -Force
                $hash = Get-AiOsArtifactHash -Path $Destination
                Write-Host "OFFICIAL_ITEM=$Index/$Total SOURCE_ID=$($Item.source_family_purpose) TRANSPORT=$transport ATTEMPT=$attempt/$MaxAttempts STATUS=COMPLETE"
                return [pscustomobject]@{
                    source_id = $Item.source_family_purpose
                    official_url = $uri.AbsoluteUri
                    destination = $Destination
                    transport_used = $transport
                    attempt_count = $attemptTotal
                    file_size = (Get-Item -LiteralPath $Destination).Length
                    sha256 = $hash
                    validation_result = "PASS"
                    failure_classification = "NONE"
                }
            }
            catch {
                $lastFailure = ConvertTo-AiOsSafeMessage -Message $_.Exception.Message
                $lastClass = Get-AiOsFailureClass -Message $lastFailure
                if (Test-Path -LiteralPath $tempPath) {
                    Remove-Item -LiteralPath $tempPath -Force
                }
                Write-Host "OFFICIAL_ITEM=$Index/$Total SOURCE_ID=$($Item.source_family_purpose) TRANSPORT=$transport ATTEMPT=$attempt/$MaxAttempts STATUS=FAILED_$lastClass"
                if ($lastClass -eq "PERMANENT") {
                    break
                }
                Start-Sleep -Seconds ([Math]::Min($attempt, 3))
            }
        }
        if ($lastClass -eq "PERMANENT") {
            break
        }
    }

    throw "AIOS_HUMAN_ONLY_DOWNLOAD_BLOCKED: official artifact failed after $attemptTotal attempts; class=$lastClass; error=$lastFailure"
}

if ($MaxAttemptsPerTransport -lt 1 -or $MaxAttemptsPerTransport -gt 3) {
    throw "AIOS_HUMAN_ONLY_DOWNLOAD_BLOCKED: MaxAttemptsPerTransport must be 1..3"
}
if ($ConnectTimeoutSeconds -lt 5 -or $ConnectTimeoutSeconds -gt 60) {
    throw "AIOS_HUMAN_ONLY_DOWNLOAD_BLOCKED: ConnectTimeoutSeconds must be 5..60"
}
if ($TotalTimeoutSeconds -lt 30 -or $TotalTimeoutSeconds -gt 600) {
    throw "AIOS_HUMAN_ONLY_DOWNLOAD_BLOCKED: TotalTimeoutSeconds must be 30..600"
}

$expectedInbox = ".aios/runtime/forex_official_data_human_inbox"
if ($InboxPath.Replace("\", "/").TrimEnd("/") -ne $expectedInbox) {
    throw "AIOS_HUMAN_ONLY_DOWNLOAD_BLOCKED: destination must be $expectedInbox"
}

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    throw "AIOS_HUMAN_ONLY_DOWNLOAD_BLOCKED: manifest not found"
}

Enable-AiOsSafeTls
$manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $InboxPath | Out-Null

$items = @(Expand-AiOsManifestItems -Items @($manifest.items))
$hashes = @()
for ($i = 0; $i -lt $items.Count; $i++) {
    $item = $items[$i]
    if ($item.secret_required -ne $false -or $item.private_account_required -ne $false) {
        throw "AIOS_HUMAN_ONLY_DOWNLOAD_BLOCKED: manifest item requested private access"
    }
    $destinationName = Split-Path -Leaf ([string]$item.expected_destination_relative_path)
    if ([string]::IsNullOrWhiteSpace($destinationName)) {
        throw "AIOS_HUMAN_ONLY_DOWNLOAD_BLOCKED: invalid destination name"
    }
    $destination = Join-Path $InboxPath $destinationName
    $hashes += Invoke-AiOsOfficialDownload -Item $item -Index ($i + 1) -Total $items.Count -Destination $destination -MaxAttempts $MaxAttemptsPerTransport -ConnectTimeout $ConnectTimeoutSeconds -MaxTime $TotalTimeoutSeconds
}

[pscustomobject]@{
    schema = "AIOS_OFFICIAL_FOREX_RESEARCH_DATA_HUMAN_ONLY_DOWNLOAD_RESULT_V1"
    status = "OFFICIAL_DATA_READY"
    artifact_count = $hashes.Count
    artifacts = $hashes
    secret_required = $false
    private_account_required = $false
    broker_request = $false
    live_host_contacted = $false
    order_attempted = $false
} | ConvertTo-Json -Depth 8
