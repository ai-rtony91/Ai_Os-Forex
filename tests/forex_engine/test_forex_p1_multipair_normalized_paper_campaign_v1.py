from __future__ import annotations

import json
from pathlib import Path

import pytest
from datetime import datetime, timedelta, timezone

import automation.forex_engine.forex_p1_multipair_normalized_paper_campaign_v1 as module
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient


def _candle(time: str, open_: float, high: float, low: float, close: float) -> dict:
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


class FakeClient(OandaReadOnlyClient):
    def __init__(self) -> None:
        super().__init__(api_token="token", account_id="account", environment="practice", timeout_seconds=1, opener=None)
        self.pricing_calls = 0

    def discover_instruments(self) -> dict:
        return {
            "instruments": [
                {"name": "EUR_USD", "type": "CURRENCY", "tradeable": True, "halted": False, "displayPrecision": 5, "pipLocation": -4},
                {"name": "USD_JPY", "type": "CURRENCY", "tradeable": True, "halted": False, "displayPrecision": 3, "pipLocation": -2},
            ]
        }

    def observation_candles(self, instrument: str, *, granularity: str, count: int, price: str = "M") -> dict:
        assert granularity == "M5"
        assert price == "M"
        if instrument == "EUR_USD":
            candles = [
                _candle(f"2026-08-01T10:{index:02d}:00Z", 1.1000 + index * 0.0001, 1.1004 + index * 0.0001, 1.0996 + index * 0.0001, 1.1001 + index * 0.0001)
                for index in range(count)
            ]
        else:
            candles = [
                _candle(f"2026-08-01T10:{index:02d}:00Z", 110.00 + index * 0.01, 110.04 + index * 0.01, 109.96 + index * 0.01, 110.01 + index * 0.01)
                for index in range(count)
            ]
        return {"instrument": instrument, "granularity": "M5", "candles": candles[:count]}

    def pricing(self, instruments: tuple[str, ...]) -> dict:
        self.pricing_calls += 1
        eur = "1.1002" if self.pricing_calls == 1 else "1.1055"
        time = "2026-08-01T10:30:00Z" if self.pricing_calls == 1 else "2026-08-01T10:35:00Z"
        jpy = "110.02"
        return {
            "prices": [
                {"instrument": "EUR_USD", "time": time, "bids": [{"price": eur}], "asks": [{"price": str(float(eur) + 0.0002)}]},
                {"instrument": "USD_JPY", "time": time, "bids": [{"price": jpy}], "asks": [{"price": "110.05"}]},
            ]
        }


class TransientStartupClient(FakeClient):
    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures
        self.discover_calls = 0

    def discover_instruments(self) -> dict:
        self.discover_calls += 1
        if self.discover_calls <= self.failures:
            raise module.OandaReadOnlyClientError("NETWORK_ERROR_SANITIZED")
        return super().discover_instruments()


