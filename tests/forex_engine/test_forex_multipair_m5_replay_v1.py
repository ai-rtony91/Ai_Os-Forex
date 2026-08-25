from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import automation.forex_engine.forex_multipair_m5_replay_v1 as module
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient

REPO_ROOT = Path(__file__).resolve().parents[2]


def candle(time: str, open_: float, high: float, low: float, close: float) -> dict:
    return {
        "time": time,
        "complete": True,
        "volume": 10,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "mid": {"o": open_, "h": high, "l": low, "c": close},
        "observed_at_utc": time,
    }


def incomplete_candle(time: str, open_: float, high: float, low: float, close: float) -> dict:
    item = candle(time, open_, high, low, close)
    item["complete"] = False
    return item


class FakeClient(OandaReadOnlyClient):
    def __init__(self) -> None:
        super().__init__(api_token="token", account_id="account", environment="practice", timeout_seconds=1, opener=None)

    def discover_instruments(self) -> dict:
        return {
            "instruments": [
                {"name": "EUR_USD", "type": "CURRENCY", "tradeable": True, "halted": False, "displayPrecision": 5, "pipLocation": -4},
                {"name": "USD_JPY", "type": "CURRENCY", "tradeable": True, "halted": False, "displayPrecision": 3, "pipLocation": -2},
            ]
        }

    def observation_candles(self, instrument: str, *, granularity: str, count: int, price: str = "M") -> dict:
        assert granularity == "M5"
        assert price in {"M", "MBA"}
        if instrument == "EUR_USD":
            candles = [
                candle("2026-08-01T10:00:00Z", 1.1000, 1.1004, 1.0996, 1.1001),
                candle("2026-08-01T10:05:00Z", 1.1001, 1.1006, 1.0999, 1.1003),
                candle("2026-08-01T10:10:00Z", 1.1003, 1.1007, 1.1000, 1.1005),
                candle("2026-08-01T10:15:00Z", 1.1005, 1.1009, 1.1001, 1.1008),
                candle("2026-08-01T10:20:00Z", 1.1008, 1.1012, 1.1004, 1.1010),
                candle("2026-08-01T10:25:00Z", 1.1010, 1.1055, 1.1009, 1.1052),
            ]
        else:
            candles = [
                candle("2026-08-01T10:00:00Z", 110.00, 110.04, 109.96, 110.01),
                candle("2026-08-01T10:05:00Z", 110.01, 110.06, 109.99, 110.03),
                candle("2026-08-01T10:10:00Z", 110.03, 110.07, 110.00, 110.05),
                candle("2026-08-01T10:15:00Z", 110.05, 110.09, 110.01, 110.08),
                candle("2026-08-01T10:20:00Z", 110.08, 110.12, 110.04, 110.10),
                candle("2026-08-01T10:25:00Z", 110.10, 110.11, 109.95, 109.97),
            ]
        payload = {"instrument": instrument, "granularity": "M5", "candles": candles[:count]}
        if price == "MBA":
            for item in payload["candles"]:
                item["bid"] = {"o": item["open"] - 0.0001, "h": item["high"] - 0.0001, "l": item["low"] - 0.0001, "c": item["close"] - 0.0001}
                item["ask"] = {"o": item["open"] + 0.0001, "h": item["high"] + 0.0001, "l": item["low"] + 0.0001, "c": item["close"] + 0.0001}
        return payload

    def pricing(self, instruments: tuple[str, ...]) -> dict:
        return {
            "prices": [
                {"instrument": "USD_JPY", "bids": [{"price": "110.00"}], "asks": [{"price": "110.02"}]},
                {"instrument": "JPY_USD", "bids": [{"price": "0.0090"}], "asks": [{"price": "0.0091"}]},
            ]
        }


class BoundaryClient(FakeClient):
    def observation_candles(self, instrument: str, *, granularity: str, count: int, price: str = "M") -> dict:
        assert granularity == "M5"
        assert price == "M"
        if instrument == "EUR_USD":
            candles = [
                candle("2026-08-01T10:00:00Z", 1.1000, 1.1004, 1.0996, 1.1001),
                candle("2026-08-01T10:05:00Z", 1.1001, 1.1006, 1.0999, 1.1003),
                candle("2026-08-01T10:10:00Z", 1.1003, 1.1007, 1.1000, 1.1005),
                candle("2026-08-01T10:15:00Z", 1.1005, 1.1009, 1.1001, 1.1008),
                candle("2026-08-01T10:20:00Z", 1.1008, 1.1012, 1.1004, 1.1010),
                candle("2026-08-01T10:25:00Z", 1.1010, 1.1014, 1.1009, 1.1011),
                incomplete_candle("2026-08-01T10:30:00Z", 1.1011, 1.1055, 1.1009, 1.1052),
            ]
        else:
            candles = [
                candle("2026-08-01T10:00:00Z", 110.00, 110.04, 109.96, 110.01),
                candle("2026-08-01T10:05:00Z", 110.01, 110.06, 109.99, 110.03),
                candle("2026-08-01T10:10:00Z", 110.03, 110.07, 110.00, 110.05),
                candle("2026-08-01T10:15:00Z", 110.05, 110.09, 110.01, 110.08),
                candle("2026-08-01T10:20:00Z", 110.08, 110.12, 110.04, 110.10),
                incomplete_candle("2026-08-01T10:25:00Z", 110.10, 110.11, 109.95, 109.97),
            ]
        return {"instrument": instrument, "granularity": "M5", "candles": candles[:count]}

