from __future__ import annotations

import json
import random
from datetime import datetime, timezone

import pytest

from automation.forex_engine.forex_cftc_crowding_unwind_price_confirmation_v1 import (
    HOLDOUT_START,
    _market_currency,
    _trade,
    baseline_gate,
    build_cftc_history,
    candidate_definitions,
    chronology_audit,
    family_fingerprint,
    iter_h1_candles,
    metrics,
    point_in_time_zscores,
    probability_of_backtest_overfitting_proxy,
    random_direction_metrics,
    split_and_fold,
)


def test_preregistered_grid_is_exactly_twelve_unique_candidates() -> None:
    rows = candidate_definitions()
    assert len(rows) == 12
    assert len({row["candidate_id"] for row in rows}) == 12
    assert {row["crowding_z_threshold"] for row in rows} == {0.5, 1.0}
    assert {row["price_confirmation_lookback_h1"] for row in rows} == {6, 12, 24}
    assert {row["maximum_holding_h1"] for row in rows} == {6, 12}
    assert len(family_fingerprint()) == 64


@pytest.mark.parametrize("expectancy", [-0.01, 0.0])
def test_negative_or_zero_expectancy_cannot_pass_no_trade_baseline(expectancy: float) -> None:
    validation = {"expectancy_r": expectancy}
    worse_random = {"expectancy_r": -1.0}
    positive_cost_free = {"expectancy_r": 0.1}
    worse_unconfirmed = {"expectancy_r": -1.0}
    assert baseline_gate(validation, worse_random, positive_cost_free, worse_unconfirmed) is False


def test_holdout_boundary_is_sealed() -> None:
    assert split_and_fold(HOLDOUT_START) == ("holdout", -1)
    assert split_and_fold(datetime(2025, 12, 31, 23, tzinfo=timezone.utc))[0] == "validation"


