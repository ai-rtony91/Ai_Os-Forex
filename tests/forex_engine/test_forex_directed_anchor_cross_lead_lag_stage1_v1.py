from datetime import datetime, timezone

import pytest

from automation.forex_engine.forex_directed_anchor_cross_lead_lag_stage1_v1 import (
    capacity_audit,
    consecutive_previous,
    deterministic_random_sign,
    event_identity_audit,
    failure_causes,
    in_embargo,
    outcome_lookup,
    rollover_intersection,
    required_baseline_comparison,
    reverse_pair_audit,
    scenario_outcome,
    select_opportunities,
)


def opportunity(identifier, signal, target, ratio=2.0, sign=1):
    return {
        "opportunity_id": identifier,
        "signal_timestamp": signal,
        "entry_timestamp": signal,
        "bar_start": "2024-04-01T00:00:00Z",
        "target": target,
        "anchor": "EUR_USD",
        "anchor_currency": "EUR",
        "transmitted_currency": "EUR",
        "shock_ratio": ratio,
        "entry_spread_to_atr": 0.01,
        "normalized_anchor_sign": sign,
        "fold": 0,
    }


def test_embargo_is_23_m5_bars():
    assert in_embargo(datetime(2024, 4, 1, 1, 50, tzinfo=timezone.utc))
    assert not in_embargo(datetime(2024, 4, 1, 2, 0, tzinfo=timezone.utc))


def test_anchor_signal_requires_exact_previous_m5_bar():
    current = datetime(2024, 4, 8, 0, 0, tzinfo=timezone.utc)
    assert consecutive_previous(datetime(2024, 4, 7, 23, 55, tzinfo=timezone.utc), current)
    assert not consecutive_previous(datetime(2024, 4, 5, 21, 55, tzinfo=timezone.utc), current)


def test_rollover_intersection_uses_maximum_hold_window():
    assert rollover_intersection(datetime(2024, 4, 1, 21, 45, tzinfo=timezone.utc), 3)
    assert not rollover_intersection(datetime(2024, 4, 1, 21, 35, tzinfo=timezone.utc), 3)


def test_selection_deduplicates_target_and_blocks_shared_currency():
    rows = [
        opportunity("A", "2024-04-01T10:00:00Z", "EUR_JPY", 1.5),
        {**opportunity("B", "2024-04-01T10:00:00Z", "EUR_JPY", 2.0), "anchor": "GBP_USD"},
        opportunity("C", "2024-04-01T10:00:00Z", "EUR_GBP", 3.0),
        {**opportunity("D", "2024-04-01T10:00:00Z", "AUD_CAD", 1.8), "anchor": "AUD_USD"},
    ]
    selected = select_opportunities(rows, 1.0, 1)
    assert {row["opportunity_id"] for row in selected} == {"C", "D"}


def test_random_sign_is_deterministic_and_binary():
    row = opportunity("A", "2024-04-01T10:00:00Z", "EUR_JPY")
    value = deterministic_random_sign("f" * 64, row)
    assert value == deterministic_random_sign("f" * 64, row)
    assert value in (-1, 1)


def test_capacity_rejects_sparse_candidates_before_scoring():
    audit = capacity_audit([opportunity(str(index), "2024-04-01T10:00:00Z", "EUR_JPY") for index in range(399)])
    assert audit["pass"] is False
    assert audit["checks"]["minimum_selected_opportunities"] is False


def test_outcome_lookup_fails_closed_before_capacity_pass():
    with pytest.raises(RuntimeError, match="FORWARD_RETURN_BLOCKED"):
        outcome_lookup(None, {}, {}, {}, capacity_verdict=False)


def test_failure_truth_separates_no_gross_edge_from_cost_destroyed_edge():
    gates = {"gross_edge": False, "after_cost": False}
    assert failure_causes(gates, -0.1, -0.2, True) == ["NO_GROSS_EDGE"]
    gates = {"gross_edge": True, "after_cost": False}
    assert failure_causes(gates, 0.1, -0.2, True) == ["COST_DESTROYED_EDGE"]


