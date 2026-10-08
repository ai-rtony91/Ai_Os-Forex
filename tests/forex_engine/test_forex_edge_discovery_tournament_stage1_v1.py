from __future__ import annotations

import json
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from automation.forex_engine import forex_edge_discovery_tournament_stage0_v1 as stage0
from automation.forex_engine import forex_edge_discovery_tournament_stage1_v1 as subject
from automation.forex_engine.forex_edge_validation_pipeline_v1 import sha256_value, validate_trial_ledger


REPO_ROOT = Path(__file__).resolve().parents[2]


def bar(moment: datetime, close: float, *, spread: float = 0.0002) -> dict[str, object]:
    half = spread / 2
    side = lambda value: {"o": value, "h": value, "l": value, "c": value}
    return {
        "timestamp": subject.timestamp_text(moment),
        "instrument": "EUR_USD",
        "complete": True,
        "mid": side(close),
        "bid": side(close - half),
        "ask": side(close + half),
    }


def test_frozen_grid_and_runtime_contracts_are_exact() -> None:
    first_wave = stage0.first_wave_manifest()
    snapshot = subject.verify_runtime_contracts(REPO_ROOT, first_wave["cells"], require_pre_score=False)
    assert len(snapshot["cell_identity_mappings"]) == 72
    assert snapshot["pkt040"] == {"required": 38, "certified": 38, "blocked": 0, "readiness_percent": 100.0}
    assert snapshot["pkt041"]["reference_count"] == 7
    current, index, trusted, trusted_index = _canonical_and_trusted_memory()
    assert snapshot["pre_score_trial_memory"] == validate_trial_ledger(current)
    assert snapshot["memory_compatibility"]["validation_mode"] == "TRUSTED_CORRECTED_PREFIX_PLUS_VALIDATED_APPEND_ONLY_TAIL"
    assert snapshot["memory_compatibility"]["later_ledger_records"] == len(current) - len(trusted)
    assert snapshot["memory_compatibility"]["later_fingerprint_entries"] == len(index["entries"]) - len(trusted_index["entries"])


def _canonical_and_trusted_memory() -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]], dict[str, object]]:
    current_ledger = subject.read_trial_ledger(REPO_ROOT / subject.TRIAL_LEDGER_RELATIVE)
    current_index = json.loads((REPO_ROOT / subject.FINGERPRINT_INDEX_RELATIVE).read_text(encoding="utf-8"))
    trusted_ledger = subject.read_trial_ledger(REPO_ROOT / subject.TRUSTED_CORRECTED_LEDGER_RELATIVE)
    trusted_index = json.loads((REPO_ROOT / subject.TRUSTED_CORRECTED_FINGERPRINT_INDEX_RELATIVE).read_text(encoding="utf-8"))
    return current_ledger, current_index, trusted_ledger, trusted_index


def test_append_only_memory_accepts_trusted_snapshot_and_valid_later_records_idempotently() -> None:
    current_ledger, current_index, trusted_ledger, trusted_index = _canonical_and_trusted_memory()
    original = copy.deepcopy((current_ledger, current_index, trusted_ledger, trusted_index))
    trusted = subject.verify_append_only_corrected_memory(trusted_ledger, trusted_index, trusted_ledger, trusted_index)
    first = subject.verify_append_only_corrected_memory(current_ledger, current_index, trusted_ledger, trusted_index)
    second = subject.verify_append_only_corrected_memory(current_ledger, current_index, trusted_ledger, trusted_index)
    assert trusted["later_ledger_records"] == trusted["later_fingerprint_entries"] == 0
    assert first == second
    assert first["later_ledger_records"] == len(current_ledger) - len(trusted_ledger)
    assert first["later_fingerprint_entries"] == len(current_index["entries"]) - len(trusted_index["entries"])
    assert (current_ledger, current_index, trusted_ledger, trusted_index) == original


@pytest.mark.parametrize("mutation", ["changed", "missing", "reordered"])
def test_append_only_memory_rejects_changed_or_missing_historical_record(mutation: str) -> None:
    current_ledger, current_index, trusted_ledger, trusted_index = _canonical_and_trusted_memory()
    damaged = copy.deepcopy(current_ledger)
    if mutation == "changed":
        damaged[0]["provenance"] = "TAMPERED"
    elif mutation == "missing":
        damaged.pop(0)
    else:
        damaged[0], damaged[1] = damaged[1], damaged[0]
    with pytest.raises((RuntimeError, ValueError)):
        subject.verify_append_only_corrected_memory(damaged, current_index, trusted_ledger, trusted_index)


