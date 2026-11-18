import csv
from pathlib import Path

import pytest

from automation.forex_engine.config import ForexEngineConfig
from automation.forex_engine.historical_data_readiness import HistoricalDataReadinessEngine
from automation.forex_engine.large_dataset_backtest_adapter import (
    MINIMUM_BACKTEST_CANDLES_PER_GROUP,
    LargeDatasetBacktestAdapter,
)
from automation.forex_engine.models import (
    Candle,
    EngineMode,
    LargeDatasetBacktestStatus,
)


def _adapter():
    return LargeDatasetBacktestAdapter(ForexEngineConfig())


def _synthetic_dataset(tmp_path, row_count=1000):
    return HistoricalDataReadinessEngine(ForexEngineConfig()).generate_synthetic_dataset(
        tmp_path / "synthetic.csv",
        row_count=row_count,
    )


def _write_invalid_csv(path):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("timestamp", "symbol", "timeframe", "open"))
        writer.writeheader()
        writer.writerow({"timestamp": "2026-01-05T00:00:00Z", "symbol": "EURUSD", "timeframe": "5m", "open": "1.08"})
    return Path(path)


def _candle(symbol="EURUSD", timeframe="5m", timestamp="2026-01-05T00:00:00Z"):
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=1.08,
        high=1.09,
        low=1.07,
        close=1.085,
        volume=1000,
        source="local_test",
    )


def test_rejects_url_path():
    with pytest.raises(ValueError, match="URL"):
        _adapter().build_backtest_report("https://example.invalid/history.csv")


def test_load_validated_dataset_from_synthetic_csv(tmp_path):
    candles = _adapter().load_validated_dataset(_synthetic_dataset(tmp_path))
    assert candles
    assert all(isinstance(candle, Candle) for candle in candles)


def test_group_candles_by_symbol_timeframe(tmp_path):
    candles = _adapter().load_validated_dataset(_synthetic_dataset(tmp_path))
    grouped = _adapter().group_candles(candles)
    assert {(key.symbol, key.timeframe) for key in grouped} == {
        ("EURUSD", "5m"),
        ("GBPUSD", "5m"),
        ("USDJPY", "5m"),
        ("XAUUSD", "5m"),
    }


def test_group_summaries_include_counts_and_timestamps(tmp_path):
    grouped = _adapter().group_candles(_adapter().load_validated_dataset(_synthetic_dataset(tmp_path)))
    summaries = _adapter().summarize_groups(grouped)
    assert all(summary.candle_count == 250 for summary in summaries)
    assert all(summary.first_timestamp for summary in summaries)
    assert all(summary.last_timestamp for summary in summaries)


def test_small_group_marked_insufficient():
    grouped = _adapter().group_candles([_candle(timestamp="2026-01-05T00:00:00Z")])
    summary = _adapter().summarize_groups(grouped)[0]
    assert summary.candle_count < MINIMUM_BACKTEST_CANDLES_PER_GROUP
    assert summary.status == LargeDatasetBacktestStatus.INSUFFICIENT_DATA


def test_ready_dataset_runs_group_backtest(tmp_path):
    report = _adapter().build_backtest_report(_synthetic_dataset(tmp_path))
    assert report.adapter_status == LargeDatasetBacktestStatus.BACKTEST_COMPLETED
    assert any(result.backtest_status == LargeDatasetBacktestStatus.BACKTEST_COMPLETED for result in report.group_results)


def test_invalid_dataset_skips_backtest(tmp_path):
    report = _adapter().build_backtest_report(_write_invalid_csv(tmp_path / "invalid.csv"))
    assert report.adapter_status == LargeDatasetBacktestStatus.INVALID_DATASET
    assert report.group_results == []


def test_backtest_report_contains_recommendations(tmp_path):
    report = _adapter().build_backtest_report(_synthetic_dataset(tmp_path))
    assert report.recommendations


def test_backtest_report_mode_is_paper_only(tmp_path):
    report = _adapter().build_backtest_report(_synthetic_dataset(tmp_path))
    assert report.mode == EngineMode.PAPER_ONLY


def test_xauusd_recommendation_present_when_xauusd_group_exists(tmp_path):
    report = _adapter().build_backtest_report(_synthetic_dataset(tmp_path))
    assert any("XAUUSD" in recommendation for recommendation in report.recommendations)


def test_large_dataset_demo_imports_without_network():
    import automation.forex_engine.run_large_dataset_backtest_demo as demo

    assert demo.main


def test_existing_demos_still_import():
    import automation.forex_engine.run_backtest_demo as backtest_demo
    import automation.forex_engine.run_broker_sandbox_demo as broker_sandbox_demo
    import automation.forex_engine.run_confidence_demo as confidence_demo
    import automation.forex_engine.run_historical_data_readiness_demo as historical_demo
    import automation.forex_engine.run_market_data_demo as market_data_demo
    import automation.forex_engine.run_paper_demo as paper_demo
    import automation.forex_engine.run_paper_operator_demo as paper_operator_demo
    import automation.forex_engine.run_parameter_optimization_demo as parameter_demo
    import automation.forex_engine.run_portfolio_optimization_demo as portfolio_demo
    import automation.forex_engine.run_risk_management_demo as risk_management_demo
    import automation.forex_engine.run_signal_rules_demo as signal_rules_demo
    import automation.forex_engine.run_strategy_comparison_demo as strategy_comparison_demo
    import automation.forex_engine.run_walk_forward_demo as walk_forward_demo

    assert backtest_demo.main
    assert broker_sandbox_demo.main
    assert confidence_demo.main
    assert historical_demo.main
    assert market_data_demo.main
    assert paper_demo.main
    assert paper_operator_demo.main
    assert parameter_demo.main
    assert portfolio_demo.main
    assert risk_management_demo.main
    assert signal_rules_demo.main
    assert strategy_comparison_demo.main
    assert walk_forward_demo.main


def test_no_live_trading_demo_created():
    assert not Path("automation/forex_engine/run_live_trading_demo.py").exists()
