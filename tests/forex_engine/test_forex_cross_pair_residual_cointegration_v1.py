import json
import math

import pytest

from automation.forex_engine.forex_cross_pair_residual_cointegration_v1 import (
    FAMILY,
    base_gate,
    candidate_definitions,
    canonical_bytes,
    crosses_rollover,
    currency_exposure,
    executable_leg_return,
    exposure_allowed,
    fit_ols,
    in_embargo,
    matched_random_baseline,
    pair_leg_weights,
    residual_z,
    should_exit,
    split_and_fold,
    write_outputs,
)
from automation.forex_engine.forex_cross_sectional_currency_strength_v1 import iter_candles


def bar(bid_open="1.0000", ask_open="1.0002", bid_close="1.0010", ask_close="1.0012"):
    return {"bid": {"o": bid_open, "c": bid_close}, "ask": {"o": ask_open, "c": ask_close}}


def metric(expectancy=-0.1):
    return {"trade_count": 200, "long_residual_trades": 100, "short_residual_trades": 100, "expectancy_r": expectancy, "profit_factor": 0.9, "maximum_drawdown_pct": 11.0, "relationship_counts": {"EURUSD_GBPUSD": 100, "EURUSD_USDJPY_SIGNED": 100}, "relationship_breadth": 2, "largest_relationship_share": 0.5, "instrument_counts": {"EUR_USD": 200, "GBP_USD": 100, "USD_JPY": 100}, "instrument_breadth": 3, "regime_counts": {"LOW_TRAINING_VOL": 100, "HIGH_TRAINING_VOL": 100, "UNKNOWN_TRAINING_VOL": 0}, "regime_expectancy": {"LOW_TRAINING_VOL": expectancy, "HIGH_TRAINING_VOL": expectancy, "UNKNOWN_TRAINING_VOL": 0.0}, "largest_regime_share": 0.5, "positive_folds": 0, "fold_expectancy": {str(i): expectancy for i in range(6)}, "largest_trade_share": 0.01, "block_standard_error": 0.02, "uncertainty_lower_bound": expectancy - 0.04, "average_holding_minutes": 20.0, "average_cost_burden_r": 0.1}


def fake_result():
    rows = {}
    for definition in candidate_definitions():
        rows[definition["candidate_id"]] = {"definition": definition, "development": metric(), "validation": metric(), "stress_validation": metric(-0.2), "cost_free_validation": metric(0.01), "simplest_fixed_ratio_validation": metric(-0.05), "matched_random_direction_validation": metric(0.0), "fit_audit": {"refit_count": 2, "fit_failures": 0, "beta_mean": 1.0, "beta_cv": 0.1}, "rollover_rejections": 0, "embargo_rejections": 1, "multiple_testing": {"trial_count": 8}, "gates": {"base": False, "walk_forward": False, "cost_stress": False, "parameter_stability": False, "leakage": True, "concentration": True, "multiple_testing": False}, "pre_holdout_pass": False}
    return {"status": "CLOSED_FAILED_POSTMORTEM_COMPLETE", "candidate_results": rows, "survivors": [], "holdout_status": "NOT_EVALUATED", "safety": {"network": False, "broker": False, "credentials": False, "collector": False, "paper": False, "live": False, "money_movement": False}}


def test_candidate_grid_is_exact_and_bounded():
    definitions = candidate_definitions()
    assert len(definitions) == 8
    assert {item["group"] for item in definitions} == {"EURUSD_GBPUSD", "EURUSD_USDJPY_SIGNED"}
    assert {item["training_window"] for item in definitions} == {1440, 4320}


def test_ols_uses_only_supplied_training_values():
    x = [float(i) for i in range(10)]
    y = [2.0 + 1.5 * value + (0.01 if i % 2 else -0.01) for i, value in enumerate(x)]
    first = fit_ols(y, x)
    future_x = x + [1000.0]
    future_y = y + [-1000.0]
    assert first == fit_ols(future_y[:10], future_x[:10])
    assert first["beta"] == pytest.approx(1.5, abs=0.01)


def test_ols_rejects_malformed_and_constant_history():
    with pytest.raises(ValueError):
        fit_ols([1.0], [1.0])
    with pytest.raises(ValueError):
        fit_ols([1.0, 2.0, 3.0], [1.0, 1.0, 1.0])


def test_residual_sign_and_signed_pair_weights():
    fit = {"intercept": 0.0, "beta": 1.0, "residual_mean": 0.0, "residual_sd": 0.5}
    assert residual_z(2.0, 1.0, fit) == pytest.approx(2.0)
    weights = pair_leg_weights("EURUSD_USDJPY_SIGNED", "SHORT_RESIDUAL", 1.0)
    assert weights["EUR_USD"] < 0 and weights["USD_JPY"] < 0


def test_exposure_aggregation_and_cap():
    weights = pair_leg_weights("EURUSD_GBPUSD", "LONG_RESIDUAL", 1.0)
    exposure = currency_exposure(weights)
    assert math.isclose(sum(exposure.values()), 0.0, abs_tol=1e-12)
    assert exposure_allowed(weights)
    assert not exposure_allowed({"EUR_USD": 10.0})


