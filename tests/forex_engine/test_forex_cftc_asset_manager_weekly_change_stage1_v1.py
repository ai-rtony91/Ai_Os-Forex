import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from automation.forex_engine import forex_cftc_asset_manager_weekly_change_stage1_v1 as module
from automation.forex_engine.forex_cftc_asset_manager_weekly_change_stage0_v1 import candidate_definitions


def candle(time: datetime, bid: float = 1.0, ask: float = 1.0002) -> dict:
    mid = (bid + ask) / 2
    return {
        "time": time,
        "bid": {"o": bid, "h": bid + 0.001, "l": bid - 0.001, "c": bid + 0.0001},
        "ask": {"o": ask, "h": ask + 0.001, "l": ask - 0.001, "c": ask + 0.0001},
        "mid": {"o": mid, "h": mid + 0.001, "l": mid - 0.001, "c": mid + 0.0001},
    }


def test_baseline_gate_rejects_negative_and_zero_expectancy() -> None:
    assert module.baseline_comparison_pass(-0.01, {"worse": -0.20}) is False
    assert module.baseline_comparison_pass(0.0, {"worse": -0.20}) is False


def test_baseline_gate_requires_beating_every_comparator() -> None:
    assert module.baseline_comparison_pass(0.01, {"weaker": 0.0}) is True
    assert module.baseline_comparison_pass(0.01, {"stronger": 0.02}) is False


