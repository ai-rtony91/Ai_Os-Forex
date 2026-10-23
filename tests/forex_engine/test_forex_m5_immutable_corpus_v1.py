from datetime import datetime, timezone

import pytest

from automation.forex_engine.forex_m5_immutable_corpus_v1 import (
    chunk_windows,
    corpus_window,
    drawdown_contract,
    normalize_candle,
    quality,
)


def raw(complete=True):
    side = {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.15"}
    return {"time": "2026-01-01T00:00:00Z", "complete": complete, "volume": 1, "bid": side, "ask": {**side, "o": "1.11", "h": "1.21", "l": "1.01", "c": "1.16"}, "mid": side}


def test_window_is_m5_aligned_and_chunked():
    start, end = corpus_window(datetime(2026, 4, 1, 12, 17, tzinfo=timezone.utc), 30)
    assert end.minute == 15
    windows = chunk_windows(start, end)
    assert windows[0][0] == start
    assert windows[-1][1] == end
    assert all(left[1] == right[0] for left, right in zip(windows, windows[1:]))


def test_only_completed_mba_candles_are_accepted():
    assert normalize_candle("EUR_USD", raw(False)) is None
    candle = normalize_candle("EUR_USD", raw())
    assert candle["complete"] is True
    assert candle["ask"]["c"] >= candle["bid"]["c"]


def test_negative_spread_is_rejected():
    item = raw()
    item["ask"] = {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.0"}
    with pytest.raises(ValueError, match="NEGATIVE_BID_ASK_SPREAD"):
        normalize_candle("EUR_USD", item)


def test_quality_reports_but_does_not_fill_gaps():
    one = normalize_candle("EUR_USD", raw())
    two = {**one, "timestamp": "2026-01-01T00:10:00Z"}
    result = quality([one, two])
    assert result["record_count"] == 2
    assert result["gap_counts"]["unexpected"] == 1


def test_drawdown_contract_is_peak_equity_percentage():
    contract = drawdown_contract()
    assert contract["canonical_unit"] == "PERCENT_OF_RUNNING_PEAK_EQUITY"
    assert contract["paper60_conversion_status"] == "NOT_RELIABLY_CONVERTIBLE"
