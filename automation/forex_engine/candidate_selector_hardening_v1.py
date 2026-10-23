"""Deterministic repo-safe candidate selector hardening gate."""

from __future__ import annotations

from typing import Any, Mapping

from automation.forex_engine.evidence_depth_walkforward_sufficiency_v1 import (
    PROTECTED_FALSE_FIELDS,
)


PACKET_ID = "PKT-FOREX-EVIDENCE-CANDIDATE-DEMO-READINESS-CONSOLIDATED-V1"


def run_candidate_selector_hardening_v1(
    candidates: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    candidate_rows = [
        dict(candidate) for candidate in (_default_candidates() if candidates is None else candidates)
    ]
    rejected: list[dict[str, Any]] = []
    rejection_reasons: dict[str, list[str]] = {}
    accepted: list[dict[str, Any]] = []

    for candidate in candidate_rows:
        reasons = _candidate_rejection_reasons(candidate)
        candidate_id = str(candidate.get("candidate_id", "unknown_candidate"))
        if reasons:
            rejected.append({"candidate_id": candidate_id, "reasons": reasons})
            rejection_reasons[candidate_id] = reasons
            continue
        scored = dict(candidate)
        scored["score"] = _score_candidate(candidate)
        accepted.append(scored)

    selected = max(accepted, key=lambda item: item["score"]) if accepted else None
    promotion_blockers = [] if selected else ["no_review_ready_candidate"]
    result: dict[str, Any] = {
        "selector_status": "REVIEW_READY_CANDIDATE_SELECTED"
        if selected
        else "NO_REVIEW_READY_CANDIDATE_BLOCKED",
        "candidates_evaluated": len(candidate_rows),
        "selected_candidate": selected,
        "rejected_candidates": rejected,
        "rejection_reasons": rejection_reasons,
        "selection_reason": _selection_reason(selected),
        "best_candidate_score": selected["score"] if selected else 0,
        "promotion_allowed": selected is not None,
        "promotion_blockers": promotion_blockers,
        "safe_next_action": "Send selected review-ready candidate to owner review gate."
        if selected
        else "Collect stronger repo-safe evidence before promotion review.",
        "packet_id": PACKET_ID,
    }
    result.update({field: False for field in PROTECTED_FALSE_FIELDS})
    return result


def _candidate_rejection_reasons(candidate: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if int(candidate.get("trade_count", 0)) < 30:
        reasons.append("insufficient_sample")
    if float(candidate.get("expectancy", 0.0)) <= 0:
        reasons.append("negative_expectancy")
    if float(candidate.get("profit_factor", 0.0)) < 1.25:
        reasons.append("low_profit_factor")
    if float(candidate.get("max_drawdown_percent", 100.0)) > 12.0:
        reasons.append("excessive_drawdown")
    if not bool(candidate.get("walkforward_evidence")):
        reasons.append("missing_walk_forward_evidence")
    if int(candidate.get("evidence_depth_score", 0)) < 75:
        reasons.append("weak_evidence_depth")
    if bool(candidate.get("mitigation_worsened")):
        reasons.append("mitigation_worsened")
    if not bool(candidate.get("owner_review_ready")):
        reasons.append("missing_owner_review_readiness")
    return reasons


def _score_candidate(candidate: Mapping[str, Any]) -> int:
    expectancy_score = int(float(candidate.get("expectancy", 0.0)) * 100)
    factor_score = int(float(candidate.get("profit_factor", 0.0)) * 20)
    depth_score = int(candidate.get("evidence_depth_score", 0))
    drawdown_penalty = int(float(candidate.get("max_drawdown_percent", 0.0)) * 2)
    return expectancy_score + factor_score + depth_score - drawdown_penalty


def _selection_reason(selected: Mapping[str, Any] | None) -> str:
    if not selected:
        return "all_candidates_rejected_by_hardening_gates"
    return "highest_scored_candidate_after_sample_expectancy_profit_factor_drawdown_walkforward_depth_mitigation_and_owner_review_gates"


def _default_candidates() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": "CANDIDATE-EURUSD-C1",
            "trade_count": 42,
            "expectancy": 0.34,
            "profit_factor": 1.62,
            "max_drawdown_percent": 7.5,
            "walkforward_evidence": True,
            "evidence_depth_score": 86,
            "mitigation_worsened": False,
            "owner_review_ready": True,
        },
        {
            "candidate_id": "CANDIDATE-GBPUSD-WEAK",
            "trade_count": 18,
            "expectancy": 0.12,
            "profit_factor": 1.18,
            "max_drawdown_percent": 9.0,
            "walkforward_evidence": False,
            "evidence_depth_score": 61,
            "mitigation_worsened": False,
            "owner_review_ready": False,
        },
        {
            "candidate_id": "CANDIDATE-USDJPY-DRAWDOWN",
            "trade_count": 36,
            "expectancy": 0.28,
            "profit_factor": 1.38,
            "max_drawdown_percent": 16.0,
            "walkforward_evidence": True,
            "evidence_depth_score": 78,
            "mitigation_worsened": True,
            "owner_review_ready": True,
        },
    ]


def build_report_markdown(result: Mapping[str, Any]) -> str:
    selected = result.get("selected_candidate") or {}
    lines = [
        "# AIOS Forex Candidate Selector Hardening V1 Report",
        "",
        f"Selector status: {result.get('selector_status')}",
        f"Candidates evaluated: {result.get('candidates_evaluated')}",
        f"Selected candidate: {selected.get('candidate_id')}",
        f"Best candidate score: {result.get('best_candidate_score')}",
        f"Promotion allowed: {result.get('promotion_allowed')}",
        "",
        "Rejected candidates:",
    ]
    for rejected in result.get("rejected_candidates", []):
        lines.append(f"- {rejected.get('candidate_id')}: {', '.join(rejected.get('reasons', []))}")
    lines.extend(["", "Safe next action:", str(result.get("safe_next_action")), ""])
    return "\n".join(lines)


__all__ = ["build_report_markdown", "run_candidate_selector_hardening_v1"]
