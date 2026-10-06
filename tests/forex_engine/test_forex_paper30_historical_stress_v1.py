from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest

from automation.forex_engine import forex_paper30_historical_stress_v1 as stress


def _trade(index: int, instrument: str = "PAIR_00", realized_r: float = 0.25) -> dict:
    hour = index // 12
    minute = (index % 12) * 5
    timestamp = f"2026-08-20T{hour:02d}:{minute:02d}:00Z"
    return {
        "trade_id": f"T{index:04d}",
        "instrument": instrument,
        "direction": "BUY",
        "entry_timestamp_utc": timestamp,
        "exit_timestamp_utc": timestamp,
        "entry_price": 1.0,
        "initial_stop": 0.99,
        "exit_price": 1.0 + realized_r * 0.01,
        "entry_index": index,
        "exit_index": index,
        "exit_reason": "PROTECTIVE_STOP",
        "price_r": realized_r,
        "quote_r": realized_r,
        "realized_r": realized_r,
        "initial_risk_distance": 0.01,
    }


def _timestamps(count: int = 96) -> list[str]:
    return [_trade(index)["entry_timestamp_utc"] for index in range(count)]


def test_holdout_v1_and_v2_rows_are_excluded_by_development_boundary() -> None:
    history = {
        "candles": [
            {"timestamp": "2026-08-21T02:35:00Z", "open": 1, "high": 1.1, "low": .9, "close": 1},
            {"timestamp": "2026-08-21T02:40:00Z", "open": 1, "high": 1.1, "low": .9, "close": 1},
            {"timestamp": "2026-08-21T02:45:00Z", "open": 1, "high": 1.1, "low": .9, "close": 1},
            {"timestamp": "2026-08-22T02:45:00Z", "open": 1, "high": 1.1, "low": .9, "close": 1},
        ]
    }
    bounded = stress.filter_development_candles(
        {"EUR_USD": history}, "2026-08-21T02:40:00.000000000Z"
    )
    assert [candle.timestamp for candle in bounded["EUR_USD"]] == [
        "2026-08-21T02:35:00Z",
        "2026-08-21T02:40:00Z",
    ]


def test_fixed_strategy_only_and_buy_only_reproduction(monkeypatch: pytest.MonkeyPatch) -> None:
    buy = _trade(0)
    sell = {**_trade(1), "direction": "SELL"}
    incomplete = {**_trade(2), "exit_reason": "END_OF_DATA"}
    monkeypatch.setattr(stress, "_simulate_symbol", lambda candles, period, factor: [buy, sell, incomplete])
    candles = [SimpleNamespace(timestamp="2026-08-20T00:00:00Z")]
    result = stress.reproduce_trades(
        {"PAIR_00": candles}, "2026-08-20T12:00:00Z", "2026-08-21T00:00:00Z"
    )
    assert [trade["direction"] for trade in result] == ["BUY"]
    assert "candidate" not in inspect.getsource(stress.reproduce_trades).lower()


def test_68_pair_contribution_support_and_reconciliation() -> None:
    instruments = [f"PAIR_{index:02d}" for index in range(68)]
    trades = [_trade(index, instrument, 1.0 if index % 2 == 0 else -0.5) for index, instrument in enumerate(instruments)]
    records, summary = stress.pair_contribution(trades, instruments)
    assert len(records) == 68
    assert summary["pair_net_r_reconciliation"] == pytest.approx(
        sum(float(trade["realized_r"]) for trade in trades)
    )


def test_trade_hash_is_deterministic() -> None:
    trades = [_trade(index, realized_r=(-0.5 if index % 3 == 0 else 0.75)) for index in range(40)]
    assert stress._canonical_semantic_trade_hash(trades) == stress._canonical_semantic_trade_hash(list(trades))


def test_exactly_eight_chronological_folds() -> None:
    timestamps = _timestamps()
    folds = stress.chronological_folds([_trade(index) for index in range(96)], timestamps)
    assert len(folds) == 8
    assert all(folds[index]["end_timestamp"] < folds[index + 1]["start_timestamp"] for index in range(7))


def test_forward_path_never_reads_after_terminal_exit() -> None:
    candles = [
        SimpleNamespace(timestamp="T0", high=1.00),
        SimpleNamespace(timestamp="T1", high=1.04),
        SimpleNamespace(timestamp="T2", high=1.08),
        SimpleNamespace(timestamp="T3", high=2.00),
    ]
    trade = {
        **_trade(0, realized_r=-0.5),
        "entry_timestamp_utc": "T1",
        "exit_timestamp_utc": "T2",
        "entry_price": 1.0,
        "initial_risk_distance": 0.1,
        "entry_index": 1,
        "exit_index": 2,
    }
    result = stress.forward_path_metrics([trade], {"PAIR_00": candles})
    assert result["lookahead_detected"] is False
    assert result["reached_1r_count"] == 0


