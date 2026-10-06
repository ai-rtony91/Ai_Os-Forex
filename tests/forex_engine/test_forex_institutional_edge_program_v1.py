from automation.forex_engine import forex_institutional_edge_program_v1 as module


def test_scorecard_has_separate_critical_capability_scores():
    acquisition = {"external_information_coverage_score": 55, "status": "HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED"}
    corpus = {"frozen": False}
    market = {"capability_score": 0}
    scorecard = module.build_scorecard(acquisition, corpus, market)
    expected = {
        "EXECUTION_INTEGRITY",
        "COST_ACCOUNTING_INTEGRITY",
        "MARKET_CORPUS_REGIME_COVERAGE",
        "EXTERNAL_INFORMATION_COVERAGE",
        "POINT_IN_TIME_INTEGRITY",
        "MECHANISM_RESEARCH_COVERAGE",
        "STATISTICAL_PROOF",
        "FORWARD_PROOF",
        "PAPER_PROFITABILITY",
        "LIVE_AND_FUNDING_READINESS",
    }
    assert set(scorecard) == expected
    assert scorecard["FORWARD_PROOF"]["score"] == 0
    assert scorecard["LIVE_AND_FUNDING_READINESS"]["score"] == 0


def test_registry_preview_caps_at_48_and_requires_frozen_corpus_for_eligibility():
    registry = module.hypothesis_registry({"status": "HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED"})
    assert registry["hypothesis_count"] == 48
    assert not any(item["data_eligible"] for item in registry["hypotheses"])
    assert {item["track"] for item in registry["hypotheses"]} == set(range(1, 9))


def test_failure_memory_flattens_source_fields():
    state = {"sources": ["A"], "nested": {"usable_families": ["B"]}}
    assert sorted(module._flatten_sources(state)) == ["A", "B"]
