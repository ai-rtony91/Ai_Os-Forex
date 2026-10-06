from __future__ import annotations

import json
from pathlib import Path

import pytest

import automation.forex_engine.forex_rr_calibration_v1 as module
from automation.forex_engine.forex_rr_calibration_v1 import (
    build_rr_calibration_report,
    calibrate_actual_entry_geometry,
    evaluate_rr_configuration,
    run_rr_calibration,
    split_calibration_validation,
    trade_result_classification,
    write_rr_calibration_artifacts,
)


def _trade(entry_ts: str, realized_r: float, *, instrument: str = "EUR_USD", max_favorable_r: float = 3.0, exit_reason: str = "paper_target") -> dict[str, object]:
    return {
        "instrument": instrument,
        "entry_timestamp_utc": entry_ts,
        "exit_timestamp_utc": entry_ts,
        "realized_r": realized_r,
        "realized_pl_quote_currency": realized_r,
        "risk_amount_quote": 1.0,
        "max_favorable_r": max_favorable_r,
        "mfe_r": max_favorable_r,
        "mae_r": 0.5,
        "holding_duration_seconds": 300,
        "exit_reason": exit_reason,
    }


def _replay_cache_for_fixture() -> dict[str, object]:
    candles = [
        {"observed_at_utc": "2026-08-01T10:00:00Z", "high": 100.5, "low": 99.5},
        {"observed_at_utc": "2026-08-01T10:05:00Z", "high": 102.0, "low": 100.2},
        {"observed_at_utc": "2026-08-01T10:10:00Z", "high": 102.4, "low": 100.1},
        {"observed_at_utc": "2026-08-01T10:15:00Z", "high": 103.1, "low": 98.9},
    ]
    return {
        "pair_histories": {
            "EUR_USD": {
                "candles": candles,
            }
        }
    }


def test_actual_entry_geometry_recomputes_risk_from_ask():
    result = calibrate_actual_entry_geometry(
        signal_reference_entry=1.1000,
        actual_paper_entry=1.1002,
        stop_price=1.0990,
        units=100,
        target_rr=2.0,
        display_precision=5,
    )
    assert result["actual_paper_entry"] == pytest.approx(1.1002)
    assert result["risk_amount"] == pytest.approx((1.1002 - 1.0990) * 100)
    assert result["effective_reward_risk"] == pytest.approx((result["target_price"] - result["actual_paper_entry"]) / (result["actual_paper_entry"] - result["stop_price"]))
    assert result["risk_amount"] == pytest.approx(0.12)


def test_actual_entry_geometry_fails_closed_on_precision_violation():
    with pytest.raises(ValueError, match="invalid_actual_entry_geometry"):
        calibrate_actual_entry_geometry(
            signal_reference_entry=1.1000,
            actual_paper_entry=1.1002,
            stop_price=1.1002,
            units=100,
            target_rr=2.0,
            display_precision=5,
        )


@pytest.mark.parametrize("target_rr", [2.0, 2.5, 3.0, 4.0])
def test_target_rr_geometry_versions_are_stable(target_rr: float):
    result = calibrate_actual_entry_geometry(
        signal_reference_entry=1.1000,
        actual_paper_entry=1.1002,
        stop_price=1.0990,
        units=100,
        target_rr=target_rr,
        display_precision=5,
    )
    assert result["nominal_reward_risk"] == pytest.approx(target_rr)
    assert result["effective_reward_risk"] >= 2.0


def test_target_rr_geometry_changes_with_requested_rr():
    base = calibrate_actual_entry_geometry(
        signal_reference_entry=1.1000,
        actual_paper_entry=1.1002,
        stop_price=1.0990,
        units=100,
        target_rr=2.0,
        display_precision=5,
    )
    wider = calibrate_actual_entry_geometry(
        signal_reference_entry=1.1000,
        actual_paper_entry=1.1002,
        stop_price=1.0990,
        units=100,
        target_rr=4.0,
        display_precision=5,
    )
    assert base["target_price"] < wider["target_price"]
    assert base["nominal_reward_risk"] == pytest.approx(2.0)
    assert wider["nominal_reward_risk"] == pytest.approx(4.0)


