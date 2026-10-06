import json
import math
from pathlib import Path

import pytest

from automation.forex_engine.forex_currency_factor_regime_allocation_v1 import (
    FAMILY,
    RollingMedian,
    RollingStats,
    base_gate,
    candidate_definitions,
    canonical_bytes,
    crosses_rollover,
    currency_exposure,
    directions_for_factor,
    duplicate_rejected_mechanism,
    exposure_allowed,
    factor_z,
    in_embargo,
    inverse_volatility_weights,
    mechanism_fingerprint,
    portfolio_leg_returns,
    should_exit,
    signed_usd_factor,
    split_and_fold,
    write_outputs,
)
from automation.forex_engine.forex_cross_sectional_currency_strength_v1 import iter_candles


def bar(bid_open="1.0000", ask_open="1.0002", bid_close="1.0010", ask_close="1.0012"):
    return {"bid": {"o": bid_open, "c": bid_close}, "ask": {"o": ask_open, "c": ask_close}}


def metric(expectancy=-0.1):
    return {
        "trade_count": 250, "long_factor_trades": 125, "short_factor_trades": 125,
        "expectancy_r": expectancy, "profit_factor": 0.9, "maximum_drawdown_pct": 11.0,
        "instrument_counts": {pair: 250 for pair in ("EUR_USD", "GBP_USD", "USD_JPY")},
        "instrument_breadth": 3, "instrument_absolute_contribution": {pair: 1.0 for pair in ("EUR_USD", "GBP_USD", "USD_JPY")},
        "largest_instrument_contribution_share": 1 / 3, "regime_counts": {"ELEVATED": 125, "EXTREME": 125},
        "regime_expectancy": {"ELEVATED": expectancy, "EXTREME": expectancy}, "largest_regime_share": 0.5,
        "positive_folds": 0, "fold_expectancy": {str(i): expectancy for i in range(6)}, "largest_trade_share": 0.01,
        "block_standard_error": 0.01, "uncertainty_lower_bound": expectancy - 0.02, "average_holding_minutes": 30.0,
        "average_turnover": 0.005, "average_cost_burden_r": 0.05,
    }


def fake_result():
    rows = {}
    for definition in candidate_definitions():
        rows[definition["candidate_id"]] = {
            "definition": definition,
            "development": metric(), "validation": metric(), "stress_validation": metric(-0.2),
            "cost_free_validation": metric(0.01), "simplest_equal_weight_validation": metric(-0.05),
            "matched_random_direction_validation": metric(0.0), "trial_accounting": {"family_trial_count": 8, "random_seed": 6016},
            "multiple_testing": {"trial_count": 8, "pbo_proxy": 0.0, "deflated_expectancy_lower_bound": -0.2},
            "gates": {"base": False, "walk_forward": False, "cost_stress": False, "parameter_stability": False,
                      "leakage": True, "concentration": True, "regime_robustness": False, "multiple_testing": False,
                      "reproducibility": True},
            "pre_holdout_pass": False,
        }
    return {
        "status": "CLOSED_FAILED_POSTMORTEM_COMPLETE", "candidate_results": rows, "survivors": [],
        "family_fingerprint": mechanism_fingerprint(), "holdout_status": "NOT_EVALUATED",
        "safety": {name: False for name in ("network", "broker", "credentials", "collector", "paper", "practice", "live", "orders", "money_movement")},
    }


def test_exact_bounded_candidate_grid():
    definitions = candidate_definitions()
    assert len(definitions) == 8
    assert {item["factor_lookback"] for item in definitions} == {60, 240}
    assert {item["regime_window"] for item in definitions} == {1440, 4320}
    assert {item["activation_z"] for item in definitions} == {0.5, 1.0}


def test_currency_factor_signs_and_directions():
    assert signed_usd_factor({"EUR_USD": -0.03, "GBP_USD": -0.06, "USD_JPY": 0.09}) == pytest.approx(0.06)
    assert directions_for_factor(1) == {"EUR_USD": -1, "GBP_USD": -1, "USD_JPY": 1}
    assert directions_for_factor(-1) == {"EUR_USD": 1, "GBP_USD": 1, "USD_JPY": -1}
    with pytest.raises(ValueError):
        signed_usd_factor({"EUR_USD": 0.0})


def test_factor_z_uses_only_supplied_completed_history():
    history = [0.001 if index % 3 else -0.0002 for index in range(60)]
    original = factor_z(history, 60)
    tracker = RollingStats(60)
    for value in history:
        tracker.add(value)
    assert tracker.z_of_sum() == pytest.approx(original)
    assert factor_z(history[:59], 60) == 0.0


def test_rolling_regime_median_is_past_only_and_exact():
    tracker = RollingMedian(4)
    for value in (4.0, 1.0, 3.0, 2.0):
        tracker.add(value)
    assert tracker.ready() and tracker.median() == 2.5
    past = tracker.median()
    assert 10.0 / past == 4.0
    tracker.add(10.0)
    assert tracker.median() == 2.5


