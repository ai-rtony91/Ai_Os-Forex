from __future__ import annotations

import json

from automation.forex_engine import candidate_selector_hardening_v1 as module
from automation.forex_engine.evidence_depth_walkforward_sufficiency_v1 import (
    PROTECTED_FALSE_FIELDS,
)


def test_result_is_deterministic_and_json_serializable():
    first = module.run_candidate_selector_hardening_v1()
    second = module.run_candidate_selector_hardening_v1()

    assert first == second
    json.dumps(first)


def test_rejects_weak_and_unsafe_candidates():
    result = module.run_candidate_selector_hardening_v1()
    reasons = result["rejection_reasons"]

    assert "insufficient_sample" in reasons["CANDIDATE-GBPUSD-WEAK"]
    assert "low_profit_factor" in reasons["CANDIDATE-GBPUSD-WEAK"]
    assert "missing_walk_forward_evidence" in reasons["CANDIDATE-GBPUSD-WEAK"]
    assert "excessive_drawdown" in reasons["CANDIDATE-USDJPY-DRAWDOWN"]
    assert "mitigation_worsened" in reasons["CANDIDATE-USDJPY-DRAWDOWN"]


def test_selects_only_best_review_ready_candidate():
    result = module.run_candidate_selector_hardening_v1()

    assert result["selector_status"] == "REVIEW_READY_CANDIDATE_SELECTED"
    assert result["selected_candidate"]["candidate_id"] == "CANDIDATE-EURUSD-C1"
    assert result["promotion_allowed"] is True


def test_no_candidate_blocks_promotion():
    result = module.run_candidate_selector_hardening_v1(
        [
            {
                "candidate_id": "BAD",
                "trade_count": 4,
                "expectancy": -0.1,
                "profit_factor": 0.9,
                "max_drawdown_percent": 20,
                "walkforward_evidence": False,
                "evidence_depth_score": 20,
                "mitigation_worsened": True,
                "owner_review_ready": False,
            }
        ]
    )

    assert result["promotion_allowed"] is False
    assert "no_review_ready_candidate" in result["promotion_blockers"]


def test_explicit_empty_candidates_do_not_load_samples():
    result = module.run_candidate_selector_hardening_v1([])
    assert result["candidates_evaluated"] == 0
    assert result["selected_candidate"] is None
    assert result["promotion_allowed"] is False


def test_protected_booleans_remain_false():
    result = module.run_candidate_selector_hardening_v1()

    for field in PROTECTED_FALSE_FIELDS:
        assert result[field] is False
