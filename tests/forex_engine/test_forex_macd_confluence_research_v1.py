from __future__ import annotations

from pathlib import Path

import pytest

import automation.forex_engine.forex_macd_confluence_research_v1 as module
from automation.forex_engine.models import Candle


def candles() -> list[Candle]:
    values = [1.0, 1.2, 1.1, 1.3, 1.4, 1.6, 1.5, 1.7, 1.8, 1.9]
    return [
        Candle(
            symbol="EURUSD",
            timeframe="5m",
            timestamp=f"2026-08-01T10:{index:02d}:00Z",
            open=value - 0.01,
            high=value + 0.02,
            low=value - 0.03,
            close=value,
            volume=10,
            source="test",
        )
        for index, value in enumerate(values)
    ]


def test_ema_is_deterministic():
    values = [1.0, 2.0, 3.0, 4.0]
    assert module.ema_series(values, 3) == module.ema_series(values, 3)
    assert module.ema_series(values, 3)[0] == pytest.approx(1.0)


def test_macd_is_deterministic_and_signals_align():
    series = module.macd_series([item.close for item in candles()])
    again = module.macd_series([item.close for item in candles()])
    assert series == again
    assert len(series["macd_line"]) == len(candles())
    assert len(series["signal_line"]) == len(candles())
    assert len(series["histogram"]) == len(candles())


def test_macd_no_lookahead_uses_completed_candles_only():
    base = candles()
    extended = base + [
        Candle(
            symbol="EURUSD",
            timeframe="5m",
            timestamp="2026-08-01T10:10:00Z",
            open=2.0,
            high=2.1,
            low=1.9,
            close=2.05,
            volume=10,
            source="test",
        )
    ]
    base_snapshot = module.macd_snapshot([item.close for item in base])
    extended_snapshot = module.macd_snapshot([item.close for item in extended[: len(base)]])
    assert base_snapshot == extended_snapshot
    assert module.macd_snapshot([item.close for item in extended]) != base_snapshot


def test_macd_filter_shapes_cover_all_four_standard_filters():
    history = candles()
    control = module.evaluate_macd_filter(history)
    filter_a = module.evaluate_macd_filter(history, "FILTER_A_SIGNAL")
    filter_b = module.evaluate_macd_filter(history, "FILTER_B_ZERO")
    filter_c = module.evaluate_macd_filter(history, "FILTER_C_FULL")
    filter_d = module.evaluate_macd_filter(history, "FILTER_D_ACCELERATION")
    assert control["signals"] >= control["closed"]
    assert filter_a["signals"] == control["signals"]
    assert filter_b["signals"] == control["signals"]
    assert filter_c["signals"] == control["signals"]
    assert filter_d["signals"] == control["signals"]
    assert filter_a["closed"] <= control["closed"]
    assert filter_b["closed"] <= control["closed"]
    assert filter_c["closed"] <= control["closed"]
    assert filter_d["closed"] <= control["closed"]


def test_replay_cache_loader_smoke_and_research_shape():
    cache = module.load_replay_cache()
    assert isinstance(cache, dict)
    assert "pair_histories" in cache
    instrument, history = next(iter(cache["pair_histories"].items()))
    candles = history.get("sanitized_candles") or history.get("candles")
    assert isinstance(candles, list) and candles
    result = module.evaluate_macd_filter(
        [
            Candle(
                symbol=instrument.replace("_", ""),
                timeframe="5m",
                timestamp=str(item["timestamp"]),
                open=float(item["bid"]["open"]),
                high=float(item["ask"]["high"]),
                low=float(item["bid"]["low"]),
                close=float(item["bid"]["close"]),
                volume=float(item.get("volume", 0.0)),
                source="replay_cache",
            )
            for item in candles[:80]
        ]
    )
    assert result["signals"] >= 0
    assert result["closed"] >= 0
