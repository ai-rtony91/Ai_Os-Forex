"""Tests for paper evidence promotion gate."""
from __future__ import annotations

import inspect

import pytest

from automation.forex_engine import paper_evidence_promotion_gate as gate


def _profitable_result(**overrides):
    result = {
        "profitability_ready": True,
        "sample_size_met": True,
        "expectancy_per_trade": 40.0,
        "expectancy_r": 0.4,
        "profit_factor": 2.2,
        "win_rate_pct": 60.0,
        "average_win": 120.0,
        "average_loss": 80.0,
        "max_drawdown": 200.0,
        "risk_quality_passed": True,
        "evidence_quality_passed": True,
        "blocked_reasons": [],
    }
    result.update(overrides)
    return result


@pytest.mark.parametrize("field", [
    "expectancy_per_trade", "expectancy_r", "profit_factor", "max_drawdown",
])
@pytest.mark.parametrize("value", [None, "invalid", True, float("nan"), float("inf"), -float("inf")])
def test_invalid_metrics_require_new_evidence(field, value):
    result = gate.evaluate_paper_evidence_promotion(_profitable_result(**{field: value}))
    assert result["allowed"] is False
    assert result["decision"] == gate.DECISION_MORE_EVIDENCE_REQUIRED
    assert "invalid_profitability_metrics" in result["blocked_reasons"]
    assert result["promotion_reasons"] == []


def test_negative_drawdown_cannot_be_promoted():
    result = gate.evaluate_paper_evidence_promotion(_profitable_result(max_drawdown=-100.0))
    assert result["allowed"] is False
    assert result["decision"] == gate.DECISION_MORE_EVIDENCE_REQUIRED
    assert "invalid_profitability_metrics" in result["blocked_reasons"]


@pytest.mark.parametrize("field", [
    "minimum_profit_factor", "maximum_drawdown",
    "minimum_expectancy_per_trade", "minimum_expectancy_r",
])
@pytest.mark.parametrize("value", [None, "invalid", True, float("nan"), float("inf"), -1.0])
def test_invalid_limits_cannot_promote_evidence(field, value):
    result = gate.evaluate_paper_evidence_promotion(_profitable_result(), limits={field: value})
    assert result["allowed"] is False
    assert result["decision"] == gate.DECISION_MORE_EVIDENCE_REQUIRED
    assert "invalid_promotion_limits" in result["blocked_reasons"]


@pytest.mark.parametrize("limits", [False, 0, "", [], "invalid", 42, [("minimum_profit_factor", 1.2)]])
def test_invalid_limits_container_requires_repair(limits):
    result = gate.evaluate_paper_evidence_promotion(_profitable_result(), limits=limits)
    assert result["decision"] == gate.DECISION_MORE_EVIDENCE_REQUIRED
    assert "invalid_promotion_limits" in result["blocked_reasons"]
    assert result["allowed"] is False
    assert result["promotion_reasons"] == []
    assert result["safety"]["broker_execution_allowed"] is False


@pytest.mark.parametrize("reasons", [None, "", "negative_expectancy", 42, {}, set(), [None], [False], [42]])
def test_invalid_blocked_reasons_requires_repair(reasons):
    result = gate.evaluate_paper_evidence_promotion(_profitable_result(blocked_reasons=reasons))
    assert result["decision"] == gate.DECISION_MORE_EVIDENCE_REQUIRED
    assert "invalid_profitability_evidence" in result["blocked_reasons"]
    assert result["allowed"] is False
    assert result["promotion_reasons"] == []
    assert result["safety"]["real_orders_allowed"] is False


def test_valid_demo_candidate():
    result = gate.evaluate_paper_evidence_promotion(_profitable_result())
    assert result["allowed"] is True
    assert result["decision"] == gate.DECISION_DEMO_CANDIDATE
    assert result["demo_candidate"] is True
    assert result["requires_more_evidence"] is False
    assert result["rejected"] is False
    assert result["promotion_reasons"] == [
        "positive_expectancy",
        "acceptable_drawdown",
        "acceptable_profit_factor",
        "sample_size_met",
        "evidence_quality_passed",
        "risk_quality_passed",
    ]


