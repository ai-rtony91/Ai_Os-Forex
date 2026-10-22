from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from automation.forex_engine import forex_persistent_all_pairs_m1_m2_observer_v1 as observer  # noqa: E402
from automation.forex_engine.oanda_read_only_client import (  # noqa: E402
    OandaReadOnlyClient,
    ReadOnlyMethodRejected,
)


NOW = datetime(2026, 8, 18, 16, 30, tzinfo=timezone.utc)


def _candle_payload(instrument: str, granularity: str, *, count: int = 8):
    start = NOW - timedelta(minutes=count * (1 if granularity == "M1" else 2 if granularity == "M2" else 5))
    candles = []
    for index in range(count):
        stamp = start + timedelta(minutes=(index + 1) * (1 if granularity == "M1" else 2 if granularity == "M2" else 5))
        open_price = 1.1000 + index * 0.0001
        candles.append({
            "time": stamp.isoformat().replace("+00:00", "Z"), "complete": True, "volume": 10,
            "mid": {"o": str(open_price), "h": str(open_price + 0.0003), "l": str(open_price - 0.0001), "c": str(open_price + 0.0002)},
        })
    candles.append({"time": (NOW + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"), "complete": False, "mid": {"o": "9", "h": "9", "l": "9", "c": "9"}})
    return {"instrument": instrument, "granularity": granularity, "candles": candles}


def _quote(instrument: str = "EUR_USD"):
    return {
        "instrument": instrument, "time": NOW.isoformat().replace("+00:00", "Z"),
        "bids": [{"price": "1.10010"}], "asks": [{"price": "1.10020"}],
    }


def _accepted_evaluation(direction: str = "BUY"):
    candidate = SimpleNamespace(
        direction=direction, stop_loss=1.0990, take_profit=1.1025,
        regime_trend="SUPERTREND_UP" if direction == "BUY" else "SUPERTREND_DOWN",
    )
    return {"accepted": True, "candidate": candidate, "no_trade_reasons": []}


def test_instrument_discovery_keeps_only_enabled_forex_pairs():
    result = observer.eligible_forex_instruments({"instruments": [
        {"name": "EUR_USD", "type": "CURRENCY", "tradeable": True, "displayPrecision": 5, "pipLocation": -4}, {"name": "USD_JPY", "type": "CURRENCY", "tradeable": False},
        {"name": "XAU_USD", "type": "METAL", "tradeable": True}, {"name": "EUR_GBP", "type": "CURRENCY", "tradeable": True, "halted": True},
    ]})
    assert result["eligible_instruments"] == ["EUR_USD"]
    assert {item["reason"] for item in result["excluded_instruments"]} == {"not_tradeable", "not_forex_classified", "halted"}
    assert result["raw_payload_included"] is False


def test_observation_client_extends_get_only_contract_without_loosening_legacy_candles():
    observed = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self): return b'{"instruments": []}'

    def opener(request, **_kwargs):
        observed["method"] = request.get_method()
        observed["url"] = request.full_url
        return Response()

    client = OandaReadOnlyClient(api_token="private", account_id="private", opener=opener)
    assert client.discover_instruments() == {"instruments": []}
    assert observed["method"] == "GET" and "/instruments" in observed["url"]
    with pytest.raises(ReadOnlyMethodRejected):
        client.request_json("POST", "/v3/accounts/private/orders")
    with pytest.raises(ValueError, match="unsupported_candle_granularity"):
        client.candles("EUR_USD", granularity="M1", count=50)


def test_completed_candle_parser_excludes_incomplete_data_and_rejects_lookahead():
    candles = observer.completed_candles(_candle_payload("EUR_USD", "M1"), instrument="EUR_USD", granularity="M1")
    assert len(candles) == 8
    assert candles[-1].close < 2
    with pytest.raises(ValueError, match="candle_payload_identity_mismatch"):
        observer.completed_candles(_candle_payload("EUR_USD", "M1"), instrument="GBP_USD", granularity="M1")


def test_spread_gate_uses_buy_ask_and_explicit_usd_conversion_status():
    quote = observer.build_quote_snapshot(_quote(), instrument="EUR_USD", collected_at=NOW)
    result = observer.spread_gate(
        instrument="EUR_USD", quote=quote, stop=1.0990, target=1.1025,
        direction="BUY", units=100, mids={"EUR_USD": quote["mid"]},
    )
    assert result["entry_price"] == quote["ask"]
    assert result["estimated_spread_cost_usd"] == pytest.approx(0.01)
    assert result["eligible"] is True

    unavailable = observer.spread_gate(
        instrument="EUR_JPY", quote={**quote, "bid": 170.00, "ask": 170.01}, stop=169.0, target=172.0,
        direction="BUY", units=100, mids={},
    )
    assert unavailable["spread_usd_status"] == "CONVERSION_UNAVAILABLE"
    assert "usd_spread_conversion_unavailable" in unavailable["rejection_reasons"]


def test_candidate_path_is_m2_first_with_m1_confirmation_and_no_lookahead(monkeypatch):
    monkeypatch.setattr(observer, "evaluate_supertrend_pullback", lambda *_args, **_kwargs: _accepted_evaluation())
    quote = observer.build_quote_snapshot(_quote(), instrument="EUR_USD", collected_at=NOW)
    m1 = observer.completed_candles(_candle_payload("EUR_USD", "M1"), instrument="EUR_USD", granularity="M1")
    m2 = observer.completed_candles(_candle_payload("EUR_USD", "M2"), instrument="EUR_USD", granularity="M2")
    m5 = observer.completed_candles(_candle_payload("EUR_USD", "M5"), instrument="EUR_USD", granularity="M5")
    result = observer.candidate_evidence(instrument="EUR_USD", quote=quote, m1=m1, m2=m2, m5=m5, mids={"EUR_USD": quote["mid"]})
    assert result["candidate_status"] == "PAPER_ELIGIBLE"
    assert result["decision_timeframe"] == "M2"
    assert result["m1_confirmation"] == "m1_bullish_close_confirmation"
    assert result["lookahead_used"] is False
    assert result["paper_eligible"] is True


def test_scheduler_and_fair_batching_account_for_deadlines_without_drift():
    ticks = iter([10.0, 10.4, 11.2])
    cadence = observer.MonotonicCadence(interval_seconds=1.0, monotonic=lambda: next(ticks))
    deadline = cadence.next_deadline()
    assert deadline.scheduled_at_monotonic == 10.0
    assert deadline.observed_at_monotonic == 10.4
    assert deadline.missed_seconds == pytest.approx(0.4)
    assert observer.fair_batches(["EUR_USD", "GBP_USD", "USD_JPY"], batch_size=2, rotation=1) == [("GBP_USD", "USD_JPY"), ("EUR_USD",)]


def test_cycle_is_fair_and_degrades_candle_work_without_opening_sessions(monkeypatch):
    client = OandaReadOnlyClient(api_token="private", account_id="private", environment="practice")
    calls = []
    client.pricing = lambda instruments: {"prices": [_quote(item) for item in instruments]}
    client.observation_candles = lambda instrument, **kwargs: (calls.append((instrument, kwargs["granularity"])) or _candle_payload(instrument, kwargs["granularity"]))
    monkeypatch.setattr(observer, "evaluate_supertrend_pullback", lambda *_args, **_kwargs: _accepted_evaluation())
    cycle = observer.observer_cycle(client, universe=["EUR_USD", "GBP_USD"], candle_budget=1, now=NOW)
    assert cycle["paper_sessions_opened"] == 0
    assert cycle["qualifying_trades_incremented"] == 0
    assert len(calls) == 3
    assert any(item["candidate_status"] == "DEGRADED_RATE_LIMIT" for item in cycle["decisions"])
    assert all(item["broker_write_performed"] is False for item in cycle["decisions"])


def test_observer_rejects_live_transport_before_any_observation():
    client = OandaReadOnlyClient(api_token="private", account_id="private", environment="live")
    with pytest.raises(ValueError, match="practice_environment_required"):
        observer.observer_cycle(client, universe=["EUR_USD"])


def test_durable_evidence_rejects_secrets_and_observer_lock_is_isolated(tmp_path):
    with pytest.raises(ValueError, match="sensitive_or_raw_artifact_field_forbidden"):
        observer.append_evidence(tmp_path / "events.jsonl", {"token": "must-not-write"})
    owner = observer.acquire_observer_lock(tmp_path, now=NOW)
    assert owner is not None
    assert observer.acquire_observer_lock(tmp_path, now=NOW) is None
    assert observer.observer_lock_path(tmp_path).name == "observer.lock"
    cycle = {"cycle_timestamp_utc": NOW.isoformat().replace("+00:00", "Z"), "paper_only": True}
    path = observer.write_cycle_evidence(tmp_path, cycle, owner=owner)
    assert json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))["qualifying_trades"] == 0
    assert path.name.startswith("observer-events-") and path.suffix == ".jsonl"
    assert observer.release_observer_lock(tmp_path, owner) is True


