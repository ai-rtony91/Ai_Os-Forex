"""Synthetic only. No corpus or account access."""
from copy import deepcopy
from datetime import timedelta
import pytest
from automation.forex_engine.edge_research.features import snapshots, ny_time, utc, no_entry, financing_exit, validate_bar


def bars(count=80):
    result = []
    for i in range(count):
        close = 1.1 + i * .0001
        mid = dict(o=close-.00005, h=close+.00015, l=close-.0002, c=close)
        result.append(dict(instrument="EUR_USD", complete=True,
            timestamp=(utc("2024-01-02T12:00:00Z")+timedelta(minutes=5*i)).isoformat(),
            mid=mid, bid={k:v-.00005 for k,v in mid.items()},
            ask={k:v+.00005 for k,v in mid.items()}, volume=5))
    return result


@pytest.mark.parametrize("stamp,offset,hour", [
    ("2024-03-10T06:59:00Z", -5, 1), ("2024-03-10T07:00:00Z", -4, 3),
    ("2024-11-03T05:59:00Z", -4, 1), ("2024-11-03T06:00:00Z", -5, 1),
    ("2025-03-09T06:59:00Z", -5, 1), ("2025-03-09T07:00:00Z", -4, 3)])
def test_dst(stamp, offset, hour):
    value = ny_time(utc(stamp))
    assert value.utcoffset() == timedelta(hours=offset)
    assert value.hour == hour


def test_no_financing_schedule():
    assert financing_exit(utc("2024-06-03T18:00:00Z")) == utc("2024-06-03T20:30:00Z")
    assert financing_exit(utc("2024-01-03T18:00:00Z")) == utc("2024-01-03T21:30:00Z")
    assert no_entry(utc("2024-06-03T20:00:00Z"))
    assert no_entry(utc("2024-06-03T21:10:00Z"))
    assert not no_entry(utc("2024-06-03T21:15:00Z"))


def test_calculated_reference_and_warmup():
    result = snapshots("EUR_USD", bars())
    assert result[1]["atr3"] is None
    assert result[2]["atr3"] == pytest.approx(.00035)
    assert result[2]["supertrend"] == pytest.approx(1.100175-.0007)
    assert result[2]["event_direction"] == 0
    assert result[3]["event_direction"] == 1
    assert sum(bool(x["event_direction"]) for x in result) == 1
    assert result[13]["rsi14"] is None
    assert result[14]["rsi14"] == 100
    assert result[25]["macd12_26"] == pytest.approx(.0007)
    assert result[32]["macd_signal9"] is None
    assert result[33]["macd_signal9"] == pytest.approx(.0007)
    assert result[19]["bollinger_mean20"] == pytest.approx(1.10095)
    assert result[19]["bandwidth"] == pytest.approx(4*(33.25**.5)*.0001/1.10095)
    assert result[19]["adx"] is None
    assert result[0]["feature_available_at"] == utc("2024-01-02T12:05:00Z").isoformat()


def test_future_change_does_not_change_past():
    original = bars()
    changed = deepcopy(original)
    for row in changed[45:]:
        for side in ("bid", "ask", "mid"):
            row[side] = {k:v*1.1 for k,v in row[side].items()}
    assert snapshots("EUR_USD", original)[:45] == snapshots("EUR_USD", changed)[:45]
    assert snapshots("EUR_USD", original[:45]) == snapshots("EUR_USD", original)[:45]


def test_gap_resets_startup_and_confirmation():
    source = bars()
    del source[20]
    result = snapshots("EUR_USD", source)
    assert result[20]["rsi14"] is None
    assert result[20]["atr3"] is None
    assert result[23]["event_direction"] == 1


def test_pivot_available_only_after_confirmation():
    source = bars(10)
    for side in ("bid", "ask", "mid"):
        source[4][side]["h"] += .01
    result = snapshots("EUR_USD", source)
    assert result[5]["confirmed_swing_high"] is None
    pivot = result[6]["confirmed_swing_high"]
    assert pivot["turning_time"] == source[4]["timestamp"]
    assert pivot["available_at"] == result[6]["feature_available_at"]


@pytest.mark.parametrize("defect", ["crossed", "ohlc", "nan", "incomplete", "off_grid"])
def test_invalid_prices_fail(defect):
    row = bars(1)[0]
    if defect == "crossed": row["bid"]["c"] = row["ask"]["c"]+.000001
    if defect == "ohlc": row["mid"]["l"] = 2
    if defect == "nan": row["ask"]["h"] = float("nan")
    if defect == "incomplete": row["complete"] = False
    if defect == "off_grid": row["timestamp"] = "2024-01-02T12:01:00Z"
    with pytest.raises(ValueError): validate_bar(row, "EUR_USD")


def test_duplicate_and_calendar_fail_closed():
    with pytest.raises(ValueError): snapshots("EUR_USD", bars(1)*2)
    with pytest.raises(ValueError): ny_time(utc("2026-01-01T00:00:00Z"))
