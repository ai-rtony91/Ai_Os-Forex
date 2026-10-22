from datetime import datetime, timedelta, timezone
import json

import pytest

from automation.forex_engine.forex_intraday_of_week_usd_settlement_flow_stage1_v1 import (
    BASE_SLIPPAGE_PIPS,
    DEVELOPMENT_END,
    FROZEN_BASELINES,
    REQUIRED_JOURNAL_FIELDS,
    assign_frozen_risk_weights,
    baseline_comparison_pass,
    build_capacity,
    classify_failures,
    maximum_drawdown_pct,
    parse_time,
    passes_fold_boundary_embargo,
    pip_size,
    profit_factor,
    reverse_identity_check,
    simulate_trade,
    stream_development_candles,
)
from automation.forex_engine.forex_intraday_of_week_usd_settlement_flow_stage0_v1 import PAIRS


def candle(timestamp, mid_open=1.0, mid_close=1.0, half_spread=0.00005, high=None, low=None):
    high = max(mid_open, mid_close) + 0.0001 if high is None else high
    low = min(mid_open, mid_close) - 0.0001 if low is None else low
    return {
        "time": timestamp,
        "mid": {"o": mid_open, "h": high, "l": low, "c": mid_close},
        "bid": {"o": mid_open - half_spread, "h": high - half_spread, "l": low - half_spread, "c": mid_close - half_spread},
        "ask": {"o": mid_open + half_spread, "h": high + half_spread, "l": low + half_spread, "c": mid_close + half_spread},
    }


def test_stream_parser_stops_at_validation_timestamp_before_price_fields(tmp_path):
    path = tmp_path / "EUR_USD.H1.json"
    path.write_text(
        """{
  "candles": [
    {
      "complete": true,
      "time": "2024-12-31T23:00:00.000000000Z",
      "bid": {"o":"1.0","h":"1.1","l":"0.9","c":"1.0"},
      "mid": {"o":"1.0","h":"1.1","l":"0.9","c":"1.0"},
      "ask": {"o":"1.0","h":"1.1","l":"0.9","c":"1.0"}
    },
    {
      "complete": true,
      "time": "2025-01-01T00:00:00.000000000Z",
      "bid": THIS_MUST_NEVER_BE_PARSED
    }
  ]
}
""",
        encoding="utf-8",
    )
    rows, boundary = stream_development_candles(path)
    assert len(rows) == 1
    assert boundary["first_excluded_timestamp"].startswith("2025-01-01")
    assert boundary["excluded_row_price_fields_parsed"] == 0
    assert boundary["stopped_before_validation_outcomes"] is True


def test_timestamp_parser_accepts_nanosecond_zulu():
    assert parse_time("2024-01-02T03:00:00.000000000Z") == datetime(2024, 1, 2, 3, tzinfo=timezone.utc)


def test_fold_boundary_embargo_excludes_first_21_hours():
    assert passes_fold_boundary_embargo(datetime(2024, 1, 1, 0, tzinfo=timezone.utc)) is False
    assert passes_fold_boundary_embargo(datetime(2024, 1, 1, 20, tzinfo=timezone.utc)) is False
    assert passes_fold_boundary_embargo(datetime(2024, 1, 1, 21, tzinfo=timezone.utc)) is True
    assert passes_fold_boundary_embargo(datetime(2024, 1, 2, 0, tzinfo=timezone.utc)) is True


def test_executable_bid_ask_and_slippage_reduce_long_result():
    start = datetime(2024, 1, 3, tzinfo=timezone.utc)
    candles = [candle(start + timedelta(hours=index), mid_open=1.0 + index * 0.0001, mid_close=1.0 + (index + 1) * 0.0001) for index in range(21)]
    event = {"entry_index": 0, "exit_index": 20, "atr": 0.01, "pair": "EUR_USD"}
    gross = simulate_trade(candles, event, 1, None)
    net = simulate_trade(candles, event, 1, BASE_SLIPPAGE_PIPS)
    assert net["result_r"] < gross["result_r"]
    assert net["entry_price"] > gross["entry_price"]
    assert net["exit_price"] < gross["exit_price"]


def test_long_and_short_stops_use_executable_sides():
    start = datetime(2024, 1, 3, tzinfo=timezone.utc)
    candles = [candle(start + timedelta(hours=index)) for index in range(21)]
    candles[2]["bid"]["l"] = 0.98
    long_event = {"entry_index": 0, "exit_index": 20, "atr": 0.01, "pair": "EUR_USD"}
    assert simulate_trade(candles, long_event, 1, BASE_SLIPPAGE_PIPS)["exit_reason"] == "ATR_STOP"
    candles = [candle(start + timedelta(hours=index)) for index in range(21)]
    candles[3]["ask"]["h"] = 1.02
    assert simulate_trade(candles, long_event, -1, BASE_SLIPPAGE_PIPS)["exit_reason"] == "ATR_STOP"


