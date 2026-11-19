from automation.forex_engine.market_context_features_v1 import build_market_context_snapshots


def candles(pair="EURUSD", n=28):
    return [{"symbol": pair, "timeframe": "5m", "timestamp": f"2024-01-01T00:{i:02d}:00+00:00", "open": 1+i*.001, "high": 1.002+i*.001, "low": .999+i*.001, "close": 1.001+i*.001, "volume": 1, "completed": True} for i in range(n)]


def test_determinism_and_completed_candle_boundary():
    data = candles(); a = build_market_context_snapshots(data); b = build_market_context_snapshots(data)
    assert a == b and all(item["completed"] for item in a)
    data[-1]["completed"] = False
    try: build_market_context_snapshots(data)
    except ValueError as exc: assert "completed" in str(exc)
    else: raise AssertionError("incomplete candle was accepted")


def test_anatomy_atr_normalization_and_ema_relationships():
    snapshot = build_market_context_snapshots(candles())[-1]
    assert 0 <= snapshot["candle"]["body_range_ratio"] <= 1
    assert snapshot["atr"] is not None
    assert snapshot["atr_normalized"]["range"] > 0
    assert snapshot["ema"]["ordering"] == "FAST_ABOVE"


def test_no_lookahead_pair_isolation_and_join_fields():
    data = candles(); data[20]["setup_id"] = "S-1"; data[20]["rejection_reason"] = "spread"
    full = build_market_context_snapshots(data)
    for prefix_length in range(1, len(data) + 1):
        assert build_market_context_snapshots(data[:prefix_length]) == full[:prefix_length]
    before = build_market_context_snapshots(data[:20])[-1]
    after = build_market_context_snapshots(data[:22])[19]
    assert before == after
    assert after["setup_id"] is None
    assert full[20]["setup_id"] == "S-1"
    assert full[20]["rejection_reason"] == "spread"
    other = candles("GBPUSD")
    assert build_market_context_snapshots(other)[-1]["pair"] == "GBPUSD"


def test_supertrend_structure_missing_history_is_explicit():
    first = build_market_context_snapshots(candles(n=3))[0]
    assert first["supertrend"]["value"] is None
    assert first["structure"]["higher_high"] is None
    assert first["session"] == "ASIA"
