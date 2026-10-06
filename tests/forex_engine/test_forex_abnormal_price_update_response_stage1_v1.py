import gzip
import json
import sqlite3

import pytest

from automation.forex_engine.forex_abnormal_price_update_response_stage1_v1 import (
    EVENT_COLUMNS,
    NO_TRADE_EXPECTANCY_R,
    audit_matched_controls,
    audit_journal_bytes,
    baseline_comparison_pass,
    break_even_cost,
    classify_failures,
    create_event_table,
    deterministic_random_direction,
    event_dict,
    fold_index,
    gate_reasons,
    in_embargo,
    journal_bytes,
    matched_nonshock_rows,
    metrics,
    pip_size,
    robust_center_scale,
    scenario_outcome,
    terminal_status,
)
from datetime import datetime, timezone


def sample_row(value, direction="LONG", fold=0):
    return {
        "strategy_id": "TEST",
        "candidate_id": "C",
        "candidate_fingerprint": "F",
        "event_id": str(value),
        "instrument": "EUR_USD",
        "direction": direction,
        "signal_timestamp": "2024-04-02T00:00:00Z",
        "entry_timestamp": "2024-04-02T00:00:00Z",
        "exit_timestamp": "2024-04-02T00:05:00Z",
        "entry_price": 1.0,
        "exit_price": 1.0,
        "stop_loss": 0.99,
        "take_profit": None,
        "signal_close_spread_pips": 1.0,
        "entry_open_spread_pips": 1.0,
        "exit_bar_close_spread_pips": 1.0,
        "modeled_slippage_pips_per_side": 0.1,
        "net_result_r": value,
        "gross_result_r": value + 0.1,
        "stress_result_r": value - 0.1,
        "fold": fold,
        "result_r": value,
        "entry_reason": "TEST",
        "exit_reason": "TIME",
        "session": "LONDON",
        "volatility_regime": "NORMAL",
        "trend_or_range_regime": "RANGE",
        "economic_event_proximity": "NOT_APPLICABLE",
        "filter_results": {},
    }


def test_pip_size_handles_jpy_and_non_jpy():
    assert pip_size("USD_JPY") == 0.01
    assert pip_size("EUR_USD") == 0.0001


def test_robust_history_is_past_only_primitive():
    center, scale = robust_center_scale([0, 1, 2, 3, 4, 5, 6, 100])
    assert center == 3.5
    assert scale == 2.9652


def test_fold_and_embargo_are_chronological():
    assert fold_index(datetime(2024, 4, 1, 0, 30, tzinfo=timezone.utc)) == 0
    assert in_embargo(datetime(2024, 4, 1, 0, 5, tzinfo=timezone.utc))
    assert not in_embargo(datetime(2024, 4, 1, 0, 30, tzinfo=timezone.utc))


def test_random_direction_is_deterministic_and_binary():
    first = deterministic_random_direction("C", "E")
    assert first == deterministic_random_direction("C", "E")
    assert first in {"LONG", "SHORT"}


