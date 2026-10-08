import hashlib
import json
from pathlib import Path

import pytest

from automation.forex_engine.forex_frozen_21_series_phase1_postmortem_v1 import (
    DATASET_ID,
    DATASET_SHA256,
    INPUT_HASHES,
    check_rejected_method,
    promote_verified_outputs,
    run_postmortem,
)

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / ".aios/runtime/forex_frozen_21_series_edge_research_v1"


def execute(tmp_path: Path):
    output = tmp_path / "out"
    return run_postmortem(INPUT, output, tmp_path / "report.md", tmp_path / "plan.md", "b86c65140ed03d53d6c8d6c3618e50da0502f51b", DATASET_ID, DATASET_SHA256), output


def test_input_hash_contract_is_current():
    for name, expected in INPUT_HASHES.items():
        assert hashlib.sha256((INPUT / name).read_bytes()).hexdigest() == expected


def test_postmortem_accounts_for_all_candidates_and_families(tmp_path):
    receipt, output = execute(tmp_path)
    postmortem = json.loads((output / "AIOS_FOREX_PHASE1_POSTMORTEM.json").read_text())
    assert receipt["status"] == "PASS"
    assert postmortem["candidate_count"] == 24
    assert postmortem["family_count"] == 8
    assert postmortem["survivor_count"] == 0


def test_rejection_ledger_has_enforceable_unique_fingerprints(tmp_path):
    _, output = execute(tmp_path)
    ledger = json.loads((output / "AIOS_FOREX_PHASE1_POSTMORTEM.json").read_text())["rejection_ledger"]
    assert len(ledger["candidate_rows"]) == 24
    assert len(ledger["family_rows"]) == 8
    assert len({item["exact_rules_fingerprint"] for item in ledger["candidate_rows"]}) == 24
    assert len({item["family_fingerprint"] for item in ledger["family_rows"]}) == 8
    assert all(item["disposition"] == "REJECTED_DO_NOT_RETEST" for item in ledger["candidate_rows"] + ledger["family_rows"])


def test_every_candidate_has_required_failure_dimensions(tmp_path):
    _, output = execute(tmp_path)
    data = json.loads((output / "AIOS_FOREX_PHASE1_POSTMORTEM.json").read_text())
    required = {"signal_failure", "gross_performance", "after_cost_failure", "cost_sensitivity", "cost_destroyed_gross_edge", "drawdown_failure", "stability_failure", "direction_failure", "instrument_concentration", "session_concentration", "regime_dependence", "trade_count_deficiency", "fold_inconsistency", "parameter_fragility", "largest_trade_dependence", "leakage", "evidence_deficiency"}
    assert all(required <= set(item["failure"]) for item in data["candidate_analyses"])
    assert all(item["failure"]["gross_performance"] == "NO_EVIDENCE" for item in data["candidate_analyses"])


def test_holdout_remains_sealed_and_safety_false(tmp_path):
    receipt, output = execute(tmp_path)
    prereg = json.loads((output / "AIOS_FOREX_NEXT_FAMILY_PREREGISTRATION.json").read_text())
    assert receipt["holdout_status"] == "NOT_EVALUATED"
    assert prereg["sealed_final_holdout"] == "DO_NOT_OPEN"
    assert not any(receipt["safety"].values())


def test_next_family_is_distinct_and_bounded(tmp_path):
    _, output = execute(tmp_path)
    prereg = json.loads((output / "AIOS_FOREX_NEXT_FAMILY_PREREGISTRATION.json").read_text())
    assert prereg["family"] == "CROSS_SECTIONAL_CURRENCY_STRENGTH_MOMENTUM"
    assert prereg["candidate_cap"] == 12
    assert len(prereg["parameter_grid"]["lookback_bars"]) == 3
    assert "BID_ASK_AFTER_COST" in prereg["baselines"]


def test_outputs_are_deterministic(tmp_path):
    _, first = execute(tmp_path / "a")
    _, second = execute(tmp_path / "b")
    names = sorted(path.name for path in first.iterdir())
    assert names == sorted(path.name for path in second.iterdir())
    assert all((first / name).read_bytes() == (second / name).read_bytes() for name in names)
    for name in ("report.md", "plan.md", "AIOS_FOREX_FROZEN_21_SERIES_PHASE1_POSTMORTEM_V1_STATE.json"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_dataset_mismatch_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="state identity mismatch"):
        run_postmortem(INPUT, tmp_path / "out", tmp_path / "report", tmp_path / "plan", "head", "wrong", DATASET_SHA256)