def test_persistent_observer_rechecks_universe_and_uses_its_own_runtime_root(monkeypatch, tmp_path):
    client = OandaReadOnlyClient(api_token="private", account_id="private", environment="practice")
    client.discover_instruments = lambda: {"instruments": [{"name": "EUR_USD", "type": "CURRENCY", "tradeable": True, "displayPrecision": 5, "pipLocation": -4}]}
    client.pricing = lambda instruments: {"prices": [_quote(item) for item in instruments]}
    client.observation_candles = lambda instrument, **kwargs: _candle_payload(instrument, kwargs["granularity"])
    monkeypatch.setattr(observer, "evaluate_supertrend_pullback", lambda *_args, **_kwargs: _accepted_evaluation())
    service = observer.PersistentObserver(client, runtime_root=tmp_path, candle_budget=1)
    assert not (tmp_path / "observer.lock").exists()
    service.start(now=NOW)
    cycle = service.cycle(now=NOW)
    assert service.universe == ("EUR_USD",)
    assert cycle["qualifying_trades_incremented"] == 0
    assert (tmp_path / "heartbeat.json").exists()
    assert service.stop() is True


def test_outcome_summary_never_awards_campaign_credit():
    def outcome(candidate_id, status, gross):
        return {
            "record_type": "PAPER_OUTCOME", "candidate_id": candidate_id, "status": status,
            "gross_pl_usd": gross, "estimated_spread_cost_usd": 0.0,
            "estimated_slippage_cost_usd": 0.0, "net_pl_usd": gross,
            "mfe_price": 1.2, "mae_price": 1.0, "holding_seconds": 60.0, "r_multiple": gross,
        }
    result = observer.summarize_outcomes([
        outcome("one", "CLOSED", 1.0), outcome("two", "CLOSED", -0.5), outcome("three", "ACTIVE", 0.0),
    ])
    assert result == {
        "wins": 1, "losses": 1, "flats": 1, "unclosed": 1, "net_pl_usd": 0.5,
        "qualifying_trades_incremented": 0, **observer.SAFETY,
    }
    bad = outcome("bad", "CLOSED", 1.0) | {"net_pl_usd": 0.9}
    with pytest.raises(ValueError, match="paper_outcome_net_pl_mismatch"):
        observer.validate_paper_outcome(bad)


