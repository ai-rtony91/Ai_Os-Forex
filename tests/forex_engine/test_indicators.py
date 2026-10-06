import pytest

from automation.forex_engine.daily_edge_report import deterministic_supertrend_sample
from automation.forex_engine.indicators import DOWN, FLAT, UP, atr, supertrend, true_range


def test_true_range_basic_correctness():
    candles = deterministic_supertrend_sample(count=4)
    ranges = true_range(candles)
    assert len(ranges) == 4
    assert ranges[0] == pytest.approx(candles[0].high - candles[0].low)
    assert all(value > 0 for value in ranges)


def test_atr_same_length_output_and_initial_none():
    candles = deterministic_supertrend_sample(count=8)
    values = atr(candles, period=3)
    assert len(values) == len(candles)
    assert values[:2] == [None, None]
    assert values[-1] is not None


def test_supertrend_direction_values_are_constrained():
    candles = deterministic_supertrend_sample(count=12)
    trend = supertrend(candles, period=3, multiplier=2)
    assert len(trend) == len(candles)
    assert {item["direction"] for item in trend}.issubset({UP, DOWN, FLAT})


def test_supertrend_handles_insufficient_data_cleanly():
    candles = deterministic_supertrend_sample(count=2)
    trend = supertrend(candles, period=3, multiplier=2)
    assert [item["supertrend"] for item in trend] == [None, None]
def research_bars_fixture_v1(count=180):
    from datetime import datetime, timedelta, timezone
    from math import sin
    start = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
    bars = []
    previous = 1.1
    for i in range(count):
        close = 1.1+0.006*sin(i/9)+0.001*sin(i/2)
        bars.append({"timestamp": (start+timedelta(minutes=5*i)).isoformat(), "o": previous,
                     "h": max(previous, close)+0.0004, "l": min(previous, close)-0.0004, "c": close})
        previous = close
    return bars


def test_research_supertrend_known_atr_seed_and_wilder_update():
    import pytest
    from automation.forex_engine.indicators import supertrend_research_v1
    rows = research_bars_fixture_v1(4)
    for row in rows:
        row.update(o=10, h=11, l=9, c=10)
    rows[3].update(h=12, l=8)
    path = supertrend_research_v1(rows, 3, 2)
    assert path[1]["atr"] is None and path[1]["direction"] == 0
    assert path[2]["atr"] == 2 and path[2]["band"] == 6
    assert path[3]["atr"] == pytest.approx(8/3)
    assert path[2]["available_at"] > path[2]["timestamp"]


def test_research_supertrend_zero_volatility_and_gaps_fail():
    import pytest
    from automation.forex_engine.indicators import supertrend_research_v1
    rows = research_bars_fixture_v1(5)
    flat = [{**row, "o": 1, "h": 1, "l": 1, "c": 1} for row in rows]
    assert all(p["direction"] == 0 for p in supertrend_research_v1(flat, 3, 2))
    with pytest.raises(ValueError, match="BAR_GAP"):
        supertrend_research_v1(rows[:2]+rows[3:], 3, 2)
    with pytest.raises(ValueError, match="BAR_MISSING"):
        supertrend_research_v1(rows[:2]+[None], 3, 2)


def test_research_supertrend_future_mutation_and_inversion():
    import pytest
    from automation.forex_engine.indicators import supertrend_research_v1
    rows = research_bars_fixture_v1()
    path = supertrend_research_v1(rows, 7, 2)
    altered = [{**r} for r in rows]
    for row in altered[80:]:
        row.update(o=2, h=2.1, l=1.9, c=2)
    assert supertrend_research_v1(altered, 7, 2)[:80] == path[:80]
    reflected = [{**r, "o": 3-r["o"], "h": 3-r["l"], "l": 3-r["h"], "c": 3-r["c"]} for r in rows]
    inverse = supertrend_research_v1(reflected, 7, 2)
    assert all(a["direction"] == -b["direction"] for a,b in zip(path[20:], inverse[20:]))
