import pytest

from automation.forex_engine.backtest import (
    END_OF_BACKTEST,
    STOP_LOSS,
    TAKE_PROFIT,
    BacktestEngine,
    close_remaining_trades_at_end,
    evaluate_open_trades_against_candle,
    generate_demo_signal_from_candle,
    run_backtest,
    run_supertrend_edge_backtest,
)
from automation.forex_engine.confidence import ConfidenceEngine
from automation.forex_engine.config import ForexEngineConfig
from automation.forex_engine.costs import TradeCostAssumptions
from automation.forex_engine.daily_edge_report import deterministic_supertrend_sample
from automation.forex_engine.market_data import load_fixture_candles
from automation.forex_engine.models import Candle, Direction, EngineMode
from automation.forex_engine.paper_execution import PaperExecutionEngine
from automation.forex_engine.risk import RiskEngine


def candle(**overrides):
    data = {
        "symbol": "EURUSD",
        "timeframe": "5m",
        "timestamp": "2026-06-06T09:00:00Z",
        "open": 1.0800,
        "high": 1.0820,
        "low": 1.0790,
        "close": 1.0810,
        "volume": 1000,
        "source": "local_test_fixture",
    }
    data.update(overrides)
    return Candle(**data)


def paper_engine():
    config = ForexEngineConfig()
    return PaperExecutionEngine(config, RiskEngine(config))


def open_trade(engine, signal):
    assessment = ConfidenceEngine(engine.config).score_signal(signal)
    return engine.submit_signal(signal, assessment)


def test_backtest_loads_fixture_and_runs():
    candles = load_fixture_candles("EURUSD", "5m", ForexEngineConfig())
    result = run_backtest(candles)
    assert result.mode == EngineMode.PAPER_ONLY
    assert result.candles_processed > 0


def test_backtest_rejects_empty_candles():
    with pytest.raises(ValueError, match="empty"):
        run_backtest([])


def test_backtest_rejects_mixed_symbols():
    candles = [candle(symbol="EURUSD"), candle(symbol="GBPUSD", timestamp="2026-06-06T09:05:00Z")]
    with pytest.raises(ValueError, match="one symbol"):
        run_backtest(candles)


def test_demo_signal_generation_buy():
    signal = generate_demo_signal_from_candle(candle(close=1.0810), candle(close=1.0800), ForexEngineConfig())
    assert signal.direction == Direction.BUY


def test_demo_signal_generation_sell():
    signal = generate_demo_signal_from_candle(candle(close=1.0790), candle(close=1.0800), ForexEngineConfig())
    assert signal.direction == Direction.SELL


def test_demo_signal_generation_flat():
    assert generate_demo_signal_from_candle(candle(close=1.0800), candle(close=1.0800), ForexEngineConfig()) is None


def test_take_profit_closes_buy():
    engine = paper_engine()
    signal = generate_demo_signal_from_candle(candle(close=1.0810), candle(close=1.0800), engine.config)
    trade = open_trade(engine, signal)
    closed = evaluate_open_trades_against_candle(
        engine,
        candle(high=trade.take_profit, low=trade.entry_price, timestamp="2026-06-06T09:05:00Z"),
    )
    assert closed[0].metadata["close_reason"] == TAKE_PROFIT


def test_stop_loss_closes_buy():
    engine = paper_engine()
    signal = generate_demo_signal_from_candle(candle(close=1.0810), candle(close=1.0800), engine.config)
    trade = open_trade(engine, signal)
    closed = evaluate_open_trades_against_candle(
        engine,
        candle(high=trade.entry_price, low=trade.stop_loss, timestamp="2026-06-06T09:05:00Z"),
    )
    assert closed[0].metadata["close_reason"] == STOP_LOSS


def test_take_profit_closes_sell():
    engine = paper_engine()
    signal = generate_demo_signal_from_candle(candle(close=1.0790), candle(close=1.0800), engine.config)
    trade = open_trade(engine, signal)
    closed = evaluate_open_trades_against_candle(
        engine,
        candle(high=trade.entry_price, low=trade.take_profit, timestamp="2026-06-06T09:05:00Z"),
    )
    assert closed[0].metadata["close_reason"] == TAKE_PROFIT