def test_negative_or_zero_expectancy_never_passes_baseline():
    favorable_negative_baselines = {"random": -2.0, "simple": -1.0}
    assert baseline_comparison_pass(-0.01, favorable_negative_baselines) is False
    assert baseline_comparison_pass(0.0, favorable_negative_baselines) is False
    assert baseline_comparison_pass(0.01, favorable_negative_baselines) is True
    assert baseline_comparison_pass(0.01, {"simple": 0.02}) is False


def test_failure_classification_preserves_baseline_and_cost_failures():
    metrics = {
        "gross_expectancy_r": 0.01,
        "after_cost_expectancy_r": -0.02,
        "stress_expectancy_r": -0.03,
        "profit_factor": 0.9,
        "maximum_drawdown_pct": 20.0,
        "trade_count": 200,
        "positive_fold_count": 0,
        "positive_pair_count": 1,
        "positive_currency_count": 1,
        "long_count": 100,
        "short_count": 100,
    }
    failures = classify_failures(metrics, False, True)
    assert "COST_DESTROYED_EDGE" in failures
    assert "BASELINE_FAILURE" in failures
    assert "WALK_FORWARD_FAILURE" in failures


def test_profit_factor_and_drawdown_are_deterministic():
    assert profit_factor([1.0, -0.5, 0.5, -0.5]) == 1.5
    rows = [
        {"date": "2024-01-01", "net_result_r": 1.0, "initial_equity_risk_fraction": 0.00025},
        {"date": "2024-01-02", "net_result_r": -1.0, "initial_equity_risk_fraction": 0.00025},
        {"date": "2024-01-03", "net_result_r": -1.0, "initial_equity_risk_fraction": 0.00025},
    ]
    assert maximum_drawdown_pct(rows) > 0


def test_capacity_gate_does_not_score_outcomes(monkeypatch):
    import automation.forex_engine.forex_intraday_of_week_usd_settlement_flow_stage1_v1 as module

    monkeypatch.setattr(module, "build_pair_events", lambda pair, candles: [])
    monkeypatch.setattr(module, "simulate_trade", lambda *args, **kwargs: pytest.fail("outcome function called"))
    events, capacity = build_capacity({pair: [] for pair in PAIRS})
    assert events == []
    assert capacity["capacity_pass"] is False
    assert capacity["outcome_function_calls_before_capacity_verdict"] == 0


def test_pip_size_is_pair_specific():
    assert pip_size("USD_JPY") == 0.01
    assert pip_size("EUR_USD") == 0.0001


def test_preregistered_journal_field_name_is_exact():
    assert "modeled_slippage" in REQUIRED_JOURNAL_FIELDS
    assert "economic_event_proximity" in REQUIRED_JOURNAL_FIELDS
    assert "initial_equity_risk_fraction" in REQUIRED_JOURNAL_FIELDS
    assert "atr_stop_distance" in REQUIRED_JOURNAL_FIELDS
    assert "planned_time_exit_timestamp" in REQUIRED_JOURNAL_FIELDS


def test_sparse_day_risk_shrinks_instead_of_breaking_pair_cap():
    rows = [{"date": "2024-05-20", "net_result_r": -1.0}]
    assign_frozen_risk_weights(rows)
    assert rows[0]["initial_equity_risk_fraction"] == 0.00025
    assert maximum_drawdown_pct(rows) == pytest.approx(0.025)
    ten = [{"date": "2024-05-21", "net_result_r": 0.0} for _ in range(10)]
    assign_frozen_risk_weights(ten)
    assert sum(row["initial_equity_risk_fraction"] for row in ten) == pytest.approx(0.0025)


def test_frozen_baseline_ids_are_exact():
    assert FROZEN_BASELINES == (
        "NO_TRADE_ZERO_EXPECTANCY",
        "MATCHED_DETERMINISTIC_RANDOM_DIRECTION_IDENTICAL_PAIR_DATES",
        "ALWAYS_LONG_FOREIGN_SAME_WINDOW",
        "ALWAYS_SHORT_FOREIGN_SAME_WINDOW",
        "WEEKDAY_AGNOSTIC_SAME_WINDOW",
        "COST_FREE_GROSS",
        "BASE_AND_STRESS_COST",
    )


def test_reverse_identity_audit_detects_cost_or_stop_drift():
    shared = {
        "event_id": "event-1", "pair": "EUR_USD", "date": "2024-01-03",
        "signal_timestamp": "2024-01-03T00:00:00Z", "entry_timestamp": "2024-01-03T00:00:00Z",
        "planned_time_exit_timestamp": "2024-01-03T20:00:00Z", "atr_stop_distance": 0.01,
        "spread": 0.0001, "modeled_slippage": 0.1,
    }
    rows = {
        "original": [{**shared, "direction": "LONG"}],
        "reverse": [{**shared, "direction": "SHORT"}],
    }
    assert reverse_identity_check("original", "reverse", rows)["status"] == "PASS"
    rows["reverse"][0]["atr_stop_distance"] = 0.02
    check = reverse_identity_check("original", "reverse", rows)
    assert check["status"] == "FAIL"
    assert check["same_atr_stop_distance"] is False
