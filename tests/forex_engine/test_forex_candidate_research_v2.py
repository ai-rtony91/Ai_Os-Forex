from automation.forex_engine.forex_candidate_research_v2 import (
    ALTERNATIVE_FAMILIES,
    Candidate,
    alternative_signal,
    fold_boundaries,
    gate,
    metrics,
    partitions,
)


def test_partitions_are_chronological_and_non_overlapping():
    split = partitions("2026-01-01T00:00:00Z", "2026-05-01T00:00:00Z")
    assert split["development"]["end_utc"] == split["validation"]["start_utc"]
    assert split["validation"]["end_utc"] == split["holdout"]["start_utc"]


def test_drawdown_is_peak_equity_percentage():
    trades = [
        {"realized_r": 2, "exit_time": "2026-01-01T00:00:00Z", "instrument": "EUR_USD", "session": "ASIA", "exit_reason": "TAKE_PROFIT", "mfe_r": 2},
        {"realized_r": -1, "exit_time": "2026-01-01T00:05:00Z", "instrument": "GBP_USD", "session": "LONDON", "exit_reason": "STOP", "mfe_r": 0},
    ]
    result = metrics(trades)
    assert 0 < result["maximum_drawdown_pct"] < 1
    assert result["net_r"] == 1


def test_promotion_gate_enforces_profitability_and_diversity():
    value = {"trades": 100, "expectancy_r": 0.1, "profit_factor": 1.2, "maximum_drawdown_pct": 5, "pair_count": 8, "largest_pair_share": 0.2, "session_distribution": {"ASIA": 1, "LONDON": 1, "NEW_YORK": 1}}
    assert gate(value) == (True, [])
    value["profit_factor"] = 1.09
    assert "PROFIT_FACTOR_BELOW_1_10" in gate(value)[1]


def test_target_only_candidate_changes_no_signal_parameters():
    candidate = Candidate("target", long_target_r=2.0, short_enabled=False)
    assert candidate.confirmation_closes == 2
    assert candidate.max_extension_atr is None
    assert candidate.structure_lookback == 0


def test_zero_trade_metrics_fail_closed():
    result = metrics([])
    passed, blockers = gate(result)
    assert passed is False
    assert "TRADE_COUNT_BELOW_30" in blockers


def _row(timestamp, close, high=None, low=None):
    high = close if high is None else high
    low = close if low is None else low
    component = {"o": close, "h": high, "l": low, "c": close}
    return {"timestamp": timestamp, "mid": dict(component), "bid": dict(component), "ask": dict(component), "instrument": "EUR_USD", "volume": 1}


def test_mean_reversion_adapter_uses_only_prior_completed_window():
    family = ALTERNATIVE_FAMILIES[0]
    rows = [_row(f"2026-01-01T{i:02d}:00:00Z", 100.0) for i in range(20)]
    rows.append(_row("2026-01-01T20:00:00Z", 99.0))
    assert alternative_signal(rows, 20, family, "BUY") == (98.0, 100.0)
    assert alternative_signal(rows, 20, family, "SELL") is None


def test_breakout_adapter_uses_prior_range_and_conservative_levels():
    family = ALTERNATIVE_FAMILIES[1]
    rows = [_row(f"2026-01-01T{i:02d}:00:00Z", 100.0, 101.0, 99.0) for i in range(20)]
    rows.append(_row("2026-01-01T20:00:00Z", 102.0))
    assert alternative_signal(rows, 20, family, "BUY") == (99.0, 104.0)


def test_development_contract_freezes_four_contiguous_folds():
    folds = fold_boundaries("2026-01-01T00:00:00Z", "2026-01-05T00:00:00Z")
    assert len(folds) == 4
    assert all(folds[index]["end_utc"] == folds[index + 1]["start_utc"] for index in range(3))