class TransientPricingClient(FakeClient):
    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    def pricing(self, instruments: tuple[str, ...]) -> dict:
        self.pricing_calls += 1
        if self.pricing_calls <= self.failures:
            raise module.OandaReadOnlyClientError("NETWORK_ERROR_SANITIZED")
        return super().pricing(instruments)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _runtime_root(name: str) -> Path:
    root = REPO_ROOT / ".tmp" / "forex_multipair_normalized_tests" / name
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_normalized_campaign_opens_then_closes_and_records_trade(monkeypatch):
    client = FakeClient()
    runtime_root = _runtime_root("campaign")
    base_time = datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc)
    clock_index = {"value": 0}

    def now():
        offset = clock_index["value"]
        clock_index["value"] += 1
        return base_time + timedelta(minutes=offset * 5)
    monkeypatch.setattr(module, "_acquire_lock", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "_touch_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(module, "_release_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        module,
        "replay_candidate",
        lambda instrument, candles, snapshot, strategy_config=None: (
            {
                "strategy_id": module.STRATEGY_ID,
                "strategy_name": module.STRATEGY_ID,
                "protocol_version": module.PROTOCOL_VERSION,
                "instrument": instrument.instrument,
                "base_currency": instrument.base_currency,
                "quote_currency": instrument.quote_currency,
                "direction": "BUY",
                "timeframe": "M5",
                "display_precision": instrument.display_precision,
                "pip_location": instrument.pip_location,
                "pip_size": instrument.pip_size,
                "entry_price": 1.1000,
                "stop_price": 1.0990,
                "target_price": 1.1020,
                "risk_distance": 0.0010,
                "risk_pips": 10.0,
                "planned_reward_risk": 2.0,
                "planned_target_reward_risk": 2.0,
                "units": 100,
                "entry_rationale": "test",
                "candidate_id": f"cand-{instrument.instrument}",
                "status": "PAPER_ELIGIBLE",
                "sanitized": True,
                "current": True,
                "mode": "PAPER_ONLY",
                "paper_only": True,
                "quote_currency": instrument.quote_currency,
                "realized_pl_usd": "NOT_COMPUTABLE",
            }
            if instrument.instrument == "EUR_USD" and snapshot["ask"] < 1.1020
            else None
        ),
    )

    def fake_run_pipeline(input_path: Path, ledger_path: Path, state_path: Path, report_path: Path) -> dict:
        record = json.loads(input_path.read_text(encoding="utf-8"))
        ledger = {
            "version": module.VERSION,
            "records": [record],
            "broker_write_performed": False,
            "practice_order_performed": False,
            "live_trade_performed": False,
            "money_movement_performed": False,
            "credentials_persisted": False,
        }
        ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        state = {
            "version": module.VERSION,
            "pipeline_status": "COMPLETE",
            "input_records": 1,
            "accepted_records": 1,
            "rejected_records": 0,
            "duplicate_records": 0,
            "rejections": [],
            "qualifying_trade_count": 1,
            "p1_status_before": "NO_EVIDENCE",
            "p1_status_after": "READY_FOR_P1_REVIEW",
            "profitability_proven": True,
            "ready_for_p2_review": True,
            "next_safe_action": "none",
            "p1_evaluator_result": {"trade_count": 1, "win_rate": 1.0, "gross_profit": 1.0, "gross_loss": 0.0, "net_pl": 1.0, "expectancy_per_trade": 1.0, "profit_factor": None, "maximum_drawdown": 0.0, "consecutive_losses": 0},
            "broker_write_performed": False,
            "practice_order_performed": False,
            "live_trade_performed": False,
            "money_movement_performed": False,
            "credentials_persisted": False,
        }
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report_path.write_text("# ok\n", encoding="utf-8")
        return state

    monkeypatch.setattr(module, "run_pipeline", fake_run_pipeline)

    state = module.run_normalized_multipair_campaign(
        client,
        cycles=2,
        reviewer_identity="Human Owner Anthony",
        runtime_root=runtime_root,
        now=now,
        sleep=lambda *_args, **_kwargs: None,
    )

    assert state["accepted_qualifying_trades"] == 1
    assert state["active_position_status"] == "NONE"
    assert (runtime_root / "AIOS_FOREX_MULTIPAIR_NORMALIZED_PAPER_CAMPAIGN_STATE.json").exists()
    telemetry = (runtime_root / "AIOS_FOREX_MULTIPAIR_NORMALIZED_CYCLE_PROVENANCE.jsonl").read_text(encoding="utf-8")
    assert "PAPER_SESSION_OPEN" in telemetry
    assert "PAPER_SESSION_CLOSE" in telemetry
    tombstone = json.loads((runtime_root / "active.json").read_text(encoding="utf-8"))
    assert tombstone["status"] == "CLOSED"
    assert tombstone["closed_reason"] == "paper_target"