@pytest.mark.parametrize("mutation", ["broken_chain", "duplicate_event", "invalid_status"])
def test_append_only_memory_rejects_broken_chain_or_duplicate_event(mutation: str) -> None:
    current_ledger, current_index, trusted_ledger, trusted_index = _canonical_and_trusted_memory()
    damaged = copy.deepcopy(current_ledger)
    if mutation == "broken_chain":
        damaged[-1]["previous_record_sha256"] = "0" * 64
    elif mutation == "duplicate_event":
        duplicate = {
            "sequence": len(damaged) + 1,
            "previous_record_sha256": damaged[-1]["record_sha256"],
            "event_id": damaged[0]["event_id"],
            "status": "PROPOSED_UNSCORED",
            "scored_trial_increment": 0,
            "proposed_count": 0,
            "provenance": "TEST_DUPLICATE_EVENT",
        }
        duplicate["record_sha256"] = sha256_value(duplicate)
        damaged.append(duplicate)
    else:
        damaged[-1]["status"] = "INVALID_LATER_STATUS"
        damaged[-1].pop("record_sha256")
        damaged[-1]["record_sha256"] = sha256_value(damaged[-1])
    with pytest.raises(ValueError):
        subject.verify_append_only_corrected_memory(damaged, current_index, trusted_ledger, trusted_index)


def test_append_only_memory_rejects_changed_or_missing_historical_fingerprint() -> None:
    current_ledger, current_index, trusted_ledger, trusted_index = _canonical_and_trusted_memory()
    changed = copy.deepcopy(current_index)
    trusted_id = trusted_index["entries"][0]["candidate_id"]
    changed_entry = next(row for row in changed["entries"] if row["candidate_id"] == trusted_id)
    changed_entry["status"] = "TAMPERED"
    with pytest.raises(RuntimeError, match="HISTORICAL_FINGERPRINT_ENTRY_CHANGED"):
        subject.verify_append_only_corrected_memory(current_ledger, changed, trusted_ledger, trusted_index)
    missing = copy.deepcopy(current_index)
    missing["entries"] = [row for row in missing["entries"] if row["candidate_id"] != trusted_id]
    with pytest.raises(RuntimeError, match="HISTORICAL_FINGERPRINT_ENTRY_CHANGED"):
        subject.verify_append_only_corrected_memory(current_ledger, missing, trusted_ledger, trusted_index)


def test_append_only_memory_rejects_conflicting_later_candidate_identity() -> None:
    current_ledger, current_index, trusted_ledger, trusted_index = _canonical_and_trusted_memory()
    conflicting = copy.deepcopy(current_index)
    trusted_ids = {row["candidate_id"] for row in trusted_index["entries"]}
    later_entry = next(row for row in conflicting["entries"] if row["candidate_id"] not in trusted_ids)
    later_entry["candidate_id"] = "CONFLICTING_LATER_CANDIDATE_ID"
    with pytest.raises(RuntimeError, match="CANDIDATE_IDENTITY_CONFLICT"):
        subject.verify_append_only_corrected_memory(current_ledger, conflicting, trusted_ledger, trusted_index)


def test_runtime_candidate_identity_is_name_stable() -> None:
    assert subject._runtime_candidate_id("FXT-A-L12-H3-ORIG") == "PKT038_A_L12_H3_PRIMARY"
    assert subject._runtime_candidate_id("FXT-D-L288-H48-INV") == "PKT038_D_L288_H48_INVERSE"
    with pytest.raises(ValueError, match="INVALID_STAGE1_CELL_ID"):
        subject._runtime_candidate_id("renamed-winner")


def test_causal_momentum_is_invariant_to_future_change() -> None:
    closes = [1.0 + index * 0.00001 for index in range(330)]
    segments = [0] * len(closes)
    before = subject.causal_momentum_values(closes, segments)
    changed = list(closes)
    changed[-1] = 9.0
    after = subject.causal_momentum_values(changed, segments)
    assert before[328] == after[328]


def test_currency_graph_rejects_disconnected_and_duplicate_lineage() -> None:
    with pytest.raises(ValueError, match="DISCONNECTED_CURRENCY_GRAPH"):
        subject.CurrencyGraphProjector(["EUR_USD", "AUD_NZD"])
    with pytest.raises(ValueError, match="DUPLICATE_SYNTHETIC_LINEAGE"):
        subject.CurrencyGraphProjector(["EUR_USD", "USD_EUR"])