@pytest.mark.parametrize("proposal,reason", [
    ({"family": "BREAKOUT", "economic_mechanism": "BREAKOUT"}, "REJECTED_OR_RENAMED_MECHANISM"),
    ({"family": "break out", "economic_mechanism": "break-out"}, "REJECTED_OR_RENAMED_MECHANISM"),
    ({"family": "NEW", "economic_mechanism": "NEW", "parent_failed_family": "MOMENTUM"}, "COSMETIC_VARIATION"),
    ({"family": "NEW", "economic_mechanism": "NEW", "selection_basis": "PAIR_ONLY_FILTER"}, "PAIR_ONLY_FILTER"),
    ({"family": "NEW", "economic_mechanism": "NEW", "selection_basis": "SESSION_ONLY_FILTER"}, "SESSION_ONLY_FILTER"),
    ({"family": "NEW", "economic_mechanism": "NEW", "selection_basis": "LOOSER_THRESHOLD"}, "LOOSER_THRESHOLD"),
    ({"family": "NEW", "economic_mechanism": "NEW", "selection_basis": "VALIDATION_MINING"}, "VALIDATION_MINING"),
    ({"family": "NEW", "economic_mechanism": "NEW", "selection_basis": "MINOR_EXIT_CHANGE"}, "MINOR_EXIT_CHANGE"),
])
def test_rejected_variations_are_blocked(tmp_path, proposal, reason):
    _, output = execute(tmp_path)
    ledger = json.loads((output / "AIOS_FOREX_PHASE1_POSTMORTEM.json").read_text())["rejection_ledger"]
    assert check_rejected_method(proposal, ledger) == {"status": "REJECT", "reason": reason}


def test_distinct_cross_sectional_mechanism_is_eligible(tmp_path):
    _, output = execute(tmp_path)
    data = json.loads((output / "AIOS_FOREX_PHASE1_POSTMORTEM.json").read_text())
    assert data["next_family_duplicate_check"] == {"status": "ELIGIBLE", "reason": "DISTINCT_MECHANISM"}


def test_preregistration_construction_contract_is_exact(tmp_path):
    _, output = execute(tmp_path)
    p = json.loads((output / "AIOS_FOREX_NEXT_FAMILY_PREREGISTRATION.json").read_text())
    assert p["return_signs"] == {"base": 1, "quote": -1}
    assert p["signal_timing"] == "COMPLETED_BAR_ONLY"
    assert p["entry_timing"] == "NEXT_ELIGIBLE_TRADABLE_BID_OR_ASK"
    assert p["missing_pair_behavior"] == "SKIP_UNSYNCHRONIZED_TIMESTAMP"
    assert p["candidate_cap"] == 12
    assert p["final_holdout"]["status"] == "SEALED"


def test_receipt_acceptance_and_manifest_are_complete(tmp_path):
    receipt, output = execute(tmp_path)
    assert all(value == "PASS" for value in receipt["acceptance"].values())
    assert receipt["candidate_fingerprint_count"] == 24
    assert receipt["family_fingerprint_count"] == 8
    assert "--expected-dataset-hash" in receipt["reproduction_command"]
    assert all(item["bytes"] > 0 and len(item["sha256"]) == 64 for item in receipt["manifest"].values())


def test_verified_promotion_matches_every_byte(tmp_path):
    execute(tmp_path / "stage")
    names = {
        "postmortem": tmp_path / "stage/out/AIOS_FOREX_PHASE1_POSTMORTEM.json",
        "receipt": tmp_path / "stage/out/AIOS_FOREX_PHASE1_POSTMORTEM_RECEIPT.json",
    }
    finals = {key: tmp_path / "final" / path.name for key, path in names.items()}
    proof = promote_verified_outputs(names, finals)
    assert proof["status"] == "PASS" and proof["files_promoted"] == 2
    assert all(finals[key].read_bytes() == path.read_bytes() for key, path in names.items())


def test_changed_source_hash_fails_closed(tmp_path):
    copied = tmp_path / "inputs"
    copied.mkdir()
    for name in INPUT_HASHES:
        (copied / name).write_bytes((INPUT / name).read_bytes())
    (copied / "AIOS_FOREX_PHASE1_RESULTS.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="input hash mismatch"):
        run_postmortem(copied, tmp_path / "out", tmp_path / "report", tmp_path / "plan", "b86c65140ed03d53d6c8d6c3618e50da0502f51b", DATASET_ID, DATASET_SHA256)