def test_trade_classification_boundaries():
    assert trade_result_classification(-0.1) == "LOSS_R"
    assert trade_result_classification(0.0) == "FLAT_R"
    assert trade_result_classification(0.9) == "POSITIVE_LT_1R"
    assert trade_result_classification(1.5) == "R_1_TO_LT_2"
    assert trade_result_classification(2.2) == "R_2_TO_LT_2_5"
    assert trade_result_classification(2.7) == "R_2_5_TO_LT_3"
    assert trade_result_classification(3.5) == "R_3_TO_LT_4"
    assert trade_result_classification(4.0) == "R_4_PLUS"


def test_split_is_deterministic():
    records = [_trade(f"2026-08-01T10:{index:02d}:00Z", 1.0) for index in range(10)]
    split = split_calibration_validation(records, calibration_fraction=0.7)
    assert len(split.calibration) == 7
    assert len(split.validation) == 3
    assert split.calibration[0]["entry_timestamp_utc"] == "2026-08-01T10:00:00Z"


def test_evaluation_metrics_and_zero_credit():
    records = [_trade(f"2026-08-01T10:{index:02d}:00Z", 1.5 if index % 2 == 0 else -1.0, max_favorable_r=4.0 if index % 2 == 0 else 1.0, exit_reason="paper_target" if index % 2 == 0 else "paper_stop") for index in range(10)]
    result = evaluate_rr_configuration(records, target_rr=2.0)
    assert result["qualifying_credit_awarded"] is False
    assert result["zero_qualifying_credit"] is True
    assert result["validation"]["profit_factor"] is not None
    assert result["validation"]["maximum_drawdown_r"] >= 0


def test_rr_sample_count_is_separated_from_integrity():
    records = [_trade(f"2026-08-01T10:{index:02d}:00Z", 0.5 if index % 2 == 0 else -0.5, max_favorable_r=4.0) for index in range(100)]
    result = evaluate_rr_configuration(records, target_rr=2.5)
    assert result["sample_count_sufficient"] is True
    assert result["sample_valid_for_promotion"] is True
    assert result["accounting_integrity"] is True
    assert result["normalization_integrity"] is True


def test_target_dependent_exit_fixture_diverges():
    trade = {
        "instrument": "EUR_USD",
        "entry_timestamp_utc": "2026-08-01T10:00:00Z",
        "direction": "BUY",
        "entry_price": 100.0,
        "actual_paper_entry": 100.0,
        "stop_price": 99.0,
        "display_precision": 2,
        "units": 1.0,
        "realized_r": 0.0,
        "realized_pl_quote_currency": 0.0,
        "risk_amount_quote": 1.0,
    }
    cache = _replay_cache_for_fixture()
    two_r = module._outcome_for_target(trade, target_rr=2.0, replay_cache=cache)
    two_point_five_r = module._outcome_for_target(trade, target_rr=2.5, replay_cache=cache)
    three_r = module._outcome_for_target(trade, target_rr=3.0, replay_cache=cache)
    four_r = module._outcome_for_target(trade, target_rr=4.0, replay_cache=cache)
    assert two_r["exit_reason"] == "paper_target"
    assert two_r["realized_r"] == pytest.approx(2.0)
    assert two_point_five_r["exit_reason"] == "paper_stop"
    assert three_r["exit_reason"] == "paper_stop"
    assert four_r["exit_reason"] == "paper_stop"
    assert two_r["TARGET_GEOMETRY_HASH"] != four_r["TARGET_GEOMETRY_HASH"]
    assert two_r["EXIT_OUTCOME_HASH"] != four_r["EXIT_OUTCOME_HASH"]
    assert two_r["REALIZED_R"] == pytest.approx(2.0)