def test_graph_strength_is_zero_sum_and_directional() -> None:
    projector = subject.CurrencyGraphProjector(["EUR_USD", "GBP_USD", "EUR_GBP"])
    strengths = projector.strengths([0.02, -0.01, 0.03])
    assert sum(strengths.values()) == pytest.approx(0.0, abs=1e-12)
    top, bottom, _ = projector.quartiles([0.02, -0.01, 0.03])
    assert subject.graph_select("EUR_GBP", "LONG", top, bottom)


def test_leave_target_pair_out_marks_graph_bridge_infeasible() -> None:
    start = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
    pairs = ("EUR_USD", "USD_JPY")
    bars = {
        pair: [
            {**bar(start + timedelta(minutes=5 * index), 1.0 + index * 0.0001), "instrument": pair}
            for index in range(13)
        ]
        for pair in pairs
    }
    event = {
        "pair": "EUR_USD", "lookback": 12,
        "bar_timestamp": bars["EUR_USD"][-1]["timestamp"],
    }
    graph, audit = subject.build_graph_diagnostics(pairs, lambda pair: bars[pair], [event])
    row = graph[(12, event["bar_timestamp"])]["leave_target_pair_out"]["EUR_USD"]
    assert row["status"] == "NOT_FEASIBLE_PAIR_IS_GRAPH_BRIDGE"
    assert audit["leave_target_pair_out_infeasible_bridge_pairs"] == ["EUR_USD"]


def test_side_correct_costs_and_inverse_are_recalculated() -> None:
    start = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
    bars = [bar(start, 1.1000), bar(start + timedelta(minutes=5), 1.1010)]
    gross_long = subject.trade_outcome("EUR_USD", bars, 0, 2, "LONG", "GROSS")
    base_long = subject.trade_outcome("EUR_USD", bars, 0, 2, "LONG", "BASE")
    base_short = subject.trade_outcome("EUR_USD", bars, 0, 2, "SHORT", "BASE")
    assert gross_long["result_pips"] == pytest.approx(10.0)
    assert base_long["result_pips"] < gross_long["result_pips"]
    assert base_short["result_pips"] < -gross_long["result_pips"]
    assert base_long["entry_price"] == pytest.approx(1.10011)
    assert base_short["entry_price"] == pytest.approx(1.09989)


def test_certified_pip_metadata_covers_all_58_and_exact_regression_pairs() -> None:
    metadata = subject.certified_instrument_metadata()
    assert len(metadata) == 58
    assert subject.pip_size("EUR_HUF") == pytest.approx(0.01)
    assert subject.pip_size("USD_HUF") == pytest.approx(0.01)
    assert subject.pip_size("HKD_JPY") == pytest.approx(0.0001)
    assert subject.pip_size("USD_JPY") == pytest.approx(0.01)
    assert subject.pip_size("EUR_USD") == pytest.approx(0.0001)
    with pytest.raises(ValueError, match="PAIR_MISSING_CERTIFIED_INSTRUMENT_METADATA"):
        subject.pip_size("AAA_BBB")


def test_certified_non_suffix_pip_size_controls_slippage_and_pip_conversion() -> None:
    start = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
    hkd_jpy = [bar(start, 17.0), bar(start + timedelta(minutes=5), 17.001)]
    gross = subject.trade_outcome("HKD_JPY", hkd_jpy, 0, 2, "LONG", "GROSS")
    base = subject.trade_outcome("HKD_JPY", hkd_jpy, 0, 2, "LONG", "BASE")
    assert gross["result_pips"] == pytest.approx(10.0)
    assert base["slippage_pips_per_side"] == pytest.approx(0.1)
    assert gross["result_pips"] - base["result_pips"] > 2.0


def test_partition_boundary_and_financing_fail_closed() -> None:
    boundary = datetime(2025, 3, 31, 23, 55, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="PARTITION_BOUNDARY_CROSSING"):
        subject.trade_outcome("EUR_USD", [bar(boundary, 1.0)], 0, 1, "LONG", "BASE")
    rollover = datetime(2024, 1, 2, 21, 55, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="UNSUPPORTED_FINANCING_BOUNDARY"):
        subject.trade_outcome("EUR_USD", [bar(rollover, 1.0)], 0, 1, "LONG", "BASE")


