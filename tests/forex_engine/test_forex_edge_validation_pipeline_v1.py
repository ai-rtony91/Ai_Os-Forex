from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest

from automation.forex_engine import forex_edge_validation_pipeline_v1 as pipeline


REPO_ROOT = Path(__file__).resolve().parents[2]


def spec(name: str = "A", **changes):
    return pipeline._scientific_spec(name, **changes)


def test_capability_denominator_and_promotion_states_are_frozen():
    assert len(pipeline.CAPABILITY_NAMES) == 38
    assert len(set(pipeline.CAPABILITY_NAMES)) == 38
    assert pipeline.PROMOTION_STATES[0] == "EDGE_HYPOTHESIS"
    assert pipeline.PROMOTION_STATES[-1] == "PAPER_VALIDATED_EDGE"
    assert set(pipeline.TRANSITION_VALIDATORS) == set(pipeline.PROMOTION_STATES[:-1])


def test_candidate_fingerprint_ignores_names_and_operational_identity():
    first = spec("ORIGINAL")
    second = spec("RENAMED")
    second.update({"packet_id": "OTHER", "worker": "WEST_OCC_999", "path": "renamed.py"})
    assert pipeline.candidate_fingerprint(first) == pipeline.candidate_fingerprint(second)
    reconciled = pipeline.reconcile_fingerprints([first, second])
    assert reconciled["unique_fingerprints"] == 1
    assert reconciled["duplicate_specifications"] == 1


def test_candidate_fingerprint_changes_only_for_scientific_change():
    first = spec()
    changed = spec(parameters={"threshold": 1.1})
    assert pipeline.candidate_fingerprint(first) != pipeline.candidate_fingerprint(changed)
    incomplete = dict(first)
    del incomplete["cost_contract"]
    with pytest.raises(ValueError, match="FINGERPRINT_FIELDS_MISSING"):
        pipeline.candidate_fingerprint(incomplete)
    with pytest.raises(ValueError, match="FINGERPRINT_COLLISION"):
        pipeline.reconcile_fingerprints([first, changed], digest_function=lambda _value: "forced-collision")


def test_trial_ledger_preserves_lower_bound_proposals_and_schema_read():
    records = pipeline.bootstrap_trial_ledger()
    summary = pipeline.validate_trial_ledger(records)
    assert summary["scored_attempt_lower_bound"] == 1220
    assert summary["proposed_unscored_count"] == 518
    schema = next(row for row in records if row["event_id"] == "PKT_FOREX_039_SCHEMA_INSPECTION")
    assert schema["scored_trial_increment"] == 0


def test_trial_ledger_tamper_nonmonotonic_and_duplicate_fail_closed(tmp_path):
    records = pipeline.bootstrap_trial_ledger()
    tampered = [dict(row) for row in records]
    tampered[1]["proposed_count"] += 1
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        pipeline.validate_trial_ledger(tampered)
    reordered = [dict(row) for row in records]
    reordered[1]["sequence"] = 9
    with pytest.raises(ValueError, match="NON_MONOTONIC"):
        pipeline.validate_trial_ledger(reordered)
    path = tmp_path / "ledger.jsonl"
    pipeline.write_initial_trial_ledger(path)
    with pytest.raises(ValueError, match="DUPLICATE_EVENT"):
        pipeline.append_trial_record(path, {"event_id": records[0]["event_id"], "status": "DUPLICATE", "scored_trial_increment": 0})


def test_trial_ledger_append_increments_once_and_proposal_never_scores(tmp_path):
    path = tmp_path / "ledger.jsonl"
    pipeline.write_initial_trial_ledger(path)
    pipeline.append_trial_record(path, {"event_id": "NEW_CELL", "status": "OUTCOME_EXAMINED", "scored_trial_increment": 1, "proposed_count": 0})
    assert pipeline.validate_trial_ledger(pipeline.read_trial_ledger(path))["scored_attempt_lower_bound"] == 1221
    with pytest.raises(ValueError, match="INVALID_TRIAL_INCREMENT"):
        pipeline.append_trial_record(path, {"event_id": "BAD_PROPOSAL", "status": "PROPOSED_UNSCORED", "scored_trial_increment": 1})