def stub_strategy(candles, config):
    last = candles[-1]
    if len(candles) < 4:
        return {"accepted": False, "no_trade_reasons": ["insufficient_candles"]}
    if last.symbol == "EURUSD":
        return {
            "accepted": True,
            "signal": SimpleNamespace(direction="BUY", entry_price=1.1000, stop_loss=1.0990, take_profit=1.1020),
            "candidate": SimpleNamespace(direction="BUY", stop_loss=1.0990, take_profit=1.1020, entry_price=1.1000, metadata={"atr": 0.0010}),
            "no_trade_reasons": [],
        }
    return {
        "accepted": True,
        "signal": SimpleNamespace(direction="SELL", entry_price=110.080, stop_loss=110.120, take_profit=109.960),
        "candidate": SimpleNamespace(direction="SELL", stop_loss=110.120, take_profit=109.960, entry_price=110.080, metadata={"atr": 0.10}),
        "no_trade_reasons": [],
    }


def _runtime_root(name: str) -> Path:
    root = REPO_ROOT / ".aios" / "runtime" / "forex_multipair_m5_replay_v1_tests" / name
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_build_replay_cache_creates_sanitized_files(monkeypatch):
    client = FakeClient()
    runtime_root = _runtime_root("replay_cache")
    monkeypatch.setattr(module, "REPLAY_ROOT", runtime_root)
    cache = module.build_replay_cache(client, runtime_root=runtime_root, candle_count=5)
    assert cache["discovered_pairs"] == ["EUR_USD", "USD_JPY"]
    assert (runtime_root / "EUR_USD_M5.json").exists()
    assert (runtime_root / "USD_JPY_M5.json").exists()
    text = (runtime_root / "replay_cache.json").read_text(encoding="utf-8")
    assert "OANDA_API_TOKEN" not in text
    assert "account_id" not in text.lower()


def test_build_replay_cache_preserves_mba_components(monkeypatch):
    client = FakeClient()
    runtime_root = _runtime_root("replay_cache_mba")
    monkeypatch.setattr(module, "REPLAY_ROOT", runtime_root)
    cache = module.build_replay_cache(client, runtime_root=runtime_root, candle_count=5, price_component="MBA")
    assert cache["pair_histories"]["EUR_USD"]["price_component"] == "MBA"
    assert "bid" in cache["pair_histories"]["EUR_USD"]["sanitized_candles"][0]
    assert "ask" in cache["pair_histories"]["EUR_USD"]["sanitized_candles"][0]
    reloaded = json.loads((runtime_root / "replay_cache.json").read_text(encoding="utf-8"))
    candle = reloaded["pair_histories"]["EUR_USD"]["sanitized_candles"][0]
    assert candle["ask"]["close"] > candle["bid"]["close"]
    assert candle["ask"]["close"] - candle["bid"]["close"] == pytest.approx(0.0002)
    assert "pricing" not in json.dumps(candle).lower()


def test_fetch_replay_history_keeps_only_completed_tail(monkeypatch):
    client = BoundaryClient()

    def observing_observation_candles(instrument: str, *, granularity: str, count: int, price: str = "M") -> dict:
        payload = BoundaryClient.observation_candles(client, instrument, granularity=granularity, count=count, price=price)
        assert count == 6
        return payload

    monkeypatch.setattr(client, "observation_candles", observing_observation_candles)
    history = module.fetch_replay_history(client, "EUR_USD", candle_count=5)
    assert history["requested_count"] == 6
    assert history["returned_count"] == 5
    assert [row["timestamp"] for row in history["candles"]] == [
        "2026-08-01T10:05:00Z",
        "2026-08-01T10:10:00Z",
        "2026-08-01T10:15:00Z",
        "2026-08-01T10:20:00Z",
        "2026-08-01T10:25:00Z",
    ]


