"""Tests for deterministic paper-only candidate discovery Packet U."""
from __future__ import annotations

import inspect

from automation.forex_engine import next_candidate_discovery_u_v1 as module


def _run():
    return module.run_next_candidate_discovery(write_reports=False)


def test_multiple_candidates_generated():
    payload = _run()
    assert payload["candidate_count"] >= 4
    assert len(payload["candidates"]) >= 4
    candidate_ids = [row["candidate_id"] for row in payload["candidates"]]
    assert "c1-eur-buy" in candidate_ids


def test_leaderboard_generated():
    payload = _run()
    leaderboard = payload["leaderboard"]
    assert "ranked" in leaderboard
    assert len(leaderboard["ranked"]) == payload["candidate_count"]
    assert leaderboard["champion"]
    assert leaderboard["runner_up"]


def test_champion_and_replacement_analysis_fields():
    payload = _run()
    replacement = payload["replacement_analysis"]
    assert replacement["anchor_candidate_id"] == "c1-eur-buy"
    assert "champion_candidate_id" in replacement
    assert "replacement_recommendation" in replacement
    assert replacement["rejected_count"] == len(replacement["rejected_candidates"])


def test_ranking_deterministic():
    first = _run()
    second = _run()
    assert first["leaderboard"]["ranked"] == second["leaderboard"]["ranked"]
    assert first["champion"] == second["champion"]
    assert first["runner_up"] == second["runner_up"]


def test_rejected_candidates_and_exceeds_anchor_logic():
    payload = _run()
    leaderboard = payload["leaderboard"]
    rejected = leaderboard["rejected"]
    assert all(item["candidate_id"] in (row["candidate_id"] for row in payload["candidates"]) for item in rejected)
    assert isinstance(leaderboard["any_candidate_exceeds_anchor"], bool)
    assert isinstance(leaderboard["candidates_exceed_anchor"], list)


def test_anchor_meets_canonical_sample_depth():
    payload = _run()
    anchor = payload["leaderboard"]["anchor_candidate"]
    assert anchor["candidate_id"] == "c1-eur-buy"
    assert payload["genuine_campaign_evidence"] is False
    assert payload["campaign_state"]["accepted_qualifying_trades"] == 0
    assert anchor["closed_trade_count"] == 0
    assert anchor["promotion_status"] == "REJECT_INSUFFICIENT_SAMPLE"
    assert "insufficient_sample" in anchor["blocker_reasons"]


def test_no_forbidden_execution_surfaces():
    source = inspect.getsource(module)
    forbidden = (
        "requests",
        "socket",
        "urllib",
        "subprocess",
        "oanda",
    )
    for token in forbidden:
        assert token not in source
