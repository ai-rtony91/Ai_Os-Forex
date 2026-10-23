import hashlib
import json

from automation.forex_engine.forex_abnormal_price_update_response_stage0_v1 import (
    DEVELOPMENT_END,
    build_preregistration,
    build_sources,
    canonical_bytes,
    partition_is_development,
    robust_history_observation,
)


def test_canonical_bytes_are_stable_and_newline_terminated():
    assert canonical_bytes({"b": 2, "a": 1}) == b'{\n  "a": 1,\n  "b": 2\n}\n'


def test_partition_gate_excludes_validation_boundary():
    assert partition_is_development({
        "start_utc": "2025-03-01T00:00:00Z",
        "end_utc": DEVELOPMENT_END,
        "path": "partitions/EUR_USD/2025-03.jsonl.gz",
    })
    assert not partition_is_development({
        "start_utc": DEVELOPMENT_END,
        "end_utc": "2025-05-01T00:00:00Z",
        "path": "partitions/EUR_USD/2025-04.jsonl.gz",
    })


def test_robust_history_scale_is_zero_for_constant_series():
    center, scale = robust_history_observation([1.0] * 8)
    assert center == 1.0
    assert scale == 0.0


def test_robust_history_uses_median_and_mad():
    center, scale = robust_history_observation([0, 1, 2, 3, 4, 5, 6, 100])
    assert center == 3.5
    assert scale == 2.9652


def test_provider_source_forbids_transaction_volume_equivalence():
    sources = build_sources()
    assert sources["provider_field_name"] == "OANDA_PRICE_UPDATE_COUNT_PROXY"
    assert "TRANSACTION_VOLUME" in sources["prohibited_names"]
    assert sources["status"].startswith("PASS")


def test_preregistration_freezes_exact_eight_candidates():
    registration = build_preregistration(["EUR_USD", "USD_JPY"])
    assert registration["parameter_grid"]["candidate_count"] == 8
    assert len(registration["candidates"]) == 8
    assert len({item["candidate_fingerprint"] for item in registration["candidates"]}) == 8


def test_preregistration_enforces_no_trade_baseline_and_positive_net():
    registration = build_preregistration(["EUR_USD"])
    assert "NO_TRADE_ZERO_EXPECTANCY" in registration["baselines"]
    assert registration["stage1_rejection_gates"]["after_cost_expectancy_must_exceed_zero"] is True
    assert registration["stage2_promotion_gates"]["after_cost_expectancy_must_exceed_zero"] is True


def test_family_fingerprint_reproduces_from_canonical_payload():
    first = build_preregistration(["EUR_USD"])
    second = build_preregistration(["EUR_USD"])
    assert first["strategy_mechanism_fingerprint"] == second["strategy_mechanism_fingerprint"]
    assert len(first["strategy_mechanism_fingerprint"]) == hashlib.sha256().digest_size * 2


def test_preregistration_is_json_serializable():
    json.dumps(build_preregistration(["EUR_USD"]), sort_keys=True)