def test_predictive_correlation_and_search_adjustment_are_deterministic() -> None:
    assert module.pearson_correlation([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(1.0)
    assert module.SEARCH_ADJUSTED_STANDARD_ERROR_MULTIPLE == 3.8


def test_exact_frozen_ten_candidate_grid() -> None:
    candidates = candidate_definitions()
    assert len(candidates) == 10
    assert len({item["candidate_fingerprint"] for item in candidates}) == 10
    assert {item["maximum_holding_h1"] for item in candidates} == {6, 12}


@pytest.mark.parametrize(
    ("variant", "zsign", "expected"),
    [
        ("ORIGINAL_LONG_CONTINUATION", 1, 1),
        ("ORIGINAL_LONG_CONTINUATION", -1, None),
        ("EXACT_REVERSED_SHORT", 1, -1),
        ("ORIGINAL_SHORT_CONTINUATION", -1, -1),
        ("EXACT_REVERSED_LONG", -1, 1),
        ("SYMMETRIC_BIDIRECTIONAL", 1, 1),
        ("SYMMETRIC_BIDIRECTIONAL", -1, -1),
    ],
)
def test_direction_arms_are_exact_and_bounded(variant: str, zsign: int, expected: int | None) -> None:
    event = {"positive_pair_sign": 1, "zsign": zsign}
    assert module.candidate_event_order_sign(variant, event) == expected


def test_pair_factor_direction_is_base_minus_quote_for_direct_and_cross_pairs() -> None:
    event = {"positive_pair_sign": 1, "zsign": 1}
    assert module.candidate_event_order_sign("ORIGINAL_LONG_CONTINUATION", event) == 1
    assert module.candidate_event_order_sign("EXACT_REVERSED_SHORT", event) == -1


def test_timestamp_first_reader_skips_old_prices_and_never_parses_cutoff_prices(tmp_path: Path) -> None:
    source = tmp_path / "H1.json"
    source.write_text(
        "{\n  \"candles\": [\n"
        "    {\n      \"time\": \"2024-06-01T00:00:00Z\",\n      \"bid\": THIS_OLD_PRICE_MUST_NOT_BE_PARSED\n    },\n"
        "    {\n      \"time\": \"2024-07-01T00:00:00Z\",\n      \"complete\": true,\n"
        "      \"bid\": {\"o\": \"1.0\", \"h\": \"1.1\", \"l\": \"0.9\", \"c\": \"1.0\"},\n"
        "      \"ask\": {\"o\": \"1.1\", \"h\": \"1.2\", \"l\": \"1.0\", \"c\": \"1.1\"},\n"
        "      \"mid\": {\"o\": \"1.05\", \"h\": \"1.15\", \"l\": \"0.95\", \"c\": \"1.05\"}\n    },\n"
        "    {\n      \"time\": \"2025-04-01T00:00:00Z\",\n      \"bid\": THIS_VALIDATION_PRICE_MUST_NOT_BE_PARSED\n    }\n"
        "  ]\n}\n",
        encoding="utf-8",
    )
    rows, audit = module.stream_development_candles(source)
    assert len(rows) == 1
    assert audit == {
        "first_excluded_timestamp": "2025-04-01T00:00:00Z",
        "excluded_row_price_fields_parsed": 0,
        "stopped_before_validation_outcomes": True,
    }


def test_base_and_stress_costs_are_worse_than_gross() -> None:
    start = datetime(2024, 7, 15, 7, tzinfo=timezone.utc)
    candles = [candle(start + timedelta(hours=index), 1.0 + index * 0.0001, 1.0002 + index * 0.0001) for index in range(8)]
    event = {"entry_index": 0, "exit_index": 6, "atr": 0.01, "holding": 6, "pair": "EUR_USD"}
    gross = module.simulate_trade(candles, event, 1, None)["result_r"]
    base = module.simulate_trade(candles, event, 1, module.BASE_SLIPPAGE_PIPS)["result_r"]
    stress = module.simulate_trade(candles, event, 1, module.STRESS_SLIPPAGE_PIPS)["result_r"]
    assert gross > base > stress


def test_base_stop_loss_is_exactly_one_r_after_executable_cost_sizing() -> None:
    start = datetime(2024, 7, 15, 7, tzinfo=timezone.utc)
    candles = [candle(start + timedelta(hours=index), 1.0, 1.0002) for index in range(2)]
    event = {"entry_index": 0, "exit_index": 1, "atr": 0.0005, "holding": 1, "pair": "EUR_USD"}
    risk_distance = module.executable_initial_risk_distance(candles, event, 1)
    result = module.simulate_trade(candles, event, 1, module.BASE_SLIPPAGE_PIPS, risk_distance)
    assert result["exit_reason"] == "ATR_STOP"
    assert result["result_r"] == pytest.approx(-1.0)


def test_sparse_basket_never_reallocates_above_pair_cap() -> None:
    rows = [{"entry_timestamp": "2024-07-15T07:00:00Z", "base_currency": "EUR", "quote_currency": "USD", "frozen_initial_equity_risk_fraction": module.PAIR_RISK_CAP} for _ in range(3)]
    module.assign_frozen_risk_weights(rows)
    assert all(row["initial_equity_risk_fraction"] == pytest.approx(module.PAIR_RISK_CAP) for row in rows)
    assert sum(row["initial_equity_risk_fraction"] for row in rows) < module.PORTFOLIO_RISK_CAP


def test_reverse_identity_requires_same_events_and_opposite_sides() -> None:
    common = {
        "event_id": "event",
        "instrument": "EUR_USD",
        "base_currency": "EUR",
        "quote_currency": "USD",
        "source_observation": "2024-07-09T00:00:00Z",
        "signal_zscore": 1.25,
        "signal_timestamp": "2024-07-12T21:30:00Z",
        "entry_timestamp": "2024-07-15T07:00:00Z",
        "planned_time_exit_timestamp": "2024-07-15T13:00:00Z",
        "fold": 1,
        "maximum_holding_h1": 6,
        "atr_stop_distance": 0.002,
        "initial_equity_risk_fraction": module.PAIR_RISK_CAP,
        "spread": 0.0002,
        "modeled_slippage": 0.1,
        "stress_modeled_slippage_pips_per_side": 0.5,
    }
    rows = {"left": [{**common, "order_sign": 1}], "right": [{**common, "order_sign": -1}]}
    assert module.reverse_identity_check("left", "right", rows)["status"] == "PASS"
    rows["right"][0]["order_sign"] = 1
    assert module.reverse_identity_check("left", "right", rows)["status"] == "FAIL"


def test_symmetric_union_audit_rejects_size_drift() -> None:
    row = {
        "event_id": "event",
        "base_currency": "EUR",
        "quote_currency": "USD",
        "source_observation": "2024-07-09T00:00:00Z",
        "signal_zscore": 1.25,
        "signal_timestamp": "2024-07-12T21:30:00Z",
        "entry_timestamp": "2024-07-15T07:00:00Z",
        "planned_time_exit_timestamp": "2024-07-15T13:00:00Z",
        "maximum_holding_h1": 6,
        "fold": 1,
        "atr_stop_distance": 0.002,
        "order_sign": 1,
        "entry_price": 1.1,
        "exit_timestamp": "2024-07-15T13:00:00Z",
        "exit_price": 1.2,
        "exit_reason": "TIME_EXIT_H6",
        "stop_loss": 1.0,
        "executable_initial_risk_distance": 0.1,
        "initial_equity_risk_fraction": module.PAIR_RISK_CAP,
        "spread": 0.0002,
        "modeled_slippage": 0.1,
        "stress_modeled_slippage_pips_per_side": 0.5,
        "gross_result_r": 1.1,
        "net_result_r": 1.0,
        "stress_result_r": 0.9,
    }
    assert module.symmetric_union_check(6, [row], [], [dict(row)])["status"] == "PASS"
    drifted = {**row, "initial_equity_risk_fraction": module.PAIR_RISK_CAP * 2}
    assert module.symmetric_union_check(6, [row], [], [drifted])["status"] == "FAIL"


def test_completion_hash_and_preregistration_are_frozen() -> None:
    root = Path(__file__).resolve().parents[2]
    assert module.sha256_file(root / ".aios/staging/PKT_FOREX_035/PKT_FOREX_035_EXPANSION58_COMPLETION.json") == module.STAGE0_COMPLETION_SHA256
    prereg = root / ".aios/staging/PKT_FOREX_035/expansion58/run1/AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_PREREGISTRATION.json"
    assert module.sha256_file(prereg) == module.PREREGISTRATION_SHA256


def test_full_development_run_is_bounded_and_complete(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    result = module.run(root, tmp_path / "run")
    assert result["candidate_count_scored"] == 10
    assert result["trade_journal_rows"] == 7524
    assert result["actual_computational_attempt_lower_bound_after"] == 1220
    assert result["governed_after_cost_candidates_after"] == 168
    assert result["validation_rows_opened"] == 0
    assert result["final_holdout_rows_opened"] == 0
    reverse = json.loads((tmp_path / "run/AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_REVERSE_AUDIT.json").read_text(encoding="utf-8"))
    assert reverse["status"] == "PASS"
    assert all(item["status"] == "PASS" for item in reverse["symmetric_union_checks"])
