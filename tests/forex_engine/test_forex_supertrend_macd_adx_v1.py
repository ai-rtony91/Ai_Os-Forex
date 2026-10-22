from __future__ import annotations

from automation.forex_engine.forex_supertrend_macd_adx_v1 import adx, ema, macd, supertrend


def candles(count: int = 80, step: float = 0.001):
    rows = []
    for index in range(count):
        close = 1.10 + index * step
        rows.append(
            {
                "time": f"2026-01-01T{index % 24:02d}:00:00Z",
                "open": close - step / 2,
                "high": close + abs(step) * 2,
                "low": close - abs(step) * 2,
                "close": close,
                "complete": True,
            }
        )
    return rows


def test_ema_is_seeded_by_sma_then_recursive():
    result = ema([1, 2, 3, 4, 5], 3)
    assert result[0] is None
    assert result[2] == 2
    assert result[3] == 3
    assert result[4] == 4


def test_supertrend_detects_completed_causal_uptrend():
    result = supertrend(candles(), period=7, multiplier=2.0)
    mature = [row for row in result if row["value"] is not None]
    assert mature
    assert mature[-1]["trend"] == 1
    assert mature[-1]["atr"] is not None


def test_macd_histogram_available_after_warmup():
    result = macd(candles(), fast=8, slow=17, signal=9)
    hist = [row["histogram"] for row in result if row["histogram"] is not None]
    assert hist
    assert result[-1]["macd"] > 0


def test_adx_and_directional_indicators_available_after_warmup():
    result = adx(candles(), period=7)
    mature = [row for row in result if row["adx"] is not None]
    assert mature
    assert mature[-1]["adx"] >= 0
    assert mature[-1]["plus_di"] is not None
    assert mature[-1]["minus_di"] is not None
