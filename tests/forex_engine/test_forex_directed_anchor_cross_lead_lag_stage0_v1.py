import json

import pytest

from automation.forex_engine.forex_directed_anchor_cross_lead_lag_stage0_v1 import (
    ANCHORS,
    EXPECTED_CANDIDATE_FINGERPRINTS,
    MECHANISM_DESCRIPTOR,
    MECHANISM_FINGERPRINT,
    TARGETS,
    build_preregistration,
    build_source_registry,
    candidate_definitions,
    canonical_bytes,
    directed_links,
    order_sign,
    sha256_bytes,
    target_exposure_sign,
)


def test_exact_anchor_target_and_link_counts():
    links = directed_links()
    assert len(ANCHORS) == 7
    assert len(TARGETS) == len(set(TARGETS)) == 41
    assert all("USD" not in target.split("_") for target in TARGETS)
    assert sum(map(len, links.values())) == 62
    assert min(map(len, links.values())) >= 4


def test_target_exposure_orientation_is_exact():
    assert target_exposure_sign("EUR_JPY", "EUR") == 1
    assert target_exposure_sign("EUR_JPY", "JPY") == -1
    with pytest.raises(ValueError, match="TARGET_DOES_NOT_CONTAIN"):
        target_exposure_sign("EUR_JPY", "AUD")


def test_anchor_and_target_quote_orientation_normalizes_currency_strength():
    assert order_sign(1, "EUR_USD", "EUR_JPY", "CONTINUATION") == 1
    assert order_sign(1, "USD_JPY", "EUR_JPY", "CONTINUATION") == 1
    assert order_sign(-1, "USD_JPY", "EUR_JPY", "CONTINUATION") == -1


def test_exact_reverse_is_arithmetic_negative_for_every_link_and_shock_sign():
    for anchor, targets in directed_links().items():
        for target in targets:
            for shock_sign in (-1, 1):
                continuation = order_sign(shock_sign, anchor, target, "CONTINUATION")
                reverse = order_sign(shock_sign, anchor, target, "EXACT_REVERSE")
                assert reverse == -continuation


def test_eight_candidate_fingerprints_are_exact_and_unique():
    definitions = candidate_definitions()
    assert len(definitions) == 8
    assert len({item["candidate_fingerprint"] for item in definitions}) == 8
    assert {item["candidate_id"]: item["candidate_fingerprint"] for item in definitions} == EXPECTED_CANDIDATE_FINGERPRINTS
    assert MECHANISM_FINGERPRINT == "1f5948e3538c1ef55a1f91fca91cc41ff3e49aac5d6dd77a1f14a584a3bccfec"
    assert sha256_bytes(canonical_bytes(MECHANISM_DESCRIPTOR, compact=True)) == MECHANISM_FINGERPRINT


def test_preregistration_freezes_costs_baselines_capacity_and_sealed_data():
    prereg = build_preregistration()
    assert prereg["preregistered_before_outcome_access"] is True
    assert prereg["dataset"]["validation_access"] == "PROHIBITED_UNLESS_STAGE1_SURVIVOR"
    assert prereg["dataset"]["final_holdout"] == "SEALED_SINGLE_USE"
    assert prereg["stage1_pre_score_capacity_gate"]["minimum_selected_opportunities_per_candidate"] == 400
    assert prereg["cost_model"]["base"].endswith("0.10 pip adverse slippage per side")
    assert "NO_TRADE_ZERO_EXPECTANCY" in prereg["baselines"]
    assert "WRONG_CURRENCY_ANCHOR_FIXED_ROTATION" in prereg["baselines"]
    assert len(prereg["chronological_folds"]) == 6


def test_source_registry_is_complete_and_never_edge_proof():
    registry = build_source_registry()
    assert len(registry["sources"]) == 4
    required = {
        "source_id", "url", "title", "author_or_organization", "publication_date",
        "access_date", "source_type", "claimed_economic_mechanism",
        "claimed_market_and_timeframe", "exact_disclosed_rules", "claimed_performance",
        "costs_included", "walk_forward_included", "source_code_exists", "license",
        "replication_risks", "aios_dataset_compatibility", "existing_fingerprint_match",
        "research_priority", "final_disposition",
    }
    assert all(required <= set(source) for source in registry["sources"])
    assert all("EDGE_PROOF" not in source["final_disposition"] or "NOT_EDGE_PROOF" in source["final_disposition"] for source in registry["sources"])


def test_canonical_json_is_deterministic_and_rejects_nan():
    assert canonical_bytes({"b": 2, "a": 1}) == canonical_bytes({"a": 1, "b": 2})
    assert json.loads(canonical_bytes({"a": 1})) == {"a": 1}
    with pytest.raises(ValueError):
        canonical_bytes({"bad": float("nan")})


def test_mechanism_hash_is_not_derived_from_candidate_results():
    assert sha256_bytes(canonical_bytes({"fingerprint": MECHANISM_FINGERPRINT}, compact=True)) != MECHANISM_FINGERPRINT
