import gzip
import json
from pathlib import Path

import pytest

from automation.forex_engine.forex_cross_sectional_short_horizon_reversal_v1 import (
    FAMILY,
    baseline_gate,
    base_gate,
    block_bootstrap_lower_bound,
    build_artifacts,
    candidate_definitions,
    candidate_fingerprint,
    canonical_bytes,
    choose_reversal_pair,
    conservative_exit,
    crosses_rollover,
    currency_strength,
    family_fingerprint,
    in_embargo,
    iter_pair_rows,
    metrics,
    pair_return_signs,
    pip_size,
    random_direction_metrics,
    rejected_fingerprints,
    reversal_pair,
    split_and_fold,
    true_range,
    write_artifacts,
)


def bar():
    return {
        "instrument": "EUR_USD",
        "timestamp": "2025-01-01T00:00:00Z",
        "complete": True,
        "bid": {"o": 1.0000, "h": 1.0020, "l": 0.9980, "c": 1.0010},
        "ask": {"o": 1.0002, "h": 1.0022, "l": 0.9982, "c": 1.0012},
        "mid": {"o": 1.0001, "h": 1.0021, "l": 0.9981, "c": 1.0011},
    }


def passing_metric():
    return {
        "expectancy_r": 0.1,
        "profit_factor": 1.2,
        "maximum_drawdown_pct": 5.0,
        "trade_count": 250,
        "long_trades": 125,
        "short_trades": 125,
        "instrument_breadth": 3,
        "currency_breadth": 6,
    }


def fake_result():
    rows = {}
    for definition in candidate_definitions():
        value = {
            "trade_count": 0, "long_trades": 0, "short_trades": 0, "expectancy_r": 0.0,
            "profit_factor": 0.0, "maximum_drawdown_pct": 0.0, "instrument_breadth": 0,
            "currency_breadth": 0, "pair_counts": {}, "currency_counts": {}, "regime_counts": {},
            "largest_pair_share": 1.0, "largest_currency_share": 1.0, "largest_regime_share": 1.0,
            "positive_folds": 0, "fold_expectancy": {str(i): 0.0 for i in range(6)},
            "largest_trade_share": 0.0, "block_bootstrap_lower_bound": 0.0,
            "block_bootstrap_standard_error": 0.0, "average_cost_burden_r": 0.0,
        }
        rows[definition["candidate_id"]] = {
            "definition": definition, "candidate_fingerprint": candidate_fingerprint(definition),
            "development": value, "validation": value, "stress_validation": value,
            "cost_free_validation": value, "matched_random_direction_validation": value,
            "trial_accounting": {"cumulative_configuration_count": 64}, "neighbor_ids": [],
            "multiple_testing": {"cumulative_trial_count": 64},
            "gates": {key: False for key in ("base", "walk_forward", "cost_stress", "parameter_stability", "leakage", "concentration", "regime_robustness", "baseline", "multiple_testing", "reproducibility")},
            "rejection_causes": ["NO_GROSS_EDGE"], "pre_holdout_pass": False,
        }
    return {
        "status": "CLOSED_FAILED_POSTMORTEM_COMPLETE", "eligible_pair_count": 58,
        "candidate_count": 12, "cumulative_trial_count": 64, "candidate_results": rows,
        "family_fingerprint": family_fingerprint(), "best_candidate": sorted(rows)[0], "survivors": [],
        "verified_partition_count": 1, "baselines": [str(i) for i in range(6)],
        "no_trade_baseline_expectancy_r": 0.0,
        "duplicate_audit": {"collision": False}, "holdout_status": "NOT_EVALUATED",
        "holdout_partitions_opened": 0,
        "safety": {key: False for key in ("network", "broker", "credentials", "collector", "paper", "practice", "live", "orders", "money_movement")},
    }


