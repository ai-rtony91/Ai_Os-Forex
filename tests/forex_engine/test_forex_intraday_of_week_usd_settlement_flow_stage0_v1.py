import json

import pytest

from automation.forex_engine.forex_intraday_of_week_usd_settlement_flow_stage0_v1 import (
    F7_CONTRACT_FINGERPRINT,
    EXPECTED_CANDIDATE_FINGERPRINTS,
    EXPECTED_MECHANISM_FINGERPRINT,
    H1_CORPUS_SHA256,
    MECHANISM_DESCRIPTOR,
    PAIRS,
    VARIANTS,
    build_preregistration,
    build_source_registry,
    candidate_definitions,
    canonical_bytes,
    foreign_per_usd_order_sign,
    mechanism_fingerprint,
    sha256_bytes,
    variant_foreign_direction,
)


def test_exact_h1_usd_pair_scope_is_frozen():
    assert len(PAIRS) == len(set(PAIRS)) == 17
    assert all("USD" in pair.split("_") for pair in PAIRS)
    assert H1_CORPUS_SHA256 == "4357f24113ba54b9a6f8d6a3d87860109ca7429dbbd627b20c3d5a30540c6b32"


def test_foreign_per_usd_orientation_is_exact():
    assert foreign_per_usd_order_sign("EUR_USD", 1) == 1
    assert foreign_per_usd_order_sign("EUR_USD", -1) == -1
    assert foreign_per_usd_order_sign("USD_JPY", 1) == -1
    assert foreign_per_usd_order_sign("USD_JPY", -1) == 1
    with pytest.raises(ValueError, match="INVALID_PAIR"):
        foreign_per_usd_order_sign("EUR_JPY", 1)


def test_original_and_reverse_weekday_directions_are_arithmetic_opposites():
    for weekday in (2, 3, 4):
        assert variant_foreign_direction("WED_FRI_EXACT_REVERSED_SHORT", weekday) == -variant_foreign_direction("WED_FRI_ORIGINAL_LONG", weekday)
    for weekday in (0, 1):
        assert variant_foreign_direction("MON_TUE_EXACT_REVERSED_LONG", weekday) == -variant_foreign_direction("MON_TUE_ORIGINAL_SHORT", weekday)
    assert [variant_foreign_direction("SYMMETRIC_ORIGINAL", day) for day in range(5)] == [-1, -1, 1, 1, 1]


def test_exact_five_candidates_are_unique_and_no_parameter_mining():
    candidates = candidate_definitions()
    assert len(VARIANTS) == len(candidates) == 5
    assert len({item["candidate_fingerprint"] for item in candidates}) == 5
    assert {item["candidate_id"]: item["candidate_fingerprint"] for item in candidates} == EXPECTED_CANDIDATE_FINGERPRINTS


def test_preregistration_freezes_costs_baselines_gates_and_sealed_data():
    prereg = build_preregistration()
    assert prereg["preregistered_before_outcome_access"] is True
    assert prereg["dataset"]["validation"].endswith("UNOPENED_UNLESS_STAGE1_SURVIVOR")
    assert prereg["dataset"]["final_holdout"] == "2026_ROWS_SEALED_SINGLE_USE"
    assert prereg["parameter_grid"]["fitted_parameters"] == 0
    assert prereg["cost_model"]["base"].endswith("0.10 pip adverse slippage per side")
    assert "NO_TRADE_ZERO_EXPECTANCY" in prereg["baselines"]
    assert "WEEKDAY_AGNOSTIC_SAME_WINDOW" in prereg["baselines"]
    assert prereg["stage1_rejection_gates"]["after_cost_expectancy_must_exceed_zero"] is True
    assert len(prereg["chronological_folds"]) == 6


def test_source_registry_preserves_support_counterevidence_and_license():
    registry = build_source_registry()
    assert len(registry["sources"]) == 4
    required = {
        "source_id", "url", "title", "author_or_organization", "publication_date",
        "access_date", "source_type", "claimed_economic_mechanism", "claimed_market_and_timeframe",
        "exact_disclosed_rules", "claimed_performance", "costs_included", "walk_forward_included",
        "source_code_exists", "license", "replication_risks", "aios_dataset_compatibility",
        "existing_fingerprint_match", "research_priority", "final_disposition",
    }
    assert all(required <= set(source) for source in registry["sources"])
    dispositions = {source["source_id"]: source["final_disposition"] for source in registry["sources"]}
    assert dispositions["YAMORI_KURIHARA_2004_DOW_DECAY"].startswith("COUNTEREVIDENCE")
    assert dispositions["FXABSOLUTE_EDGE_GUIDE"].endswith("NOT_EDGE_PROOF")


def test_f7_lineage_and_mechanism_hash_are_deterministic():
    assert F7_CONTRACT_FINGERPRINT == "e3fbdbb0a0fdfba17f4646c32769ed9e1732fee40ba113bc7eb78585c8fca27f"
    assert mechanism_fingerprint() == sha256_bytes(canonical_bytes(MECHANISM_DESCRIPTOR, compact=True))
    assert mechanism_fingerprint() == EXPECTED_MECHANISM_FINGERPRINT


def test_canonical_json_rejects_nan():
    assert json.loads(canonical_bytes({"b": 2, "a": 1})) == {"a": 1, "b": 2}
    with pytest.raises(ValueError):
        canonical_bytes({"bad": float("nan")})
