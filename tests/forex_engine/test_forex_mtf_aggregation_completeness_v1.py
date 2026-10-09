"""Synthetic timestamps only; no source data, research run, or broker access."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from automation.forex_engine import forex_mtf_gross_edge_surface_v1 as surface


def candle(stamp, value=1.0, complete=True):
    return {
        "time": stamp, "timestamp": stamp.isoformat().replace("+00:00", "Z"),
        "open": value, "high": value + 2, "low": value - 1,
        "close": value + 1, "bid_close": value + .9,
        "ask_close": value + 1.1, "spread": .2, "complete": complete,
    }


def assert_unverified(row):
    assert row["complete"] is False
    assert row["completeness_status"] == "UNVERIFIED"
    assert row["completeness_reason"] == "expected_constituents_unverified"


@pytest.mark.parametrize("minutes", [15, 30, 240, 1440, 10080, 43200])
def test_sparse_source_rows_never_certify_an_aggregate(minutes):
    # Returning complete=True for the only observed bar would fail this test.
    rows = [candle(datetime(2024, 2, 14, 12, tzinfo=timezone.utc))]
    out = surface.resample(rows, minutes)
    assert len(out) == 1
    assert_unverified(out[0])


@pytest.mark.parametrize("stamps", [
    [datetime(2024, 2, 1, tzinfo=timezone.utc) + timedelta(hours=i) for i in range(29 * 24)],
    [datetime(2024, 2, 1, tzinfo=timezone.utc), datetime(2024, 2, 29, 23, tzinfo=timezone.utc)],
    [datetime(2024, 2, 14, 12, tzinfo=timezone.utc)] * 4,
], ids=["every_calendar_hour", "month_endpoints_only", "duplicate_hours"])
def test_observed_hour_counts_do_not_invent_an_fx_calendar(stamps):
    out = surface.resample([candle(stamp) for stamp in stamps], 43200)
    assert len(out) == 1
    assert_unverified(out[0])


@pytest.mark.parametrize("complete", [False, None, True])
def test_source_completion_does_not_prove_bucket_coverage(complete):
    out = surface.resample([candle(datetime(2024, 2, 1, tzinfo=timezone.utc), complete=complete)], 43200)
    assert_unverified(out[0])


def test_calendar_months_keep_leap_day_and_year_boundaries_and_ohlc():
    stamps = [datetime(2023, 12, 31, 23, tzinfo=timezone.utc),
              datetime(2024, 1, 1, tzinfo=timezone.utc),
              datetime(2024, 2, 1, tzinfo=timezone.utc),
              datetime(2024, 2, 29, 23, tzinfo=timezone.utc),
              datetime(2024, 3, 1, tzinfo=timezone.utc)]
    rows = [candle(stamp, value=i + 1) for i, stamp in enumerate(stamps)]
    before = deepcopy(rows)
    out = surface.resample(list(reversed(rows)), 43200)
    assert [(r["time"].year, r["time"].month) for r in out] == [(2023, 12), (2024, 1), (2024, 2), (2024, 3)]
    feb = out[2]
    assert {k: feb[k] for k in ("open", "high", "low", "close")} == {"open": 3, "high": 6, "low": 2, "close": 5}
    assert feb["timestamp"] == rows[3]["timestamp"]
    assert feb["bid_close"] == rows[3]["bid_close"]
    assert feb["ask_close"] == rows[3]["ask_close"]
    assert rows == before
    for row in out:
        assert_unverified(row)


@pytest.mark.parametrize("flag", [False, None, 1, "true", "false", "absent"])
def test_native_row_conversion_does_not_invent_source_completion(flag):
    raw = {"time": "2024-02-01T00:00:00Z", "mid": {"o": 1, "h": 2, "l": .5, "c": 1.5}}
    if flag != "absent":
        raw["complete"] = flag
    assert surface.candle_from_repo_row(raw)["complete"] is False


def test_native_row_conversion_preserves_explicit_completed_flag():
    raw = {"time": "2024-02-01T00:00:00Z", "mid": {"o": 1, "h": 2, "l": .5, "c": 1.5}, "complete": True}
    assert surface.candle_from_repo_row(raw)["complete"] is True


def test_h1_sampling_cannot_become_monthly_completeness(monkeypatch):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    source = [{"time": start + timedelta(hours=i),
               "mid": {"o": 1, "h": 2, "l": .5, "c": 1.5},
               "bid": {"c": 1.4}, "ask": {"c": 1.6}}
              for i in range(3200)]
    # p27's inspected loader contract yields completed source candles only.
    # Replace only its IO boundary; the real load_h1_rows/resample execute.
    monkeypatch.setattr(surface.p27, "load_h1", lambda *args: source)
    monkeypatch.setattr(surface, "ROW_CACHE", {})
    rows = surface.load_h1_rows("SYNTHETIC_ONLY")
    assert len(rows) == 1600
    assert rows[1]["time"] - rows[0]["time"] == timedelta(hours=2)
    assert surface.load_h1_rows("SYNTHETIC_ONLY") is rows
    assert all(row["complete"] is True for row in rows)  # Individual H1 closure only.
    out = surface.candles_for("SYNTHETIC_ONLY", "MN1")
    assert out
    for row in out:
        assert_unverified(row)


@pytest.mark.parametrize("flag", [False, None, 1, "true"])
def test_indicator_cache_rejects_uncertain_rows_before_index_misalignment(flag):
    start = datetime(2024, 2, 1, tzinfo=timezone.utc)
    rows = [candle(start + timedelta(hours=i)) for i in range(80)]
    rows[25]["complete"] = flag
    with pytest.raises(ValueError, match="^unverified_candle_completeness$"):
        surface.build_indicator_caches(rows)


def test_completed_native_indicator_rows_keep_full_length():
    start = datetime(2024, 2, 1, tzinfo=timezone.utc)
    rows = [candle(start + timedelta(hours=i), value=1 + i / 100) for i in range(80)]
    caches = surface.build_indicator_caches(rows)
    assert all(len(series) == len(rows) for values in caches.values() for series in values.values())


def test_empty_input_does_not_synthesize_a_month():
    assert surface.resample([], 43200) == []


def test_timeframe_universe_does_not_gain_s45_or_six_month_admission():
    assert surface.TIMEFRAME_MINUTES == {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440, "W1": 10080, "MN1": 43200}
