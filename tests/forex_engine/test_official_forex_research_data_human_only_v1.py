import re
from pathlib import Path


SCRIPT = Path("scripts/forex_delivery/Download-AiOsOfficialForexResearchData.HUMAN_ONLY.ps1")


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_official_downloader_has_bounded_transport_ladder():
    text = _script_text()
    assert "Invoke-AiOsIwrDownload" in text
    assert "Invoke-AiOsCurlDownload" in text
    assert "Invoke-AiOsHttpClientDownload" in text
    assert '$transports = @("IWR", "CURL", "HTTPCLIENT")' in text
    assert "[int]$MaxAttemptsPerTransport = 3" in text
    assert "$MaxAttemptsPerTransport -gt 3" in text
    assert "--fail" in text
    assert "--location" in text
    assert "--silent" in text
    assert "--show-error" in text
    assert "--connect-timeout" in text
    assert "--max-time" in text
    assert "Expand-AiOsManifestItems" in text
    assert "official_url_template" in text


def test_official_downloader_classifies_transient_failure_for_fallback():
    text = _script_text()
    assert "Get-AiOsFailureClass" in text
    assert "underlying connection was closed" in text
    assert "unexpected error occurred on a receive" in text
    assert "timeout" in text
    assert "http 429" in text
    assert "http 503" in text
    assert "STATUS=FAILED_$lastClass" in text


def test_official_downloader_uses_atomic_temp_then_validate_then_promote():
    text = _script_text()
    temp_index = text.index("$tempPath = Join-Path")
    validate_index = text.index("Test-AiOsExpectedContent -Path $tempPath")
    move_index = text.index("Move-Item -LiteralPath $tempPath -Destination $Destination -Force")
    assert temp_index < validate_index < move_index
    assert "Remove-Item -LiteralPath $tempPath -Force" in text
    assert "Get-AiOsArtifactHash -Path $Destination" in text


def test_official_downloader_reuses_existing_valid_artifact():
    text = _script_text()
    assert "Test-AiOsExpectedContent -Path $Destination" in text
    assert "TRANSPORT=REUSE" in text
    assert "attempt_count = 0" in text


def test_official_downloader_validates_source_and_content_without_private_access():
    text = _script_text()
    assert 'if ($Uri.Scheme -ne "https")' in text
    assert "www.bankofengland.co.uk" in text
    assert "fred.stlouisfed.org" in text
    assert "www.cftc.gov" in text
    assert "www.bls.gov" in text
    assert "secret_required -ne $false" in text
    assert "private_account_required -ne $false" in text
    assert "expected_content_type" in text
    assert "expected_content_markers" in text
    assert "OFFICIAL_ITEM=$Index/$Total" in text


def test_official_downloader_stays_public_get_only_and_broker_free():
    text = _script_text()
    assert "[System.Net.SecurityProtocolType]::Tls12" in text
    assert "--insecure" not in text
    forbidden_methods = re.findall(r"-Method\s+(?!Get\b)\w+", text)
    assert forbidden_methods == []
    assert "fxtrade" not in text
    assert "fxpractice" not in text


def test_official_downloader_rejects_html_misroutes_for_data_files():
    text = _script_text()
    assert "access denied" in text.lower()
    assert "bot activity" in text.lower()
    assert "challenge" in text.lower()
    assert "BEGIN:VCALENDAR" in text
    assert "$bytes[0] -ne 0x50" in text
    assert "$prefix.Contains(\",\")" in text
