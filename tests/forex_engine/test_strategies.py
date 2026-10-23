import pytest


def test_supertrend_research_v1_clusters_ties_empty_and_bound():
    from automation.forex_engine.strategies import cluster_scores_v1
    tied = cluster_scores_v1([0]*7)
    assert tied["converged"] and tied["labels"] == [0]*7 and tied["empty_clusters"] == [1, 2]
    separate = cluster_scores_v1([-3, -2, -1, 0, 1, 2, 3])
    assert separate == cluster_scores_v1([-3, -2, -1, 0, 1, 2, 3])
    assert separate["iterations"] <= 32 and separate["centers"] == sorted(separate["centers"])
    with pytest.raises(ValueError):
        cluster_scores_v1([float("nan")])


@pytest.mark.parametrize("policy", ["CLASSIC", "ADAPTIVE_CLUSTER", "CONSENSUS", "STABILITY_SELECTED"])
def test_supertrend_research_v1_policy_future_mutation_and_lagged_scores(policy):
    from tests.forex_engine.test_indicators import research_bars_fixture_v1
    from automation.forex_engine.indicators import supertrend_research_v1
    from automation.forex_engine.strategies import supertrend_policy_v1
    from automation.forex_engine.forex_high_throughput_edge_factory_v1 import supertrend_research_catalog_v1
    catalog = supertrend_research_catalog_v1()
    start = catalog.family_ranges()["SUPERTREND_"+policy+"_RESEARCH_V1"][0][0]
    impl = catalog.spec_at(start)["implementation"]
    bars = research_bars_fixture_v1()
    path = supertrend_policy_v1(bars, impl, supertrend_research_v1)
    changed = [{**r} for r in bars]
    for r in changed[80:]:
        r.update(o=2, h=2.1, l=1.9, c=2)
    assert supertrend_policy_v1(changed, impl, supertrend_research_v1)[:80] == path[:80]
    assert all(row["score_as_of_index"] == i-1 and not row["score_is_after_cost_pnl"] for i,row in enumerate(path))
    changed = [{**r} for r in bars]
    changed[79].update(o=1.1, c=1.2, h=1.21, l=1.09)
    updated = supertrend_policy_v1(changed, impl, supertrend_research_v1)
    assert updated[79]["lagged_scores"] == path[79]["lagged_scores"]
    if policy in {"ADAPTIVE_CLUSTER", "STABILITY_SELECTED"}:
        assert updated[79]["selected_multiplier"] == path[79]["selected_multiplier"]


def test_supertrend_research_v1_consensus_neutral_and_closed_htf():
    from tests.forex_engine.test_indicators import research_bars_fixture_v1
    from automation.forex_engine.strategies import supertrend_policy_v1, closed_higher_timeframe_v1
    bars = research_bars_fixture_v1(12)
    def disagree(rows, period, factor):
        return [{"timestamp": r["timestamp"], "available_at": r["timestamp"], "atr": 1,
                 "band": r["c"]-1 if factor == 1 else r["c"]+1, "direction": 1 if factor == 1 else -1} for r in rows]
    impl = {"policy": "CONSENSUS", "atr_period": 2, "factors": [1,2], "normalization": "DIRECTION",
            "consensus_threshold": 1, "neutral_rule": "CASH", "update_cadence": 1}
    assert all(r["direction"] == 0 for r in supertrend_policy_v1(bars, impl, disagree))
    htf = [{"available_at": "2026-01-02T13:00:00Z", "value": 1}, {"available_at": "2026-01-02T14:00:00Z", "value": 999}]
    assert closed_higher_timeframe_v1(htf, "2026-01-02T13:30:00Z")["value"] == 1


def test_supertrend_research_v1_plateau_is_after_cost_correlated_development():
    from automation.forex_engine.strategies import after_cost_plateau_v1
    broad = [{"after_cost": True, "expectancy_r": x} for x in (.10,.11,.09)]
    assert after_cost_plateau_v1(broad,1,1,1,.1)["broad_positive_development_plateau"]
    narrow = [{"after_cost": True, "expectancy_r": x} for x in (-1,2,-1)]
    assert not after_cost_plateau_v1(narrow,1,1,.75,.1)["broad_positive_development_plateau"]
    with pytest.raises(ValueError, match="AFTER_COST_EVIDENCE"):
        after_cost_plateau_v1([{"after_cost": False, "expectancy_r": .5}],0,1,.5,.1)


def test_supertrend_research_v1_technical_and_eight_matched_masks():
    from tests.forex_engine.test_indicators import research_bars_fixture_v1
    from automation.forex_engine.strategies import technical_context_v1, matched_filter_v1, MATCHED_CHANNELS_V1
    rows = research_bars_fixture_v1()
    context = technical_context_v1(rows,20)
    assert len(context["directions"]) == 4 and not context["orders_allowed"]
    missing = {"state": "MISSING", "direction": None}
    assert matched_filter_v1(1,context,missing,missing,())["accept"]
    assert matched_filter_v1(1,context,missing,missing,("SENTIMENT",))["state"] == "DATA_BLOCKED"
    assert len(MATCHED_CHANNELS_V1) == 8
    assert not matched_filter_v1(1,context,{"state":"KNOWN","direction":-1},missing,("SENTIMENT",))["accept"]


