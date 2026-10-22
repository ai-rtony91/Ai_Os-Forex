from __future__ import annotations

import json

from automation.forex_engine.forex_p1_experience_learning_loop_v1 import (
    SCHEMA, append_experience_event, build_experience_event, classify_experience,
    config_hash, export_csv, filter_value_scorecard, near_threshold_bucket,
    postmortem_learning_summary, read_experience_ledger, similarity_bucket,
    walk_forward_scorecard, append_cycle_experience, event_from_cycle_record,
    excursion_metrics, simulate_exit_policy, is_completed_bar, distinct_bar_decision,
    rsi_confirmation, mtf_confirmation, post_exit_horizon_returns, trade_quality_metrics,
    run_entry_experiments, run_exit_experiments, write_learning_reports,
)


def event(number: int, source: str, decision: str, outcome: float | None, gate: str = "atr"):
    return build_experience_event(
        experience_id=str(number), event_type="DECISION_OUTCOME", strategy_name="supertrend_pullback_v1",
        strategy_config={"atr_period": 3}, git_commit="abc123", dataset_identity={"window": "fixture"},
        decision_utc=f"2026-01-01T00:0{number}:00Z", production_decision=decision,
        shadow_classification=source, outcome_r=outcome, features={"first_failed_gate": gate, "session_bucket": "LONDON"},
    )


def test_four_way_classification_and_unresolved():
    assert classify_experience(production_decision="ACCEPTED", outcome_r=1) == "TRUE_POSITIVE"
    assert classify_experience(production_decision="ACCEPTED", outcome_r=-1) == "FALSE_POSITIVE"
    assert classify_experience(production_decision="REJECTED", outcome_r=1) == "FALSE_NEGATIVE"
    assert classify_experience(production_decision="REJECTED", outcome_r=-1) == "TRUE_NEGATIVE"
    assert classify_experience(production_decision="REJECTED", outcome_r=None) == "UNRESOLVED"


def test_append_sanitization_hash_and_csv(tmp_path):
    record = event(1, "SHADOW_COUNTERFACTUAL", "REJECTED", 1)
    record["api_token"] = "secret"
    ledger = tmp_path / "ledger.jsonl"
    append_experience_event(ledger, record)
    loaded = read_experience_ledger(ledger)
    assert loaded[0]["schema"] == SCHEMA
    assert loaded[0]["strategy_config_hash"] == config_hash({"atr_period": 3})
    assert "api_token" not in loaded[0]
    assert all(json.loads(line)["schema"] == SCHEMA for line in ledger.read_text().splitlines())
    csv_path = tmp_path / "ledger.csv"
    export_csv(loaded, csv_path)
    assert "outcome_classification" in csv_path.read_text()


def test_scorecard_walkforward_separation_and_similarity():
    records = [event(1, "SHADOW_COUNTERFACTUAL", "REJECTED", 1), event(2, "SHADOW_COUNTERFACTUAL", "REJECTED", -1), event(3, "ACTUAL_PAPER", "ACCEPTED", 1)]
    scorecard = filter_value_scorecard(records)
    assert scorecard["atr"]["would_win"] == 1
    assert scorecard["atr"]["would_lose"] == 1
    assert walk_forward_scorecard(records)["selection_uses_test"] is False
    assert postmortem_learning_summary(records)["mixed_accounting"] is False
    assert near_threshold_bucket(4.9) == "0_5_PERCENT"
    assert near_threshold_bucket(21) == "OVER_20_PERCENT"
    assert similarity_bucket({"volatility_regime": "NORMAL", "session_bucket": "LONDON", "supertrend_age_bucket": 3, "spread_risk_bucket": "LOW"}) == "NORMAL|LONDON|3|LOW"


def test_cycle_adapter_is_deduplicated_and_preserves_lifecycle(tmp_path):
    record = {"campaign_identity": "c", "cycle_number": 1, "cycle_action": "PAPER_SESSION_OPEN",
              "cycle_completed_utc": "2026-01-01T00:05:00Z", "strategy_name": "supertrend_pullback_v1",
              "paper_session_event": "OPEN", "signal_status": "BUY", "ask": 1.1, "stop": 1.0, "target": 1.3}
    event_value = event_from_cycle_record(record, git_commit="abc", dataset_identity="d")
    assert event_value["event_type"] == "PAPER_SESSION_OPEN"
    assert event_value["production_decision"] == "ACCEPTED"
    assert append_cycle_experience(tmp_path, record, git_commit="abc", dataset_identity="d") is True
    assert append_cycle_experience(tmp_path, record, git_commit="abc", dataset_identity="d") is False
    assert len(read_experience_ledger(tmp_path / "AIOS_FOREX_P1_EXPERIENCE_LEDGER.jsonl")) == 1


def test_mfe_mae_exit_and_ambiguous_candle():
    candles = [{"high": 1.3, "low": 0.95, "close": 1.1, "observed_at_utc": "t1"}]
    metrics = excursion_metrics(1.0, 0.9, candles)
    assert metrics["mfe_r"] == 3.0 and metrics["mae_r"] == 0.5
    assert simulate_exit_policy(1.0, 0.9, [{"high": 1.3, "low": 0.85, "close": 1.1}])["result"] == "AMBIGUOUS"
    assert simulate_exit_policy(1.0, 0.9, [{"high": 1.1, "low": 0.99, "close": 1.08}])["result"] == "UNRESOLVED"


def test_shadow_guards_and_feature_helpers():
    assert is_completed_bar({"is_bar_closed": True}) is True
    assert is_completed_bar({"is_bar_closed": False}) is False
    assert distinct_bar_decision("bar-2", "bar-1") is True
    assert distinct_bar_decision("bar-1", "bar-1") is False
    assert rsi_confirmation(71)["status"] == "FAIL"
    assert mtf_confirmation(m5_direction="BUY", h1_direction="BUY")["passed"] is True
    assert post_exit_horizon_returns(1.0, [{"close": 1.1}, {"close": 0.9}])["1_bar_return"] == 0.1
    assert trade_quality_metrics(realized_r=1, mfe_r=2, mae_r=0.5, stop_distance=0.1)["exit_efficiency_realized_to_mfe"] == 0.5


def test_experiment_specs_are_shadow_only_and_reports_are_derived(tmp_path):
    records = [event(1, "SHADOW_COUNTERFACTUAL", "REJECTED", -1)]
    assert run_entry_experiments(records)["production_mutation_allowed"] is False
    assert run_exit_experiments(records)["production_mutation_allowed"] is False
    readiness = {"status": "AIOS_FOREX_30_TO_50_PAPER_CAMPAIGN_READY"}
    paths = write_learning_reports(records, tmp_path, readiness=readiness)
    assert paths["csv"].exists()
    assert (tmp_path / "AIOS_FOREX_PAPER_CAMPAIGN_READINESS_REPORT.md").exists()
