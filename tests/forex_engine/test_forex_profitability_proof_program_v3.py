from pathlib import Path

from automation.forex_engine import forex_profitability_proof_program_v3 as module


def test_missing_data_builds_human_gate_and_attack_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ROOT", tmp_path / "runtime")
    monkeypatch.setattr(module, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(module, "REPORT", tmp_path / "report.md")
    monkeypatch.setattr(module, "PIPELINE_STATE", tmp_path / "pipeline.json")
    monkeypatch.setattr(module, "PIPELINE_REPORT", tmp_path / "pipeline.md")
    monkeypatch.setattr(module, "SUPERTREND_STATE", tmp_path / "supertrend.json")
    monkeypatch.setattr(module, "SUPERTREND_REPORT", tmp_path / "supertrend.md")
    monkeypatch.setattr(module, "ATLAS_STATE", tmp_path / "atlas.json")
    monkeypatch.setattr(module, "ATLAS_REPORT", tmp_path / "atlas.md")
    monkeypatch.setattr(module, "SCORE_JSON", tmp_path / "score.json")
    monkeypatch.setattr(module, "SCORE_MD", tmp_path / "score.md")
    monkeypatch.setattr(module, "PRACTICE_HANDOFF", tmp_path / "practice.md")
    monkeypatch.setattr(module, "PRACTICE_HANDOFF_STATE", tmp_path / "practice_state.json")
    monkeypatch.setattr(module, "OFFICIAL_HANDOFF", tmp_path / "official.md")
    monkeypatch.setattr(module, "OFFICIAL_MANIFEST", tmp_path / "manifest.json")
    monkeypatch.setattr(module, "OFFICIAL_INBOX", tmp_path / "official_inbox")
    monkeypatch.setattr(module, "PRACTICE_INBOX", tmp_path / "practice_inbox")
    monkeypatch.setattr(module, "OFFICIAL_SCRIPT", Path("scripts/forex_delivery/Download-AiOsOfficialForexResearchData.HUMAN_ONLY.ps1"))
    monkeypatch.setattr(module, "PRACTICE_SCRIPT", Path("scripts/forex_delivery/Acquire-AiOsOandaPracticeHistory.HUMAN_ONLY.ps1"))
    module.OFFICIAL_MANIFEST.write_text(
        '{"items":[{"source_owner":"CFTC","expected_destination_relative_path":".aios/runtime/forex_official_data_breakthrough_v1/human_download_inbox/CFTC"}]}',
        encoding="utf-8",
    )

    state = module.execute()

    assert state["packet_id"] == "PKT-EAST-FOREX-PROFITABILITY-CLOSURE-021"
    assert state["status"] == "HUMAN_DATA_ACQUISITION_REQUIRED"
    assert state["remaining_authorized_work_count"] == 0
    assert state["data_gates"]["official_missing_count"] == 1
    assert state["data_gates"]["practice_missing"] is True
    assert state["attack_to_finish"][0]["status"] == "WAITING_HUMAN"
    assert state["attack_to_finish"][1]["status"] == "WAITING_HUMAN"


def test_scorecard_keeps_profitability_and_funding_at_zero_before_evidence():
    card = module.scorecard(
        missing_official=[{"source_owner": "BLS"}],
        practice_missing=True,
        external={"external_information_coverage_score": 86, "status": "HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED", "pending_human_download_items": 1},
        market={"capability_score": 0, "status": "HUMAN_PRACTICE_DATA_ACQUISITION_REQUIRED", "blocker": "practice"},
    )

    assert card["LONG_EDGE"]["score"] == 0
    assert card["SHORT_EDGE"]["score"] == 0
    assert card["BIDIRECTIONAL_PAPER"]["score"] == 0
    assert card["FUNDING_READINESS"]["score"] == 0