def test_exact_bounded_candidate_grid_and_fingerprints():
    definitions = candidate_definitions()
    assert len(definitions) == 12
    assert {item["lookback_bars"] for item in definitions} == {3, 6, 12}
    assert {item["dispersion_bps"] for item in definitions} == {2.0, 4.0}
    assert {item["holding_bars"] for item in definitions} == {3, 6}
    assert len({candidate_fingerprint(item) for item in definitions}) == 12
    assert len(family_fingerprint()) == 64


def test_signed_currency_returns_and_reversal_direction():
    assert pair_return_signs("EUR_USD") == {"EUR": 1, "USD": -1}
    scores = currency_strength({"EUR_USD": 0.02, "GBP_USD": -0.01})
    assert scores["EUR"] > scores["USD"] > scores["GBP"]
    assert reversal_pair("EUR", "USD", {"EUR_USD"}) == ("EUR_USD", "SHORT")
    assert reversal_pair("EUR", "GBP", {"GBP_EUR"}) == ("GBP_EUR", "LONG")


def test_deterministic_pair_tie_breaking():
    selected = choose_reversal_pair({"AUD": 1.0, "EUR": 1.0, "JPY": -1.0}, {"AUD_JPY", "EUR_JPY"})
    assert selected == ("AUD_JPY", "SHORT", 2.0)


def test_jpy_pip_size_and_true_range():
    assert pip_size("USD_JPY") == 0.01
    assert pip_size("EUR_USD") == 0.0001
    assert true_range(bar(), 1.01) == pytest.approx(0.0119)


def test_conservative_stop_precedes_target_and_costs_apply():
    position = {
        "pair": "EUR_USD", "direction": "LONG", "entry": 1.0, "mid_entry": 1.0001,
        "risk_distance": 0.001, "stop": 0.999, "target": 1.0015, "age": 3, "holding_bars": 3,
    }
    reason, net_value, gross_value, _ = conservative_exit(position, bar(), 0.10)
    assert reason == "STOP" and net_value == pytest.approx(-1.0)
    assert isinstance(gross_value, float)


def test_time_exit_uses_bid_ask_and_slippage():
    value = bar()
    value["bid"]["l"] = 1.0
    value["bid"]["h"] = 1.001
    position = {
        "pair": "EUR_USD", "direction": "LONG", "entry": 1.00021, "mid_entry": 1.0001,
        "risk_distance": 0.001, "stop": 0.99, "target": 1.02, "age": 3, "holding_bars": 3,
    }
    result = conservative_exit(position, value, 0.10)
    assert result and result[0] == "TIME" and result[1] < result[2]


def test_rollover_embargo_and_holdout_boundaries():
    assert crosses_rollover("2025-01-01T21:40:00Z", 3)
    assert not crosses_rollover("2025-01-01T12:00:00Z", 3)
    assert in_embargo("2025-04-01T00:00:00Z")
    assert split_and_fold("2024-06-01T00:00:00Z")[0] == "development"
    assert split_and_fold("2025-06-01T00:00:00Z") == ("validation", -1)
    with pytest.raises(ValueError, match="FINAL_HOLDOUT"):
        split_and_fold("2026-01-01T00:00:00Z")


def test_partition_reader_rejects_holdout_row_without_silencing(tmp_path):
    root = tmp_path
    path = root / "partitions" / "EUR_USD" / "2025-12.jsonl.gz"
    path.parent.mkdir(parents=True)
    rows = [bar(), {**bar(), "timestamp": "2026-01-01T00:00:00Z"}]
    with gzip.open(path, "wt", encoding="ascii") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    data = path.read_bytes()
    item = {"instrument": "EUR_USD", "start_utc": "2025-12-01T00:00:00Z", "path": path.relative_to(root).as_posix(), "bytes": len(data), "sha256": __import__("hashlib").sha256(data).hexdigest()}
    verification = {}
    iterator = iter_pair_rows(root, {"artifacts": [item]}, "EUR_USD", verification)
    assert next(iterator)["timestamp"].startswith("2025")
    with pytest.raises(ValueError, match="HOLDOUT"):
        next(iterator)


