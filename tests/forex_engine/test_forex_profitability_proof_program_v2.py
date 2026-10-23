from automation.forex_engine import forex_profitability_proof_program_v2 as module


def test_synthetic_controls_preview_declares_positive_and_negative_controls():
    controls = module.synthetic_controls_preview()
    assert len(controls["positive_controls"]) == 6
    assert len(controls["negative_controls"]) == 6
    assert controls["status"] == "NOT_RUN_DATA_BLOCKED"


def test_scorecard_keeps_long_short_and_funding_unproven():
    card = module.scorecard(
        {"status": "HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED", "remaining_human_download_items": [1]},
        {"status": "HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED", "external_information_coverage_score": 86, "pending_human_download_items": 3},
        {"status": "HUMAN_PRACTICE_DATA_ACQUISITION_REQUIRED", "capability_score": 0, "blocker": "practice"},
        {"script_sha256": "abc"},
    )
    assert card["LONG_HISTORICAL_EDGE"]["score"] == 0
    assert card["SHORT_HISTORICAL_EDGE"]["score"] == 0
    assert card["FUNDING_READINESS"]["score"] == 0
