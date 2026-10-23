from __future__ import annotations

import ast
import importlib.util
import json
import math
import uuid
from pathlib import Path

import pytest

from automation.forex_engine import forex_factor_common_component_momentum_stage0_v1 as subject
from automation.forex_engine.forex_edge_discovery_tournament_stage1_v1 import CurrencyGraphProjector
from automation.forex_engine.forex_edge_validation_pipeline_v1 import validate_trial_ledger


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "scripts/forex_delivery/run_forex_factor_common_component_momentum_stage0_v1.py"
SPEC = importlib.util.spec_from_file_location("pkt043_runner", RUNNER_PATH)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_metadata_only_evidence_has_exact_58_pair_precision_contract() -> None:
    evidence = subject.load_stage0_evidence(REPO_ROOT)
    audit = subject.validate_instrument_metadata(evidence["pair_metadata"])
    assert audit["pair_count"] == 58
    assert audit["exact_regressions"] == {"EUR_HUF": 0.01, "USD_HUF": 0.01, "HKD_JPY": 0.0001}
    assert evidence["corrected_input"]["validation_shards_opened"] == 0
    assert evidence["corrected_input"]["holdout_shards_opened"] == 0


def test_invalid_or_missing_metadata_fails_closed() -> None:
    evidence = subject.load_stage0_evidence(REPO_ROOT)
    broken = dict(evidence["pair_metadata"])
    broken.pop("EUR_USD")
    with pytest.raises(ValueError, match="PAIR_COUNT_NOT_58"):
        subject.validate_instrument_metadata(broken)
    broken = {pair: dict(row) for pair, row in evidence["pair_metadata"].items()}
    broken["HKD_JPY"]["pip_size"] = 0.01
    with pytest.raises(ValueError, match="PIP_CONTRACT_INVALID|CORRECTIVE_PIP_REGRESSION"):
        subject.validate_instrument_metadata(broken)


def test_component_projection_is_deterministic_zero_sum_and_reconstructs() -> None:
    pairs = ("EUR_USD", "GBP_USD", "EUR_GBP")
    values = (0.01, -0.02, 0.031)
    first = subject.decompose_returns(pairs, values)
    second = subject.decompose_returns(pairs, values)
    assert first == second
    assert math.isclose(math.fsum(first["strengths"].values()), 0.0, abs_tol=1e-12)
    for raw, common, residual in zip(values, first["common"], first["residual"]):
        assert math.isclose(raw, common + residual, abs_tol=1e-12)


def test_graph_duplicate_disconnection_and_residual_degeneracy_fail_closed() -> None:
    with pytest.raises(ValueError, match="DUPLICATE_SYNTHETIC_LINEAGE"):
        CurrencyGraphProjector(("EUR_USD", "USD_EUR"))
    with pytest.raises(ValueError, match="DISCONNECTED_CURRENCY_GRAPH"):
        CurrencyGraphProjector(("EUR_USD", "GBP_JPY"))
    audit = subject.graph_eligibility(("EUR_USD", "GBP_USD"))
    assert audit["status"] == "RESIDUAL_INELIGIBLE_MECHANICALLY_ZERO"


def test_normalized_signal_is_future_invariant_and_zero_variance_blocks() -> None:
    values = [math.sin(index / 9.0) * 0.001 + index * 1e-7 for index in range(350)]
    expected = subject.normalized_component_momentum(values, 320, 48)
    changed = list(values)
    changed[321:] = [100.0] * (len(changed) - 321)
    assert subject.normalized_component_momentum(changed, 320, 48) == expected
    with pytest.raises(ValueError, match="ZERO_COMPONENT_VOLATILITY"):
        subject.normalized_component_momentum([1.0] * 350, 320, 48)


def test_feature_entry_exit_partition_boundary_is_strict() -> None:
    subject.validate_information_boundary(100, 101, 149, 149)
    with pytest.raises(ValueError, match="BOUNDARY"):
        subject.validate_information_boundary(100, 101, 150, 149)
    with pytest.raises(ValueError, match="BOUNDARY"):
        subject.validate_information_boundary(101, 101, 149, 149)


def test_cards_are_complete_unique_and_bounded() -> None:
    evidence = subject.load_stage0_evidence(REPO_ROOT)
    cards = subject.build_edge_cards(evidence["pairs"])
    assert len(cards) == 36
    assert len({row["CANDIDATE_FINGERPRINT"] for row in cards}) == 36
    assert {row["SCIENTIFIC_SPECIFICATION"]["parameters"]["component"] for row in cards} == {"COMMON", "RESIDUAL"}
    assert {row["FORMATION_WINDOW"]["m5_intervals"] for row in cards} == {12, 48, 288}
    assert {row["PREDICTION_OR_HOLDING_HORIZON"]["m5_intervals"] for row in cards} == {3, 12, 48}
    assert all(row["PROMOTION_BOUNDARY"].startswith("AT_MOST_MECHANISM_OBSERVED") for row in cards)


