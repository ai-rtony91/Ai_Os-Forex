"""Repo-safe Forex edge autopilot V1.
This orchestrator repeats only local evidence and proof gates. It never reads
credentials, contacts a broker, starts a scheduler/daemon, places orders, or
creates demo/live authority.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from automation.forex_engine.broker_connection_proof_boundary_readiness_v1 import (
    run_broker_connection_proof_boundary_readiness_v1,
)
from automation.forex_engine.candidate_selector_hardening_v1 import (
    run_candidate_selector_hardening_v1,
)
from automation.forex_engine.forex_110_profit_evidence_truth_lock_v1 import (
    run_profit_evidence_truth_lock,
)
from automation.forex_engine.forex_110_walkforward_oos_sufficiency_truth_lock_v1 import (
    run_walkforward_oos_sufficiency_truth_lock,
)
from automation.forex_engine.forex_statistical_profit_proof_gate_v1 import (
    evaluate_forex_statistical_profit_proof_gate,
    to_jsonable_dict as statistical_result_to_jsonable_dict,
)
from automation.forex_engine.profit_proof_ledger_v1 import (
    evaluate_profit_proof_ledger,
    result_to_jsonable_dict as ledger_result_to_jsonable_dict,
)
from automation.forex_engine.profitability_evidence_intake_v1 import DEFAULT_REPORT_ROOT
from automation.forex_engine.strategy_promotion_router_v1 import (
    result_to_jsonable_dict as promotion_result_to_jsonable_dict,
    route_strategy_promotion,
)
from automation.forex_engine.trusted_profit_22_6_readiness_v1 import (
    evaluate_trusted_profit_22_6_readiness,
    result_to_jsonable_dict as trusted_profit_result_to_jsonable_dict,
)
PACKET_ID = "PKT-FOREX-EDGE-AUTOPILOT-V1"
ENGINE_VERSION = "forex_edge_autopilot_v1"
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
def run_forex_edge_autopilot_v1(
    report_root: str | Path = DEFAULT_REPORT_ROOT,
    *,
    target_candidate_count: int = 3,
    cycles: int = 1,
) -> dict[str, Any]:
    """Run repo-safe edge gates and return the ranked candidate basket."""
    safe_cycles = max(1, int(cycles))
    target = max(1, int(target_candidate_count))
    root = Path(report_root)
    runs = []
    latest: dict[str, Any] = {}
    for cycle_index in range(1, safe_cycles + 1):
        latest = _run_one_cycle(root, target, cycle_index)
        runs.append(latest)
        if latest["candidate_count"] >= target:
            break
    final = dict(latest)
    final.update(
        {
            "packet_id": PACKET_ID,
            "engine_version": ENGINE_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cycles_requested": safe_cycles,
            "cycles_completed": len(runs),
            "target_candidate_count": target,
            "runs": runs,
            "status": (
                "TARGET_REVIEW_CANDIDATES_FOUND"
                if latest.get("candidate_count", 0) >= target
                else "SEARCH_CONTINUES_REPO_SAFE"
            ),
            "stop_reason": _stop_reason(latest, target),
            "next_safe_action": _next_safe_action(latest, target),
            "permissions": {field: False for field in PROTECTED_FALSE_FIELDS},
            "blocked_actions": list(PROTECTED_FALSE_FIELDS),
        }
    )
    final.update({field: False for field in PROTECTED_FALSE_FIELDS})
    return final
def _run_one_cycle(report_root: Path, target: int, cycle_index: int) -> dict[str, Any]:
    profit_lock = run_profit_evidence_truth_lock(report_root)
    walkforward_lock = run_walkforward_oos_sufficiency_truth_lock(report_root)
    ledger = ledger_result_to_jsonable_dict(evaluate_profit_proof_ledger())
    selector = run_candidate_selector_hardening_v1()
    promotion = promotion_result_to_jsonable_dict(route_strategy_promotion())
    trusted_22_6 = trusted_profit_result_to_jsonable_dict(
        evaluate_trusted_profit_22_6_readiness()
    )
    statistical = statistical_result_to_jsonable_dict(
        evaluate_forex_statistical_profit_proof_gate()
    )
    broker_boundary = run_broker_connection_proof_boundary_readiness_v1()
    candidates = _candidate_basket(
        profit_lock=profit_lock,
        walkforward_lock=walkforward_lock,
        ledger=ledger,
        selector=selector,
        promotion=promotion,
    )
    rejected = _rejected_candidates(ledger, selector)
    return {
        "cycle_index": cycle_index,
        "candidate_count": len(candidates),
        "target_candidate_count": target,
        "candidate_basket": candidates,
        "rejected_or_blocked_candidates": rejected,
        "proof_gates": {
            "profit_truth_lock_status": profit_lock.get("truth_lock_status"),
            "profit_proof_status": profit_lock.get("profit_proof_status"),
            "walk_forward_oos_status": walkforward_lock.get("walk_forward_oos_status"),
            "walkforward_truth_lock_status": walkforward_lock.get("truth_lock_status"),
            "ledger_status": ledger.get("ledger_status"),
            "selector_status": selector.get("selector_status"),
            "strategy_promotion_status": promotion.get("promotion_status"),
            "statistical_classification": statistical.get("classification"),
            "trusted_22_6_status": trusted_22_6.get("readiness_status"),
            "broker_boundary_status": broker_boundary.get("readiness_status"),
        },
        "false_positive_controls": {
            "sample_selector_not_used_as_trade_authority": True,
            "weak_candidates_rejected": len(rejected),
            "broker_or_slippage_gaps_keep_secondary_candidates_review_only": True,
            "all_trading_permissions_false": True,
        },
        "protected_boundary": "broker_practice_read_only_owner_runtime_boundary",
    }
def _candidate_basket(
    *,
    profit_lock: Mapping[str, Any],
    walkforward_lock: Mapping[str, Any],
    ledger: Mapping[str, Any],
    selector: Mapping[str, Any],
    promotion: Mapping[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    top_candidate_id = str(profit_lock.get("top_candidate_id") or "NONE")
    if (
        profit_lock.get("truth_lock_status") == "PROVEN"
        and walkforward_lock.get("walk_forward_oos_status") == "PROVEN"
    ):
        candidates.append(
            {
                "candidate_id": top_candidate_id,
                "tier": "PRIMARY_EDGE_PROOF",
                "status": "PROVEN_FOR_OPERATOR_REVIEW_ONLY",
                "source": "profit_truth_lock_and_walkforward_oos_truth_lock",
                "metrics": profit_lock.get("normalized_profitability_summary", {}),
                "permissions": "review_only_no_demo_live_or_order_authority",
            }
        )
    selected = selector.get("selected_candidate") or {}
    selected_id = str(selected.get("candidate_id") or "NONE")
    if selector.get("selector_status") == "REVIEW_READY_CANDIDATE_SELECTED" and selected_id != "NONE":
        candidates.append(
            {
                "candidate_id": selected_id,
                "tier": "SECONDARY_REVIEW_READY",
                "status": "REVIEW_READY_NEEDS_BROKER_SLIPPAGE_RECONCILIATION",
                "source": "candidate_selector_hardening",
                "metrics": selected,
                "permissions": "review_only_no_demo_live_or_order_authority",
            }
        )
    if promotion.get("promotion_status") == "STRATEGY_PROMOTION_REVIEW_READY":
        strategy = str(promotion.get("best_strategy") or "UNKNOWN")
        if strategy not in {item["candidate_id"] for item in candidates}:
            candidates.append(
                {
                    "candidate_id": strategy,
                    "tier": "STRATEGY_REVIEW_ONLY",
                    "status": _strategy_review_status(promotion.get("supertrend_status")),
                    "source": "strategy_promotion_router",
                    "metrics": {
                        "promotion_score": promotion.get("promotion_score"),
                        "expectancy_status": promotion.get("expectancy_status"),
                        "proof_status": promotion.get("proof_status"),
                    },
                    "permissions": "review_only_no_demo_live_or_order_authority",
                }
            )
    return candidates
def _strategy_review_status(raw: Any) -> str:
    if isinstance(raw, Mapping):
        return str(raw.get("status") or raw.get("recommendation") or "REVIEW_READY")
    return str(raw or "REVIEW_READY")
def _rejected_candidates(
    ledger: Mapping[str, Any], selector: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rejected: list[dict[str, Any]] = []
    for item in ledger.get("candidate_results", []) or []:
        candidate = item.get("candidate") if isinstance(item, Mapping) else None
        candidate_id = str((candidate or item).get("candidate_id", "unknown"))
        classification = str(item.get("classification", "UNKNOWN"))
        if "BLOCKED" in classification or "REJECT" in classification:
            rejected.append(
                {
                    "candidate_id": candidate_id,
                    "source": "profit_proof_ledger",
                    "classification": classification,
                    "reasons": list(item.get("blockers", []) or item.get("reasons", []) or []),
                }
            )
    for item in selector.get("rejected_candidates", []) or []:
        if not isinstance(item, Mapping):
            continue
        rejected.append(
            {
                "candidate_id": str(item.get("candidate_id", "unknown")),
                "source": "candidate_selector_hardening",
                "classification": "REJECTED_BY_HARDENING",
                "reasons": list(item.get("reasons", []) or []),
            }
        )
    return rejected
def _stop_reason(latest: Mapping[str, Any], target: int) -> str:
    if int(latest.get("candidate_count", 0)) >= target:
        return "TARGET_REVIEW_CANDIDATES_FOUND_REPO_SAFE"
    return "BROKER_PRACTICE_READ_ONLY_BOUNDARY_OR_MORE_DATA_REQUIRED"
def _next_safe_action(latest: Mapping[str, Any], target: int) -> str:
    if int(latest.get("candidate_count", 0)) >= target:
        return (
            "Review the ranked basket, then run the owner-approved OANDA Practice "
            "read-only PAPER campaign locally to collect more closed paper trades."
        )
    return (
        "Continue repo-safe evidence search and collect more PAPER records only after "
        "owner-approved runtime-only OANDA Practice credentials are present locally."
    )
def build_report_markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# AIOS Forex Edge Autopilot V1",
        "",
        f"Packet ID: `{result.get('packet_id', PACKET_ID)}`",
        f"Status: {result.get('status')}",
        f"Stop reason: {result.get('stop_reason')}",
        f"Cycles completed: {result.get('cycles_completed')}/{result.get('cycles_requested')}",
        f"Candidates found: {result.get('candidate_count')}/{result.get('target_candidate_count')}",
        "",
        "## Candidate Basket",
    ]
    for candidate in result.get("candidate_basket", []) or []:
        lines.extend(
            [
                f"- {candidate.get('candidate_id')}",
                f"  - Tier: {candidate.get('tier')}",
                f"  - Status: {candidate.get('status')}",
                f"  - Source: {candidate.get('source')}",
                f"  - Permissions: {candidate.get('permissions')}",
            ]
        )
    if not result.get("candidate_basket"):
        lines.append("- none")
    lines.extend(["", "## Proof Gates"])
    for key, value in sorted((result.get("proof_gates") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Rejected / Blocked Candidates"])
    for rejected in result.get("rejected_or_blocked_candidates", []) or []:
        reasons = ", ".join(str(item) for item in rejected.get("reasons", [])) or "see gate"
        lines.append(
            f"- {rejected.get('candidate_id')}: {rejected.get('classification')} ({reasons})"
        )
    if not result.get("rejected_or_blocked_candidates"):
        lines.append("- none")
    lines.extend(
        [
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
    "PROTECTED_FALSE_FIELDS",
    "build_report_markdown",
    "run_forex_edge_autopilot_v1",
]

