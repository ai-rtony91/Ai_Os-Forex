import pytest

from automation.forex_engine.daily_edge_report import deterministic_supertrend_sample
from automation.forex_engine.models import Direction
from automation.forex_engine.indicators import DOWN, UP
from automation.forex_engine.strategies import (
    SupertrendPullbackConfig,
    classify_r_multiple,
    evaluate_supertrend_pullback,
    planned_reward_risk,
    realized_r_multiple,
)


def test_supertrend_pullback_valid_long():
    result = evaluate_supertrend_pullback(deterministic_supertrend_sample(count=8))
    assert result["accepted"] is True
    assert result["signal"].direction == Direction.BUY


def test_supertrend_pullback_valid_short():
    candles = deterministic_supertrend_sample(count=8)
    for candle in candles:
        candle.open = round(2.2 - candle.open, 5)
        candle.close = round(2.2 - candle.close, 5)
        high = round(max(candle.open, candle.close) + 0.00035, 5)
        low = round(min(candle.open, candle.close) - 0.00035, 5)
        candle.high = high
        candle.low = low
    result = evaluate_supertrend_pullback(candles)
    assert result["accepted"] is True
    assert result["signal"].direction == Direction.SELL


def test_supertrend_pullback_blocks_chop():
    candles = deterministic_supertrend_sample(count=10)
    for index, candle in enumerate(candles):
        candle.open = 1.0800
        candle.close = 1.0808 if index % 2 else 1.0792
        candle.high = max(candle.open, candle.close) + 0.0005
        candle.low = min(candle.open, candle.close) - 0.0005
    result = evaluate_supertrend_pullback(candles, SupertrendPullbackConfig(chop_lookback=6))
    assert result["accepted"] is False
    assert any("chop" in reason for reason in result["no_trade_reasons"])


def test_supertrend_pullback_blocks_weak_candle():
    candles = deterministic_supertrend_sample(count=8)
    candles[-1].open = candles[-1].close - 0.00005
    candles[-1].high = candles[-1].close + 0.001
    candles[-1].low = candles[-1].close - 0.001
    result = evaluate_supertrend_pullback(candles)
    assert result["accepted"] is False
    assert any("weak_candle" in reason for reason in result["no_trade_reasons"])


def test_supertrend_pullback_blocks_extended_entry():
    candles = deterministic_supertrend_sample(count=8)
    candles[-1].open = candles[-2].close
    candles[-1].close = candles[-2].close + 0.006
    candles[-1].high = candles[-1].close + 0.0005
    candles[-1].low = candles[-1].open - 0.0003
    result = evaluate_supertrend_pullback(candles)
    assert result["accepted"] is False
    assert any("extended" in reason for reason in result["no_trade_reasons"])


def test_supertrend_pullback_blocks_bad_reward_risk():
    candles = deterministic_supertrend_sample(count=8)
    result = evaluate_supertrend_pullback(candles, SupertrendPullbackConfig(min_reward_risk=10.0))
    assert result["accepted"] is False
    assert any("reward_risk" in reason for reason in result["no_trade_reasons"])


def test_supertrend_pullback_minimum_boundary_accepts_when_other_gates_pass(monkeypatch):
    candles = deterministic_supertrend_sample(count=8)
    config = SupertrendPullbackConfig(min_reward_risk=1.5, target_reward_risk=2.0)
    monkeypatch.setattr(
        "automation.forex_engine.strategies.supertrend",
        lambda _candles, *_args, **_kwargs: [
            *([{"direction": DOWN, "lower_band": 1.0990, "upper_band": 1.1010}] * (len(_candles) - 1)),
            {"direction": UP, "lower_band": 1.0990, "upper_band": 1.1010},
        ],
    )
    monkeypatch.setattr(
        "automation.forex_engine.strategies.atr",
        lambda _candles, *_args, **_kwargs: [0.0006] * len(_candles),
    )
    for candle in candles:
        candle.open = 1.0995
        candle.close = 1.10045
        candle.high = 1.1010
        candle.low = 1.0990
    result = evaluate_supertrend_pullback(candles, config)
    assert result["accepted"] is True
    assert result["candidate"].metadata["planned_reward_risk"] == 2.0
    assert result["candidate"].metadata["target_reward_risk"] == 2.0


def test_rr_helpers_classify_and_compute_expected_values():
    assert planned_reward_risk(1.1000, 1.0990, 1.1020) == pytest.approx(2.0)
    assert realized_r_multiple(2.0, 1.0) == 2.0
    assert classify_r_multiple(2.0, 1.0) == "POSITIVE_R"
    assert classify_r_multiple(-1.0, 1.0) == "NEGATIVE_R"
    assert classify_r_multiple(0.0, 1.0) == "FLAT_R"
    assert classify_r_multiple(1.0, 0.0) == "INVALID_R"