def test_missing_contract_field_and_fingerprint_tamper_fail_closed() -> None:
    evidence = subject.load_stage0_evidence(REPO_ROOT)
    card = subject.build_edge_cards(evidence["pairs"])[0]
    missing = dict(card)
    missing.pop("ENTRY_TRIGGER")
    with pytest.raises(ValueError, match="FIELDS_MISSING"):
        subject.validate_edge_card(missing)
    tampered = dict(card)
    tampered["CANDIDATE_FINGERPRINT"] = "0" * 64
    with pytest.raises(ValueError, match="FINGERPRINT_MISMATCH"):
        subject.validate_edge_card(tampered)


def test_novelty_and_comparator_are_frozen_before_outcomes() -> None:
    evidence = subject.load_stage0_evidence(REPO_ROOT)
    cards = subject.build_edge_cards(evidence["pairs"])
    _, index = subject.current_memory(REPO_ROOT)
    novelty = subject.novelty_map(cards, index)
    assert novelty["duplicate_new_card_ids"] == []
    assert novelty["new_unique_count"] == 36
    baselines = subject._baseline_rows(index)
    assert len(baselines) == 18
    assert all(row["role"] == "HISTORICAL_MATCHED_BASELINE_NOT_NEW_PROPOSAL" for row in baselines)


def test_registration_is_append_only_zero_increment_and_idempotent() -> None:
    evidence = subject.load_stage0_evidence(REPO_ROOT)
    cards = subject.build_edge_cards(evidence["pairs"])
    ledger, index = subject.current_memory(REPO_ROOT)
    first_ledger, first_index, first_receipt = subject.prepare_memory_registration(cards, ledger, index)
    updated_records = [json.loads(line) for line in first_ledger.decode("ascii").splitlines()]
    updated_index = json.loads(first_index)
    second_ledger, second_index, second_receipt = subject.prepare_memory_registration(cards, updated_records, updated_index)
    assert first_ledger == second_ledger
    assert first_index == second_index
    assert first_receipt == second_receipt
    summary = validate_trial_ledger(updated_records)
    assert summary == validate_trial_ledger(ledger)
    assert updated_records == ledger
    assert updated_index["entries"] == index["entries"]
    assert first_receipt["new_proposed_unscored_count"] == 36
    assert first_receipt["idempotency_status"] == "PASS"


def test_stage0_artifacts_are_deterministic_and_open_zero_outcomes() -> None:
    first = subject.build_stage0(REPO_ROOT)
    second = subject.build_stage0(REPO_ROOT)
    assert first == second
    receipt = json.loads(first["AIOS_FOREX_FACTOR_COMPONENT_STAGE0_RECEIPT.json"])
    assert receipt["eligible_specifications"] == 36
    assert receipt["historical_baseline_references"] == 18
    assert receipt["frozen_next_screen_budget"] == 54
    assert receipt["new_scored_trial_increment"] == 0
    assert receipt["market_rows_opened"] == receipt["validation_rows_opened"] == receipt["holdout_rows_opened"] == 0
    assert all(value == "PASS" for value in receipt["acceptance"].values())


def test_runner_is_packet_scoped_and_reproducible(tmp_path: Path) -> None:
    output = REPO_ROOT / ".aios/staging/PKT_FOREX_043" / f"pytest_occ82_{uuid.uuid4().hex}"
    result = runner.run(output)
    assert result["status"] == "PASS"
    assert result["new_scored_trial_increment"] == 0
    assert result["market_rows_opened"] == 0
    assert len(list(output.iterdir())) == 11
    with pytest.raises(ValueError, match="OUTSIDE"):
        runner.run(tmp_path / "outside")


def test_source_has_no_network_broker_or_market_reader() -> None:
    source_path = REPO_ROOT / "automation/forex_engine/forex_factor_common_component_momentum_stage0_v1.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = {node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)}
    imports.update(node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert not ({"requests", "urllib", "oandapyV20", "pandas", "numpy"} & imports)
    lowered = source_path.read_text(encoding="utf-8").lower()
    for forbidden in ("place_order(", "create_order(", "practice_api", "live_api", "market_data_root", "pair_histories"):
        assert forbidden not in lowered


def test_synthetic_certification_exercises_real_component_code() -> None:
    evidence = subject.load_stage0_evidence(REPO_ROOT)
    receipt = subject.synthetic_certification(evidence["pairs"])
    assert receipt["status"] == "PASS"
    assert receipt["check_count"] == 12
    assert all(value == "PASS" for value in receipt["checks"].values())
