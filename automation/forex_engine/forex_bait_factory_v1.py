"""Repo-safe Forex bait factory V1.
The factory builds candidate bait from local hypotheses, labels it HOT/WARM/COLD,
runs proof review gates, and prepares a paper-campaign handoff. It does not read
secrets, contact brokers, place orders, or start background runtime.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from automation.forex_engine.candidate_scoring_v1 import (
    REVIEW_READY,
    candidate_scores_to_jsonable_dict,
    score_candidates as score_review_candidates,
)
from automation.forex_engine.forex_edge_autopilot_v1 import run_forex_edge_autopilot_v1
from automation.forex_engine.next_candidate_discovery_u_v1 import (
    DEFAULT_REPORT_ROOT,
    run_next_candidate_discovery,
)
from automation.forex_engine.profit_proof_ledger_v1 import (
    evaluate_profit_proof_ledger,
    result_to_jsonable_dict as ledger_result_to_jsonable_dict,
)
PACKET_ID = "PKT-FOREX-BAIT-FACTORY-V1"
ENGINE_VERSION = "forex_bait_factory_v1"
PIPELINE = [
    "hypothesis_builder",
    "warm_cold_scorer",
    "proof_ledger",
    "edge_autopilot",
    "paper_campaign_handoff",
]
PROTECTED_FALSE_FIELDS = (
    "broker_api_used",
    "credentials_used",
    "env_read",
    "account_identifiers_used",
    "order_execution",
    "demo_authorized",
    "live_authorized",
    "scheduler_started",
    "daemon_started",
    "webhook_started",
    "background_loop_started",
    "broker_action_allowed",
    "real_money_allowed",
    "compounding_allowed",
    "bank_movement_allowed",
    "live_trading_allowed",
    "order_submission_allowed",
)
PAPER_COMMAND = (
    "python scripts\\forex_delivery\\run_forex_p1_supervised_paper_campaign_v1.py "
    "--owner-local-runtime --cycles 30"
)
def run_forex_bait_factory_v1(
    *,
    target_bait_count: int = 3,
    cycles: int = 1,
    report_root: str | Path = DEFAULT_REPORT_ROOT,
) -> dict[str, Any]:
    """Build a repo-safe bait box and connect it to proof/autopilot gates."""
    target = max(1, int(target_bait_count))
    safe_cycles = max(1, int(cycles))
    runs: list[dict[str, Any]] = []
    latest: dict[str, Any] = {}
    for cycle_index in range(1, safe_cycles + 1):
        latest = _run_one_cycle(target, cycle_index, Path(report_root))
        runs.append(latest)
        if latest["bait_count"] >= target:
            break
    result = dict(latest)
    result.update(
        {
            "packet_id": PACKET_ID,
            "engine_version": ENGINE_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pipeline": list(PIPELINE),
            "cycles_requested": safe_cycles,
            "cycles_completed": len(runs),
            "target_bait_count": target,
            "runs": runs,
            "status": (
                "BAIT_READY_FOR_REVIEW"
                if int(latest.get("bait_count", 0)) >= target
                else "BAIT_SEARCH_CONTINUES"
            ),
            "stop_reason": (
                "TARGET_BAIT_COUNT_FOUND_REPO_SAFE"
                if int(latest.get("bait_count", 0)) >= target
                else "TARGET_BAIT_COUNT_NOT_MET_REPO_SAFE"
            ),
            "next_safe_action": _next_safe_action(latest, target),
            "permissions": {field: False for field in PROTECTED_FALSE_FIELDS},
            "blocked_actions": list(PROTECTED_FALSE_FIELDS),
        }
    )
    result.update({field: False for field in PROTECTED_FALSE_FIELDS})
    return result
def _run_one_cycle(target: int, cycle_index: int, report_root: Path) -> dict[str, Any]:
    hypotheses = run_next_candidate_discovery(
        write_reports=False, report_root=report_root
    )
    candidate_rows = list(hypotheses.get("candidates") or [])
    score_input = [_score_input_from_candidate(candidate) for candidate in candidate_rows]
    scored = candidate_scores_to_jsonable_dict(score_review_candidates(score_input))
    scored_by_id = {item["candidate_id"]: item for item in scored.get("results", [])}
    bait_box = [_bait_item(candidate, scored_by_id.get(str(candidate.get("candidate_id")))) for candidate in candidate_rows]
    bait_box = sorted(bait_box, key=_bait_sort_key)
    label_counts = _label_counts(bait_box)
    proof_input = [_proof_input_from_candidate(item) for item in candidate_rows]
    proof_ledger = ledger_result_to_jsonable_dict(evaluate_profit_proof_ledger(proof_input))
    edge_autopilot = run_forex_edge_autopilot_v1(
        report_root, target_candidate_count=min(target, 3), cycles=1,
        candidates=proof_input,
    )
    proven_ids = {item["candidate_id"] for item in edge_autopilot["candidate_basket"]}
    selected = proof_ledger.get("selected_candidate") or {}
    ready_bait = [
        item for item in bait_box
        if item["label"] == "HOT"
        and item["candidate_id"] == selected.get("candidate_id")
        and item["candidate_id"] in proven_ids
    ]
    handoff = _paper_campaign_handoff(ready_bait, edge_autopilot)
    return {
        "cycle_index": cycle_index,
        "hypothesis_builder": {
            "packet_id": hypotheses.get("packet_id"),
            "candidate_count": hypotheses.get("candidate_count"),
            "genuine_campaign_evidence": hypotheses.get("genuine_campaign_evidence"),
        },
        "warm_cold_scorer": scored,
        "proof_ledger": {
            "ledger_status": proof_ledger.get("ledger_status"),
            "top_candidate_id": selected.get("candidate_id", "NONE"),
        },
        "edge_autopilot": {
            "status": edge_autopilot.get("status"),
            "candidate_count": edge_autopilot.get("candidate_count"),
            "stop_reason": edge_autopilot.get("stop_reason"),
        },
        "paper_campaign_handoff": handoff,
        "bait_box": bait_box,
        "bait_count": len(ready_bait),
        "label_counts": label_counts,
        "cold_count": label_counts["COLD"],
        "false_positive_controls": {
            "cold_bait_blocked_from_proof_promotion": True,
            "paper_handoff_does_not_execute": True,
            "broker_keys_required_locally_only": True,
            "proof_ledger_and_edge_autopilot_recheck_bait": True,
        },
        "target_bait_count": target,
    }
def _proof_input_from_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate.get("candidate_id"),
        "strategy_name": candidate.get("strategy_id"),
        "direction": candidate.get("direction"),
        "total_trades": candidate.get("closed_trade_count"),
        "expectancy": candidate.get("expectancy"),
        "profit_factor": candidate.get("profit_factor"),
        "max_drawdown": candidate.get("max_drawdown"),
    }


def _score_input_from_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    blockers = list(candidate.get("blocker_reasons") or [])
    return {
        "candidate_id": candidate.get("candidate_id"),
        "expectancy": candidate.get("expectancy"),
        "profit_factor": candidate.get("profit_factor"),
        "max_drawdown": candidate.get("max_drawdown"),
        "sample_size": candidate.get("closed_trade_count"),
        "evidence_age_days": candidate.get("evidence_age_days", 999),
        "evidence_present": False,
        "required_evidence_complete": False,
        "demo_readiness": False,
        "risk_controls_present": False,
        "risk_blocked": False,
        "regime_alignment_score": 75 if not blockers else 35,
        "operator_confidence_score": 70 if not blockers else 20,
    }
def _bait_item(candidate: Mapping[str, Any], score: Mapping[str, Any] | None) -> dict[str, Any]:
    score = score or {}
    label = _label(candidate, score)
    blockers = list(candidate.get("blocker_reasons") or score.get("blockers") or [])
    observed = int(candidate.get("closed_trade_count") or 0) > 0
    return {
        "candidate_id": str(candidate.get("candidate_id") or "unknown"),
        "strategy_id": str(candidate.get("strategy_id") or "unknown"),
        "direction": str(candidate.get("direction") or "UNKNOWN"),
        "label": label,
        "decision": str(score.get("decision") or "UNKNOWN"),
        "normalized_score": float(score.get("normalized_score") or 0.0) if observed else None,
        "expectancy": float(candidate.get("expectancy") or 0.0) if observed else None,
        "profit_factor": float(candidate.get("profit_factor") or 0.0) if observed else None,
        "closed_trade_count": int(candidate.get("closed_trade_count") or 0),
        "max_drawdown": float(candidate.get("max_drawdown") or 0.0) if observed else None,
        "blockers": blockers,
        "next_step": _bait_next_step(label),
    }
def _label(candidate: Mapping[str, Any], score: Mapping[str, Any]) -> str:
    blockers = list(candidate.get("blocker_reasons") or score.get("blockers") or [])
    expectancy = float(candidate.get("expectancy") or 0.0)
    profit_factor = float(candidate.get("profit_factor") or 0.0)
    trades = int(candidate.get("closed_trade_count") or 0)
    normalized = float(score.get("normalized_score") or 0.0)
    decision = str(score.get("decision") or "")
    promotion = str(candidate.get("promotion_status") or "")
    if trades == 0:
        return "UNTESTED"
    if decision in {"REJECT", "BLOCKED_BY_RISK"}:
        return "COLD"
    if any("drawdown" in str(blocker).lower() for blocker in blockers):
        return "COLD"
    if not blockers and decision == REVIEW_READY and "READY" in promotion and normalized >= 75:
        return "HOT"
    if expectancy > 0 and profit_factor >= 1.1 and trades >= 15:
        return "WARM"
    return "COLD"
def _bait_next_step(label: str) -> str:
    if label == "UNTESTED":
        return "collect_candidate_specific_evidence"
    if label == "HOT":
        return "send_to_proof_ledger_and_edge_autopilot_review"
    if label == "WARM":
        return "collect_more_evidence_before_paper_handoff"
    return "reject_or_park_as_false_positive_risk"
def _label_counts(bait_box: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "HOT": sum(1 for item in bait_box if item.get("label") == "HOT"),
        "WARM": sum(1 for item in bait_box if item.get("label") == "WARM"),
        "COLD": sum(1 for item in bait_box if item.get("label") == "COLD"),
        "UNTESTED": sum(1 for item in bait_box if item.get("label") == "UNTESTED"),
    }
def _bait_sort_key(item: Mapping[str, Any]) -> tuple[int, float, float, str]:
    priority = {"HOT": 0, "WARM": 1, "COLD": 2, "UNTESTED": 3}.get(str(item.get("label")), 4)
    return (
        priority,
        -float(item.get("normalized_score") or 0.0),
        -float(item.get("expectancy") or 0.0),
        str(item.get("candidate_id") or ""),
    )
def _paper_campaign_handoff(
    ready_bait: list[Mapping[str, Any]], edge_autopilot: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "handoff_status": (
            "REVIEW_READY_NO_EXECUTION" if ready_bait else "BLOCKED_NO_CANDIDATE_PROOF"
        ),
        "bait_available": bool(ready_bait),
        "ready_bait_count": len(ready_bait),
        "edge_autopilot_status": edge_autopilot.get("status"),
        "command": PAPER_COMMAND,
        "requires_local_runtime_env": ["OANDA_DEMO_ACCESS_TOKEN", "OANDA_DEMO_ACCOUNT_ID"],
        "executes_now": False,
        "reason": (
            "Candidate proof is review-ready; paper remains owner-gated."
            if ready_bait else "No candidate-specific proof passed; paper handoff is blocked."
        ),
    }
def _next_safe_action(latest: Mapping[str, Any], target: int) -> str:
    if int(latest.get("bait_count", 0)) >= target:
        return "Use the bait box for proof review; start PAPER only from owner local runtime when more closed trades are needed."
    return "Collect candidate-specific, independently checked evidence before paper handoff."
def build_report_markdown(result: Mapping[str, Any]) -> str:
    pipeline = " -> ".join(str(item) for item in result.get("pipeline", PIPELINE))
    lines = [
        "# AIOS Forex Bait Factory V1",
        "",
        f"Packet ID: `{result.get('packet_id', PACKET_ID)}`",
        f"Status: {result.get('status')}",
        f"Stop reason: {result.get('stop_reason')}",
        f"Pipeline: {pipeline}",
        f"Cycles completed: {result.get('cycles_completed')}/{result.get('cycles_requested')}",
        f"Bait ready: {result.get('bait_count')}/{result.get('target_bait_count')}",
        "",
        "## Candidate Counts",
    ]
    for label, count in (result.get("label_counts") or {}).items():
        lines.append(f"- {label}: {count}")
    lines.extend(["", "## Bait Box"])
    for item in result.get("bait_box", []) or []:
        lines.append(
            f"- {item.get('label')} {item.get('candidate_id')}: "
            f"score {item.get('normalized_score') if item.get('normalized_score') is not None else 'unknown'}, "
            f"expectancy {item.get('expectancy') if item.get('expectancy') is not None else 'unknown'}, "
            f"PF {item.get('profit_factor') if item.get('profit_factor') is not None else 'unknown'}, "
            f"next {item.get('next_step')}"
        )
    if not result.get("bait_box"):
        lines.append("- none")
    handoff = result.get("paper_campaign_handoff") or {}
    lines.extend(
        [
            "",
            "## Paper Handoff",
            f"- Status: {handoff.get('handoff_status')}",
            f"- Command: `{handoff.get('command', '')}`",
            f"- Executes now: {handoff.get('executes_now', False)}",
            "",
            "## Safety",
            "- Broker/API calls: false",
            "- Credential/env reads: false",
            "- Demo/live/order authority: false",
            "- Scheduler/daemon/background loop started: false",
            "",
            "## Next Safe Action",
            str(result.get("next_safe_action")),
            "",
        ]
    )
    return "\n".join(lines)
__all__ = [
    "PACKET_ID",
    "PIPELINE",
    "PROTECTED_FALSE_FIELDS",
    "build_report_markdown",
    "run_forex_bait_factory_v1",
]