def test_true_dsr_is_deterministic_exposes_inputs_and_passes_strong_signal():
    returns = [0.020 + (index % 5 - 2) * 0.001 for index in range(120)]
    args = dict(effective_trial_count=1220, effective_sample_count=120)
    trials = [(index % 9 - 4) * 0.01 for index in range(45)]
    first = pipeline.deflated_sharpe_ratio(returns, trials, **args)
    second = pipeline.deflated_sharpe_ratio(returns, trials, **args)
    assert first == second
    assert first["status"] == "PASS"
    assert first["effective_trial_count"] == 1220
    assert first["effective_sample_count"] == 120
    assert {"skewness", "kurtosis", "selection_threshold_sharpe", "deflated_sharpe_probability"} <= set(first)


def test_dsr_reference_value_matches_frozen_calculation():
    result = pipeline.deflated_sharpe_from_moments(
        observed_sharpe=.7, trial_sharpe_mean=0, trial_sharpe_std=.25,
        effective_trial_count=100, effective_sample_count=252,
        skewness=-.5, pearson_kurtosis=5,
    )
    assert result["expected_maximum_sharpe"] == pytest.approx(.6326507233004212, abs=1e-15)
    assert result["non_normal_denominator"] == pytest.approx(1.3564659966250536, abs=1e-15)
    assert result["z_statistic"] == pytest.approx(.7866125755763924, abs=1e-15)
    assert result["deflated_sharpe_probability"] == pytest.approx(.7842456523132917, abs=1e-15)


def test_dsr_missing_context_fails_closed():
    returns = [0.01, 0.02, 0.03] * 20
    trials = [(index % 7 - 3) * .01 for index in range(35)]
    assert pipeline.deflated_sharpe_ratio(returns, trials, effective_trial_count=1)["reason"] == "INSUFFICIENT_EVIDENCE"
    assert pipeline.deflated_sharpe_ratio(returns, trials, effective_trial_count=1220, effective_sample_count=10)["reason"] == "INSUFFICIENT_EVIDENCE"
    assert pipeline.deflated_sharpe_ratio(returns, trials, effective_trial_count=1220, candidate_registered=False)["reason"] == "CANDIDATE_ABSENT_FROM_TRIAL_REGISTRY"
    assert pipeline.deflated_sharpe_ratio(returns, trials, effective_trial_count=1220, trial_distribution_reconciled=False)["reason"] == "UNRECONCILED_TRIAL_SHARPE_DISTRIBUTION"


def test_genuine_cscv_pbo_stable_signal_and_duplicate_collapse():
    matrix = [[0.03 + (row % 3) * 0.001, 0.005 * math.sin(row), -0.01, 0.03 + (row % 3) * 0.001] for row in range(64)]
    result = pipeline.cscv_pbo(matrix, ["STABLE", "NOISE", "WEAK", "RENAMED_STABLE"], subset_count=8)
    assert result["status"] == "PASS"
    assert result["duplicate_configuration_count"] == 1
    assert result["split_count"] == 35


def test_cscv_pbo_insufficient_or_misaligned_blocks():
    assert pipeline.cscv_pbo([[1.0], [2.0]], ["A"])["status"] == "BLOCK"
    assert pipeline.cscv_pbo([[1.0, 2.0], [3.0]], ["A", "B"])["status"] == "BLOCK"
    matrix = [[float(row), -float(row)] for row in range(32)]
    assert pipeline.cscv_pbo(matrix, ["A", "B"], subset_count=4, synchronized=False)["status"] == "BLOCK"
    assert pipeline.cscv_pbo(matrix, ["A", "B"], subset_count=4, labels_purged=False)["status"] == "BLOCK"


def test_multiple_testing_uses_global_history_and_blocks_reset():
    assert pipeline.holm_bonferroni([0.000001], 1220)["status"] == "PASS"
    blocked = pipeline.holm_bonferroni([0.000001], 72)
    assert blocked["status"] == "BLOCK"
    assert blocked["reason"] == "UNRECONCILED_MULTIPLE_TESTING_CONTEXT"


