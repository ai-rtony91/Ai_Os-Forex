import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from automation.forex_engine.forex_cftc_asset_manager_weekly_change_stage0_v1 import (
    COVERAGE_MAP,
    EXPECTED_MECHANISM_FINGERPRINT,
    DIRECT_PAIRS,
    FOLD_ENDS,
    HOLDING_HOURS,
    VARIANTS,
    build_preregistration,
    build_capability_audit,
    build_source_registry,
    candidate_definitions,
    canonical_bytes,
    causal_zscore,
    development_cftc_paths,
    fold_id,
    market_currency,
    mechanism_fingerprint,
    next_monday_07,
    positive_foreign_signal_pair_side,
    pair_eligibility_rows,
    pair_signal_inventory,
    predecessor_promotion_audit,
)


def certified_h1_pairs():
    matrix = json.loads(Path(".aios/staging/PKT_FOREX_027/run1/AIOS_FOREX_AUTHORITATIVE_PAIR_TIMEFRAME_MATRIX_V1.json").read_text(encoding="utf-8"))
    return sorted(row["pair"] for row in matrix["rows"] if row["granularity"] == "H1" and row["development_eligibility"] is True)


def test_exact_nine_currency_contract_scope_and_zar_typo_regression():
    assert len(COVERAGE_MAP) == len(DIRECT_PAIRS) == 9
    assert set(DIRECT_PAIRS) == {"AUD_USD", "USD_CAD", "USD_CHF", "EUR_USD", "GBP_USD", "USD_JPY", "USD_MXN", "NZD_USD", "USD_ZAR"}
    assert market_currency("SO AFRICAN RAND - CHICAGO MERCANTILE EXCHANGE") == "ZAR"
    with pytest.raises(ValueError, match="UNMAPPED"):
        market_currency("SOUTH AFRICAN RAND - CHICAGO MERCANTILE EXCHANGE")