@pytest.mark.parametrize("concept", ["MOMENTUM_CONTINUATION","SUPPORT_RESISTANCE_BOUNCE","REFERENCE_REVERSAL","BREAKOUT"])
def test_supertrend_research_v1_technical_known_long_short(concept):
    from automation.forex_engine.strategies import technical_context_v1
    rows = [{"o":1.,"h":1.01,"l":.99,"c":1.} for _ in range(11)]
    if concept == "SUPPORT_RESISTANCE_BOUNCE":
        rows[10].update(o=1.,h=1.01,l=.98,c=1.005)
    elif concept == "REFERENCE_REVERSAL":
        rows[9].update(o=1.,h=1.01,l=.97,c=.98)
        rows[10].update(o=.98,h=1.01,l=.97,c=1.005)
    else:
        rows[10].update(o=1.,h=1.04,l=.99,c=1.03)
    assert technical_context_v1(rows,10)["directions"][concept] == 1
    inverse = [{"o":3-r["o"],"h":3-r["l"],"l":3-r["h"],"c":3-r["c"]} for r in rows]
    assert technical_context_v1(inverse,10)["directions"][concept] == -1

from automation.forex_engine.daily_edge_report import deterministic_supertrend_sample
from automation.forex_engine.models import Direction
from automation.forex_engine.indicators import DOWN, UP
from automation.forex_engine.strategies import (
    SupertrendPullbackConfig,
    classify_r_multiple,
    evaluate_supertrend_pullback,
    planned_reward_risk,
    realized_r_multiple,
)


def test_supertrend_pullback_valid_long():
    result = evaluate_supertrend_pullback(deterministic_supertrend_sample(count=8))
    assert result["accepted"] is True
    assert result["signal"].direction == Direction.BUY


def test_supertrend_pullback_valid_short():
    candles = deterministic_supertrend_sample(count=8)
    for candle in candles:
        candle.open = round(2.2 - candle.open, 5)
        candle.close = round(2.2 - candle.close, 5)
        high = round(max(candle.open, candle.close) + 0.00035, 5)
        low = round(min(candle.open, candle.close) - 0.00035, 5)
        candle.high = high
        candle.low = low
    result = evaluate_supertrend_pullback(candles)
    assert result["accepted"] is True
    assert result["signal"].direction == Direction.SELL


def test_supertrend_pullback_blocks_chop():
    candles = deterministic_supertrend_sample(count=10)
    for index, candle in enumerate(candles):
        candle.open = 1.0800
        candle.close = 1.0808 if index % 2 else 1.0792
        candle.high = max(candle.open, candle.close) + 0.0005
        candle.low = min(candle.open, candle.close) - 0.0005
    result = evaluate_supertrend_pullback(candles, SupertrendPullbackConfig(chop_lookback=6))
    assert result["accepted"] is False
    assert any("chop" in reason for reason in result["no_trade_reasons"])


def test_supertrend_pullback_blocks_weak_candle():
    candles = deterministic_supertrend_sample(count=8)
    candles[-1].open = candles[-1].close - 0.00005
    candles[-1].high = candles[-1].close + 0.001
    candles[-1].low = candles[-1].close - 0.001
    result = evaluate_supertrend_pullback(candles)
    assert result["accepted"] is False
    assert any("weak_candle" in reason for reason in result["no_trade_reasons"])


def test_supertrend_pullback_blocks_extended_entry():
    candles = deterministic_supertrend_sample(count=8)
    candles[-1].open = candles[-2].close
    candles[-1].close = candles[-2].close + 0.006
    candles[-1].high = candles[-1].close + 0.0005
    candles[-1].low = candles[-1].open - 0.0003
    result = evaluate_supertrend_pullback(candles)
    assert result["accepted"] is False
    assert any("extended" in reason for reason in result["no_trade_reasons"])


def test_supertrend_pullback_blocks_bad_reward_risk():
    candles = deterministic_supertrend_sample(count=8)
    result = evaluate_supertrend_pullback(candles, SupertrendPullbackConfig(min_reward_risk=10.0))
    assert result["accepted"] is False
    assert any("reward_risk" in reason for reason in result["no_trade_reasons"])


def test_supertrend_pullback_minimum_boundary_accepts_when_other_gates_pass(monkeypatch):
    candles = deterministic_supertrend_sample(count=8)
    config = SupertrendPullbackConfig(min_reward_risk=1.5, target_reward_risk=2.0)
    monkeypatch.setattr(
        "automation.forex_engine.strategies.supertrend",
        lambda _candles, *_args, **_kwargs: [
            *([{"direction": DOWN, "lower_band": 1.0990, "upper_band": 1.1010}] * (len(_candles) - 1)),
            {"direction": UP, "lower_band": 1.0990, "upper_band": 1.1010},
        ],
    )
    monkeypatch.setattr(
        "automation.forex_engine.strategies.atr",
        lambda _candles, *_args, **_kwargs: [0.0006] * len(_candles),
    )
    for candle in candles:
        candle.open = 1.0995
        candle.close = 1.10045
        candle.high = 1.1010
        candle.low = 1.0990
    result = evaluate_supertrend_pullback(candles, config)
    assert result["accepted"] is True
    assert result["candidate"].metadata["planned_reward_risk"] == 2.0
    assert result["candidate"].metadata["target_reward_risk"] == 2.0


def test_rr_helpers_classify_and_compute_expected_values():
    assert planned_reward_risk(1.1000, 1.0990, 1.1020) == pytest.approx(2.0)
    assert realized_r_multiple(2.0, 1.0) == 2.0
    assert classify_r_multiple(2.0, 1.0) == "POSITIVE_R"
    assert classify_r_multiple(-1.0, 1.0) == "NEGATIVE_R"
    assert classify_r_multiple(0.0, 1.0) == "FLAT_R"
    assert classify_r_multiple(1.0, 0.0) == "INVALID_R"