def test_pullback_state_machine_confirms_and_expires_deterministically() -> None:
    start = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
    bars = [bar(start + timedelta(minutes=5 * i), value) for i, value in enumerate([1.0, 0.997, 0.998, 1.001, 1.002])]
    event = {"index": 0, "direction": "LONG", "endpoint": 1.0, "impulse_size": 0.01}
    assert subject.pullback_entry(bars, event)["entry_index"] == 4
    flat = [bar(start + timedelta(minutes=5 * i), 1.0) for i in range(14)]
    assert subject.pullback_entry(flat, event)["state"] == "EXPIRED"


def test_journal_preserves_losing_rows() -> None:
    row = {
        "event_id": "E", "pair": "EUR_USD", "lookback": 12, "horizon": 3,
        "signal_direction": "LONG", "signal_timestamp": "2024-01-01T00:00:00Z",
        "graph_selected": False, "pullback_states": {"C": "EXPIRED"},
        "arms": {"A": {"ORIG": {"outcomes": {"BASE": {"result_pips": -1.0}}}, "INV": {"outcomes": None}}},
    }
    payload = subject.journal_bytes([row])
    audit = subject.audit_journal(payload, 1)
    assert audit["pass"] is True
    assert audit["losing_outcomes"] == 1


def test_reporting_repair_counts_only_executed_directions_and_ranks_executed_cell() -> None:
    journal_rows = [{
        "arms": {
            "A": {
                "ORIG": {"cell_id": "FXT-A-L12-H3-ORIG", "trade_direction": "LONG", "outcomes": {"BASE": {"result_pips": -1.0}}},
                "INV": {"cell_id": "FXT-A-L12-H3-INV", "trade_direction": "SHORT", "outcomes": None},
            }
        }
    }]
    result = {
        "mechanism_observed_cells": [],
        "cell_results": {
            "FXT-A-L12-H3-ORIG": {"metrics": {"executed_count": 1, "long_executed": 99, "short_executed": 99, "base_after_cost_mean_pips": -1.0}, "failure_classifications": ["COST_DESTROYED_EDGE"]},
            "FXT-A-L12-H3-INV": {"metrics": {"executed_count": 0, "long_executed": 99, "short_executed": 99, "base_after_cost_mean_pips": 0.0}, "failure_classifications": ["INSUFFICIENT_TRADES"]},
        },
    }
    repaired = subject.repair_execution_direction_counts(result, subject.journal_bytes(journal_rows))
    assert repaired["cell_results"]["FXT-A-L12-H3-ORIG"]["metrics"]["long_executed"] == 1
    assert repaired["cell_results"]["FXT-A-L12-H3-INV"]["metrics"]["short_executed"] == 0
    assert subject.postmortem(repaired)["best_original_cell"] == "FXT-A-L12-H3-ORIG"


def test_memory_update_adds_exactly_72_scored_attempts_without_erasing_proposals() -> None:
    cells = stage0.first_wave_manifest()["cells"]
    contracts = subject.verify_runtime_contracts(REPO_ROOT, cells, require_pre_score=False)
    result = {
        "scored_cell_ids": sorted(row["cell_id"] for row in cells),
        "mechanism_observed_cells": [],
        "cell_results": {row["cell_id"]: {"mechanism_observed": False} for row in cells},
    }
    _, _, trusted_ledger, trusted_index = _canonical_and_trusted_memory()
    ledger = trusted_ledger[:11]
    index = copy.deepcopy(trusted_index)
    for row in index["entries"]:
        if row["candidate_id"].startswith("PKT038_"):
            row["status"] = "PROPOSED_UNSCORED"
            for key in ("stage1_packet_id", "stage1_cell_id", "frozen_stage0_candidate_fingerprint", "result_artifact_sha256"):
                row.pop(key, None)
    index.pop("pkt039_outcome_examined", None)
    index.pop("pkt039_survivors", None)
    ledger_payload, index_payload, receipt = subject.prepare_global_memory_update(
        result, contracts, ledger, index, "0" * 64,
    )
    updated = [json.loads(line) for line in ledger_payload.decode("ascii").splitlines()]
    summary = validate_trial_ledger(updated)
    assert len(updated) == 83
    assert summary["scored_attempt_lower_bound"] == 1292
    assert summary["proposed_unscored_count"] == 525
    updated_index = json.loads(index_payload)
    assert updated_index["pkt039_outcome_examined"] == 72
    assert sum(row["status"] == "VALID_TEST_REJECTED" for row in updated_index["entries"]) == 72
    assert receipt["scored_attempt_lower_bound_after"] == 1292