def synchronized_rows(count=120, effect=0.01):
    return [{"timestamp": f"T{index:04d}", "pair_returns": {"EUR_USD": effect + (index % 3) * 0.0001, "GBP_USD": effect + (index % 5) * 0.0001}} for index in range(count)]


def test_dependence_aware_bootstrap_is_synchronized_deterministic_and_overlap_aware():
    first = pipeline.synchronized_block_bootstrap(synchronized_rows(), block_size=4, label_horizon=4, runs=200)
    second = pipeline.synchronized_block_bootstrap(synchronized_rows(), block_size=4, label_horizon=4, runs=200)
    assert first == second
    assert first["status"] == "PASS"
    assert first["cross_pair_resampling"] == "SYNCHRONIZED"
    assert first["effective_blocks"] == 30
    assert pipeline.validate_resampling_contract("IID", synchronized_columns=False, block_size=4, label_horizon=4)["status"] == "BLOCK"
    assert pipeline.validate_resampling_contract("SYNCHRONIZED_MOVING_BLOCK", synchronized_columns=True, block_size=3, label_horizon=4)["status"] == "BLOCK"


def test_bootstrap_blocks_unstable_membership_and_insufficient_effective_blocks():
    rows = synchronized_rows()
    rows[-1] = {"timestamp": "T0119", "pair_returns": {"EUR_USD": 0.01}}
    assert pipeline.synchronized_block_bootstrap(rows, block_size=4, label_horizon=4, runs=100)["status"] == "BLOCK"
    assert pipeline.synchronized_block_bootstrap(synchronized_rows(20), block_size=4, label_horizon=4, runs=100)["status"] == "BLOCK"


def test_walk_forward_folds_are_chronological_embargoed_and_train_selected():
    from datetime import datetime, timedelta, timezone

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    timestamps = [(start + timedelta(minutes=5 * i)).isoformat().replace("+00:00", "Z") for i in range(120)]
    folds = pipeline.chronological_folds(timestamps, fold_count=4, embargo_observations=4, minimum_train=40, minimum_test=10)
    assert len(folds) == 4
    assert all(fold["train_end"] < fold["embargo_start"] <= fold["embargo_end"] < fold["test_start"] for fold in folds)
    results = [{"selected_using": "TRAIN_ONLY", "test_count": fold["test_count"], "test_expectancy": 0.01} for fold in folds]
    assert pipeline.validate_walk_forward(folds, results)["status"] == "PASS"
    results[0]["selected_using"] = "TEST_FOLD"
    assert pipeline.validate_walk_forward(folds, results)["status"] == "BLOCK"
    fold = folds[0]
    train_end = datetime.fromisoformat(fold["train_end"].replace("Z", "+00:00"))
    test_start = datetime.fromisoformat(fold["test_start"].replace("Z", "+00:00"))
    labels = [
        {"partition": "TRAIN", "start": (train_end - timedelta(minutes=10)).isoformat(), "end": train_end.isoformat()},
        {"partition": "TRAIN", "start": (train_end - timedelta(minutes=5)).isoformat(), "end": (train_end + timedelta(minutes=5)).isoformat()},
        {"partition": "TEST", "start": test_start.isoformat(), "end": (test_start + timedelta(minutes=5)).isoformat()},
    ]
    label_audit = pipeline.validate_fold_labels(fold, labels)
    assert label_audit["status"] == "PASS"
    assert label_audit["purged_train_crossers"] == 1


def test_parameter_plateau_and_needle_are_distinguished():
    adjacency = {"P2": ["P1", "P3", "P4", "P5"]}
    assert pipeline.parameter_neighborhood("P2", {"P1": .8, "P2": 1.0, "P3": .7, "P4": .6, "P5": .9}, adjacency)["status"] == "ROBUST_PLATEAU"
    assert pipeline.parameter_neighborhood("P2", {"P1": -.1, "P2": 1.0, "P3": 0, "P4": -.2, "P5": .1}, adjacency)["status"] == "FRAGILE"


