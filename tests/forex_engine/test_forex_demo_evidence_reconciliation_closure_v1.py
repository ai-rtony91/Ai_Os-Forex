from __future__ import annotations

import pytest

from automation.forex_engine import forex_demo_evidence_reconciliation_closure_v1 as closure


def _accepted(snapshot: dict, intent: dict | None = None) -> bool:
    return closure.reconcile_demo_evidence(
        snapshot,
        intent if intent is not None else closure.valid_demo_intent(),
    )["closure_accepted"]


def test_inventory_classification_is_deterministic_and_honest() -> None:
    first = closure.inventory_demo_evidence()
    second = closure.inventory_demo_evidence()
    assert first == second
    assert first["genuine_demo_evidence_count"] == 0
    assert first["read_only_demo_evidence_count"] == 1
    assert first["synthetic_demo_evidence_count"] == 3
    assert first["planning_only_count"] == 2
    assert first["genuine_demo_records_reconciled"] == 0
    assert first["genuine_demo_records_insufficient"] == 1
    assert first["historical_candidates"][0]["reconciliation_status"] == (
        "INSUFFICIENT_FOR_RECONCILIATION"
    )


def test_synthetic_reconciliation_success() -> None:
    result = closure.reconcile_demo_evidence(
        closure.valid_demo_snapshot(),
        closure.valid_demo_intent(),
    )
    assert result["closure_accepted"] is True
    engine = result["engine_result"]
    for field in (
        "pair_match",
        "side_match",
        "units_match",
        "price_within_tolerance",
        "stop_loss_match",
        "take_profit_match",
        "position_seen",
        "order_seen",
    ):
        assert engine[field] is True


def test_wrong_pair_fails_reconciliation() -> None:
    intent = closure.valid_demo_intent()
    intent["pair"] = "GBP_USD"
    assert _accepted(closure.valid_demo_snapshot(), intent) is False


def test_wrong_side_fails_reconciliation() -> None:
    snapshot = closure.valid_demo_snapshot()
    for row in snapshot["positions_summary"] + snapshot["orders"]:
        row["side"] = "SELL"
    assert _accepted(snapshot) is False


def test_wrong_units_fail_reconciliation() -> None:
    snapshot = closure.valid_demo_snapshot()
    for row in snapshot["positions_summary"] + snapshot["orders"]:
        row["units"] = 999.0
    assert _accepted(snapshot) is False


def test_bad_price_fails_reconciliation() -> None:
    snapshot = closure.valid_demo_snapshot()
    for row in snapshot["positions_summary"] + snapshot["orders"]:
        row["entry_price"] = 1.2
    assert _accepted(snapshot) is False


@pytest.mark.parametrize("field,value", [("stop_loss", 1.09), ("take_profit", 1.12)])
def test_bad_stop_loss_or_take_profit_fails_reconciliation(field: str, value: float) -> None:
    snapshot = closure.valid_demo_snapshot()
    for row in snapshot["positions_summary"] + snapshot["orders"]:
        row[field] = value
    assert _accepted(snapshot) is False


def test_stale_data_fails_closed() -> None:
    snapshot = closure.valid_demo_snapshot()
    snapshot["fresh"] = False
    result = closure.reconcile_demo_evidence(snapshot, closure.valid_demo_intent())
    assert result["closure_accepted"] is False
    assert result["engine_result"]["stale_data"] is True


def test_credential_material_fails_closed() -> None:
    snapshot = closure.valid_demo_snapshot()
    snapshot["credentials"] = True
    result = closure.reconcile_demo_evidence(snapshot, closure.valid_demo_intent())
    assert result["closure_accepted"] is False
    assert "credentials_true" in result["closure_blocked_reasons"]


def test_broker_write_fails_closed() -> None:
    snapshot = closure.valid_demo_snapshot()
    snapshot["broker_write"] = True
    result = closure.reconcile_demo_evidence(snapshot, closure.valid_demo_intent())
    assert result["closure_accepted"] is False
    assert "broker_write_true" in result["closure_blocked_reasons"]


def test_all_required_negative_paths_fail_closed() -> None:
    proof = closure.synthetic_reconciliation_proof()
    assert proof["demo_reconciliation_engine_ready"] is True
    assert proof["demo_reconciliation_fail_closed"] is True
    assert set(proof["negative_cases"]) == {
        "wrong_pair",
        "wrong_side",
        "wrong_units",
        "price_outside_tolerance",
        "wrong_stop_loss",
        "wrong_take_profit",
        "stale_snapshot",
        "account_identifier_material",
        "credentials_true",
        "broker_write_true",
        "order_submit_true",
        "live_trading_true",
        "network_submit_true",
    }


def test_result_quality_dimensions_remain_separate() -> None:
    proof = closure.demo_result_quality_proof()
    assert proof["demo_result_quality_gate_ready"] is True
    losing = proof["reconciled_losing_result"]
    assert losing["demo_result_complete"] is True
    assert losing["demo_result_reconciled"] is True
    assert losing["demo_result_profitable"] is False
    assert losing["demo_result_safe"] is True


def test_profitability_does_not_override_reconciliation() -> None:
    result = closure.demo_result_quality_proof()["profitable_mismatched_result"]
    assert result["demo_result_profitable"] is True
    assert result["demo_result_reconciled"] is False
    assert result["demo_result_safe"] is False
    assert result["profit_proof_accepted"] is False


def test_repeated_demo_pipeline_ready_without_fabricated_profit_proof() -> None:
    repeated = closure.repeated_demo_readiness(
        closure.synthetic_reconciliation_proof(),
        closure.demo_result_quality_proof(),
    )
    assert repeated["repeated_demo_evidence_pipeline_ready"] is True
    assert repeated["repeated_demo_profit_proof_complete"] is False


def test_paper30_count_and_hashes_remain_unchanged() -> None:
    before = closure.paper30_snapshot()
    after = closure.paper30_snapshot()
    assert before == after
    assert before["forward_count"] == 0


def test_live_execution_remains_false() -> None:
    assert closure.valid_demo_intent()["live_trading"] is False
    proof = closure.synthetic_reconciliation_proof()
    assert proof["network_calls"] is False
    assert proof["broker_calls"] is False