def test_exact_positive_foreign_signal_pair_sides():
    assert {currency: positive_foreign_signal_pair_side(currency) for currency in ("AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "MXN", "NZD", "ZAR")} == {
        "AUD": ("AUD_USD", 1), "CAD": ("USD_CAD", -1), "CHF": ("USD_CHF", -1),
        "EUR": ("EUR_USD", 1), "GBP": ("GBP_USD", 1), "JPY": ("USD_JPY", -1),
        "MXN": ("USD_MXN", -1), "NZD": ("NZD_USD", 1), "ZAR": ("USD_ZAR", -1),
    }


def test_all_58_pairs_are_mapped_with_exact_33_eligible_and_24_crosses():
    rows = pair_eligibility_rows(certified_h1_pairs())
    assert len(rows) == len({row["pair"] for row in rows}) == 58
    assert sum(row["eligible"] for row in rows) == 33
    assert sum(row["mapping_type"] == "DIRECT_USD_MAPPING" for row in rows) == 9
    assert sum(row["mapping_type"] == "DERIVED_CROSS_BASE_MINUS_QUOTE" for row in rows) == 24
    assert sum(row["mapping_type"] == "UNSUPPORTED" for row in rows) == 25
    assert next(row for row in rows if row["pair"] == "EUR_GBP")["mapping_formula"] == "Z_EUR_MINUS_Z_GBP"
    unsupported = next(row for row in rows if row["pair"] == "USD_CNH")
    assert unsupported["mapping_formula"] == "NONE"
    assert unsupported["exclusion_reason"] == "MISSING_POINT_IN_TIME_CFTC_CONTRACT:CNH"


def test_cross_pair_signal_is_causal_base_minus_quote_and_aligned():
    decision = datetime(2025, 1, 6, 7, tzinfo=timezone.utc)
    available = datetime(2025, 1, 3, 21, 30, tzinfo=timezone.utc)
    base = {"decision": decision, "source_available": available, "source_observation": available, "zscore": 1.25, "weekly_change": 0.04, "normalized_net": 0.10}
    quote = {"decision": decision, "source_available": available, "source_observation": available, "zscore": -0.75, "weekly_change": -0.01, "normalized_net": 0.02}
    row = pair_signal_inventory("EUR_GBP", {"EUR": [base], "GBP": [quote]})[0]
    assert row["pair_zscore"] == pytest.approx(2.0)
    assert row["pair_weekly_change"] == pytest.approx(0.05)
    assert row["pair_normalized_net"] == pytest.approx(0.08)
    assert row["source_available"] < row["decision"]


def test_only_2024_and_2025_cftc_paths_are_eligible(tmp_path):
    names = [path.name for path, _ in development_cftc_paths(tmp_path)]
    assert names == ["cftc_2024.json", "cftc_2025.json"]
    assert "cftc_2026.json" not in names


def test_predecessor_promotion_is_independently_byte_verified():
    audit = predecessor_promotion_audit(__import__("pathlib").Path.cwd())
    assert audit["status"] == "PASS"
    assert audit["canonical_artifact_count"] == 32
    assert audit["byte_identical_artifact_count"] == 32
    assert audit["mismatches"] == []


def test_current_change_is_excluded_from_prior_26_normalization():
    levels = [0.0]
    for index in range(1, 28):
        levels.append(levels[-1] + float(index))
    expected = (27.0 - sum(range(1, 27)) / 26.0) / (sum((value - 13.5) ** 2 for value in range(1, 27)) / 26.0) ** 0.5
    assert causal_zscore(levels, 27) == pytest.approx(expected)
    changed_current = levels[:-1] + [levels[-2] + 2700.0]
    assert causal_zscore(changed_current, 27) > 100.0


def test_next_monday_decision_is_strictly_after_publication():
    friday = datetime(2025, 1, 3, 21, 30, tzinfo=timezone.utc)
    assert next_monday_07(friday) == datetime(2025, 1, 6, 7, tzinfo=timezone.utc)
    monday = datetime(2025, 1, 6, 8, tzinfo=timezone.utc)
    assert next_monday_07(monday) == datetime(2025, 1, 13, 7, tzinfo=timezone.utc)


def test_six_frozen_fold_boundaries_assign_expected_week_counts():
    dates = [datetime(2024, 7, 15, 7, tzinfo=timezone.utc)]
    while len(dates) < 38:
        dates.append(dates[-1].replace() + __import__("datetime").timedelta(days=7))
    counts = [sum(fold_id(date) == index for date in dates) for index in range(1, 7)]
    assert len(FOLD_ENDS) == 6
    assert counts == [7, 7, 6, 6, 6, 6]


def test_exact_five_direction_variants_two_horizons_and_unique_fingerprints():
    rows = candidate_definitions()
    assert len(VARIANTS) == 5
    assert HOLDING_HOURS == (6, 12)
    assert len(rows) == len({row["candidate_fingerprint"] for row in rows}) == 10
    assert {row["variant"] for row in rows} == set(VARIANTS)
    assert {row["maximum_holding_h1"] for row in rows} == {6, 12}


def test_preregistration_freezes_costs_baselines_gates_and_sealed_data():
    rows = pair_eligibility_rows(certified_h1_pairs())
    pairs = tuple(row["pair"] for row in rows if row["eligible"])
    totals = {"causal_pair_signals": 1254, "positive_pair_z": 627, "negative_pair_z": 627, "zero_pair_z": 0}
    prereg = build_preregistration(pairs, totals)
    assert prereg["preregistered_before_outcome_access"] is True
    assert "exclude the current change" in prereg["signal_calculation"]
    assert prereg["dataset"]["validation"].endswith("UNOPENED_UNLESS_STAGE1_SURVIVOR")
    assert prereg["dataset"]["final_holdout"] == "2026_ROWS_SEALED_SINGLE_USE"
    assert prereg["parameter_grid"]["candidate_count"] == 10
    assert prereg["parameter_grid"]["fitted_parameters"] == 0
    assert prereg["cost_model"]["base"].endswith("0.10 pip adverse slippage per side")
    assert "NO_TRADE_ZERO_EXPECTANCY" in prereg["baselines"]
    assert "ASSET_MANAGER_NET_LEVEL_SIGN" in prereg["baselines"]
    assert prereg["stage1_rejection_gates"]["after_cost_expectancy_must_exceed_zero"] is True
    assert prereg["stage1_rejection_gates"]["minimum_positive_folds"] == 4
    assert len(prereg["pair_universe"]) == 33
    assert prereg["risk_limits"]["maximum_pair_initial_risk_fraction"] == pytest.approx(0.0025 / 33)
    assert prereg["multiple_testing"]["expected_after_stage1"] == {"attempts": 1220, "governed_after_cost_candidates": 168}


def test_capability_audit_records_missing_unified_components_without_claiming_invalidation():
    rows = pair_eligibility_rows(certified_h1_pairs())
    pairs = tuple(row["pair"] for row in rows if row["eligible"])
    audit = build_capability_audit(certified_h1_pairs(), pairs)
    assert audit["capabilities"]["dataset_hash_cache"]["status"] == "MISSING_UNIFIED"
    assert audit["capabilities"]["champion_selection"]["status"] == "MISSING_UNIFIED"
    assert audit["pair_and_grouping_engine"]["certified_pair_count"] == 58
    assert audit["pair_and_grouping_engine"]["directed_pair_relationship_count"] == 116
    assert audit["successor_repair_packet_required"] is True


def test_source_registry_records_placebo_counterevidence_and_fxabsolute_limits():
    registry = build_source_registry()
    required = {
        "source_id", "url", "title", "author_or_organization", "publication_date", "access_date",
        "source_type", "claimed_economic_mechanism", "claimed_market_and_timeframe", "exact_disclosed_rules",
        "claimed_performance", "costs_included", "walk_forward_included", "source_code_exists", "license",
        "replication_risks", "aios_dataset_compatibility", "existing_fingerprint_match", "research_priority", "final_disposition",
    }
    assert len(registry["sources"]) == 5
    assert all(required <= set(source) for source in registry["sources"])
    placebo = next(source for source in registry["sources"] if source["source_id"] == "KREMENS_SPECULATOR_RISK_PLACEBO")
    assert "PLACEBO" in placebo["final_disposition"]
    fxabsolute = next(source for source in registry["sources"] if source["source_id"] == "FXABSOLUTE_EDGE_GUIDE")
    assert fxabsolute["final_disposition"].endswith("NOT_EDGE_PROOF")


def test_mechanism_and_canonical_json_are_exact_and_deterministic():
    assert mechanism_fingerprint() == EXPECTED_MECHANISM_FINGERPRINT
    assert json.loads(canonical_bytes({"b": 2, "a": 1})) == {"a": 1, "b": 2}
    with pytest.raises(ValueError):
        canonical_bytes({"bad": float("nan")})
