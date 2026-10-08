"""Tests for deterministic paper-only candidate discovery Packet U."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

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


def test_unverified_anchor_has_no_scored_trades():
    payload = _run()
    anchor = payload["leaderboard"]["anchor_candidate"]
    assert anchor["candidate_id"] == "c1-eur-buy"
    assert payload["genuine_campaign_evidence"] is False
    assert anchor["closed_trade_count"] == 0
    assert anchor["promotion_status"] == "REJECT_INSUFFICIENT_SAMPLE"
    assert "insufficient_sample" in anchor["blocker_reasons"]


def test_unrelated_paper_trade_cannot_authenticate_profile_pnl(tmp_path: Path):
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (report_root / "AIOS_FOREX_P1_30_TRADE_CAMPAIGN_V1_STATE.json").write_text(
        json.dumps({
            "accepted_qualifying_trades": 1,
            "trade_results": [{
                "trade_id": "paper-1",
                "strategy_name": "unrelated_strategy",
                "realized_paper_pl": 0.183,
            }],
        }),
        encoding="utf-8",
    )
    payload = module.run_next_candidate_discovery(
        write_reports=False, report_root=report_root
    )
    assert payload["genuine_campaign_evidence"] is False
    assert all(row["closed_trade_count"] == 0 for row in payload["candidates"])
    assert all(row["promotion_status"] != "PROFIT_OBJECTIVE_READY" for row in payload["candidates"])


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
