from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from automation.forex_engine import forex_pro_historical_evidence_marathon_v1 as marathon


@pytest.fixture(scope="module")
def reproduced_population():
    first = marathon.generate_historical_population()
    second = marathon.generate_historical_population()
    return first, second


def test_frozen_strategy_hash_matches_runtime_state():
    state = json.loads(marathon.PAPER30_STATE_PATH.read_text(encoding="utf-8"))
    assert marathon.STRATEGY_SHA256 == "13b96b3e227a2b5873ba5916a4987cf571868626339d1a89e2cd6e0e25bd1435"
    assert state["strategy_config_sha256"] == marathon.STRATEGY_SHA256


def test_holdout_v1_dataset_is_not_addressed_by_module():
    source = Path(marathon.__file__).read_text(encoding="utf-8").lower()
    assert "forex_final_holdout_v1" not in source
    assert "final_holdout_v1.json" not in source


def test_holdout_v2_dataset_is_not_addressed_by_module():
    source = Path(marathon.__file__).read_text(encoding="utf-8").lower()
    assert "forex_final_holdout_v2" not in source
    assert "final_holdout_v2.json" not in source


def test_forward_paper_credit_is_zero():
    assert marathon._forward_count() == 0
    source = Path(marathon.__file__).read_text(encoding="utf-8")
    assert '"HISTORICAL_BACKFILL_TRADE_COUNT": 0' in source
    assert '"QUALIFYING_FORWARD_TRADES_CREDITED": 0' in source


def test_unique_and_simulated_counts_are_separate_concepts():
    assert marathon.ORDINARY_BOOTSTRAP_RUNS == 50_000
    assert marathon.PERMUTATION_RUNS == 50_000
    assert "UNIQUE_HISTORICAL_TRADES" in Path(marathon.__file__).read_text(encoding="utf-8")
    assert "RESAMPLED_SIMULATIONS" in Path(marathon.__file__).read_text(encoding="utf-8")


def test_resume_packet_records_single_authorized_execution():
    assert marathon.PACKET_ID == "PKT-EAST-FOREX-PRO-HISTORICAL-EVIDENCE-MARATHON-022R2"
    assert marathon.AUTHORIZED_MARATHON_EXECUTIONS == 1


def test_historical_population_reproduces_deterministically(reproduced_population):
    first, second = reproduced_population
    assert len(first["trades"]) == len(second["trades"]) == 431
    assert marathon.semantic_trade_hash(first["trades"]) == marathon.semantic_trade_hash(second["trades"])
    assert first["train_end"] == second["train_end"] == "2026-08-20T09:30:00.000000000Z"


def test_historical_population_matches_prior_authorized_hash(reproduced_population):
    first, _second = reproduced_population
    assert marathon._canonical_semantic_trade_hash(first["trades"]) == marathon.EXPECTED_LEGACY_TRADE_HASH
    assert first["duplicates"] == 0


def test_rolling_windows_are_deterministic():
    values = [1.5, -1.0, 0.5, -0.25] * 10
    assert marathon.rolling_analysis(values, 30) == marathon.rolling_analysis(values, 30)
    assert marathon.rolling_analysis(values, 30)["window_count"] == 11


def test_sample_size_ladder_is_deterministic():
    values = [1.0, -0.5] * 150
    first = [marathon.rolling_analysis(values, size) for size in marathon.SAMPLE_SIZES]
    second = [marathon.rolling_analysis(values, size) for size in marathon.SAMPLE_SIZES]
    assert first == second


def test_ordinary_bootstrap_is_deterministic():
    values = [1.5, -1.0, 0.25, -0.5]
    assert marathon.ordinary_bootstrap(values, 30, runs=200) == marathon.ordinary_bootstrap(values, 30, runs=200)


def test_block_bootstrap_is_deterministic():
    values = [1.5, -1.0, 0.25, -0.5] * 4
    assert marathon.moving_block_bootstrap(values, 30, 5, runs=200) == marathon.moving_block_bootstrap(values, 30, 5, runs=200)


def test_monte_carlo_permutation_is_deterministic():
    values = [2.0, -1.0, -0.5, 1.0] * 5
    first = marathon.permutation_sequence_risk(values, runs=200)
    second = marathon.permutation_sequence_risk(values, runs=200)
    assert first == second
    assert sum(values) == pytest.approx(sum(reversed(values)))