def test_source_outcome_fields_do_not_drive_target_replay():
    trade = {
        "instrument": "EUR_USD",
        "entry_timestamp_utc": "2026-08-01T10:00:00Z",
        "direction": "BUY",
        "entry_price": 100.0,
        "actual_paper_entry": 100.0,
        "stop_price": 99.0,
        "display_precision": 2,
        "units": 1.0,
        "exit_price": 999.0,
        "exit_reason": "paper_target",
        "realized_r": 999.0,
        "realized_pl_quote_currency": 999.0,
        "risk_amount_quote": 1.0,
    }
    cache = _replay_cache_for_fixture()
    outcome = module._outcome_for_target(trade, target_rr=2.5, replay_cache=cache)
    assert outcome["exit_reason"] == "paper_stop"
    assert outcome["realized_r"] == pytest.approx(-1.0)


def test_realized_r_unit_scale_is_not_percentage_based():
    assert module._realized_r_from_pl_and_risk(-100.0, 100.0) == pytest.approx(-1.0)
    assert module._realized_r_from_pl_and_risk(200.0, 100.0) == pytest.approx(2.0)
    assert module._realized_r_from_pl_and_risk(300.0, 100.0) == pytest.approx(3.0)
    assert module._realized_r_from_pl_and_risk(2000.0, 1000.0) == pytest.approx(2.0)


def test_trade_stats_remain_in_r_units():
    trades = [
        {"instrument": "EUR_USD", "realized_r": 2.0, "exit_reason": "paper_target"},
        {"instrument": "EUR_USD", "realized_r": -1.0, "exit_reason": "paper_stop"},
        {"instrument": "EUR_USD", "realized_r": 2.0, "exit_reason": "paper_target"},
        {"instrument": "EUR_USD", "realized_r": -1.0, "exit_reason": "paper_stop"},
    ]
    stats = module._trade_stats(trades)
    assert stats["expectancy_r"] == pytest.approx(0.5)
    assert stats["net_r"] == pytest.approx(2.0)
    assert stats["profit_factor"] == pytest.approx(2.0)
    assert stats["maximum_drawdown_r"] == pytest.approx(1.0)


def test_evaluate_rr_configuration_reports_split_and_state_counts():
    records = [
        {
            "instrument": "EUR_USD",
            "entry_timestamp_utc": f"2026-08-01T10:{index:02d}:00Z",
            "actual_paper_entry": 100.0,
            "signal_reference_entry": 99.0,
            "stop_price": 99.0,
            "units": 100.0,
            "display_precision": 2,
            "realized_r": 0.0,
            "realized_pl_quote_currency": 0.0,
            "risk_amount_quote": 1.0,
            "terminal_state": "CLOSED_TRADE",
        }
        for index in range(10)
    ]
    result = evaluate_rr_configuration(records, target_rr=2.0)
    assert result["total_candidates_pre_split"] == 10
    assert result["calibration_candidates"] == 7
    assert result["validation_candidates"] == 3
    assert result["candidate_state_count_conservation"] is True
    assert result["state_counts"]["closed_trade_count"] == 10
    assert result["state_counts"]["censored_trade_count"] == 0
    assert result["hashes"]["TARGET_GEOMETRY_HASH"] != result["hashes"]["EXIT_OUTCOME_HASH"]
    assert result["hashes"]["EXIT_OUTCOME_HASH"] != result["hashes"]["REALIZED_R_SERIES_HASH"]


def test_run_rr_calibration_prefers_positive_validation_expectancy_only_when_sufficient():
    records = [_trade(f"2026-08-01T10:{index:02d}:00Z", 0.5 if index < 6 else -0.5, max_favorable_r=4.0) for index in range(10)]
    result = run_rr_calibration(records)
    assert result["schema"] == "AIOS_FOREX_RR_CALIBRATION_V1"
    assert result["qualifying_credit_awarded"] is False
    assert result["broker_writes"] is False
    assert result["live_trades"] is False


def test_artifacts_written():
    records = [_trade(f"2026-08-01T10:{index:02d}:00Z", 1.0, max_favorable_r=4.0) for index in range(10)]
    result = run_rr_calibration(records)
    report_root = Path(".tmp") / "rr_calibration_reports"
    paths = write_rr_calibration_artifacts(result, report_root=report_root)
    assert paths["report"].exists()
    assert paths["results"].exists()
    report = build_rr_calibration_report(result)
    assert "RECOMMENDED_TARGET_RR" in report
    assert "QUALIFYING_CREDIT_AWARDED" in report