def test_bid_ask_and_slippage_reduce_leg_return():
    net, gross = executable_leg_return(1.0, bar(), bar("1.0010", "1.0012", "1.0020", "1.0022"), "EUR_USD", 0.10)
    assert net < gross
    short_net, short_gross = executable_leg_return(-1.0, bar(), bar("0.9990", "0.9992", "0.9980", "0.9982"), "EUR_USD", 0.10)
    assert short_net < short_gross


def test_rollover_crossing_is_rejected():
    assert crosses_rollover("2025-03-03T21:10:00")
    assert not crosses_rollover("2025-03-03T12:00:00")


def test_exit_precedence_stop_then_convergence_then_time():
    position = {"age": 60}
    assert should_exit(position, 3.6) == "STOP"
    assert should_exit(position, 0.4) == "CONVERGENCE"
    assert should_exit(position, 1.0) == "TIME"


def test_split_is_chronological_and_holdout_is_not_a_split():
    assert split_and_fold("2024-02-01T00:00:00")[0] == "development"
    assert split_and_fold("2025-05-01T00:00:00") == ("validation", -1)


def test_fold_and_validation_embargo_are_enforced():
    assert in_embargo("2024-01-01T00:01:00")
    assert not in_embargo("2024-01-10T00:00:00")
    assert in_embargo("2025-04-01T00:01:00")
    assert not in_embargo("2025-04-10T00:00:00")


def test_stream_stops_before_parsing_sealed_holdout(tmp_path):
    path = tmp_path / "batch.json"
    path.write_text('{\n"candles": [\n{"complete":true,"time":"2025-12-31T23:59:00.000000000Z","bid":{"o":"1"},"ask":{"o":"1"}},\n{"complete":true,"time":"2026-01-01T00:00:00.000000000Z","forbidden":true},\nNOT_JSON\n]}', encoding="utf-8")
    candles = list(iter_candles(path, "2026-01-01T00:00:00"))
    assert len(candles) == 1 and "forbidden" not in candles[0]


def test_base_gate_requires_every_threshold():
    passing = metric(0.1)
    passing.update({"profit_factor": 1.2, "maximum_drawdown_pct": 5.0, "positive_folds": 4})
    assert base_gate(passing)
    passing["short_residual_trades"] = 49
    assert not base_gate(passing)


def test_random_baseline_is_seeded():
    trades = [{"r": 1.0, "gross_r": 1.1, "group": "EURUSD_GBPUSD", "direction": "LONG_RESIDUAL", "fold": index % 6, "instruments": ["EUR_USD", "GBP_USD"], "regime": "LOW_TRAINING_VOL", "holding_minutes": 10} for index in range(200)]
    assert matched_random_baseline(trades) == matched_random_baseline(trades)


def test_outputs_are_deterministic_sealed_and_fingerprinted(tmp_path):
    code = tmp_path / "code.py"
    code.write_text("pass\n", encoding="utf-8")
    result = fake_result()
    for name in ("a", "b"):
        root = tmp_path / name
        write_outputs(result, root / "runtime", root / "report.md", root / "rejection.json", code)
    files = ["AIOS_FOREX_CROSS_PAIR_RESIDUAL_CONTRACT.json", "AIOS_FOREX_CROSS_PAIR_RESIDUAL_CANDIDATE_REGISTRY.json", "AIOS_FOREX_CROSS_PAIR_RESIDUAL_RESULTS.json", "AIOS_FOREX_CROSS_PAIR_RESIDUAL_CHECKPOINT.json", "AIOS_FOREX_CROSS_PAIR_RESIDUAL_MANIFEST.json", "AIOS_FOREX_CROSS_PAIR_RESIDUAL_RECEIPT.json"]
    assert all((tmp_path / "a/runtime" / item).read_bytes() == (tmp_path / "b/runtime" / item).read_bytes() for item in files)
    rejection = json.loads((tmp_path / "a/rejection.json").read_text())
    assert rejection["family"] == FAMILY
    assert len(rejection["family_fingerprint"]) == 64
    assert len(rejection["candidate_rows"]) == 8
    assert rejection["next_distinct_family"]["family"] == "CURRENCY_FACTOR_REGIME_ALLOCATION"
    receipt = json.loads((tmp_path / "a/runtime/AIOS_FOREX_CROSS_PAIR_RESIDUAL_RECEIPT.json").read_text())
    assert receipt["holdout_status"] == "NOT_EVALUATED"
    assert all(not value for value in receipt["safety"].values())


def test_rejected_mechanism_fingerprint_is_label_independent():
    definition = {"economic_mechanism": "TRAIN_ONLY_DYNAMIC_RELATIONSHIP_RESIDUAL_CONVERGENCE", "groups": ["a", "b"], "scope": "all"}
    renamed = {**definition, "display_label": "renamed"}
    assert canonical_bytes(definition) != canonical_bytes(renamed)
    mechanism_only = {key: definition[key] for key in ("economic_mechanism", "groups", "scope")}
    renamed_mechanism_only = {key: renamed[key] for key in ("economic_mechanism", "groups", "scope")}
    assert canonical_bytes(mechanism_only) == canonical_bytes(renamed_mechanism_only)
