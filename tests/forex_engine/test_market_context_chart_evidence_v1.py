from math import isclose
from xml.etree import ElementTree

from automation.forex_engine.market_context_chart_evidence_v1 import render_market_context_svg
from automation.forex_engine.market_context_features_v1 import build_market_context_snapshots


def candles(pair="EURUSD", n=28):
    return [{"symbol": pair, "timeframe": "5m", "timestamp": f"2024-01-01T00:{i:02d}:00+00:00", "open": 1+i*.001, "high": 1.002+i*.001, "low": .999+i*.001, "close": 1.001+i*.001, "volume": 1, "completed": True} for i in range(n)]


def test_chart_is_deterministic_and_uses_snapshot_window():
    snapshots = build_market_context_snapshots(candles())[-8:]
    svg = render_market_context_svg(snapshots)
    assert svg == render_market_context_svg(snapshots)
    assert "EURUSD 5m" in svg and "circle" in svg and "polyline" in svg



def test_equal_opposite_moves_have_equal_visible_candle_bodies():
    snapshots = [
        {
            "pair": "EURUSD", "timeframe": "5m", "timestamp": "2024-01-01T00:00:00+00:00",
            "ohlc": {"open": 1.0, "high": 3.0, "low": 0.0, "close": 2.0},
            "supertrend": {"value": None},
        },
        {
            "pair": "EURUSD", "timeframe": "5m", "timestamp": "2024-01-01T00:05:00+00:00",
            "ohlc": {"open": 2.0, "high": 3.0, "low": 0.0, "close": 1.0},
            "supertrend": {"value": None},
        },
    ]
    svg = ElementTree.fromstring(render_market_context_svg(snapshots))
    bodies = [
        rect for rect in svg.findall("{http://www.w3.org/2000/svg}rect")
        if rect.attrib.get("fill") in ("#16803c", "#b42318")
    ]
    assert len(bodies) == 2
    assert [body.attrib["fill"] for body in bodies] == ["#16803c", "#b42318"]
    heights = [float(body.attrib["height"]) for body in bodies]
    assert all(height > 1.0 for height in heights)
    assert all(isclose(height, 153.333, abs_tol=0.001) for height in heights)
    assert isclose(heights[0], heights[1], abs_tol=0.001)
