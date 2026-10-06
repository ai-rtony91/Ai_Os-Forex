from automation.forex_engine.forex_normalized_strategy_research_v3 import CONFIGS, atr, signal


def row(close, high=None, low=None):
    high = close if high is None else high
    low = close if low is None else low
    component = {"o": close, "h": high, "l": low, "c": close}
    return {"mid": dict(component), "bid": dict(component), "ask": dict(component), "timestamp": "2026-01-01T00:00:00Z", "instrument": "EUR_USD"}


def test_signal_preserves_canonical_three_five_ma_and_momentum():
    rows = [row(value) for value in (1.0, 1.0, 1.01, 1.02, 1.03)]
    assert signal(rows, 4) == "BUY"
    rows = [row(value) for value in (1.03, 1.02, 1.01, 1.0, 0.99)]
    assert signal(rows, 4) == "SELL"


def test_atr_uses_only_completed_current_and_prior_candles():
    rows = [row(1.0, 1.1, 0.9) for _ in range(15)]
    assert round(atr(rows, 14), 8) == 0.2


def test_hypothesis_set_is_bounded_and_geometry_only():
    assert len(CONFIGS) == 4
    assert {item.hypothesis_id for item in CONFIGS} <= {"H1_SCALE_NORMALIZATION", "H2_STOP_GEOMETRY", "H3_TARGET_GEOMETRY"}
