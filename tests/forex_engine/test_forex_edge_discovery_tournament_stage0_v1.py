from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from automation.forex_engine import forex_edge_discovery_tournament_stage0_v1 as tournament
from scripts.forex_delivery.run_forex_edge_discovery_tournament_stage0_v1 import REJECTION_INPUTS, run


REPO_ROOT = Path(__file__).resolve().parents[2]


def _obs(pair: str, value: float, lineage: str) -> dict[str, object]:
    return {"pair": pair, "log_return": value, "timestamp": "2024-01-02T00:00:00Z", "lineage": lineage, "native": True}


def test_edge_cards_are_complete_ranked_and_not_claimed_as_edges() -> None:
    cards = tournament.edge_cards()
    required = {"EDGE_ID", "HYPOTHESIS", "ECONOMIC_OR_BEHAVIORAL_RATIONALE", "PRIMARY_SIGNAL", "REGIME_CONDITIONS", "EXPECTED_HOLDING_HORIZON", "EXPECTED_FAILURE_REGIMES", "PAIR_UNIVERSE", "TIMEFRAME", "ENTRY_MECHANISM", "INVALIDATION_MECHANISM", "EXIT_FAMILY", "COST_MODEL", "PORTFOLIO_EXPOSURE_MODEL", "PARAMETER_FAMILY", "PRE_REGISTERED_VARIANTS", "TRIAL_COUNT_INCREMENT_RULE", "FALSIFICATION_CRITERIA", "PROMOTION_CRITERIA", "EDGE_FINGERPRINT"}
    assert len(cards) == 10
    assert [card["PRIORITY"] for card in cards] == list(range(1, 11))
    assert all(required <= card.keys() for card in cards)
    assert cards[0]["EDGE_ID"] == "CROSS_SECTIONAL_CURRENCY_MOMENTUM"
    assert cards[-1]["EDGE_ID"] == "ROUND_NUMBER_CONDITIONAL_ORDER_STATE"


def test_first_wave_is_exactly_36_primary_plus_36_inverse() -> None:
    manifest = tournament.first_wave_manifest()
    assert manifest["primary_cell_count"] == 36
    assert manifest["inverse_diagnostic_cell_count"] == 36
    assert len(manifest["cells"]) == 72
    assert len({row["candidate_fingerprint"] for row in manifest["cells"]}) == 72
    assert {row["arm"] for row in manifest["cells"]} == {"A", "B", "C", "D"}
    assert {row["formation_lookback_m5"] for row in manifest["cells"]} == {12, 48, 288}
    assert {row["forward_horizon_m5"] for row in manifest["cells"]} == {3, 12, 48}
    assert all(row["status"] == "PROPOSED_UNSCORED" for row in manifest["cells"])
    assert manifest["new_outcome_scored_trials"] == 0


def test_source_map_separates_findings_adaptations_and_choices() -> None:
    rows = tournament.source_experiment_map()["sources"]
    assert len(rows) == 5
    assert all({"published_finding", "aios_adaptation", "untested_design_choices", "instrument_universe", "sampling_frequency", "formation_horizon", "holding_horizon", "execution_assumptions", "limitations"} <= row.keys() for row in rows)
    bis = next(row for row in rows if row["source_id"] == "BIS_WORK366_CURRENCY_MOMENTUM")
    assert bis["sampling_frequency"] == "MONTHLY"
    assert "intraday edge" in bis["limitations"][0]


def test_future_data_invariance_for_normalized_momentum() -> None:
    closes = [100.0 * math_factor(index) for index in range(340)]
    baseline = tournament.normalized_momentum(closes, 320, 48)
    changed = list(closes)
    changed[321:] = [value * 4 for value in changed[321:]]
    assert tournament.normalized_momentum(changed, 320, 48) == pytest.approx(baseline)


def math_factor(index: int) -> float:
    return 1.0 + 0.0002 * index + 0.00003 * ((index % 7) - 3)