def test_pair_concentration_reconciles():
    trades = [
        {"instrument": "A", "realized_r": 2.0},
        {"instrument": "A", "realized_r": -0.5},
        {"instrument": "B", "realized_r": 1.0},
    ]
    _records, summary = marathon.pair_analysis(trades, ["A", "B"])
    assert summary["PAIR_NET_R_RECONCILIATION"] == pytest.approx(2.5)


def test_leave_one_pair_out_is_deterministic():
    trades = [{"instrument": name, "realized_r": value} for name, value in zip("ABC", (1.0, -0.5, 2.0))]
    assert marathon.leave_one_pair_out(trades, list("ABC")) == marathon.leave_one_pair_out(trades, list("ABC"))


def test_leave_five_pairs_out_is_deterministic():
    instruments = list("ABCDEFGH")
    trades = [{"instrument": name, "realized_r": index / 10 - 0.2} for index, name in enumerate(instruments)]
    assert marathon.leave_five_pairs_out(trades, instruments, runs=10) == marathon.leave_five_pairs_out(trades, instruments, runs=10)


def test_mfe_is_causal_and_excludes_primary_exit_bar():
    candles = [
        SimpleNamespace(timestamp=f"2026-01-01T00:{index:02d}:00Z", high=high, low=low)
        for index, (high, low) in enumerate(
            [(1.0, 1.0), (1.005, 0.999), (1.009, 0.998), (1.10, 0.99), (1.06, 1.0)]
        )
    ]
    trade = {
        "instrument": "A",
        "trade_id": "one",
        "entry_index": 1,
        "exit_index": 3,
        "entry_price": 1.0,
        "initial_risk_distance": 0.01,
        "exit_timestamp_utc": candles[3].timestamp,
        "exit_reason": "PROTECTIVE_STOP",
        "realized_r": -1.0,
    }
    result = marathon.path_excursions([trade], {"A": candles})
    assert result["MFE_CAUSAL"] is True
    assert result["REACHED_1_0R_COUNT"] == 0
    assert result["5R_REACHED_BEFORE_PRIMARY_EXIT_COUNT"] == 0
    assert result["5R_REACHED_AFTER_PRIMARY_EXIT_WOULD_HAVE_OCCURRED_COUNT"] == 1


def test_latency_stress_is_deterministic():
    values = [1.0, -0.5] * 60
    assert marathon.friction_analysis(values) == marathon.friction_analysis(values)
    assert marathon.friction_analysis(values)["BREAKEVEN_FRICTION_R"] == pytest.approx(0.25)


def test_confidence_intervals_are_deterministic():
    values = [1.0, -0.5, 0.25, -0.25] * 10
    assert marathon.confidence_intervals(values, runs=200) == marathon.confidence_intervals(values, runs=200)


def test_false_confidence_probability_is_quantitative_and_deterministic():
    values = [1.0] * 30 + [-1.0] * 30 + [1.0, -0.5] * 30
    first = marathon.false_confidence_analysis(values)
    second = marathon.false_confidence_analysis(values)
    assert first == second
    assert first["PAPER30_FALSE_CONFIDENCE_PROBABILITY"] == pytest.approx(
        first["PASS_THEN_NEXT_30_POOR_PROBABILITY"]
    )


def test_json_is_standards_compliant_and_rejects_nonfinite():
    payload = {"finite": 1.0, "nested": [False, None]}
    marathon._strict_json(payload)
    json.dumps(payload, allow_nan=False)
    with pytest.raises(ValueError, match="STATISTICAL_INTEGRITY_FAILURE"):
        marathon._strict_json({"bad": float("inf")})


def test_paper30_invariants_remain_unchanged_during_analysis(reproduced_population):
    before = marathon._invariant_hashes()
    _ = marathon.rolling_analysis([float(item["realized_r"]) for item in reproduced_population[0]["trades"]], 30)
    after = marathon._invariant_hashes()
    assert before == after
    assert marathon._forward_count() == 0


def test_module_has_no_network_broker_or_credential_client():
    source = Path(marathon.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("import requests", "import socket", "urllib.request", "oanda_read_only_client", "order_submit("):
        assert forbidden not in source


def test_live_execution_is_explicitly_false():
    source = Path(marathon.__file__).read_text(encoding="utf-8")
    assert '"LIVE_EXECUTION_ENABLED": False' in source
    assert '"LIVE_ORDERS": False' in source
