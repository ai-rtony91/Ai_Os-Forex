from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from automation.forex_engine.forex_profit_track_p1_strategy_evidence_v1 import (
    SAFETY_FLAGS,
    evaluate_strategy_evidence,
)

NOW = datetime(2026, 8, 6, tzinfo=timezone.utc)


def trades(count: int = 30, *, evidence_type: str = "paper", pnl_cycle=(0.02, 0.02, -0.01)):
    return [
        {
            "trade_id": f"trade-{index}",
            "entry": 1.1,
            "exit": 1.101,
            "realized_pl": pnl_cycle[index % len(pnl_cycle)],
            "timestamp": (NOW - timedelta(hours=count - index)).isoformat(),
            "evidence_type": evidence_type,
        }
        for index in range(count)
    ]


def evaluate(records):
    return evaluate_strategy_evidence(records, as_of=NOW)


def test_no_evidence_fails_closed():
    result = evaluate([])
    assert result["strategy_evidence_status"] == "NO_EVIDENCE"
    assert not result["profitability_proven"]


def test_fixture_only_receives_zero_profitability_credit():
    result = evaluate(trades(evidence_type="fixture"))
    assert result["strategy_evidence_status"] == "NO_EVIDENCE"
    assert result["trade_count"] == 0


def test_insufficient_sample():
    assert evaluate(trades(29))["strategy_evidence_status"] == "INSUFFICIENT_SAMPLE"


def test_positive_expectancy_is_review_ready():
    result = evaluate(trades())
    assert result["expectancy_per_trade"] > 0
    assert result["strategy_evidence_status"] == "READY_FOR_P2_REVIEW"


def test_negative_expectancy():
    result = evaluate(trades(pnl_cycle=(-0.01,)))
    assert result["strategy_evidence_status"] == "NEGATIVE_EXPECTANCY"


def test_profit_factor_failure():
    result = evaluate(trades(pnl_cycle=(0.01, -0.01, -0.01)))
    assert result["strategy_evidence_status"] in {"NEGATIVE_EXPECTANCY", "RISK_LIMIT_FAILED"}
    assert result["profit_factor"] < result["thresholds"]["minimum_profit_factor"]


def test_drawdown_failure():
    records = trades(pnl_cycle=(0.02, 0.02, -0.01))
    records[10]["realized_pl"] = -0.06
    result = evaluate(records)
    assert result["maximum_drawdown"] > result["thresholds"]["maximum_drawdown"]
    assert result["strategy_evidence_status"] == "RISK_LIMIT_FAILED"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda records: records.__setitem__(1, {**records[1], "trade_id": records[0]["trade_id"]}), "duplicate_trade_id"),
        (lambda records: records[0].__setitem__("realized_pl", float("nan")), "non_finite_or_invalid_realized_pl"),
        (lambda records: records.__setitem__(0, "bad"), "malformed_record"),
    ],
)
def test_bad_records_are_rejected_with_exact_reason(mutation, reason):
    records = trades()
    mutation(records)
    result = evaluate(records)
    assert any(reason in item["reasons"] for item in result["rejected_records"])
    assert result["strategy_evidence_status"] != "READY_FOR_P2_REVIEW"


def test_stale_evidence_requires_more_evidence():
    records = trades()
    for record in records:
        record["timestamp"] = (NOW - timedelta(days=8)).isoformat()
    assert evaluate(records)["strategy_evidence_status"] == "REQUIRE_MORE_EVIDENCE"


def test_output_is_sanitized_and_all_execution_permissions_are_false():
    records = trades()
    records.append({**records[0], "trade_id": "unsafe", "account_id": "private", "raw_payload": {"token": "secret"}})
    result = evaluate(records)
    serialized = json.dumps(result)
    assert '"account_id": "private"' not in serialized
    assert '"token": "secret"' not in serialized
    assert all(result[key] is False for key in SAFETY_FLAGS)
    assert result["strategy_evidence_status"] == "REQUIRE_MORE_EVIDENCE"


def test_live_evidence_cannot_advance_p1():
    result = evaluate(trades(evidence_type="live"))
    assert result["strategy_evidence_status"] == "NO_EVIDENCE"
    assert result["live_execution_allowed"] is False