def test_normalized_momentum_rejects_missing_and_zero_volatility() -> None:
    closes = [100.0 + index * 0.01 for index in range(330)]
    closes[300] = None
    with pytest.raises(ValueError, match="MISSING_OR_INVALID_CLOSE"):
        tournament.normalized_momentum(closes, 320, 12)
    with pytest.raises(ValueError, match="ZERO_OR_INVALID_VOLATILITY"):
        tournament.normalized_momentum([100.0] * 330, 320, 12)


def test_quote_inversion_preserves_currency_strength_solution() -> None:
    direct = tournament.fit_currency_strength([_obs("EUR_USD", 0.01, "a"), _obs("GBP_USD", 0.02, "b"), _obs("EUR_GBP", -0.01, "c")])
    inverse = tournament.fit_currency_strength([_obs("USD_EUR", -0.01, "ia"), _obs("USD_GBP", -0.02, "ib"), _obs("GBP_EUR", 0.01, "ic")])
    assert inverse["strengths"] == pytest.approx(direct["strengths"])
    assert direct["maximum_independent_currency_coordinates"] == 2
    assert direct["sum_constraint"] == pytest.approx(0.0, abs=1e-12)


def test_graph_disconnection_fails_closed() -> None:
    with pytest.raises(ValueError, match="DISCONNECTED_CURRENCY_GRAPH"):
        tournament.fit_currency_strength([_obs("EUR_USD", 0.01, "a"), _obs("GBP_JPY", 0.02, "b")])


def test_duplicate_synthetic_lineage_and_pair_orientation_fail_closed() -> None:
    with pytest.raises(ValueError, match="DUPLICATE_SYNTHETIC_LINEAGE"):
        tournament.fit_currency_strength([_obs("EUR_USD", 0.01, "same"), _obs("GBP_USD", 0.02, "same")])
    with pytest.raises(ValueError, match="DUPLICATE_PAIR_ORIENTATION"):
        tournament.fit_currency_strength([_obs("EUR_USD", 0.01, "a"), _obs("USD_EUR", -0.01, "b")])


def test_target_pair_lineage_change_cannot_fabricate_confirmation() -> None:
    observations = [_obs("EUR_USD", 0.01, "a"), _obs("GBP_USD", 0.02, "b"), _obs("EUR_GBP", -0.01, "c")]
    diagnostic = tournament.leave_target_pair_out(observations, "EUR_GBP")
    altered = [dict(row) for row in observations]
    altered[2]["log_return"] = 99.0
    altered_diagnostic = tournament.leave_target_pair_out(altered, "EUR_GBP")
    assert diagnostic["strengths"] == pytest.approx(altered_diagnostic["strengths"])
    assert "NOT_PROOF_OF_INDEPENDENCE" in diagnostic["diagnostic"]


def test_partition_boundaries_are_half_open_and_context_is_completed() -> None:
    args = dict(partition=tournament.M5_DEVELOPMENT, feature_times=["2024-01-02T00:00:00Z"], signal_time="2024-01-02T00:05:00Z", entry_time="2024-01-02T00:10:00Z", exit_time="2024-01-02T00:25:00Z", label_end_time="2024-01-02T00:25:00Z", context_close_time="2024-01-02T00:00:00Z")
    assert tournament.validate_half_open_event(**args)
    with pytest.raises(ValueError, match="PARTITION_BOUNDARY_CROSSING"):
        tournament.validate_half_open_event(**{**args, "exit_time": tournament.M5_DEVELOPMENT[1]})
    with pytest.raises(ValueError, match="HIGHER_TIMEFRAME_NOT_COMPLETED"):
        tournament.validate_half_open_event(**{**args, "context_close_time": "2024-01-02T00:10:00Z"})


def test_pullback_expiry_and_anchor_freeze() -> None:
    closes = [100.0, 100.1, 100.2, 101.0] + [101.1] * 13 + [101.2]
    result = tournament.pullback_state_machine(closes, pair="EUR_USD", direction="LONG", impulse_index=3, lookback=3)
    assert result["terminal_state"] == "EXPIRED"
    assert result["anchor"] == 100.0 and result["endpoint"] == 101.0