def test_hypothetical_exit_uses_buy_bid_and_keeps_zero_campaign_credit():
    quote = observer.build_quote_snapshot(_quote(), instrument="EUR_USD", collected_at=NOW)
    session = {
        "observer_owned": True, "qualifying_credit": False, "candidate_id": "candidate-one", "direction": "BUY",
        "entry": 1.1002, "stop": 1.0990, "target": 1.1003, "units": 100,
        "opened_at_utc": (NOW - timedelta(seconds=60)).isoformat().replace("+00:00", "Z"),
        "estimated_spread_cost_usd": 0.01,
    }
    result = observer.observe_hypothetical_exit(session, quote, observed_at=NOW)
    assert result["exit_price"] == quote["bid"]
    assert result["exit_reason"] == "HOLD"
    assert result["qualifying_credit"] is False
    assert result["holding_seconds"] == 60.0


def test_evidence_rotation_is_bounded_and_crash_safe(tmp_path):
    record = {"schema": observer.SCHEMA, "record_type": "OBSERVER_CYCLE", "paper_only": True, "payload": "x" * 2048}
    first = observer.append_rotating_evidence(tmp_path, record, now=NOW, max_bytes=1024, retention_files=2)
    second = observer.append_rotating_evidence(tmp_path, record, now=NOW, max_bytes=1024, retention_files=2)
    third = observer.append_rotating_evidence(tmp_path, record, now=NOW + timedelta(days=1), max_bytes=1024, retention_files=2)
    assert first != second and second != third
    assert len(list(tmp_path.glob("observer-events-*.jsonl"))) == 2
    assert third.read_text(encoding="utf-8").endswith("\n")
