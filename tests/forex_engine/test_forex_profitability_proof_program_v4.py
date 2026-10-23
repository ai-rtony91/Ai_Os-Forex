from automation.forex_engine import forex_profitability_proof_program_v4 as module


def test_falsifiability_controls_promote_positive_and_reject_negative():
    state = module.run_falsifiability_controls()
    assert state["status"] == "PASS"
    assert all(row["promoted"] for row in state["positive_controls"].values())
    assert all(row["rejected"] for row in state["negative_controls"].values())
    assert state["long_short_isolation"] == "PASS"
    assert state["leakage_rejection"] == "PASS"


def test_behavior_fingerprint_detects_equivalent_candidates():
    candidate = {
        "direction": "LONG",
        "economic_mechanism": "X",
        "entry": "next",
        "initial_stop": "1R",
        "target": "3R",
        "maximum_holding_period": "D1",
        "feature_list": ["a"],
        "parameters": {"x": 1},
        "track_name": "t",
        "cost_mode": "bidask",
    }
    assert module.behavior_fingerprint(candidate) == module.behavior_fingerprint(dict(candidate))


def test_pair_universe_uses_corpus_v2_broad_universe():
    universe = module.resolve_pair_universe()
    assert universe["intended_count"] >= 60
    assert universe["narrowing_review"] == "PASS"
