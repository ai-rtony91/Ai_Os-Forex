from pathlib import Path


def test_human_only_scripts_do_not_collect_credentials_or_run_network_clients():
    for script in [
        Path("scripts/forex_delivery/Prepare-AiOsOfficialDataDrop.HUMAN_ONLY.ps1"),
        Path("scripts/forex_delivery/Import-AiOsOfficialDataDrop.HUMAN_ONLY.ps1"),
    ]:
        text = script.read_text(encoding="utf-8").lower()
        assert "invoke-webrequest" not in text
        assert "invoke-restmethod" not in text
        assert "curl" not in text
        assert "password" not in text
        assert "token" not in text
        assert "api_key" not in text


def test_importer_is_inbox_limited_and_hashes_files():
    text = Path("scripts/forex_delivery/Import-AiOsOfficialDataDrop.HUMAN_ONLY.ps1").read_text(encoding="utf-8")
    assert "manual_drop_inbox" in text
    assert "Get-FileHash" in text
    assert "MANUAL_DROP_IMPORT_BLOCKED" in text
    assert "network_automation = $false" in text