def test_duplicate_rejection_loads_family_and_candidates(tmp_path):
    path = tmp_path / "rejection.json"
    path.write_text(json.dumps({"family_fingerprint": "f", "candidate_rows": {"a": {"candidate_fingerprint": "c"}, "b": {"rules_hash": "r"}}}), encoding="utf-8")
    families, candidates = rejected_fingerprints([path])
    assert families == {"f"} and candidates == {"c", "r"}


def test_nested_phase1_rejection_ledger_is_loaded(tmp_path):
    path = tmp_path / "phase1.json"
    path.write_text(json.dumps({"rejection_ledger": {"family_rows": [{"family_fingerprint": "family"}], "candidate_rows": [{"exact_rules_fingerprint": "candidate"}]}}), encoding="utf-8")
    families, candidates = rejected_fingerprints([path])
    assert families == {"family"} and candidates == {"candidate"}


def test_base_gate_requires_every_threshold():
    value = passing_metric()
    assert base_gate(value)
    value["short_trades"] = 49
    assert not base_gate(value)


@pytest.mark.parametrize("after_cost_expectancy", [-0.01, 0.0])
def test_baseline_gate_rejects_non_positive_after_cost_expectancy(after_cost_expectancy):
    validation = {"expectancy_r": after_cost_expectancy}
    worse_random_baseline = {"expectancy_r": -1.0}
    positive_cost_free_baseline = {"expectancy_r": 0.1}
    assert not baseline_gate(validation, worse_random_baseline, positive_cost_free_baseline)


def test_metrics_cover_concentration_and_block_uncertainty():
    trades = []
    for index in range(240):
        trades.append({"net_r": 0.2 if index % 3 else -0.1, "gross_r": 0.25, "opposite_net_r": -0.2, "pair": "EUR_USD" if index % 2 else "GBP_JPY", "direction": "LONG" if index % 2 else "SHORT", "regime": "HIGH" if index % 3 else "NORMAL", "fold": index % 6})
    value = metrics(trades)
    assert value["trade_count"] == 240 and value["instrument_breadth"] == 2
    assert value["currency_breadth"] == 4 and value["block_bootstrap_standard_error"] >= 0
    assert block_bootstrap_lower_bound([0.1] * 100)[0] == pytest.approx(0.1)


def test_random_baseline_is_seeded_and_matched_frequency():
    trades = [{"net_r": 1.0, "gross_r": 1.1, "opposite_net_r": -1.2, "pair": "EUR_USD", "direction": "LONG", "regime": "HIGH", "fold": 0} for _ in range(20)]
    first = random_direction_metrics(trades)
    second = random_direction_metrics(trades)
    assert first == second and first["trade_count"] == 20


def test_artifacts_are_complete_deterministic_and_sealed(tmp_path):
    code = tmp_path / "code.py"
    code.write_text("pass\n", encoding="utf-8")
    first = build_artifacts(fake_result(), code)
    second = build_artifacts(fake_result(), code)
    assert first == second and len(first) == 8
    receipt = json.loads(first["AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RECEIPT.json"])
    rejection = json.loads(first["AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_REJECTION_V1.json"])
    assert receipt["acceptance_status"] == "PASS" and receipt["holdout_status"] == "NOT_EVALUATED"
    assert rejection["family"] == FAMILY and len(rejection["candidate_rows"]) == 12
    assert all(not value for value in receipt["safety"].values())


def test_write_artifacts_routes_exact_files(tmp_path):
    code = tmp_path / "code.py"
    code.write_text("pass\n", encoding="utf-8")
    artifacts = build_artifacts(fake_result(), code)
    write_artifacts(artifacts, tmp_path / "runtime", tmp_path / "report.md", tmp_path / "rejection.json")
    assert len(list((tmp_path / "runtime").iterdir())) == 6
    assert (tmp_path / "report.md").is_file() and (tmp_path / "rejection.json").is_file()


def test_canonical_bytes_are_order_independent():
    assert canonical_bytes({"b": 2, "a": 1}) == canonical_bytes({"a": 1, "b": 2})