def test_fetch_replay_history_requires_mba_components_for_mba_lane(monkeypatch):
    class MbaClient(FakeClient):
        def observation_candles(self, instrument: str, *, granularity: str, count: int, price: str = "M") -> dict:
            payload = super().observation_candles(instrument, granularity=granularity, count=count, price=price)
            if price == "MBA":
                for item in payload["candles"]:
                    item["bid"] = {"o": item["open"] - 0.0001, "h": item["high"] - 0.0001, "l": item["low"] - 0.0001, "c": item["close"] - 0.0001}
                    item["ask"] = {"o": item["open"] + 0.0001, "h": item["high"] + 0.0001, "l": item["low"] + 0.0001, "c": item["close"] + 0.0001}
            return payload

    client = MbaClient()
    history = module.fetch_replay_history(client, "EUR_USD", candle_count=5, price_component="MBA")
    assert history["price_component"] == "MBA"
    assert "bid" in history["sanitized_candles"][0]
    assert "ask" in history["sanitized_candles"][0]


def test_fetch_replay_history_fails_closed_when_genuine_completed_history_is_short(monkeypatch):
    client = FakeClient()

    def short_observation_candles(instrument: str, *, granularity: str, count: int, price: str = "M") -> dict:
        payload = FakeClient.observation_candles(client, instrument, granularity=granularity, count=count, price=price)
        if instrument == "EUR_USD":
            payload["candles"] = payload["candles"][:4] + [incomplete_candle("2026-08-01T10:25:00Z", 1.1010, 1.1055, 1.1009, 1.1052)]
        return payload

    monkeypatch.setattr(client, "observation_candles", short_observation_candles)
    with pytest.raises(ValueError, match="insufficient_completed_m5_history"):
        module.fetch_replay_history(client, "EUR_USD", candle_count=5)


def test_replay_pair_counts_policy_blocked_sells(monkeypatch):
    monkeypatch.setattr(module, "evaluate_supertrend_pullback", stub_strategy)
    instrument = module.ReplayInstrument("EUR_USD", 5, -4, True, True)
    history = {
        "candles": [
            candle("2026-08-01T10:00:00Z", 1.1, 1.1004, 1.0996, 1.1001),
            candle("2026-08-01T10:05:00Z", 1.1001, 1.1006, 1.0999, 1.1003),
            candle("2026-08-01T10:10:00Z", 1.1003, 1.1007, 1.1000, 1.1005),
            candle("2026-08-01T10:15:00Z", 1.1005, 1.1009, 1.1001, 1.1008),
            candle("2026-08-01T10:20:00Z", 1.1008, 1.1012, 1.1004, 1.1010),
            candle("2026-08-01T10:25:00Z", 1.1010, 1.1055, 1.1009, 1.1052),
        ]
    }
    result = module.replay_pair(instrument, history, quote_mids={"USD_JPY": 110.0})
    assert result["valid_buy_candidates"] >= 1
    assert result["valid_sell_candidates"] == 0
    assert result["multiple_filters_blocked"] >= 0
    assert result["trade_stats"]["trade_count"] == len(result["trades"])
    assert result["trades"][0]["paper_only"] is True
    assert result["trades"][0]["realized_r"] > 0


def test_run_multipair_replay_aggregates_all_pairs(monkeypatch):
    client = FakeClient()
    runtime_root = _runtime_root("replay_run")
    monkeypatch.setattr(module, "evaluate_supertrend_pullback", stub_strategy)
    monkeypatch.setattr(
        client,
        "pricing",
        lambda instruments: {
            "prices": [
                {"instrument": "USD_JPY", "bids": [{"price": "110.00"}], "asks": [{"price": "110.02"}]},
                {"instrument": "JPY_USD", "bids": [{"price": "0.0090"}], "asks": [{"price": "0.0091"}]},
            ]
        },
    )
    result = module.run_multipair_m5_replay(client, runtime_root=runtime_root, candle_count=5)
    summary = module.summarize_replay_bridge(result)
    assert result["pair_count"] == 2
    assert result["discovered_pairs"] == 2
    assert summary["REPLAY_GRANTED_QUALIFYING_CREDIT"] is False
    assert summary["CURRENT_COLLECTOR_UNTOUCHED"] is True
    assert summary["VALID_BUY_CANDIDATES"] >= 1
    assert summary["ATR_ONLY_BLOCKED"] >= 0
    assert summary["PRICE_PRECISION"] in {"VALID", "REQUIRES_NORMALIZATION", "BLOCKING"}
    assert result["candles_per_pair"]["EUR_USD"] == 5


def test_cli_module_requires_process_credentials(monkeypatch):
    monkeypatch.delenv("OANDA_API_TOKEN", raising=False)
    monkeypatch.delenv("OANDA_ACCOUNT_ID", raising=False)
    with pytest.raises(ValueError, match="PROCESS_OANDA_PRACTICE_CREDENTIALS_REQUIRED"):
        module._load_process_credentials()