def test_insufficient_sample_requires_more_evidence():
    result = gate.evaluate_paper_evidence_promotion(
        _profitable_result(profitability_ready=False, sample_size_met=False, blocked_reasons=["insufficient_sample_size"])
    )
    assert result["allowed"] is False
    assert result["decision"] == gate.DECISION_MORE_EVIDENCE_REQUIRED
    assert result["requires_more_evidence"] is True
    assert "insufficient_sample_size" in result["blocked_reasons"]


def test_negative_expectancy_rejected():
    result = gate.evaluate_paper_evidence_promotion(
        _profitable_result(profitability_ready=False, expectancy_per_trade=-10.0, expectancy_r=-0.1, blocked_reasons=["negative_expectancy"])
    )
    assert result["decision"] == gate.DECISION_REJECTED
    assert result["rejected"] is True
    assert "negative_expectancy" in result["blocked_reasons"]


def test_excessive_drawdown_rejected():
    result = gate.evaluate_paper_evidence_promotion(
        _profitable_result(profitability_ready=False, max_drawdown=900.0, blocked_reasons=["excessive_drawdown"])
    )
    assert result["decision"] == gate.DECISION_REJECTED
    assert result["rejected"] is True
    assert "excessive_drawdown" in result["blocked_reasons"]


def test_failed_evidence_quality_requires_more_evidence():
    result = gate.evaluate_paper_evidence_promotion(
        _profitable_result(profitability_ready=False, evidence_quality_passed=False, blocked_reasons=["missing_replay_evidence"])
    )
    assert result["decision"] == gate.DECISION_MORE_EVIDENCE_REQUIRED
    assert "missing_evidence" in result["blocked_reasons"]
    assert "evidence_quality_failed" in result["blocked_reasons"]


def test_failed_risk_quality_blocks_promotion():
    result = gate.evaluate_paper_evidence_promotion(
        _profitable_result(profitability_ready=False, risk_quality_passed=False, blocked_reasons=["risk_quality_failed"])
    )
    assert result["allowed"] is False
    assert result["decision"] == gate.DECISION_REJECTED
    assert "risk_quality_failed" in result["blocked_reasons"]


def test_blocked_reasons_present_block_demo_candidate():
    result = gate.evaluate_paper_evidence_promotion(_profitable_result(blocked_reasons=["manual_review_required"]))
    assert result["allowed"] is False
    assert result["decision"] == gate.DECISION_MORE_EVIDENCE_REQUIRED
    assert result["demo_candidate"] is False
    assert result["blocked_reasons"] == ["manual_review_required"]


def test_deterministic_outputs():
    payload = _profitable_result(profitability_ready=False, sample_size_met=False, evidence_quality_passed=False, blocked_reasons=["missing_replay_evidence"])
    assert gate.evaluate_paper_evidence_promotion(payload) == gate.evaluate_paper_evidence_promotion(payload)


def test_safety_boundary_enforcement():
    result = gate.evaluate_paper_evidence_promotion(_profitable_result())
    safety = result["safety"]
    assert safety["paper_only"] is True
    assert safety["demo_review_only"] is True
    assert safety["live_trading_allowed"] is False
    assert safety["broker_execution_allowed"] is False
    assert safety["credentials_allowed"] is False
    assert safety["network_access_allowed"] is False
    assert safety["capital_allocation_modified"] is False
    assert safety["real_orders_allowed"] is False


def test_source_has_no_forbidden_runtime_apis():
    source = inspect.getsource(gate)
    forbidden = (
        "import requests",
        "from requests",
        "import urllib",
        "from urllib",
        "import subprocess",
        "from subprocess",
        "import socket",
        "from socket",
        "open(",
        "write_text",
        "write_bytes",
        "os.environ",
        "getenv(",
        "broker_sdk",
        "oanda",
    )
    for token in forbidden:
        assert token not in source
