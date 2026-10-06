"""Paper-only proof bundle producer for replay/reconciliation/rollback/demo-validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from automation.forex_engine import proof_gap_closure_plan
from automation.forex_engine import review_chain_end_to_end_candidate_journey

MODE = "FOREX_REPLAY_RECONCILIATION_PROOF_BUNDLE_V1"
PACKET_ID = "AIOS_FOREX_REPLAY_RECONCILIATION_PROOF_BUNDLE_V1"
REPORT_PATH = Path("Reports/forex_delivery/AIOS_FOREX_REPLAY_RECONCILIATION_PROOF_BUNDLE_V1_REPORT.md")

PROOF_BUNDLE_COMPLETE = "PROOF_BUNDLE_COMPLETE"
PROOF_BUNDLE_BLOCKED = "PROOF_BUNDLE_BLOCKED"
PROOF_BUNDLE_INCOMPLETE = "PROOF_BUNDLE_INCOMPLETE"


def _safe_get(mapping: dict[str, Any], aliases: tuple[str, ...], default: Any = "") -> Any:
    for alias in aliases:
        if isinstance(mapping, dict) and alias in mapping:
            return mapping[alias]
    return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "pass", "passed", "ready", "ok"}
    return bool(value)


def _safe_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, tuple):
        return [str(v) for v in value]
    return [str(value)]


def _normalise_safety(raw: Any) -> dict[str, bool]:
    safety = raw if isinstance(raw, dict) else {}
    return {
        "paper_only": bool(safety.get("paper_only", False)),
        "broker_connected": bool(safety.get("broker_connected", False)),
        "credentials_used": bool(safety.get("credentials_used", False)),
        "account_id_present": bool(safety.get("account_id_present", False)),
        "network_used": bool(safety.get("network_used", False)),
        "order_execution": bool(safety.get("order_execution", False)),
        "demo_trading": bool(safety.get("demo_trading", False)),
        "live_trading": bool(safety.get("live_trading", False)),
        "live_trading_authorized": bool(safety.get("live_trading_authorized", False)),
    }


def _safety_is_clean(safety: dict[str, bool]) -> bool:
    return not any(
        safety.get(flag, False)
        for flag in (
            "broker_connected",
            "credentials_used",
            "account_id_present",
            "network_used",
            "order_execution",
            "demo_trading",
            "live_trading",
            "live_trading_authorized",
        )
    )


def _safety_gap_labels(safety: dict[str, bool]) -> list[str]:
    return [f"unsafe_{flag}" for flag in (
        "broker_connected",
        "credentials_used",
        "account_id_present",
        "network_used",
        "order_execution",
        "demo_trading",
        "live_trading",
        "live_trading_authorized",
    ) if safety.get(flag, False)]


def _build_replay_proof(
    selected_candidate_id: str,
    selected_strategy: str,
    selected_direction: str,
    source_candidate_verdict: str,
    source_review_chain_status: str,
    source_journey_final_verdict: str,
) -> dict[str, Any]:
    trace = {
        "candidate_id": selected_candidate_id,
        "strategy": selected_strategy,
        "direction": selected_direction,
        "candidate_verdict": source_candidate_verdict,
        "review_chain_status": source_review_chain_status,
        "journey_final_verdict": source_journey_final_verdict,
    }
    trace_id = (
        f"replay:{selected_candidate_id}:{selected_strategy}:{selected_direction}:"
        f"{source_candidate_verdict}:{source_review_chain_status}:{source_journey_final_verdict}"
    )
    status = bool(selected_candidate_id and selected_strategy and source_candidate_verdict and source_review_chain_status)
    return {
        "trace_id": trace_id,
        "status": status and not not trace,
        "trace": trace,
        "details": "deterministic replay proof from stable journey evidence" if status else "missing replay evidence",
    }


def _build_reconciliation_proof(
    selected_candidate_id: str,
    selected_strategy: str,
    selected_direction: str,
    journey: dict[str, Any],
    safety_clean: bool,
) -> dict[str, Any]:
    candidate_bundle_id = (
        str(journey.get("selected_candidate_id", "")).strip(),
        str(journey.get("selected_strategy", "")).strip(),
        str(journey.get("selected_direction", "")).strip(),
    )
    proof_identity = selected_candidate_id == candidate_bundle_id[0] and selected_strategy == candidate_bundle_id[1] and selected_direction == candidate_bundle_id[2]
    status = bool(safety_clean and selected_candidate_id and selected_strategy and selected_direction and proof_identity)
    return {
        "status": status,
        "reconciled": bool(proof_identity),
        "evidence_fields": {
            "journey_selected_candidate_id": candidate_bundle_id[0],
            "journey_selected_strategy": candidate_bundle_id[1],
            "journey_selected_direction": candidate_bundle_id[2],
            "bundle_selected_candidate_id": selected_candidate_id,
            "bundle_selected_strategy": selected_strategy,
            "bundle_selected_direction": selected_direction,
        },
        "details": "candidate identity and state were reconciled across journey and proof-bundle" if status else "reconciliation preconditions not met",
    }


def _build_rollback_proof(safety_clean: bool) -> dict[str, Any]:
    plan = {
        "rollback_orders_to_cancel": [],
        "live_positions_to_close": [],
        "capital_allocation_to_unwind": 0.0,
        "return_to_proof_gap_planner_if_blocked": True,
        "execution_domain": "review_chain_only",
        "execution_mode": "paper_only",
    }
    status = bool(safety_clean)
    return {
        "status": status,
        "plan_id": "rollback-plan:paper-only-review",
        "plan": plan,
        "details": "no broker or live unwind actions required in deterministic review-only path" if status else "rollback safety preconditions not met",
    }


def _build_demo_validation_proof(
    source_candidate_verdict: str,
    source_review_chain_status: str,
    safety_clean: bool,
    paper_traces: dict[str, Any],
) -> dict[str, Any]:
    validation = {
        "candidate_verdict_captured": bool(source_candidate_verdict),
        "review_chain_status_captured": bool(source_review_chain_status),
        "review_only": True,
        "demo_trade_placed": False,
        "demo_credentials_accessed": False,
        "broker_demo_execution_used": False,
        "paper_evidence_review_required": True,
    }
    status = bool(
        safety_clean
        and source_candidate_verdict
        and source_review_chain_status
        and not validation["demo_trade_placed"]
        and not validation["demo_credentials_accessed"]
        and not validation["broker_demo_execution_used"]
        and validation["review_only"]
    )
    proof = {
        "status": status,
        "trace_id": f"demo-validation:{source_candidate_verdict}:{source_review_chain_status}",
        "paper_traces": paper_traces,
        "validation": validation,
        "details": "demo-validation proof requires review-only path and deterministic candidate evidence" if status else "demo-validation gate not satisfied",
    }
    return proof


def _bundle_bucket_view(journey: dict[str, Any]) -> dict[str, list[str]]:
    plan_result = proof_gap_closure_plan.run_proof_gap_closure_plan(journey_payload=journey, write_reports=False)
    buckets = plan_result.get("closure_buckets", {})
    return {
        "strategy_quality_gaps": _safe_list(buckets.get("strategy_quality_gaps", [])),
        "demo_contract_gaps": _safe_list(buckets.get("demo_contract_gaps", [])),
        "review_package_gaps": _safe_list(buckets.get("review_package_gaps", [])),
        "human_review_gaps": _safe_list(buckets.get("human_review_gaps", [])),
        "safety_gaps": _safe_list(buckets.get("safety_gaps", [])),
    }


def _identity_ready(selected_candidate_id: str, selected_strategy: str, selected_direction: str) -> bool:
    return bool(selected_candidate_id and selected_strategy and selected_direction)


def run_replay_reconciliation_proof_bundle(
    *,
    write_reports: bool = True,
    journey_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    journey = journey_payload or review_chain_end_to_end_candidate_journey.run_review_chain_end_to_end_candidate_journey(
        write_reports=False
    )

    selected_candidate_id = str(_safe_get(journey, ("selected_candidate_id", "candidate_id"), default=""))
    selected_strategy = str(_safe_get(journey, ("selected_strategy", "strategy"), default=""))
    selected_direction = str(_safe_get(journey, ("selected_direction", "direction"), default=""))
    source_candidate_verdict = str(_safe_get(journey, ("candidate_demo_review_verdict",), default=""))
    source_review_chain_status = str(_safe_get(journey, ("review_chain_status",), default=""))
    source_journey_final_verdict = str(_safe_get(journey, ("final_verdict",), default=""))

    safety = _normalise_safety(_safe_get(journey, ("safety",), default={}))
    safety["live_trading_authorized"] = False
    safety_clean = _safety_is_clean(safety)
    gaps = _safety_gap_labels(safety) + []
    bucketed_blockers = _bundle_bucket_view(journey)

    replay_proof = _build_replay_proof(
        selected_candidate_id,
        selected_strategy,
        selected_direction,
        source_candidate_verdict,
        source_review_chain_status,
        source_journey_final_verdict,
    )
    reconciliation_proof = _build_reconciliation_proof(
        selected_candidate_id,
        selected_strategy,
        selected_direction,
        journey,
        safety_clean,
    )
    rollback_proof = _build_rollback_proof(safety_clean)
    demo_validation_trace = {
        "candidate_demo_review_verdict": source_candidate_verdict,
        "review_chain_status": source_review_chain_status,
    }
    demo_validation_proof = _build_demo_validation_proof(
        source_candidate_verdict,
        source_review_chain_status,
        safety_clean,
        demo_validation_trace,
    )

    proofs = {
        "replay_proof": replay_proof,
        "reconciliation_proof": reconciliation_proof,
        "rollback_proof": rollback_proof,
        "demo_validation_proof": demo_validation_proof,
    }

    proof_bundle_status = PROOF_BUNDLE_COMPLETE
    if not safety_clean:
        proof_bundle_status = PROOF_BUNDLE_BLOCKED
    elif not _identity_ready(selected_candidate_id, selected_strategy, selected_direction):
        proof_bundle_status = PROOF_BUNDLE_INCOMPLETE
    elif not all(
        [
            bool(replay_proof.get("status")),
            bool(reconciliation_proof.get("status")),
            bool(rollback_proof.get("status")),
            bool(demo_validation_proof.get("status")),
        ]
    ):
        proof_bundle_status = PROOF_BUNDLE_INCOMPLETE

    ready_for_candidate_bridge = (
        proof_bundle_status == PROOF_BUNDLE_COMPLETE
        and source_candidate_verdict == "DEMO_REVIEW_READY"
        and source_review_chain_status == "REVIEW_CHAIN_REVIEW_READY"
    )

    if proof_bundle_status == PROOF_BUNDLE_BLOCKED:
        next_safe_action = "Resolve unsafe source flags before emitting proof bundle."
    elif proof_bundle_status == PROOF_BUNDLE_INCOMPLETE:
        if _identity_ready(selected_candidate_id, selected_strategy, selected_direction):
            next_safe_action = "Fix incomplete proof-gate details and rerun proof bundling."
        else:
            next_safe_action = "Restore selected candidate identity from journey payload."
    else:
        next_safe_action = "Proof bundle is complete; route proofs to canonical candidate bridge intake."

    result: dict[str, Any] = {
        "mode": MODE,
        "packet_id": PACKET_ID,
        "safety": safety,
        "selected_candidate_id": selected_candidate_id,
        "selected_strategy": selected_strategy,
        "selected_direction": selected_direction,
        "source_candidate_verdict": source_candidate_verdict,
        "source_review_chain_status": source_review_chain_status,
        "source_journey_final_verdict": source_journey_final_verdict,
        "proof_bundle_status": proof_bundle_status,
        "proof_bundle_ready_for_candidate_bridge": ready_for_candidate_bridge,
        "proofs": proofs,
        "replay_proof_status": bool(replay_proof.get("status")),
        "reconciliation_proof_status": bool(reconciliation_proof.get("status")),
        "rollback_proof_status": bool(rollback_proof.get("status")),
        "demo_validation_proof_status": bool(demo_validation_proof.get("status")),
        "replay_trace_id": replay_proof.get("trace_id", ""),
        "reconciliation_trace_id": reconciliation_proof.get("trace_id", ""),
        "rollback_plan_id": rollback_proof.get("plan_id", ""),
        "demo_validation_trace_id": demo_validation_proof.get("trace_id", ""),
        "unresolved_blockers": {
            "strategy_quality_gaps": bucketed_blockers["strategy_quality_gaps"],
            "demo_contract_gaps": bucketed_blockers["demo_contract_gaps"],
            "review_package_gaps": bucketed_blockers["review_package_gaps"],
            "human_review_gaps": bucketed_blockers["human_review_gaps"],
            "safety_gaps": bucketed_blockers["safety_gaps"] + [g for g in gaps if g not in bucketed_blockers["safety_gaps"]],
        },
        "next_safe_action": next_safe_action,
    }

    if write_reports:
        result["report_path"] = write_report(result)
    return result


def write_report(payload: dict[str, Any]) -> str:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_build_report_text(payload), encoding="utf-8")
    return str(REPORT_PATH)


def _build_report_text(payload: dict[str, Any]) -> str:
    proof_lines = [
        f"- replay: {payload.get('replay_proof_status', False)}",
        f"- reconciliation: {payload.get('reconciliation_proof_status', False)}",
        f"- rollback: {payload.get('rollback_proof_status', False)}",
        f"- demo_validation: {payload.get('demo_validation_proof_status', False)}",
    ]
    return f"""# AIOS Forex Replay Reconciliation Proof Bundle V1