def broad_robustness_records():
    records = []
    for index in range(32):
        records.append({"pnl": 1.0 + (index % 3) * .1, "pair": f"P{index%4}", "currency": f"C{index%4}", "period": f"T{index%4}", "volatility": f"V{index%2}", "liquidity": f"L{index%2}", "session": f"S{index%2}", "direction": f"D{index%2}"})
    return records


def test_regime_pair_currency_period_and_direction_robustness():
    result = pipeline.robustness_diagnostics(broad_robustness_records())
    assert result["status"] == "PASS"
    assert set(result["removal_tests"]) == {"pair", "currency", "period"}
    concentrated = [dict(row, pair="ONLY") for row in broad_robustness_records()]
    assert pipeline.robustness_diagnostics(concentrated)["status"] == "FAIL"


def test_cost_pipeline_uses_side_correct_quotes_once_and_blocks_financing():
    entry = pipeline.Quote("T0", 1.0, 1.0002)
    exit_quote = pipeline.Quote("T1", 1.0010, 1.0012)
    long_result = pipeline.costed_trade("LONG", [entry], [exit_quote], scenario=pipeline.COST_SCENARIOS["BASE"])
    short_result = pipeline.costed_trade("SHORT", [exit_quote], [entry], scenario=pipeline.COST_SCENARIOS["BASE"])
    assert long_result["entry"] == pytest.approx(1.00021)
    assert long_result["exit"] == pytest.approx(1.00099)
    assert short_result["entry"] == pytest.approx(1.00099)
    assert short_result["exit"] == pytest.approx(1.00021)
    assert pipeline.costed_trade("LONG", [entry], [exit_quote], scenario=pipeline.COST_SCENARIOS["BASE"], explicit_spread_charge=.0002)["status"] == "BLOCK"
    assert pipeline.costed_trade("LONG", [entry], [exit_quote], scenario=pipeline.COST_SCENARIOS["BASE"], rollover_boundaries=1)["reason"] == "UNSUPPORTED_FINANCING_HORIZON"


def test_cost_stress_detects_cost_destroyed_and_cost_fragile_edges():
    destroyed = pipeline.cost_stress({"GROSS": [1], "BASE": [-.1], "STRESSED": [-.2], "SEVERE_BUT_PLAUSIBLE": [-.3]})
    fragile = pipeline.cost_stress({"GROSS": [1], "BASE": [.4], "STRESSED": [.1], "SEVERE_BUT_PLAUSIBLE": [-.1]})
    assert destroyed["reason"] == "COST_DESTROYED_EDGE"
    assert fragile["reason"] == "COST_FRAGILE"


def test_stop_slippage_is_adverse_and_delay_unavailable_blocks():
    entry = pipeline.Quote("T0", 1.0, 1.0002)
    gap = pipeline.Quote("T1", .9980, .9982)
    result = pipeline.costed_trade("LONG", [entry], [gap], scenario=pipeline.COST_SCENARIOS["BASE"], stopped=True, stop_price=.9990)
    assert result["exit"] == pytest.approx(.99798)
    assert pipeline.costed_trade("LONG", [entry], [gap], scenario=pipeline.COST_SCENARIOS["STRESSED"])["status"] == "BLOCK"


def test_pair_and_signal_correlation_effective_bets():
    independent = pipeline.correlation_matrix({"A": [1, -1, 1, -1], "B": [1, 1, -1, -1]})
    assert independent["status"] == "PASS"
    assert independent["effective_independent_bets"] == pytest.approx(2.0)
    duplicate = pipeline.correlation_matrix({"A": [1, 2, 3, 4], "B": [1, 2, 3, 4]})
    assert duplicate["effective_independent_bets"] == pytest.approx(1.0)


def test_realizable_synchronized_portfolio_and_concentration():
    healthy = pipeline.simulate_portfolio(pipeline._portfolio_fixture(), maximum_currency_gross=.02)
    assert healthy["status"] == "PASS"
    assert healthy["maximum_drawdown_fraction"] == 0
    assert healthy["effective_independent_bets"] > 1
    concentrated = pipeline.simulate_portfolio(pipeline._portfolio_fixture(concentrated=True), maximum_currency_gross=.02)
    assert concentrated["status"] == "FAIL"
    assert "PAIR_CONCENTRATION" in concentrated["reasons"]
    shared = pipeline.simulate_portfolio(pipeline._portfolio_fixture(shared_currency=True), maximum_currency_gross=.004)
    assert shared["status"] == "FAIL"
    assert shared["reason"] == "CURRENCY_GROSS_EXPOSURE_LIMIT"


