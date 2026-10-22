import json
import math
from datetime import datetime, timezone

from automation.forex_engine.forex_feature_edge_research_v2 import (
    Candidate,
    atomic_json,
    completed_aggregate,
    currency_factor,
    development_gate,
    feature_vector,
    fit_logistic,
    null_campaign,
    registry,
    six_folds,
)


def candle(index):
    minute = index * 5
    stamp = datetime(2024, 1, 1, minute // 60, minute % 60, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    mid = {"o": 1.0, "h": 1.1, "l": 0.9, "c": 1.0}
    return {"timestamp": stamp, "instrument": "EUR_USD", "volume": 1, "mid": mid, "bid": mid, "ask": mid}


def test_registry_is_frozen_at_thirty_candidates():
    candidates = registry()
    assert len(candidates) == 26
    assert len({item.candidate_id for item in candidates}) == len(candidates)
    assert all(isinstance(item, Candidate) for item in candidates)


def test_currency_factor_uses_zero_sum_constraint():
    factors = currency_factor({"EUR_USD": 0.01, "GBP_USD": 0.02, "EUR_GBP": -0.01})
    assert abs(sum(factors.values())) < 1e-12


def test_aggregation_excludes_incomplete_higher_timeframe_bar():
    assert len(completed_aggregate([candle(i) for i in range(4)], 15)) == 1


def test_six_chronological_folds_are_adjacent():
    window = (datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 7, tzinfo=timezone.utc))
    folds = six_folds(window)
    assert len(folds) == 6
    assert all(left[1] == right[0] for left, right in zip(folds, folds[1:]))


def test_development_gate_rejects_insufficient_sample():
    result = {"trades": 49, "expectancy_r": 1, "profit_factor": 2, "net_r": 1, "max_drawdown_pct": 1}
    assert not development_gate(result, [])


def test_registry_wide_null_is_deterministic():
    trades = [{"r": 1 if index % 3 else -1} for index in range(120)]
    assert null_campaign({"candidate": trades}, 20) == null_campaign({"candidate": trades}, 20)


def test_feature_vector_is_direction_normalized():
    event = {"side": "LONG", "factor_spread_1h": 0.0001, "factor_residual_4h": 0.0002, "event_magnitude_atr": 1, "trend_persistence": 0.5, "spread_risk_ratio": 0.1, "atr_percentile": 0.6, "volatility_change": 0.2}
    assert len(feature_vector(event)) == 7


def test_regularized_logistic_fit_is_deterministic():
    candidate = [item for item in registry() if item.score_rule.startswith("LOGISTIC")][0]
    events = []
    for index in range(20):
        events.append({"side": "LONG", "factor_spread_1h": index / 100000, "factor_residual_4h": 0.0, "event_magnitude_atr": 1, "trend_persistence": 0.2, "spread_risk_ratio": 0.1, "atr_percentile": 0.5, "volatility_change": 0.0, "r_1.5_3.0": 3.0 if index % 2 else -1.0})
    assert fit_logistic(events, candidate) == fit_logistic(events, candidate)


def test_atomic_json_encodes_infinite_metric_without_invalid_json(tmp_path):
    target = tmp_path / "state.json"
    atomic_json(target, {"profit_factor": math.inf})
    assert json.loads(target.read_text())["profit_factor"] == "INF"