def test_deterministic_resumption_and_entry() -> None:
    closes = [100.0, 100.1, 100.2, 101.0, 100.7, 100.65, 100.8, 100.85]
    first = tournament.pullback_state_machine(closes, pair="EUR_USD", direction="LONG", impulse_index=3, lookback=3)
    second = tournament.pullback_state_machine(closes, pair="EUR_USD", direction="LONG", impulse_index=3, lookback=3)
    assert first == second
    assert first["terminal_state"] == "ENTRY_ELIGIBLE"
    assert first["trigger_index"] == 6 and first["entry_index"] == 7
    assert first["states"][-3:] == ["PULLBACK_QUALIFIED", "RESUMPTION_CONFIRMED", "ENTRY_ELIGIBLE"]


def test_event_duplication_is_rejected() -> None:
    with pytest.raises(ValueError, match="DUPLICATE_EVENT_ID"):
        tournament.reject_duplicate_event_ids(["a", "a"])
    assert tournament.reject_duplicate_event_ids(["a", "b"])


def test_forbidden_outcome_file_access_guard() -> None:
    tournament.assert_metadata_only_paths([".aios/runtime/x/manifest.json", "Reports/x_STATE.json"])
    for path in (".aios/runtime/x/partitions/p.jsonl.gz", ".aios/runtime/forex_feature_edge_research_v2/currency_factor_table.json", ".aios/runtime/x/opportunity_surface.json"):
        with pytest.raises(PermissionError, match="FORBIDDEN_OUTCOME_FILE_ACCESS"):
            tournament.assert_metadata_only_paths([path])


def test_cost_and_entry_exit_contracts_are_fail_closed() -> None:
    costs = tournament.cost_exposure_contract()
    assert costs["fills"] == {"LONG": "ASK_ENTRY_TO_BID_EXIT", "SHORT": "BID_ENTRY_TO_ASK_EXIT", "spread": "EMBEDDED_ONCE_IN_SIDE_CORRECT_FILLS_NEVER_SUBTRACTED_AGAIN"}
    assert costs["cost_states"]["SEVERE_BUT_PLAUSIBLE"]["status"].startswith("FROZEN_RESEARCH_ASSUMPTION")
    assert "MISSING_IS_NOT_ZERO" in costs["financing"]
    exits = tournament.entry_exit_contract()
    assert exits["launch_authorized"] is False
    assert exits["same_candle_stop_and_target"].startswith("CONSERVATIVE_STOP_FIRST")


def test_statistics_do_not_claim_missing_dsr_or_cscv() -> None:
    contract = tournament.statistical_contract()
    assert contract["dsr"]["implementation_status"] == "MISSING_REAL_IMPLEMENTATION"
    assert contract["cscv_pbo"]["implementation_status"] == "MISSING_REAL_CSCV_ONLY_PROXIES_EXIST"
    assert contract["global_trials"]["pre_stage1_lower_bound"] == 1220


def test_information_provenance_is_truthful_and_zero_row() -> None:
    result = tournament.information_provenance(REPO_ROOT)
    assert result["HOLDOUT_INFORMATION_PROVENANCE"] == "CONTAMINATED"
    assert result["VALIDATION_INFORMATION_PROVENANCE"] == "REUSED"
    assert result["repository_wide_access_control_repaired"] is False
    assert result["stage0_rows_opened"] == {"development_price": 0, "validation": 0, "final_holdout": 0}


def test_provenance_opens_only_pinned_metadata(monkeypatch) -> None:
    opened = []
    original = Path.open
    allowed = {(REPO_ROOT / p).resolve() for p in tournament.METADATA_PROVENANCE_HASHES}

    def guarded(path, *args, **kwargs):
        assert path.resolve() in allowed, f"Unexpected content access: {path}"
        opened.append(path.resolve())
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    result = tournament.information_provenance(REPO_ROOT)
    assert set(opened) == allowed
    assert result["protected_content_opened_by_this_check"] is False
    assert result["holdout_evidence"]["feature_campaign_holdout_results"] is None