def test_stream_reader_stops_before_holdout(tmp_path) -> None:
    path = tmp_path / "PAIR.H1.json"
    payload = {
        "instrument": "EUR_USD",
        "granularity": "H1",
        "candles": [
            {"complete": True, "time": "2025-12-31T23:00:00Z", "bid": {}, "mid": {}, "ask": {}},
            {"complete": True, "time": "2026-01-01T00:00:00Z", "bid": {}, "mid": {}, "ask": {}},
            {"complete": True, "time": "2026-01-01T01:00:00Z", "bid": {}, "mid": {}, "ask": {}},
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    rows = list(iter_h1_candles(path))
    assert [row["time"] for row in rows] == ["2025-12-31T23:00:00Z"]


def test_cftc_availability_never_uses_future_publication() -> None:
    rows = []
    for index in range(21):
        rows.append(
            {
                "coverage": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
                "available_to_strategy_utc": f"2024-{1 + index // 4:02d}-{1 + (index % 4) * 7:02d}T21:30:00Z",
                "observation_utc": f"2024-{1 + index // 4:02d}-{1 + (index % 4) * 7:02d}T00:00:00Z",
                "leveraged_long": 100 + index,
                "leveraged_short": 100 - index,
                "open_interest": 1000,
                "source_id": "TEST",
            }
        )
    history = build_cftc_history(rows)
    decision = history["EUR"][-2]["available"]
    values, sources = point_in_time_zscores(history, decision)
    assert "EUR" in values
    assert datetime.fromisoformat(sources["EUR"]) <= decision


def test_positive_expectancy_must_also_beat_all_baselines() -> None:
    validation = {"expectancy_r": 0.02}
    assert not baseline_gate(validation, {"expectancy_r": 0.03}, {"expectancy_r": 0.1}, {"expectancy_r": -0.1})
    assert not baseline_gate(validation, {"expectancy_r": -0.1}, {"expectancy_r": 0.1}, {"expectancy_r": 0.03})
    assert baseline_gate(validation, {"expectancy_r": -0.1}, {"expectancy_r": 0.1}, {"expectancy_r": -0.1})


def _bars_for_quote_side_test() -> list[dict[str, object]]:
    rows = []
    for index in range(16):
        rows.append(
            {
                "time": datetime(2024, 1, 8, index, tzinfo=timezone.utc),
                "bid_o": 0.9999,
                "bid_h": 1.0049,
                "bid_l": 0.9949,
                "bid_c": 0.9999,
                "mid_o": 1.0,
                "mid_h": 1.005,
                "mid_l": 0.995,
                "mid_c": 1.0,
                "ask_o": 1.0001,
                "ask_h": 1.0051,
                "ask_l": 0.9951,
                "ask_c": 1.0001,
            }
        )
    return rows


def test_stop_trigger_and_fill_use_executable_quote_side() -> None:
    bars = _bars_for_quote_side_test()
    bars[15]["bid_l"] = 0.984
    trade = _trade("EUR_USD", bars, 15, 1, 1, 0.10)
    assert trade is not None
    assert trade["exit_reason"] == "STOP"
    assert trade["exit_time"] == "2024-01-08T16:00:00+00:00"
    assert trade["net_r"] < trade["gross_r"]


def test_cross_rate_contract_is_not_mapped_as_main_currency_future() -> None:
    assert _market_currency("EURO FX - CHICAGO MERCANTILE EXCHANGE") == "EUR"
    assert _market_currency("EURO FX/BRITISH POUND XRATE - CHICAGO MERCANTILE EXCHANGE") is None
    assert _market_currency("EURO FX/JAPANESE YEN XRATE - CHICAGO MERCANTILE EXCHANGE") is None


def test_random_direction_is_reexecuted_through_trade_engine() -> None:
    bars = _bars_for_quote_side_test()
    original = _trade("EUR_USD", bars, 15, 1, 1, 0.10)
    assert original is not None
    original.update({"split": "development", "fold": 0, "decision_time": original["entry_time"], "information_available": {}})
    selected_side = random.Random(7).choice((-1, 1))
    expected = _trade("EUR_USD", bars, 15, selected_side, 1, 0.10)
    assert expected is not None
    result = random_direction_metrics([original], {"EUR_USD": bars}, 7)
    assert result["expectancy_r"] == pytest.approx(expected["net_r"])


def test_simultaneous_portfolio_drawdown_is_order_invariant() -> None:
    common = {"pair": "EUR_USD", "entry_time": "2024-01-08T07:00:00+00:00", "exit_time": "2024-01-08T08:00:00+00:00", "decision_time": "2024-01-08T07:00:00+00:00", "fold": 0, "side": 1}
    loss = {**common, "net_r": -4.0}
    gain = {**common, "pair": "GBP_JPY", "net_r": 4.0}
    assert metrics([loss, gain])["maximum_drawdown_pct"] == 0.0
    assert metrics([gain, loss])["maximum_drawdown_pct"] == 0.0


def test_fold_accounting_reports_all_six_preregistered_folds() -> None:
    row = {"pair": "EUR_USD", "entry_time": "2024-05-06T07:00:00+00:00", "exit_time": "2024-05-06T08:00:00+00:00", "decision_time": "2024-05-06T07:00:00+00:00", "fold": 1, "side": 1, "net_r": 0.1}
    result = metrics([row])
    assert result["fold_count"] == 6
    assert result["nonempty_fold_count"] == 1
    assert result["positive_folds"] == 1


def test_pbo_fails_closed_when_no_development_candidate_is_positive() -> None:
    rows = {"A": {"development": {"expectancy_r": 0.0}, "validation": {"expectancy_r": 1.0}}}
    assert probability_of_backtest_overfitting_proxy(rows) == 1.0


def test_chronology_audit_rejects_future_information() -> None:
    row = {"entry_time": "2024-01-08T07:00:00+00:00", "exit_time": "2024-01-08T08:00:00+00:00", "decision_time": "2024-01-08T07:00:00+00:00", "information_available": {"EUR": "2024-01-08T08:00:00+00:00", "USD": "USD_NEUTRAL_NUMERAIRE"}}
    result = chronology_audit([row])
    assert result["status"] == "FAIL"
    assert result["future_information_count"] == 1