def test_mark_to_market_portfolio_tracks_overlapping_positions_and_closure():
    healthy = pipeline.simulate_synchronized_portfolio_snapshots(pipeline._snapshot_fixture(), maximum_currency_gross=.02)
    assert healthy["status"] == "PASS"
    assert healthy["maximum_simultaneous_positions"] == 3
    assert len(healthy["equity_curve"]) == 5
    concentrated = pipeline.simulate_synchronized_portfolio_snapshots(pipeline._snapshot_fixture(concentrated=True), maximum_currency_gross=.02)
    assert concentrated["status"] == "FAIL"
    assert "PAIR_CONCENTRATION" in concentrated["reasons"]
    missing_close = pipeline._snapshot_fixture()
    missing_close[-1]["positions"] = missing_close[-1]["positions"][:-1]
    assert pipeline.simulate_synchronized_portfolio_snapshots(missing_close, maximum_currency_gross=.02)["status"] == "BLOCK"


def test_lineage_requires_complete_acyclic_declared_graph():
    assert pipeline.validate_lineage(pipeline._lineage())["status"] == "PASS"
    missing = pipeline._lineage()
    missing[-1]["parents"] = ["unknown"]
    assert pipeline.validate_lineage(missing)["reason"] == "LINEAGE_PARENT_MISSING"
    alias = pipeline._lineage() + [{"artifact_id": "copy", "content_sha256": "b" * 64, "kind": "FEATURE", "partition": "DEVELOPMENT", "min_timestamp": "2024-01-01T00:00:00Z", "max_timestamp": "2024-01-01T00:10:00Z", "parents": ["source"], "transform_fingerprint": "COPY"}]
    assert pipeline.validate_lineage(alias)["reason"] == "UNDECLARED_CONTENT_ALIAS"


def test_access_enforcement_preserves_reused_and_contaminated_truth():
    request, manifest = pipeline._access_fixture("DEVELOPMENT", "AUTHORIZED_DEVELOPMENT")
    assert pipeline.access_decision(request, manifest, pipeline._lineage())["status"] == "PASS"
    request, manifest = pipeline._access_fixture("VALIDATION", "REUSED")
    assert pipeline.access_decision(request, manifest, pipeline._lineage("VALIDATION"))["status"] == "BLOCK"
    request, manifest = pipeline._access_fixture("FINAL_HOLDOUT", "CONTAMINATED", start="2026-08-29T03:55:00Z", end="2026-08-30T03:55:00Z", sealed=True)
    assert pipeline.access_decision(request, manifest, pipeline._lineage("FINAL_HOLDOUT"))["status"] == "BLOCK"


def test_new_holdout_machinery_is_strictly_after_boundary_and_single_use():
    request, manifest = pipeline._access_fixture("FINAL_HOLDOUT", "PROVEN_UNTOUCHED", start="2026-08-29T03:50:00Z", end="2026-08-30T03:50:00Z", sealed=True)
    assert pipeline.access_decision(request, manifest, pipeline._lineage("FINAL_HOLDOUT"))["status"] == "BLOCK"
    request, manifest = pipeline._access_fixture("FINAL_HOLDOUT", "PROVEN_UNTOUCHED", start="2026-08-29T03:55:00Z", end="2026-08-30T03:55:00Z", sealed=True)
    assert pipeline.access_decision(request, manifest, pipeline._lineage("FINAL_HOLDOUT"))["status"] == "PASS"
    manifest["access_count"] = 1
    manifest["spent"] = True
    assert pipeline.access_decision(request, manifest, pipeline._lineage("FINAL_HOLDOUT"))["reason"] == "HOLDOUT_ALREADY_SPENT"


