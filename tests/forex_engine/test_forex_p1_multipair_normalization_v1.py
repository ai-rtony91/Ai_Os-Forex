from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import automation.forex_engine.forex_p1_multipair_normalization_v1 as module
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient


class FakeClient(OandaReadOnlyClient):
    def __init__(self) -> None:
        super().__init__(api_token="token", account_id="account", environment="practice", timeout_seconds=1, opener=None)

    def discover_instruments(self) -> dict:
        return {
            "instruments": [
                {"name": "EUR_USD", "type": "CURRENCY", "tradeable": True, "halted": False, "displayPrecision": 5, "pipLocation": -4},
                {"name": "USD_JPY", "type": "CURRENCY", "tradeable": True, "halted": False, "displayPrecision": 3, "pipLocation": -2},
                {"name": "BAD", "type": "STOCK", "tradeable": False, "halted": False},
            ]
        }

    def observation_candles(self, instrument: str, *, granularity: str, count: int, price: str = "M") -> dict:
        assert granularity == "M5"
        assert price == "M"
        if instrument == "EUR_USD":
            candles = [
                {"time": f"2026-08-01T10:{index:02d}:00Z", "complete": True, "volume": 10,
                 "open": 1.1000 + index * 0.0001, "high": 1.1004 + index * 0.0001,
                 "low": 1.0996 + index * 0.0001, "close": 1.1001 + index * 0.0001,
                 "mid": {"o": 1.1000 + index * 0.0001, "h": 1.1004 + index * 0.0001, "l": 1.0996 + index * 0.0001, "c": 1.1001 + index * 0.0001},
                 "observed_at_utc": f"2026-08-01T10:{index:02d}:00Z"}
                for index in range(count)
            ]
        else:
            candles = [
                {"time": f"2026-08-01T10:{index:02d}:00Z", "complete": True, "volume": 10,
                 "open": 110.0 + index * 0.01, "high": 110.04 + index * 0.01,
                 "low": 109.96 + index * 0.01, "close": 110.01 + index * 0.01,
                 "mid": {"o": 110.0 + index * 0.01, "h": 110.04 + index * 0.01, "l": 109.96 + index * 0.01, "c": 110.01 + index * 0.01},
                 "observed_at_utc": f"2026-08-01T10:{index:02d}:00Z"}
                for index in range(count)
            ]
        return {"instrument": instrument, "granularity": "M5", "candles": candles[:count]}

    def pricing(self, instruments: tuple[str, ...]) -> dict:
        return {
            "prices": [
                {"instrument": "EUR_USD", "time": "2026-08-01T10:30:00Z", "bids": [{"price": "1.1050"}], "asks": [{"price": "1.1052"}]},
                {"instrument": "USD_JPY", "time": "2026-08-01T10:30:00Z", "bids": [{"price": "110.00"}], "asks": [{"price": "110.03"}]},
            ]
        }


def test_discover_universe_is_deterministic():
    client = FakeClient()
    universe = module.discover_fixed_universe(client)
    assert universe["discovered_pairs"] == ["EUR_USD", "USD_JPY"]
    assert universe["eligible_instruments"][0]["pip_size"] == pytest.approx(0.0001)
    assert universe["eligible_instruments"][1]["pip_size"] == pytest.approx(0.01)
    assert universe["universe_fingerprint"]


def test_snapshot_and_candidate_normalization():
    snap = module.sanitized_price_snapshot(
        {"prices": [{"instrument": "EUR_USD", "time": "2026-08-01T10:30:00Z", "bids": [{"price": "1.1050"}], "asks": [{"price": "1.1052"}]}]},
        instrument="EUR_USD",
    )
    assert snap["spread"] == pytest.approx(0.0002)
    instrument = module.NormalizedInstrument("EUR_USD", 5, -4, True, True)
    candles = module.candles_to_strategy_window(
        {"candles": [
            {"observed_at_utc": "2026-08-01T10:20:00Z", "open": 1.1000, "high": 1.1004, "low": 1.0996, "close": 1.1001, "volume": 10},
            {"observed_at_utc": "2026-08-01T10:25:00Z", "open": 1.1001, "high": 1.1005, "low": 1.0998, "close": 1.1004, "volume": 10},
            {"observed_at_utc": "2026-08-01T10:30:00Z", "open": 1.1004, "high": 1.1009, "low": 1.1000, "close": 1.1008, "volume": 10},
            {"observed_at_utc": "2026-08-01T10:35:00Z", "open": 1.1008, "high": 1.1012, "low": 1.1004, "close": 1.1010, "volume": 10},
            {"observed_at_utc": "2026-08-01T10:40:00Z", "open": 1.1010, "high": 1.1015, "low": 1.1008, "close": 1.1013, "volume": 10},
            {"observed_at_utc": "2026-08-01T10:45:00Z", "open": 1.1013, "high": 1.1055, "low": 1.1012, "close": 1.1050, "volume": 10},
        ]},
        instrument="EUR_USD",
    )
    candidate = module.replay_candidate(
        instrument,
        candles,
        snap,
        strategy_config=module.SupertrendPullbackConfig(),
    )
    if candidate is not None:
        assert candidate["direction"] == "BUY"
        assert candidate["planned_reward_risk"] >= module.MIN_RR