def test_risk_normalization_and_currency_exposure_cap():
    weights = inverse_volatility_weights({"EUR_USD": 1.0, "GBP_USD": 2.0, "USD_JPY": 4.0}, directions_for_factor(1))
    assert sum(abs(value) for value in weights.values()) == pytest.approx(0.0025)
    assert math.isclose(sum(currency_exposure(weights).values()), 0.0, abs_tol=1e-12)
    assert exposure_allowed(weights)
    assert not exposure_allowed({"EUR_USD": 0.01})


def test_three_leg_bid_ask_and_slippage_reduce_return():
    entry = {pair: bar() for pair in ("EUR_USD", "GBP_USD", "USD_JPY")}
    exit_bars = {"EUR_USD": bar("1.0010", "1.0012", "1.0020", "1.0022"), "GBP_USD": bar("1.0010", "1.0012", "1.0020", "1.0022"), "USD_JPY": bar("1.0010", "1.0012", "1.0020", "1.0022")}
    position = {"entry_bars": entry, "weights": {pair: 0.0025 / 3 for pair in entry}}
    net, gross = portfolio_leg_returns(position, exit_bars, 0.10)
    assert set(net) == set(gross) == set(entry)
    assert sum(net.values()) < sum(gross.values())


def test_rollover_exit_precedence_and_embargo():
    assert crosses_rollover("2025-03-03T21:10:00")
    assert not crosses_rollover("2025-03-03T12:00:00")
    assert should_exit(15, 1, -0.1) == "FACTOR_SIGN_REVERSAL"
    assert should_exit(60, 1, 0.1) == "TIME"
    assert should_exit(14, 1, -0.1) is None
    assert in_embargo("2024-01-01T00:01:00")


def test_chronological_split_has_no_holdout_classification():
    assert split_and_fold("2024-02-01T00:00:00")[0] == "development"
    assert split_and_fold("2025-05-01T00:00:00") == ("validation", -1)
    with pytest.raises(ValueError):
        split_and_fold("2026-01-01T00:00:00")


def test_stream_stops_before_parsing_sealed_holdout(tmp_path):
    path = tmp_path / "batch.json"
    path.write_text('{\n"candles": [\n{"complete":true,"time":"2025-12-31T23:59:00.000000000Z","bid":{"o":"1"},"ask":{"o":"1"}},\n{"complete":true,"time":"2026-01-01T00:00:00.000000000Z","forbidden":true},\nNOT_JSON\n]}', encoding="utf-8")
    values = list(iter_candles(path, "2026-01-01T00:00:00"))
    assert len(values) == 1 and "forbidden" not in values[0]


def test_base_gate_requires_every_threshold():
    passing = metric(0.1)
    passing.update({"profit_factor": 1.2, "maximum_drawdown_pct": 5.0})
    assert base_gate(passing)
    passing["short_factor_trades"] = 49
    assert not base_gate(passing)


def test_mechanism_fingerprint_rejects_renamed_duplicate():
    assert duplicate_rejected_mechanism([{"family_fingerprint": mechanism_fingerprint(), "display_name": "renamed"}])
    assert duplicate_rejected_mechanism([{"economic_mechanism": "TRAIN_ONLY_SHARED_CURRENCY_FACTOR_VOLATILITY_REGIME_ALLOCATION"}])
    assert not duplicate_rejected_mechanism([{"economic_mechanism": "DIFFERENT"}])


def test_outputs_are_deterministic_complete_and_sealed(tmp_path):
    code = tmp_path / "code.py"
    code.write_text("pass\n", encoding="utf-8")
    result = fake_result()
    for name in ("a", "b"):
        root = tmp_path / name
        write_outputs(result, root / "runtime", root / "report.md", root / "rejection.json", code)
    expected = [
        "AIOS_FOREX_CURRENCY_FACTOR_REGIME_CONTRACT.json", "AIOS_FOREX_CURRENCY_FACTOR_REGIME_CANDIDATE_REGISTRY.json",
        "AIOS_FOREX_CURRENCY_FACTOR_REGIME_RESULTS.json", "AIOS_FOREX_CURRENCY_FACTOR_REGIME_CHECKPOINT.json",
        "AIOS_FOREX_CURRENCY_FACTOR_REGIME_MANIFEST.json", "AIOS_FOREX_CURRENCY_FACTOR_REGIME_RECEIPT.json",
    ]
    assert all((tmp_path / "a/runtime" / name).read_bytes() == (tmp_path / "b/runtime" / name).read_bytes() for name in expected)
    receipt = json.loads((tmp_path / "a/runtime" / expected[-1]).read_text())
    rejection = json.loads((tmp_path / "a/rejection.json").read_text())
    assert receipt["candidate_count"] == 8 and receipt["holdout_status"] == "NOT_EVALUATED"
    assert all(value is False for value in receipt["safety"].values())
    assert rejection["family"] == FAMILY and len(rejection["candidate_rows"]) == 8
    assert rejection["next_distinct_family"]["family"] == "EXTERNAL_DATA_STRATEGY_RESEARCH"


def test_canonical_encoding_and_fingerprint_are_deterministic():
    assert canonical_bytes({"b": 2, "a": 1}) == canonical_bytes({"a": 1, "b": 2})
    assert len(mechanism_fingerprint()) == 64
