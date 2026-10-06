from pathlib import Path


WRAPPER = Path("scripts/forex_delivery/Run-AiOsProfitabilityDataClosure.HUMAN_ONLY.ps1")
PRACTICE = Path("scripts/forex_delivery/Acquire-AiOsOandaPracticeHistory.HUMAN_ONLY.ps1")
OFFICIAL = Path("scripts/forex_delivery/Download-AiOsOfficialForexResearchData.HUMAN_ONLY.ps1")


def test_wrapper_is_one_human_command_and_chains_helpers_without_secret_args():
    text = WRAPPER.read_text(encoding="utf-8")
    assert "Download-AiOsOfficialForexResearchData.HUMAN_ONLY.ps1" in text
    assert "Acquire-AiOsOandaPracticeHistory.HUMAN_ONLY.ps1" in text
    assert "$PracticeScript" in text
    assert "-Token" not in text
    assert "-Method Post" not in text
    assert "-Method Put" not in text
    assert "-Method Patch" not in text
    assert "-Method Delete" not in text
    assert "secret_value_exposed = $false" in text
    assert "order_attempted = $false" in text


def test_practice_helper_resolves_universe_from_corpus_v2_not_14_pair_constant():
    text = PRACTICE.read_text(encoding="utf-8")
    assert '[string[]]$Instruments = @()' in text
    assert "AIOS_FOREX_M5_CORPUS_V2_STATE.json" in text
    assert "eligible_pairs" in text
    assert "api-fxpractice.oanda.com" in text
    assert "-Method Get" in text


def test_official_helper_uses_packet_022_single_human_inbox():
    text = OFFICIAL.read_text(encoding="utf-8")
    assert ".aios/runtime/forex_official_data_human_inbox" in text
    assert ".aios/runtime/forex_official_data_breakthrough_v1/human_download_inbox" not in text