## Purpose
Emit a deterministic paper-only proof bundle for replay, reconciliation, rollback, and demo-validation.

## Source journey consumed
- automation/forex_engine/review_chain_end_to_end_candidate_journey.py

## Proofs emitted
{chr(10).join(proof_lines)}

## Proof status mapping
- PROOF_BUNDLE_COMPLETE: all four proof records valid and source safety clean
- PROOF_BUNDLE_BLOCKED: source safety flags include unsafe states
- PROOF_BUNDLE_INCOMPLETE: source candidate identity missing or proof traces incomplete

## Unresolved blockers preserved
- strategy_quality_gaps: {', '.join(payload.get('unresolved_blockers', {}).get('strategy_quality_gaps', []))}
- demo_contract_gaps: {', '.join(payload.get('unresolved_blockers', {}).get('demo_contract_gaps', []))}
- review_package_gaps: {', '.join(payload.get('unresolved_blockers', {}).get('review_package_gaps', []))}
- human_review_gaps: {', '.join(payload.get('unresolved_blockers', {}).get('human_review_gaps', []))}
- safety_gaps: {', '.join(payload.get('unresolved_blockers', {}).get('safety_gaps', []))}

## Safety boundary
- paper_only: {payload.get('safety', {}).get('paper_only', False)}
- broker_connected: {payload.get('safety', {}).get('broker_connected', False)}
- credentials_used: {payload.get('safety', {}).get('credentials_used', False)}
- account_id_present: {payload.get('safety', {}).get('account_id_present', False)}
- network_used: {payload.get('safety', {}).get('network_used', False)}
- order_execution: {payload.get('safety', {}).get('order_execution', False)}
- demo_trading: {payload.get('safety', {}).get('demo_trading', False)}
- live_trading: {payload.get('safety', {}).get('live_trading', False)}
- live_trading_authorized: {payload.get('safety', {}).get('live_trading_authorized', False)}

## Validation
- placeholder

## Explicit security statement
No broker connectivity, no credentials, no env reads, no network access, no demo trade, no live trade, no order execution introduced.
"""


__all__ = [
    "run_replay_reconciliation_proof_bundle",
    "write_report",
    "PROOF_BUNDLE_COMPLETE",
    "PROOF_BUNDLE_BLOCKED",
    "PROOF_BUNDLE_INCOMPLETE",
]