def test_corrective_memory_appends_invalidation_and_replay_without_trial_increment() -> None:
    cells = stage0.first_wave_manifest()["cells"]
    contracts = subject.verify_runtime_contracts(REPO_ROOT, cells, require_pre_score=False)
    result = {
        "scored_cell_ids": sorted(row["cell_id"] for row in cells),
        "new_outcome_scored_trials": 0,
        "mechanism_observed_cells": [],
        "cell_results": {row["cell_id"]: {"mechanism_observed": False} for row in cells},
    }
    # Reconstruct the exact pre-correction memory so this regression remains
    # valid after the append-only corrective records are canonically promoted.
    _, _, trusted_ledger, trusted_index = _canonical_and_trusted_memory()
    ledger = trusted_ledger[:83]
    index = copy.deepcopy(trusted_index)
    for entry in index["entries"]:
        if not entry["candidate_id"].startswith("PKT038_"):
            continue
        if "prior_invalid_status" in entry:
            entry["status"] = entry.pop("prior_invalid_status")
            entry["result_artifact_sha256"] = entry.pop("prior_invalid_result_artifact_sha256")
        entry.pop("corrective_packet_id", None)
        entry.pop("corrective_result_artifact_sha256", None)
    for key in (
        "pkt039_prior_results_invalidated",
        "pkt039_corrective_replay_cells",
        "pkt039_corrective_replay_trial_increment",
        "pkt039_corrective_packet_id",
    ):
        index.pop(key, None)
    ledger_payload, index_payload, receipt = subject.prepare_corrective_memory_update(
        result, contracts, ledger, index, "1" * 64,
    )
    updated = [json.loads(line) for line in ledger_payload.decode("ascii").splitlines()]
    summary = validate_trial_ledger(updated)
    assert summary["record_count"] == 227
    assert summary["scored_attempt_lower_bound"] == 1292
    assert receipt["invalidation_records_appended"] == 72
    assert receipt["correction_records_appended"] == 72
    assert receipt["corrective_replay_trial_increment"] == 0
    updated_index = json.loads(index_payload)
    assert updated_index["pkt039_prior_results_invalidated"] == 72
    assert updated_index["pkt039_corrective_replay_cells"] == 72
    assert updated_index["pkt039_corrective_replay_trial_increment"] == 0


def test_corrective_taxonomy_is_frozen_and_not_top_n_ranking() -> None:
    def row(executed: int, gross: float, base: float, stressed: float, severe: float, observed: bool = False) -> dict[str, object]:
        return {"mechanism_observed": observed, "metrics": {"executed_count": executed, "gross_mean_pips": gross, "base_after_cost_mean_pips": base, "stressed_mean_pips": stressed, "severe_mean_pips": severe}}

    assert subject._taxonomy(row(0, 0.0, 0.0, 0.0, 0.0)) == "NO_EXECUTION"
    assert subject._taxonomy(row(10, -0.1, -1.0, -1.1, -1.2)) == "DEAD"
    assert subject._taxonomy(row(10, 0.1, -1.0, -1.1, -1.2)) == "COST_DESTROYED_EDGE"
    assert subject._taxonomy(row(10, 1.0, 0.1, -0.1, -0.2)) == "COST_NEAR_MISS"
    assert subject._taxonomy(row(10, 1.0, 0.3, 0.1, -0.1)) == "FRAGILE"
    assert subject._taxonomy(row(10, 1.0, 0.3, 0.2, 0.1, True)) == "SURVIVOR"


def test_development_artifact_selection_cannot_cross_validation_boundary() -> None:
    manifest = {
        "eligible_pairs": ["EUR_USD"],
        "artifacts": [
            {"instrument": "EUR_USD", "start_utc": "2024-01-01T00:00:00Z", "end_utc": "2025-04-01T00:00:00Z"},
            {"instrument": "EUR_USD", "start_utc": "2025-04-01T00:00:00Z", "end_utc": "2025-05-01T00:00:00Z"},
        ],
    }
    chosen = subject.development_artifacts(manifest, "EUR_USD")
    assert len(chosen) == 1
    assert chosen[0]["end_utc"] == "2025-04-01T00:00:00Z"