def test_leave_one_pair_out_is_deterministic() -> None:
    instruments = [f"PAIR_{index:02d}" for index in range(68)]
    trades = [_trade(index, instrument, 0.5 if index % 2 else -0.25) for index, instrument in enumerate(instruments)]
    first = stress.leave_one_pair_out(trades, instruments)
    second = stress.leave_one_pair_out(trades, instruments)
    assert first == second
    assert first[1]["leave_one_pair_out_runs"] == 68


def test_rolling_30_trade_windows_are_deterministic() -> None:
    trades = [_trade(index, realized_r=1.0 if index % 4 else -1.0) for index in range(50)]
    first = stress.rolling_30_trade_stress(trades)
    assert first == stress.rolling_30_trade_stress(trades)
    assert first["rolling_30_trade_window_count"] == 21


def test_bootstrap_seed_is_deterministic_at_required_size() -> None:
    realized = [1.0, -0.75, 0.5, -0.25]
    first = stress.bootstrap_30(realized)
    second = stress.bootstrap_30(realized)
    assert first == second
    assert first["bootstrap_seed"] == 20260822
    assert first["bootstrap_simulation_count"] == 10_000


def test_json_projection_is_standards_compliant() -> None:
    metrics = stress.trade_metrics([_trade(0, realized_r=1.0)])
    projected = stress.report_metrics(metrics)
    assert projected["profit_factor"] is None
    assert projected["profit_factor_status"] == "POSITIVE_INFINITY"
    json.dumps(projected, allow_nan=False)


def _qualifying_closed_record() -> dict:
    return {
        "trade_id": "PAPER-1",
        "instrument": "EUR_USD",
        "direction": "BUY",
        "exit_timestamp_utc": "2026-08-24T12:00:00Z",
        "exit_reason": "PROTECTIVE_STOP",
        "realized_r": 0.5,
        "strategy_config_sha256": stress.PAPER30_STRATEGY_CONFIG_SHA256,
        "broker_order": False,
        "historical_backfill": False,
        "qualifying": True,
    }


def _ledger_payload(trades: list[dict] | None = None) -> dict:
    return {
        "schema": stress.PAPER30_LEDGER_SCHEMA,
        "strategy_config_sha256": stress.PAPER30_STRATEGY_CONFIG_SHA256,
        "trades": [] if trades is None else trades,
    }


def test_current_authoritative_envelope_parses() -> None:
    payload = json.loads(stress.PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    metadata = stress._ledger_metadata(payload)
    assert metadata == {
        "ledger_root_type": "object",
        "ledger_schema": "AIOS_FOREX_FROZEN_CANDIDATE_PAPER30_V1",
        "ledger_trade_collection_field": "trades",
        "ledger_trade_collection_type": "list",
        "ledger_current_record_count": 0,
        "supported_ledger_shapes": [
            "OBJECT_ENVELOPE_SCHEMA_AIOS_FOREX_FROZEN_CANDIDATE_PAPER30_V1_WITH_TRADES_LIST"
        ],
    }


def test_empty_authoritative_ledger_returns_zero(tmp_path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps(_ledger_payload()), encoding="utf-8")
    assert stress._current_forward_count(ledger) == 0


def test_one_qualifying_closed_forward_trade_returns_one(tmp_path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps(_ledger_payload([_qualifying_closed_record()])), encoding="utf-8")
    assert stress._current_forward_count(ledger) == 1


def test_nonqualifying_record_is_not_credited(tmp_path) -> None:
    ledger = tmp_path / "ledger.json"
    record = {**_qualifying_closed_record(), "qualifying": False}
    ledger.write_text(json.dumps(_ledger_payload([record])), encoding="utf-8")
    assert stress._current_forward_count(ledger) == 0


def test_open_record_is_not_credited(tmp_path) -> None:
    ledger = tmp_path / "ledger.json"
    record = _qualifying_closed_record()
    del record["exit_timestamp_utc"]
    ledger.write_text(json.dumps(_ledger_payload([record])), encoding="utf-8")
    assert stress._current_forward_count(ledger) == 0


def test_malformed_envelope_fails_closed(tmp_path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({**_ledger_payload(), "trades": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="PAPER30_LEDGER_SCHEMA_UNSUPPORTED"):
        stress._current_forward_count(ledger)


def test_unsupported_root_fails_closed(tmp_path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="PAPER30_LEDGER_SCHEMA_UNSUPPORTED"):
        stress._current_forward_count(ledger)


def test_forward_paper_count_helper_is_read_only(tmp_path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps(_ledger_payload()), encoding="utf-8")
    before = ledger.read_bytes()
    assert stress._current_forward_count(ledger) == 0
    assert ledger.read_bytes() == before


def test_no_network_broker_or_candidate_search_dependency() -> None:
    source = inspect.getsource(stress)
    forbidden_imports = ("import requests", "import urllib", "OandaReadOnlyClient")
    assert not any(value in source for value in forbidden_imports)
    assert "SUPERTREND_ENTRY_GRID" not in source
    assert stress.PAPER30_STRATEGY_CONFIG_SHA256 == (
        "13b96b3e227a2b5873ba5916a4987cf571868626339d1a89e2cd6e0e25bd1435"
    )
