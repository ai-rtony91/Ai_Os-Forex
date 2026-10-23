from automation.forex_engine import forex_repaired_family_evidence_v2 as rerun


def test_score_repaired_evidence_uses_certified_families_and_classifies_failures():
    registry = [
        {"candidate_id": "A_LONG", "family": "A_TIME_SERIES_MOMENTUM", "direction": "LONG"},
        {"candidate_id": "B_LONG", "family": "B_CROSS_SECTIONAL_FACTOR", "direction": "LONG"},
    ]

    def scorer(candidate, instruments, start, end):
        assert instruments == ["EUR_USD"]
        assert (start, end) == (2005, 2018)
        return {
            "candidate_id": candidate["candidate_id"],
            "family": candidate["family"],
            "direction": candidate["direction"],
            "summary": {
                "trades": 60,
                "expectancy": -0.2,
                "profit_factor": 0.8,
                "max_drawdown_percent": 20,
                "win_rate": 0.2,
                "folds": {"positive_fold_share": 0.25},
                "pass": False,
            },
            "records": [{"r": -1.0}] * 60,
        }

    rows = rerun.score_repaired_evidence(
        registry,
        ["EUR_USD"],
        scorer,
        {"A_TIME_SERIES_MOMENTUM"},
    )

    assert len(rows) == 1
    assert rows[0]["candidate_id"] == "A_LONG"
    assert rows[0]["gross_expectancy"] is None
    assert "NO_GROSS_SIGNAL_EDGE_UNDER_PACKET027_NET_R_SCORER" in rows[0]["failure_classes"]
    assert "REGIME_INSTABILITY" in rows[0]["failure_classes"]