def test_journal_gzip_is_byte_deterministic():
    rows = [sample_row(0.1)]
    first = journal_bytes(rows)
    second = journal_bytes(rows)
    assert first == second
    lines = gzip.decompress(first).decode("utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["net_result_r"] == 0.1


def test_zero_expectancy_does_not_pass_no_trade_baseline():
    result = metrics([sample_row(0.0)], "net_result_r", 1)
    assert result["expectancy_r"] == NO_TRADE_EXPECTANCY_R
    assert not result["expectancy_r"] > NO_TRADE_EXPECTANCY_R


def test_negative_expectancy_does_not_pass_no_trade_baseline():
    result = metrics([sample_row(-0.01)], "net_result_r", 1)
    assert result["expectancy_r"] < NO_TRADE_EXPECTANCY_R
    assert not result["expectancy_r"] > NO_TRADE_EXPECTANCY_R


def test_positive_expectancy_is_required_but_not_sufficient():
    result = metrics([sample_row(0.01)], "net_result_r", 1)
    assert result["expectancy_r"] > NO_TRADE_EXPECTANCY_R
    gates = {"gross_edge": True, "after_cost": True, "profit_factor": False}
    assert "AFTER_COST_PROFIT_FACTOR_FAILURE" in gate_reasons(gates)


def test_metrics_preserve_losses_and_direction_counts():
    rows = [sample_row(1.0, "LONG", 0), sample_row(-2.0, "SHORT", 1)]
    result = metrics(rows, "net_result_r", 7)
    assert result["trade_count"] == 2
    assert result["long_trades"] == 1
    assert result["short_trades"] == 1
    assert result["expectancy_r"] == -0.5
    assert result["profit_factor"] == 0.5


def test_failed_run_status_confirms_postmortem_complete():
    assert terminal_status([]) == "CLOSED_FAILED_POSTMORTEM_COMPLETE"
    assert terminal_status(["candidate"]) == "STAGE1_SURVIVOR"


def test_journal_audit_requires_valid_jsonl_and_preserves_losses():
    payload = journal_bytes([sample_row(-0.1), sample_row(0.2)])
    audit = audit_journal_bytes(payload, 2)
    assert audit["pass"] is True
    assert audit["losing_rows"] == 1


def test_failure_classification_separates_primary_and_secondary():
    primary, secondary = classify_failures(["BASELINE_FAILURE", "COST_DESTROYED_EDGE"])
    assert primary == "COST_DESTROYED_EDGE"
    assert secondary == ["BASELINE_FAILURE"]


def test_cost_destroyed_edge_is_only_assigned_when_gross_edge_was_positive():
    gates = {"gross_edge": False, "after_cost": False}
    assert gate_reasons(gates, gross_expectancy_r=-0.1, after_cost_expectancy_r=-0.2) == ["NO_GROSS_EDGE"]
    gates = {"gross_edge": True, "after_cost": False}
    assert gate_reasons(gates, gross_expectancy_r=0.1, after_cost_expectancy_r=-0.2) == ["COST_DESTROYED_EDGE"]


def test_break_even_cost_uses_total_round_trip_units():
    result = break_even_cost(0.30, 0.10, -0.10, 0.8)
    assert result["unit_contract"] == "TOTAL_ROUND_TRIP_COST_NOT_PER_SIDE"
    assert result["estimated_r_per_additional_round_trip_pip"] == 0.25
    assert result["additional_round_trip_slippage_pips_to_zero"] == 0.4
    assert result["break_even_total_transaction_cost_r_per_trade"] == 0.30


def test_matched_baseline_uses_identical_subset_not_full_candidate_average():
    assert not baseline_comparison_pass(
        candidate_expectancy_r=0.10,
        random_expectancy_r=-0.10,
        price_expectancy_r=-0.10,
        matched_shock_expectancy_r=-0.20,
        matched_control_expectancy_r=-0.10,
        matched_control_valid=True,
    )


def matched_row(event_id="CONTROL", shock_id="SHOCK"):
    row = sample_row(0.1)
    row.update({
        "event_id": event_id,
        "signal_timestamp": "2024-04-01T00:00:00Z",
        "matched_to_shock_event_id": shock_id,
        "matched_to_shock_signal_timestamp": "2024-04-08T00:00:00Z",
        "matched_pair": "EUR_USD",
        "shock_pair": "EUR_USD",
        "matched_minute_of_week": 0,
        "shock_minute_of_week": 0,
        "matched_activity_z": 0.1,
    })
    return row


def test_zero_matches_cannot_vacuously_pass_matched_control_audit():
    audit = audit_matched_controls(10, [])
    assert audit["pass"] is False
    assert audit["nonzero_match_pass"] is False
    assert audit["coverage_pass"] is False


def test_matched_control_audit_rejects_reuse_and_field_mismatch():
    first = matched_row()
    second = matched_row(shock_id="SHOCK2")
    audit = audit_matched_controls(2, [first, second])
    assert audit["no_control_reuse_pass"] is False
    assert audit["control_reuse_count"] == 1
    bad = matched_row("CONTROL2", "SHOCK2")
    bad["shock_pair"] = "GBP_USD"
    bad["matched_activity_z"] = 0.5
    audit = audit_matched_controls(2, [first, bad])
    assert audit["same_pair_pass"] is False
    assert audit["activity_z_abs_lt_0_5_pass"] is False
    assert audit["pass"] is False


def _outcomes():
    scenario = [1.0, "2024-04-08T00:10:00Z", 1.0, 0.9, "TIME", 0.1, 1.0, 1.0, 1.0]
    return json.dumps([scenario, scenario, scenario], separators=(",", ":"))


def _event_tuple(event_id, signal_timestamp, matched_nonshock, activity_z):
    values = {
        "event_id": event_id,
        "pair": "EUR_USD",
        "signal_timestamp": signal_timestamp,
        "minute_of_week": 0,
        "entry_timestamp": signal_timestamp,
        "fold": 0,
        "session": "LONDON",
        "volatility_regime": "NORMAL",
        "trend_range_regime": "RANGE",
        "price_update_count": 10,
        "history_center": 1.0,
        "history_scale": 1.0,
        "activity_z": activity_z,
        "displacement_atr": 1.0,
        "body_direction": 1,
        "spread_pips": 1.0,
        "matched_nonshock": matched_nonshock,
        "long_3": _outcomes(),
        "short_3": _outcomes(),
        "long_6": _outcomes(),
        "short_6": _outcomes(),
    }
    return tuple(values[name] for name in EVENT_COLUMNS)


def test_matching_never_reuses_one_control_for_two_shocks():
    connection = sqlite3.connect(":memory:")
    create_event_table(connection)
    connection.execute(
        "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        _event_tuple("CONTROL", "2024-04-01T00:00:00Z", 1, 0.1),
    )
    shocks = []
    for event_id, timestamp in (("S1", "2024-04-08T00:00:00Z"), ("S2", "2024-04-15T00:00:00Z")):
        values = _event_tuple(event_id, timestamp, 0, 2.0)
        shocks.append((event_dict(values), "LONG"))
    controls, paired_shocks = matched_nonshock_rows(
        connection, shocks, candidate_id="C", fingerprint="F", arm="CONTINUATION", hold=3,
    )
    assert len(controls) == len(paired_shocks) == 1
    assert controls[0]["event_id"] == "CONTROL"
    connection.close()


def test_long_and_short_use_executable_sides_and_slippage():
    bars = [
        {"timestamp": "2024-04-01T00:00:00Z", "mid": {"o": "1.0000", "h": "1.0010", "l": "0.9990", "c": "1.0000"},
         "bid": {"o": "0.9999", "h": "1.0009", "l": "0.9989", "c": "0.9999"},
         "ask": {"o": "1.0001", "h": "1.0011", "l": "0.9991", "c": "1.0001"}},
        {"timestamp": "2024-04-01T00:05:00Z", "mid": {"o": "1.0000", "h": "1.0002", "l": "0.9998", "c": "1.0000"},
         "bid": {"o": "0.9999", "h": "1.0001", "l": "0.9997", "c": "0.9999"},
         "ask": {"o": "1.0001", "h": "1.0003", "l": "0.9999", "c": "1.0001"}},
    ]
    long = scenario_outcome(pair="EUR_USD", bars=bars, signal_index=0, holding_bars=1, direction="LONG", atr=0.01, scenario="base")
    short = scenario_outcome(pair="EUR_USD", bars=bars, signal_index=0, holding_bars=1, direction="SHORT", atr=0.01, scenario="base")
    assert long[0] == pytest.approx(1.00011)
    assert long[2] == pytest.approx(0.99989)
    assert long[3] == pytest.approx(0.99011)
    assert short[0] == pytest.approx(0.99989)
    assert short[2] == pytest.approx(1.00011)
    assert short[3] == pytest.approx(1.00989)
