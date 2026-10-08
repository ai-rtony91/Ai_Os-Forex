from pathlib import Path


SCRIPT = Path("scripts/forex_delivery/Download-AiOsOfficialForexResearchData.HUMAN_ONLY.ps1")


def test_human_download_script_is_get_only_and_credential_free():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Invoke-WebRequest" in text
    assert "-Method Get" in text
    assert "Credential" not in text
    assert "POST" not in text.upper()
    assert "human_download_inbox" in text