def test_replay_candidate_accepts_buy_and_sell_with_direction_safe_identity():
    instrument = module.NormalizedInstrument("EUR_USD", 5, -4, True, True)
    candles = [
        module.Candle(symbol="EURUSD", timeframe="5m", timestamp="2026-08-01T10:00:00Z", open=1.1000, high=1.1004, low=1.0996, close=1.1001, volume=10, source="test"),
        module.Candle(symbol="EURUSD", timeframe="5m", timestamp="2026-08-01T10:05:00Z", open=1.1001, high=1.1006, low=1.0998, close=1.1003, volume=10, source="test"),
        module.Candle(symbol="EURUSD", timeframe="5m", timestamp="2026-08-01T10:10:00Z", open=1.1003, high=1.1008, low=1.1000, close=1.1005, volume=10, source="test"),
    ]
    snapshot = {"bid": 1.1004, "ask": 1.1006}

    buy_signal = SimpleNamespace(direction=module.Direction.BUY, entry_price=1.1006, stop_loss=1.1000, take_profit=1.1018)
    sell_signal = SimpleNamespace(direction=module.Direction.SELL, entry_price=1.1004, stop_loss=1.1010, take_profit=1.0992)

    original = module.evaluate_supertrend_pullback
    try:
        module.evaluate_supertrend_pullback = lambda *_args, **_kwargs: {"accepted": True, "signal": buy_signal}
        buy_candidate = module.replay_candidate(instrument, candles, snapshot, strategy_config=module.SupertrendPullbackConfig())
        assert buy_candidate is not None
        assert buy_candidate["direction"] == module.Direction.BUY
        assert buy_candidate["stop_price"] < buy_candidate["entry_price"] < buy_candidate["target_price"]

        module.evaluate_supertrend_pullback = lambda *_args, **_kwargs: {"accepted": True, "signal": sell_signal}
        sell_candidate = module.replay_candidate(instrument, candles, snapshot, strategy_config=module.SupertrendPullbackConfig())
        assert sell_candidate is not None
        assert sell_candidate["direction"] == module.Direction.SELL
        assert sell_candidate["target_price"] < sell_candidate["entry_price"] < sell_candidate["stop_price"]
        assert sell_candidate["risk_distance"] > 0
        assert sell_candidate["planned_reward_risk"] == pytest.approx(2.0, rel=1e-9)
        assert sell_candidate["candidate_id"] != buy_candidate["candidate_id"]
    finally:
        module.evaluate_supertrend_pullback = original


def test_calibrate_candidate_to_actual_entry_supports_sell_and_rejects_invalid_geometry():
    candidate = {
        "direction": module.Direction.SELL,
        "entry_price": 1.1004,
        "stop_price": 1.1012,
        "target_price": 1.0988,
        "risk_distance": 0.0008,
        "risk_amount": 0.08,
        "planned_reward_risk": 2.0,
        "planned_target_reward_risk": 2.0,
        "display_precision": 5,
        "units": 100,
    }
    calibrated = module.calibrate_candidate_to_actual_entry(candidate, {"bid": 1.1004, "ask": 1.1006}, reward_risk=2.0)
    assert calibrated["entry_price"] == pytest.approx(1.1004)
    assert calibrated["stop_price"] == pytest.approx(1.1012)
    assert calibrated["target_price"] == pytest.approx(1.0988)
    assert calibrated["risk_distance"] == pytest.approx(1.1012 - 1.1004)
    assert calibrated["planned_reward_risk"] == pytest.approx(2.0)

    bad_candidate = dict(candidate)
    bad_candidate["stop_price"] = 1.1001
    with pytest.raises(ValueError):
        module.calibrate_candidate_to_actual_entry(bad_candidate, {"bid": 1.1004, "ask": 1.1006}, reward_risk=2.0)


def test_quote_mid_extraction_and_trade_outcome():
    mids = module.quote_mids_from_pricing(
        {"prices": [{"instrument": "USD_JPY", "time": "2026-08-01T10:30:00Z", "bids": [{"price": "110.00"}], "asks": [{"price": "110.03"}]}]}
    )
    assert mids["USD_JPY"] == pytest.approx(110.015)
    session = {
        "entry_price": 1.1000,
        "units": 100,
        "risk_amount": 0.10,
        "quote_currency": "USD",
    }
    outcome = module.normalized_trade_outcome(session, {"bid": 1.1020, "ask": 1.1022}, quote_mids=mids)
    assert outcome["realized_pl_quote_currency"] > 0
    assert outcome["roi_class"] == "POSITIVE_R"

    short_session = {
        "entry_price": 1.1000,
        "units": 100,
        "risk_amount": 0.10,
        "quote_currency": "USD",
        "direction": module.Direction.SELL,
    }
    short_outcome = module.normalized_trade_outcome(short_session, {"bid": 1.0980, "ask": 1.0982}, quote_mids=mids)
    assert short_outcome["realized_pl_quote_currency"] > 0
    assert short_outcome["roi_class"] == "POSITIVE_R"