def test_holdout_claim_is_authorized_spent_before_read_and_single_use(tmp_path):
    request, manifest = pipeline._access_fixture("FINAL_HOLDOUT", "PROVEN_UNTOUCHED", start="2026-08-29T03:55:00Z", end="2026-08-30T03:55:00Z", sealed=True)
    path = tmp_path / "guard.json"
    pipeline.initialize_holdout_guard(path, manifest, request["authorization_sha256"])
    first = pipeline.claim_holdout_access(path, request, pipeline._lineage("FINAL_HOLDOUT"))
    assert first["status"] == "PASS"
    assert first["spent"] is first["access_log_record"]["spent_before_reader"] is True
    second = pipeline.claim_holdout_access(path, request, pipeline._lineage("FINAL_HOLDOUT"))
    assert second["status"] == "BLOCK"
    assert second["reason"] == "HOLDOUT_ALREADY_SPENT"


def test_future_data_and_partition_boundaries_fail_closed():
    good = pipeline.validate_half_open_information(partition_start="2024-01-01T00:00:00Z", partition_end="2024-02-01T00:00:00Z", feature_max="2024-01-02T00:00:00Z", signal_time="2024-01-02T00:05:00Z", entry_time="2024-01-02T00:10:00Z", label_end="2024-01-02T00:30:00Z")
    assert good["status"] == "PASS"
    bad = pipeline.validate_half_open_information(partition_start="2024-01-01T00:00:00Z", partition_end="2024-02-01T00:00:00Z", feature_max="2024-01-02T00:06:00Z", signal_time="2024-01-02T00:05:00Z", entry_time="2024-01-02T00:10:00Z", label_end="2024-01-02T00:30:00Z")
    assert bad["status"] == "BLOCK"


def test_promotion_engine_never_skips_and_missing_or_contaminated_blocks():
    results = pipeline._all_pass_results()
    first = pipeline.evaluate_transition("EDGE_HYPOTHESIS", results)
    assert first["next_state"] == "MECHANISM_OBSERVED"
    missing = dict(results)
    del missing["future_leakage"]
    assert pipeline.evaluate_transition("EDGE_HYPOTHESIS", missing)["status"] == "BLOCK"
    contaminated = dict(results)
    contaminated["validation_provenance"] = pipeline.validator_result("CONTAMINATED")
    decision = pipeline.evaluate_transition("ROBUSTNESS_SURVIVOR", contaminated)
    assert decision["status"] == "BLOCK"
    assert pipeline.promotion_reference()["synthetic_terminal_state"] == "PAPER_VALIDATED_EDGE"


def test_candidate_receipt_preserves_identity_context_sections_and_blocks():
    results = pipeline._all_pass_results()
    results["validation_provenance"] = pipeline.validator_result("CONTAMINATED")
    receipt = pipeline.evaluate_candidate_receipt(spec(), {"scored": 1220}, {"validation": "REUSED"}, results)
    assert receipt["candidate_fingerprint"] == pipeline.candidate_fingerprint(spec("RENAMED"))
    assert receipt["promotion_state"] == "ROBUSTNESS_SURVIVOR"
    assert receipt["block_reasons"]
    assert {"cost_results", "uncertainty_results", "overfitting_results", "robustness_results", "portfolio_results"} <= set(receipt)


def test_adversarial_harness_passes_all_24_frozen_cases():
    result = pipeline.adversarial_synthetic_harness()
    assert result["status"] == "PASS"
    assert result["passed"] == result["total"] == 24
    assert all(case["passed"] for case in result["cases"])


def test_scientific_bundle_certifies_exactly_38_and_preserves_truth():
    artifacts = pipeline.build_scientific_artifacts()
    registry = json.loads(artifacts["AIOS_FOREX_VALIDATION_CAPABILITY_REGISTRY_V1.json"])
    receipt = json.loads(artifacts["AIOS_FOREX_VALIDATION_CERTIFICATION_RECEIPT.json"])
    assert registry["required_capabilities"] == registry["certified_capabilities"] == 38
    assert registry["blocked_capabilities"] == 0
    assert registry["readiness_percent"] == 100.0
    assert all(row["certified"] for row in registry["capabilities"])
    assert receipt["validation_information_provenance"] == "REUSED"
    assert receipt["holdout_information_provenance"] == "CONTAMINATED"
    assert receipt["new_market_rows_opened"] == receipt["new_scored_trial_increment"] == 0
    runtime = pipeline.runtime_payloads(artifacts)
    promotion = [json.loads(line) for line in runtime["AIOS_FOREX_PROMOTION_LEDGER_V1.jsonl"].decode("ascii").splitlines()]
    holdout = [json.loads(line) for line in runtime["AIOS_FOREX_HOLDOUT_PROVENANCE_LEDGER_V1.jsonl"].decode("ascii").splitlines()]
    assert pipeline.validate_hash_chain(promotion)["status"] == "PASS"
    assert pipeline.validate_hash_chain(holdout)["status"] == "PASS"