def test_startup_discovery_retries_transient_network_failures(monkeypatch):
    client = TransientStartupClient(failures=2)
    runtime_root = _runtime_root("startup_retry")
    sleeps = []
    monkeypatch.setattr(module, "_acquire_lock", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "_touch_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(module, "_release_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(module, "replay_candidate", lambda *args, **kwargs: None)
    state = module.run_normalized_multipair_campaign(
        client,
        cycles=1,
        reviewer_identity="Human Owner Anthony",
        runtime_root=runtime_root,
        now=lambda: datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc),
        sleep=sleeps.append,
    )
    assert client.discover_calls == 3
    assert sleeps == [30, 60, 300]
    assert state["campaign_status"] == "RUNNING"


def test_startup_backoff_sequence_is_bounded():
    assert [module._data_unavailable_backoff_seconds(i) for i in range(1, 7)] == [30, 60, 120, 240, 300, 300]


def test_pricing_transient_failure_records_wait_for_data(monkeypatch):
    client = TransientPricingClient(failures=1)
    runtime_root = _runtime_root("pricing_wait")
    monkeypatch.setattr(module, "_acquire_lock", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "_touch_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(module, "_release_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(module, "replay_candidate", lambda *args, **kwargs: None)
    sleeps = []
    state = module.run_normalized_multipair_campaign(
        client,
        cycles=1,
        reviewer_identity="Human Owner Anthony",
        runtime_root=runtime_root,
        now=lambda: datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc),
        sleep=sleeps.append,
    )
    telemetry = (runtime_root / "AIOS_FOREX_MULTIPAIR_NORMALIZED_CYCLE_PROVENANCE.jsonl").read_text(encoding="utf-8")
    assert "WAIT_FOR_DATA" in telemetry
    assert "data_unavailable" in telemetry
    assert sleeps == [30]
    assert state["campaign_status"] == "RUNNING"