def test_actual_entry_calibration_uses_snapshot_ask_geometry():
    candidate = {
        "direction": module.Direction.BUY,
        "entry_price": 1.1000,
        "stop_price": 1.0990,
        "target_price": 1.1020,
        "risk_distance": 0.0010,
        "risk_amount": 0.10,
        "planned_reward_risk": 2.0,
        "planned_target_reward_risk": 2.0,
        "display_precision": 5,
        "units": 100,
    }
    snapshot = {"ask": 1.1002}
    calibrated = module.calibrate_candidate_to_actual_entry(candidate, snapshot, reward_risk=2.0)
    assert calibrated["entry_price"] == pytest.approx(1.1002)
    assert calibrated["stop_price"] == pytest.approx(1.0990)
    assert calibrated["target_price"] == pytest.approx(1.1026)
    assert calibrated["risk_amount"] == pytest.approx((1.1002 - 1.0990) * 100)
    assert calibrated["planned_reward_risk"] == pytest.approx(2.0)


def test_normalized_atr_threshold_is_pip_based():
    assert module.normalized_min_atr_price("EUR_USD") == pytest.approx(0.0004)
    assert module.normalized_min_atr_price("USD_JPY") == pytest.approx(0.04)
    eur_cfg = module.normalized_strategy_config("EUR_USD")
    jpy_cfg = module.normalized_strategy_config("USD_JPY")
    assert eur_cfg.min_atr == pytest.approx(0.0004)
    assert jpy_cfg.min_atr == pytest.approx(0.04)


def test_historical_usd_pl_conversion_uses_mba_timestamp_and_quote_side():
    replay_cache = {
        "pair_histories": {
            "EUR_USD": {
                "sanitized_candles": [
                    {
                        "timestamp": "2026-08-01T10:00:00Z",
                        "bid": {"close": 1.1000},
                        "ask": {"close": 1.1002},
                    }
                ]
            },
            "USD_JPY": {
                "sanitized_candles": [
                    {
                        "timestamp": "2026-08-01T10:00:00Z",
                        "bid": {"close": 110.00},
                        "ask": {"close": 110.02},
                    }
                ]
            },
            "GBP_USD": {
                "sanitized_candles": [
                    {
                        "timestamp": "2026-08-01T10:00:00Z",
                        "bid": {"close": 1.2500},
                        "ask": {"close": 1.2503},
                    }
                ]
            },
            "USD_ZAR": {
                "sanitized_candles": [
                    {
                        "timestamp": "2026-08-01T10:00:00Z",
                        "bid": {"close": 18.0000},
                        "ask": {"close": 18.0100},
                    }
                ]
            },
        }
    }
    eur = module.historical_normalized_usd_pl(
        quote_currency="USD",
        quote_pl=15.0,
        conversion_timestamp="2026-08-01T10:00:00Z",
        replay_cache=replay_cache,
    )
    eur_jpy = module.historical_normalized_usd_pl(
        quote_currency="JPY",
        quote_pl=1000.0,
        conversion_timestamp="2026-08-01T10:00:00Z",
        replay_cache=replay_cache,
    )
    eur_gbp = module.historical_normalized_usd_pl(
        quote_currency="GBP",
        quote_pl=-10.0,
        conversion_timestamp="2026-08-01T10:00:00Z",
        replay_cache=replay_cache,
    )
    zar = module.historical_normalized_usd_pl(
        quote_currency="ZAR",
        quote_pl=100.0,
        conversion_timestamp="2026-08-01T10:00:00Z",
        replay_cache=replay_cache,
    )
    assert eur["normalized_usd_pl"] == pytest.approx(15.0)
    assert eur["conversion_provenance"] == "GENUINE_OANDA_HISTORICAL_MBA_CONVERSION"
    assert eur_jpy["conversion_pair"] == "USD_JPY"
    assert eur_jpy["conversion_side"] == "ASK"
    assert eur_jpy["normalized_usd_pl"] == pytest.approx(1000.0 / 110.02)
    assert eur_gbp["conversion_pair"] == "GBP_USD"
    assert eur_gbp["conversion_side"] == "ASK"
    assert eur_gbp["normalized_usd_pl"] == pytest.approx(-10.0 * 1.2503)
    assert zar["conversion_pair"] == "USD_ZAR"
    assert zar["conversion_side"] == "ASK"
    assert zar["normalized_usd_pl"] == pytest.approx(100.0 / 18.01)
