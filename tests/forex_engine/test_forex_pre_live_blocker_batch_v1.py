from __future__ import annotations

from automation.forex_engine.forex_pre_live_blocker_batch_v1 import (
    PRE_LIVE_BLOCKED,
    PRE_LIVE_INCOMPLETE,
    PRE_LIVE_REVIEW_READY,
    build_sample_pre_live_batch_evidence,
    evaluate_forex_pre_live_blocker_batch_v1,
)


def test_complete_pre_live_batch_is_review_ready_only() -> None:
    result = evaluate_forex_pre_live_blocker_batch_v1(build_sample_pre_live_batch_evidence())

    assert result["status"] == PRE_LIVE_REVIEW_READY
    assert result["passed"] is True
    assert result["review_ready_only"] is True
    assert result["remaining_blockers"] == []
    assert result["live_trading_allowed"] is False
    assert result["order_submission_allowed"] is False
    assert result["credential_access_allowed"] is False
    assert result["owner_approval_created"] is False


def test_missing_batch_inputs_are_incomplete() -> None:
    result = evaluate_forex_pre_live_blocker_batch_v1({})

    assert result["status"] == PRE_LIVE_INCOMPLETE
    assert "final_readiness" in result["missing_inputs"]
    assert "missing_batch_input:final_readiness" in result["remaining_blockers"]
    assert result["live_trading_allowed"] is False


def test_child_blockers_remain_visible() -> None:
    evidence = build_sample_pre_live_batch_evidence()
    evidence["profit_production_gate"] = {
        "status": "BLOCKED_LOW_PROFIT_FACTOR",
        "blockers": ["profit_factor_below_minimum"],
    }

    result = evaluate_forex_pre_live_blocker_batch_v1(evidence)

    assert result["status"] == PRE_LIVE_BLOCKED
    assert "profit_production_gate_status_not_ready:BLOCKED_LOW_PROFIT_FACTOR" in result["remaining_blockers"]
    assert "profit_production_gate:profit_factor_below_minimum" in result["remaining_blockers"]
    assert result["passed"] is False


def test_forbidden_live_or_execution_flags_block_even_nested() -> None:
    evidence = build_sample_pre_live_batch_evidence()
    evidence["runtime_supervision"] = {
        "status": "FOREX_RUNTIME_ACTIVE_SUPERVISION_READY",
        "live_trading_allowed": True,
        "blockers": [],
    }

    result = evaluate_forex_pre_live_blocker_batch_v1(evidence)

    assert result["status"] == PRE_LIVE_BLOCKED
    assert "forbidden_true:evidence.runtime_supervision.live_trading_allowed" in result["remaining_blockers"]
    assert result["live_trading_allowed"] is False


def test_operator_boundary_is_required() -> None:
    evidence = build_sample_pre_live_batch_evidence()
    evidence.pop("operator_boundary")

    result = evaluate_forex_pre_live_blocker_batch_v1(evidence)

    assert result["status"] == PRE_LIVE_BLOCKED
    assert "missing_operator_boundary" in result["remaining_blockers"]