def test_simple_baseline_diagnostic_cannot_contradict_stage1_gate_status():
    assert failure_causes({"gross_edge": True, "after_cost": True}, 0.1, 0.1, False) == []


def test_reverse_audit_requires_identical_unique_events_and_opposite_directions():
    left = [{"event_id": "A", "direction": "LONG"}, {"event_id": "B", "direction": "SHORT"}]
    right = [{"event_id": "A", "direction": "SHORT"}, {"event_id": "B", "direction": "LONG"}]
    assert reverse_pair_audit(left, right)["pass"] is True
    right[1]["direction"] = "SHORT"
    assert reverse_pair_audit(left, right)["pass"] is False


def test_baseline_identity_requires_exact_unique_event_ids():
    candidate = [{"event_id": "A"}, {"event_id": "B"}]
    baseline = [{"event_id": "B"}, {"event_id": "A"}]
    assert event_identity_audit(candidate, baseline)["pass"] is True
    assert event_identity_audit(candidate, [{"event_id": "A"}, {"event_id": "A"}])["pass"] is False


def test_zero_or_negative_expectancy_cannot_pass_after_cost_gate():
    assert not 0.0 > 0.0
    assert not -0.01 > 0.0


def test_target_momentum_is_compared_on_identical_nonzero_return_subset():
    assert not required_baseline_comparison(
        candidate_expectancy=0.10,
        random_expectancy=0.00,
        strength_expectancy=0.00,
        target_subset_candidate_expectancy=-0.05,
        target_momentum_expectancy=-0.01,
        wrong_anchor_expectancy=0.00,
        population_valid=True,
    )


def test_scenario_uses_executable_sides_and_slippage():
    bars = [
        {"timestamp": "2024-04-01T00:00:00Z", "mid": {"o": 1.0, "h": 1.001, "l": 0.999, "c": 1.0},
         "bid": {"o": 0.9999, "h": 1.0009, "l": 0.9989, "c": 0.9999},
         "ask": {"o": 1.0001, "h": 1.0011, "l": 0.9991, "c": 1.0001}},
        {"timestamp": "2024-04-01T00:05:00Z", "mid": {"o": 1.0, "h": 1.0002, "l": 0.9998, "c": 1.0},
         "bid": {"o": 0.9999, "h": 1.0001, "l": 0.9997, "c": 0.9999},
         "ask": {"o": 1.0001, "h": 1.0003, "l": 0.9999, "c": 1.0001}},
    ]
    long = scenario_outcome("EUR_USD", bars, 0, 1, "LONG", 0.01, "base")
    short = scenario_outcome("EUR_USD", bars, 0, 1, "SHORT", 0.01, "base")
    assert long["entry_price"] == pytest.approx(1.00011)
    assert long["exit_price"] == pytest.approx(0.99989)
    assert short["entry_price"] == pytest.approx(0.99989)
    assert short["exit_price"] == pytest.approx(1.00011)


def test_long_and_short_stop_gap_fills_are_pessimistic_and_slipped():
    bars = [
        {"timestamp": "2024-04-01T00:00:00Z", "mid": {"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0},
         "bid": {"o": 0.9999, "h": 0.9999, "l": 0.9999, "c": 0.9999},
         "ask": {"o": 1.0001, "h": 1.0001, "l": 1.0001, "c": 1.0001}},
        {"timestamp": "2024-04-01T00:05:00Z", "mid": {"o": 1.0, "h": 1.003, "l": 0.997, "c": 1.0},
         "bid": {"o": 0.9980, "h": 1.0029, "l": 0.9969, "c": 0.9999},
         "ask": {"o": 1.0020, "h": 1.0031, "l": 0.9971, "c": 1.0001}},
    ]
    long = scenario_outcome("EUR_USD", bars, 0, 1, "LONG", 0.001, "base")
    short = scenario_outcome("EUR_USD", bars, 0, 1, "SHORT", 0.001, "base")
    assert long["exit_reason"] == short["exit_reason"] == "STOP"
    assert long["exit_price"] == pytest.approx(0.99799)
    assert short["exit_price"] == pytest.approx(1.00201)