@pytest.mark.parametrize("path", [
    ".aios/runtime/forex_feature_edge_research_v2/currency_factor_table.json",
    "Reports/forex_delivery/AIOS_FOREX_EDGE_RESEARCH_V1_STATE.json",
    "Reports/forex_delivery/AIOS_FOREX_FEATURE_EDGE_RESEARCH_V2_STATE.json",
])
def test_protected_provenance_rejected_before_any_open(monkeypatch, path) -> None:
    monkeypatch.setattr(tournament, "METADATA_PROVENANCE_HASHES", {path: "0" * 64})
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("Content opened before denial"))
    with pytest.raises(PermissionError, match="FORBIDDEN_OUTCOME_FILE_ACCESS"):
        tournament.information_provenance(REPO_ROOT)


def test_missing_provenance_blocks(tmp_path) -> None:
    with pytest.raises(ValueError, match="PROVENANCE_METADATA_MISSING"):
        tournament.information_provenance(tmp_path)


def test_reviewed_current_source_and_historical_identity(monkeypatch) -> None:
    # Real pinned completion is retained; simulate unexplained current bytes.
    original = tournament.sha256_file
    target = next(iter(tournament.REVIEWED_PKT044_SOURCE_HASHES))
    monkeypatch.setattr(tournament, "sha256_file", lambda p: "0" * 64 if p == REPO_ROOT / target else original(p))
    with pytest.raises(ValueError, match="UNREVIEWED_CURRENT_SOURCE_CHANGED"):
        tournament.research_memory([REPO_ROOT / p for p in REJECTION_INPUTS], REPO_ROOT)


def test_historical_completion_tamper_rejected(monkeypatch) -> None:
    original = tournament.sha256_file
    monkeypatch.setattr(tournament, "sha256_file", lambda p: "0" * 64 if p == REPO_ROOT / tournament.PRIOR_COMPLETION else original(p))
    with pytest.raises(ValueError, match="PKT037_COMPLETION_HASH_MISMATCH"):
        tournament.research_memory([REPO_ROOT / p for p in REJECTION_INPUTS], REPO_ROOT)


def test_memory_preserves_pkt037_and_adds_zero_scored_trials() -> None:
    memory = tournament.research_memory([REPO_ROOT / path for path in REJECTION_INPUTS], REPO_ROOT)
    assert memory["global_attempt_lower_bound_before"] == memory["global_attempt_lower_bound_after_stage0"] == 1220
    assert memory["round_number_proposals_preserved"] == 135
    assert memory["status_classes"]["PROPOSED_UNSCORED"]["prior"] == 446
    assert memory["status_classes"]["PROPOSED_UNSCORED"]["total_spec_records"] == 518
    assert memory["new_outcome_scored_trials"] == 0


def test_source_has_no_network_broker_or_price_loader_imports() -> None:
    source = Path(tournament.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    roots.update(node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert roots.isdisjoint({"requests", "httpx", "urllib", "socket", "oandapyV20", "gzip", "pandas", "polars"})


def test_build_and_runner_are_deterministic_and_isolated(tmp_path: Path) -> None:
    artifacts1 = tournament.build_stage0([REPO_ROOT / path for path in REJECTION_INPUTS], REPO_ROOT)
    artifacts2 = tournament.build_stage0([REPO_ROOT / path for path in REJECTION_INPUTS], REPO_ROOT)
    assert artifacts1 == artifacts2
    receipt = json.loads(artifacts1["AIOS_FOREX_EDGE_TOURNAMENT_RECEIPT.json"])
    assert all(value == "PASS" for value in receipt["acceptance"].values())
    assert receipt["counters"] == {"development_price_rows_opened": 0, "validation_rows_opened": 0, "final_holdout_rows_opened": 0, "new_outcome_scored_trials": 0}
    assert receipt["verified_edge"] is False
    permitted = REPO_ROOT / ".aios/staging/PKT_FOREX_038" / f"pytest_{tmp_path.name}"
    if permitted.exists():
        pytest.skip("packet-scoped isolated test root already exists")
    result = run(permitted)
    assert result["status"] == "PASS" and result["artifact_count"] == len(artifacts1)
    with pytest.raises(FileExistsError, match="OUTPUT_ROOT_ALREADY_EXISTS"):
        run(permitted)
