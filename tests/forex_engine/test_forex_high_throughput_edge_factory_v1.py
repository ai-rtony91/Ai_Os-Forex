from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from automation.forex_engine import forex_high_throughput_edge_factory_v1 as factory
from scripts.forex_delivery.run_forex_high_throughput_edge_factory_v1 import (
    REJECTION_INPUTS,
    run,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_catalog_has_exactly_one_million_virtual_items() -> None:
    descriptor = factory.catalog_descriptor()
    assert factory.catalog_cardinality() == 1_000_000
    assert descriptor["cardinality"] == 1_000_000
    assert descriptor["materialized_item_count"] == 0
    assert descriptor["market_outcomes_read"] is False
    assert descriptor["catalog_items_count_as_trials"] is False
    assert descriptor["axis_lengths"] == {
        "mechanism": 10,
        "context": 10,
        "timeframe": 10,
        "lookback": 10,
        "threshold": 10,
        "direction": 5,
        "exit": 2,
    }


@pytest.mark.parametrize("index", [0, 1, 4095, 4096, 499_999, 999_999])
def test_random_access_round_trip(index: int) -> None:
    assert factory.encode_index(factory.decode_index(index)) == index
    assert factory.spec_at(index)["catalog_id"] == f"FXH-{index:07d}"


def test_catalog_bounds_fail_closed() -> None:
    with pytest.raises(IndexError, match="CATALOG_INDEX_OUT_OF_RANGE"):
        factory.decode_index(-1)
    with pytest.raises(IndexError, match="CATALOG_INDEX_OUT_OF_RANGE"):
        factory.decode_index(1_000_000)


def test_spec_has_every_required_building_block() -> None:
    required = {
        "economic_mechanism", "long_direction", "exact_reverse_short_direction",
        "original_short_direction", "exact_reverse_long_direction", "bidirectional_version",
        "direction_variant", "pair_selection_logic", "currency_selection_logic",
        "session_condition", "volatility_condition", "trend_condition", "range_condition",
        "relative_value_condition", "positioning_condition", "risk_sentiment_condition",
        "economic_event_condition", "signal_timeframe", "confirmation_timeframe",
        "entry_rule", "exit_rule", "stop_type", "take_profit_type", "time_exit",
        "position_sizing_rule", "exposure_cap", "holding_period_class", "candidate_fingerprint",
    }
    assert required <= factory.spec_at(321_987).keys()
    assert "H4" not in {row["signal_timeframe"] for row in factory.TIMEFRAMES}
    assert "H4" not in {row["confirmation_timeframe"] for row in factory.TIMEFRAMES}


def test_all_five_direction_variants_and_inverse_involution() -> None:
    observed = set()
    for direction_index, expected in enumerate(factory.DIRECTIONS):
        indices = (0, 0, 0, 0, 0, direction_index, 0)
        spec = factory.spec_at(factory.encode_index(indices))
        observed.add(spec["direction_variant"])
        assert factory.inverse_spec(factory.inverse_spec(spec)) == spec
        assert factory.inverse_spec(spec)["direction_variant"] == factory.INVERSE_DIRECTIONS[expected]
    assert observed == set(factory.DIRECTIONS)


def test_chunk_proof_has_245_chunks_and_last_576() -> None:
    chunks = factory.catalog_chunk_hashes(factory.catalog_descriptor()["descriptor_sha256"])
    assert len(chunks) == 245
    assert chunks[-1]["count"] == 576
    assert chunks[-1]["end_exclusive"] == 1_000_000


def test_public_sources_are_hypothesis_only_and_complete() -> None:
    required = {
        "source_id", "url", "author_or_organization", "publication_date", "source_type",
        "claimed_economic_mechanism", "claimed_market_and_timeframe", "exact_disclosed_rules",
        "claimed_performance", "costs_included", "walk_forward_included", "source_code",
        "license", "replication_risks", "aios_dataset_compatibility",
        "existing_fingerprint_match", "research_priority", "final_disposition",
    }
    sources = factory.public_sources()
    assert len(sources) >= 10
    assert all(required <= row.keys() for row in sources)
    assert all(row["evidence_status"] == "UNVERIFIED_HYPOTHESIS_SOURCE" for row in sources)
    assert any(row["source_id"] == "FXABSOLUTE_EDGE_GUIDE" for row in sources)


def test_cluster_gate_blocks_duplicates_and_selects_round_number() -> None:
    rows = factory.cluster_rows()
    by_id = {row["cluster_id"]: row for row in rows}
    assert by_id["VOLATILITY_COMPRESSION_BREAKOUT"]["stage0_disposition"] == "BLOCKED"
    assert by_id["CROSS_SECTIONAL_RELATIVE_VALUE"]["stage0_disposition"] == "BLOCKED"
    assert by_id["GENERIC_TREND_PULLBACK"]["stage0_disposition"] == "BLOCKED"
    assert by_id["ROUND_NUMBER_CONDITIONAL_ORDER_STATE"]["stage0_disposition"] == "ELIGIBLE_FOR_BOUNDED_PREREGISTRATION"


def test_real_memory_reconciliation_preserves_all_attempt_classes() -> None:
    paths = [REPO_ROOT / relative for relative in REJECTION_INPUTS]
    memory = factory.reconcile_memory(paths, REPO_ROOT)
    assert memory["current_governed_lineage"]["rejected_families"] == 16
    assert memory["current_governed_lineage"]["scored_after_cost_candidates"] == 112
    assert memory["conservative_nonoverlapping_computational_attempt_lower_bound"] == 1164
    assert memory["known_heterogeneous_fold_summary_count"] == 4600
    assert memory["current_lineage_summary_fold_windows"] == 288
    assert memory["proposed_untested_count"] == 311
    assert memory["attempted_no_data_invalid_count"] == 20
    assert memory["new_stage0_catalog_scored_trials"] == 0
    assert memory["holdout_evaluations"] == 0
    assert memory["champion_promotion_blocked_until_legacy_unknown_resolved"] is True


def test_packet_closure_and_dataset_resolver_are_exact_and_no_outcome() -> None:
    closure = factory.closure_audit(REPO_ROOT)
    assert closure["status"] == "PASS"
    assert closure["latest_checkpoint_sha256"] == factory.PRIOR_COMPLETION_SHA256
    datasets = factory.resolve_certified_datasets(REPO_ROOT)
    assert datasets["pair_count"] == datasets["eligible_pair_count"] == 58
    assert datasets["excluded_pair_count"] == 0
    assert datasets["market_price_rows_opened"] == 0
    assert datasets["validation_rows_opened"] == datasets["final_holdout_rows_opened"] == 0
    assert len({row["pair"] for row in datasets["pair_rows"]}) == 58
    assert all(row["pip_size"] == 10 ** row["pip_location"] for row in datasets["pair_rows"])


def test_successor_is_bounded_exact_and_keeps_holdout_sealed() -> None:
    paths = [REPO_ROOT / relative for relative in REJECTION_INPUTS]
    memory = factory.reconcile_memory(paths, REPO_ROOT)
    datasets = factory.resolve_certified_datasets(REPO_ROOT)
    prereg = factory.successor_preregistration(memory, factory.cluster_rows(), datasets)
    assert prereg["candidate_count"] == 135
    assert {row["direction_variant"] for row in prereg["parameter_grid"]} == set(factory.DIRECTIONS)
    assert prereg["final_holdout"] == "2026_ROWS_SEALED_SINGLE_USE"
    assert len(prereg["pair_universe"]) == 58
    assert {row["branch"] for row in prereg["parameter_grid"]} == {"ROUND_NUMBER_APPROACH_REJECTION", "ROUND_NUMBER_COMPLETED_CROSS_CONTINUATION"}
    assert "<" not in prereg["reproduction_command"]
    assert prereg["baselines"][0] == "NO_TRADE_ZERO"


def test_cost_and_champion_gates_fail_closed() -> None:
    assert factory.after_cost_pips(5.0, 1.0, 1.0, 0.1) == pytest.approx(3.8)
    passing = {"after_cost_expectancy": 0.01, "profit_factor": 1.10, "maximum_drawdown_pct": 10.0, "trades": 200, "walk_forward": True, "cost_stress": True, "parameter_stability": True, "leakage": True, "concentration": True, "baseline": True, "multiple_testing": True, "reproduction": True}
    assert factory.champion_gate(passing) is True
    assert factory.champion_gate({**passing, "after_cost_expectancy": 0.0}) is False
    assert factory.champion_gate({**passing, "multiple_testing": False}) is False


def test_source_has_no_network_or_market_execution_imports() -> None:
    source = Path(factory.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert imported_roots.isdisjoint({"requests", "httpx", "urllib", "socket", "oandapyV20"})
    assert "oanda" not in imported_roots


def test_runner_isolated_output_and_no_overwrite(tmp_path: Path, monkeypatch) -> None:
    from scripts.forex_delivery import run_forex_high_throughput_edge_factory_v1 as runner
    # Only redirect the output boundary. The actual builder and immutable
    # source checks still run; old PKT037 evidence is never overwritten.
    monkeypatch.setattr(runner, "ALLOWED_ROOT", tmp_path)
    permitted = tmp_path / "factory_stage0"
    result = run(permitted)
    assert result["status"] == "PASS"
    assert result["artifact_count"] == 13
    receipt = json.loads((permitted / "AIOS_FOREX_EDGE_FACTORY_RECEIPT.json").read_text(encoding="utf-8"))
    assert all(value == "PASS" for value in receipt["acceptance"].values())
    assert all(value is False for value in receipt["safety"].values())
    with pytest.raises(FileExistsError, match="OUTPUT_ROOT_ALREADY_EXISTS"):
        run(permitted)
def test_supertrend_catalog_v1_cardinality_family_balance_and_roundtrip():
    from automation.forex_engine.forex_high_throughput_edge_factory_v1 import supertrend_research_catalog_v1
    catalog = supertrend_research_catalog_v1()
    assert catalog.cardinality == 26176
    assert len(catalog.family_counts) == 4
    for index in [0, 63, 64, 6207, 6208, catalog.cardinality-1]:
        spec = catalog.spec_at(index)
        assert catalog.index_of(spec) == index
        assert spec == supertrend_research_catalog_v1().spec_at(index)
        assert "performance_decay" not in spec["implementation"]
    classic = catalog.spec_at(0)["implementation"]
    assert not {"performance_memory", "update_cadence", "cluster_rule"} & set(classic)


def test_supertrend_catalog_v1_static_history_noops_and_trade_equivalence():
    from automation.forex_engine.forex_high_throughput_edge_factory_v1 import (
        supertrend_research_catalog_v1, supertrend_static_prefilter_v1, supertrend_trade_equivalence_v1)
    catalog = supertrend_research_catalog_v1()
    spec = catalog.spec_at(100)
    assert supertrend_static_prefilter_v1(spec,catalog)["market_exposure"] == 0
    assert supertrend_static_prefilter_v1(spec,catalog,[spec["implementation_sha256"]])["state"] == "CLOSED_HISTORY"
    altered = {**spec, "implementation": {**spec["implementation"], "performance_decay": .1}}
    assert supertrend_static_prefilter_v1(altered,catalog)["state"] == "STATIC_REJECTED"
    groups = supertrend_trade_equivalence_v1({"a": [0,1,-1], "b": [0,1,-1], "c": [0,0,1]})
    assert groups["implementation_count"] == 3 and groups["distinct_direction_sequences"] == 2
    assert not groups["independent_samples"]