def test_stop_loss_closes_sell():
    engine = paper_engine()
    signal = generate_demo_signal_from_candle(candle(close=1.0790), candle(close=1.0800), engine.config)
    trade = open_trade(engine, signal)
    closed = evaluate_open_trades_against_candle(
        engine,
        candle(high=trade.stop_loss, low=trade.entry_price, timestamp="2026-06-06T09:05:00Z"),
    )
    assert closed[0].metadata["close_reason"] == STOP_LOSS


def test_same_candle_stop_and_target_uses_conservative_stop_first():
    engine = paper_engine()
    signal = generate_demo_signal_from_candle(candle(close=1.0810), candle(close=1.0800), engine.config)
    trade = open_trade(engine, signal)
    closed = evaluate_open_trades_against_candle(
        engine,
        candle(high=trade.take_profit, low=trade.stop_loss, timestamp="2026-06-06T09:05:00Z"),
    )
    assert closed[0].metadata["close_reason"] == STOP_LOSS


def test_end_of_backtest_closes_remaining_trades():
    engine = paper_engine()
    signal = generate_demo_signal_from_candle(candle(close=1.0810), candle(close=1.0800), engine.config)
    open_trade(engine, signal)
    closed = close_remaining_trades_at_end(engine, candle(close=1.0815, timestamp="2026-06-06T09:10:00Z"))
    assert closed[0].metadata["close_reason"] == END_OF_BACKTEST
    assert not engine.open_trades


def test_backtest_summary_fields_present():
    result = run_backtest(load_fixture_candles("EURUSD", "5m", ForexEngineConfig()))
    assert result.trades_closed == len(result.results)
    assert isinstance(result.ending_balance_usd, float)
    assert isinstance(result.net_pnl_usd, float)
    assert isinstance(result.win_rate_pct, float)
    assert hasattr(result, "profit_factor")


def test_backtest_does_not_require_network():
    result = BacktestEngine(ForexEngineConfig(), RiskEngine(ForexEngineConfig()), ConfidenceEngine(ForexEngineConfig()))
    candles = load_fixture_candles("XAUUSD", "5m", ForexEngineConfig())
    assert result.run_backtest(candles).mode == EngineMode.PAPER_ONLY


def test_supertrend_edge_backtest_returns_costed_paper_metrics():
    result = run_supertrend_edge_backtest(deterministic_supertrend_sample(count=48))
    assert result["mode"] == EngineMode.PAPER_ONLY
    assert result["strategy_name"] == "supertrend_pullback_v1"
    assert "cost_assumptions" in result
    assert result["metrics"]["total_trades"] == len(result["trades"])


def test_supertrend_edge_backtest_cost_model_reduces_result():
    candles = deterministic_supertrend_sample(count=48)
    zero_cost = run_supertrend_edge_backtest(candles, cost_assumptions=TradeCostAssumptions(0, 0, 0))
    costed = run_supertrend_edge_backtest(candles)
    assert costed["metrics"]["net_pnl_usd"] <= zero_cost["metrics"]["net_pnl_usd"]


def test_supertrend_edge_backtest_charges_the_explicit_round_trip_cost_once():
    candles = deterministic_supertrend_sample(count=48)
    assumptions = TradeCostAssumptions(spread=0.0001, slippage=0.00005, commission_per_trade_usd=0.5)
    zero_cost = run_supertrend_edge_backtest(candles, cost_assumptions=TradeCostAssumptions(0, 0, 0))
    costed = run_supertrend_edge_backtest(candles, cost_assumptions=assumptions)
    assert len(costed["trades"]) == len(zero_cost["trades"])
    for raw_trade, costed_trade in zip(zero_cost["trades"], costed["trades"], strict=True):
        assert costed_trade["entry_price"] == raw_trade["entry_price"]
        units = abs(raw_trade["position_size_units"])
        expected_cost = round(units * (assumptions.spread + 2 * assumptions.slippage) + 0.5, 2)
        assert costed_trade["pnl_usd"] == round(raw_trade["pnl_usd"] - expected_cost, 2)