def test_active_position_pricing_failure_waits_without_closing(monkeypatch):
    client = TransientPricingClient(failures=1)
    runtime_root = _runtime_root("active_wait")
    active_path = runtime_root / "active.json"
    active_path.write_text(
        json.dumps(
            {
                "schema": "AIOS_P1_SUPERVISED_PAPER_SESSION.v1",
                "status": "ACTIVE",
                "instrument": "EUR_USD",
                "entry_price": 1.1000,
                "stop_price": 1.0990,
                "target_price": 1.1020,
                "quote_currency": "USD",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_acquire_lock", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "_touch_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(module, "_release_lock", lambda *args, **kwargs: True)
    sleeps = []
    state = module.run_normalized_multipair_campaign(
        client,
        cycles=1,
        reviewer_identity="Human Owner Anthony",
        runtime_root=runtime_root,
        now=lambda: datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc),
        sleep=sleeps.append,
    )
    assert (runtime_root / "active.json").read_text(encoding="utf-8").find('"status": "ACTIVE"') != -1
    telemetry = (runtime_root / "AIOS_FOREX_MULTIPAIR_NORMALIZED_CYCLE_PROVENANCE.jsonl").read_text(encoding="utf-8")
    assert "WAIT_FOR_DATA" in telemetry
    assert "PAPER_SESSION_CLOSE" not in telemetry
    assert state["campaign_status"] == "RUNNING"


def test_normalized_campaign_supports_sell_session_and_records_sell_direction(monkeypatch):
    client = FakeClient()
    runtime_root = _runtime_root("campaign_sell")
    base_time = datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc)
    clock_index = {"value": 0}

    def now():
        offset = clock_index["value"]
        clock_index["value"] += 1
        return base_time + timedelta(minutes=offset * 5)

    monkeypatch.setattr(module, "_acquire_lock", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "_touch_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(module, "_release_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        module,
        "replay_candidate",
        lambda instrument, candles, snapshot, strategy_config=None: (
            {
                "strategy_id": module.STRATEGY_ID,
                "strategy_name": module.STRATEGY_ID,
                "protocol_version": module.PROTOCOL_VERSION,
                "instrument": instrument.instrument,
                "base_currency": instrument.base_currency,
                "quote_currency": instrument.quote_currency,
                "direction": "SELL",
                "timeframe": "M5",
                "display_precision": instrument.display_precision,
                "pip_location": instrument.pip_location,
                "pip_size": instrument.pip_size,
                "entry_price": 1.1002,
                "stop_price": 1.1015,
                "target_price": 1.0980,
                "risk_distance": 0.0013,
                "risk_pips": 13.0,
                "planned_reward_risk": 1.69230769,
                "planned_target_reward_risk": 1.69230769,
                "units": 100,
                "entry_rationale": "test",
                "candidate_id": f"cand-sell-{instrument.instrument}",
                "status": "PAPER_ELIGIBLE",
                "sanitized": True,
                "current": True,
                "mode": "PAPER_ONLY",
                "paper_only": True,
                "quote_currency": instrument.quote_currency,
                "realized_pl_usd": "NOT_COMPUTABLE",
            }
            if instrument.instrument == "EUR_USD" and snapshot["bid"] > 1.1000
            else None
        ),
    )
    pricing_calls = {"value": 0}

    def sell_pricing(_instruments: tuple[str, ...]) -> dict:
        pricing_calls["value"] += 1
        time = "2026-08-01T10:30:00Z" if pricing_calls["value"] == 1 else "2026-08-01T10:35:00Z"
        ask = "1.1004" if pricing_calls["value"] == 1 else "1.0974"
        bid = "1.1002" if pricing_calls["value"] == 1 else "1.0972"
        return {
            "prices": [
                {"instrument": "EUR_USD", "time": time, "bids": [{"price": bid}], "asks": [{"price": ask}]},
                {"instrument": "USD_JPY", "time": time, "bids": [{"price": "110.02"}], "asks": [{"price": "110.05"}]},
            ]
        }

    client.pricing = sell_pricing  # type: ignore[method-assign]

    def fake_run_pipeline(input_path: Path, ledger_path: Path, state_path: Path, report_path: Path) -> dict:
        record = json.loads(input_path.read_text(encoding="utf-8"))
        ledger = {
            "version": module.VERSION,
            "records": [record],
            "broker_write_performed": False,
            "practice_order_performed": False,
            "live_trade_performed": False,
            "money_movement_performed": False,
            "credentials_persisted": False,
        }
        ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        state = {
            "version": module.VERSION,
            "pipeline_status": "COMPLETE",
            "input_records": 1,
            "accepted_records": 1,
            "rejected_records": 0,
            "duplicate_records": 0,
            "rejections": [],
            "qualifying_trade_count": 1,
            "p1_status_before": "NO_EVIDENCE",
            "p1_status_after": "READY_FOR_P1_REVIEW",
            "profitability_proven": True,
            "ready_for_p2_review": True,
            "next_safe_action": "none",
            "p1_evaluator_result": {"trade_count": 1, "win_rate": 1.0, "gross_profit": 1.0, "gross_loss": 0.0, "net_pl": 1.0, "expectancy_per_trade": 1.0, "profit_factor": None, "maximum_drawdown": 0.0, "consecutive_losses": 0},
            "broker_write_performed": False,
            "practice_order_performed": False,
            "live_trade_performed": False,
            "money_movement_performed": False,
            "credentials_persisted": False,
        }
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report_path.write_text("# ok\n", encoding="utf-8")
        return state

    monkeypatch.setattr(module, "run_pipeline", fake_run_pipeline)

    state = module.run_normalized_multipair_campaign(
        client,
        cycles=2,
        reviewer_identity="Human Owner Anthony",
        runtime_root=runtime_root,
        now=now,
        sleep=lambda *_args, **_kwargs: None,
    )

    assert state["accepted_qualifying_trades"] == 1
    ledger = json.loads((runtime_root / "AIOS_FOREX_MULTIPAIR_NORMALIZED_PAPER_LEDGER.json").read_text(encoding="utf-8"))
    assert ledger["records"][0]["direction"] == "SELL"
    assert ledger["records"][0]["realized_r"] > 0
    tombstone = json.loads((runtime_root / "active.json").read_text(encoding="utf-8"))
    assert tombstone["status"] == "CLOSED"
    assert tombstone["closed_reason"] == "paper_target"