def test_two_isolated_runs_are_byte_identical_and_runtime_complete(tmp_path):
    first, second = tmp_path / "run1", tmp_path / "run2"
    result1 = pipeline.write_certification(first / "science", first / "runtime")
    result2 = pipeline.write_certification(second / "science", second / "runtime")
    comparison = pipeline.compare_certifications(first / "science", second / "science")
    assert result1["aggregate_sha256"] == result2["aggregate_sha256"]
    assert comparison["status"] == "PASS" and comparison["byte_identical"] is True
    assert {path.name for path in (first / "runtime").iterdir()} == {
        "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl",
        "AIOS_FOREX_FINGERPRINT_INDEX_V1.json",
        "AIOS_FOREX_VALIDATION_CAPABILITY_REGISTRY_V1.json",
        "AIOS_FOREX_PROMOTION_LEDGER_V1.jsonl",
        "AIOS_FOREX_HOLDOUT_PROVENANCE_LEDGER_V1.jsonl",
    }
    with pytest.raises(ValueError, match="OUTPUT_COLLISION"):
        pipeline.write_certification(first / "science", tmp_path / "other")
    promoted = pipeline.promote_runtime(first / "runtime", tmp_path / "canonical_runtime")
    assert promoted["status"] == "PASS" and promoted["artifact_count"] == 5
    # A validated replacement is allowed and remains byte-identical.
    assert pipeline.promote_runtime(second / "runtime", tmp_path / "canonical_runtime") == promoted | {"runtime_root": str(tmp_path / "canonical_runtime")}


def test_source_is_synthetic_only_and_has_no_market_or_broker_reader():
    source_path = REPO_ROOT / "automation/forex_engine/forex_edge_validation_pipeline_v1.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert not ({"requests", "oandapyV20", "pandas", "numpy"} & imports)
    lowered = source_path.read_text(encoding="utf-8").lower()
    for forbidden in ("place_order(", "create_order(", "practice_api", "live_api", "market_data_root"):
        assert forbidden not in lowered


def test_pkt039_frozen_hashes_remain_exact():
    expected = {
        "automation/orchestration/work_packets/active/PKT-FOREX-039.md": "69517621a5b1875d86c5490863f7bb6099942c6ba6e9e812bd647e03ec64944d",
        "automation/forex_engine/forex_edge_discovery_tournament_stage1_v1.py": "37cf2662b8a169fa7a8a13647d1c19e39ebe16261cea3d26161ee1c986fc39c5",
        "scripts/forex_delivery/run_forex_edge_discovery_tournament_stage1_v1.py": "4832af379e30ab3525c208f197704069e8fe32abe3ddfad02adb5480aea940ab",
        "tests/forex_engine/test_forex_edge_discovery_tournament_stage1_v1.py": "19c1052bb3713217fe9d0c4490bec0d2e9ff656a63f250ccfde1868bde4c43f2",
        ".aios/staging/PKT_FOREX_042/final_run1/AIOS_FOREX_PKT039_CORRECTIVE_MANIFEST.json": "9df195ac79f68671b99e54293874974b88fb3574cb681e1c58f7822358c3b191",
        ".aios/staging/PKT_FOREX_042/final_run2/AIOS_FOREX_PKT039_CORRECTIVE_MANIFEST.json": "9df195ac79f68671b99e54293874974b88fb3574cb681e1c58f7822358c3b191",
    }
    for relative, digest in expected.items():
        assert pipeline.sha256_file(REPO_ROOT / relative) == digest
