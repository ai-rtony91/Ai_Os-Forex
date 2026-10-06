"""Readiness state recalculation for staged Forex review pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .proof_bundle_to_candidate_bridge import run_proof_bundle_to_candidate_bridge
from .review_chain_end_to_end_candidate_journey import (
    JOURNEY_REVIEW_READY,
    run_review_chain_end_to_end_candidate_journey,
)


PacketResult = dict[str, Any]

PACKET_ID = "AIOS_FOREX_READINESS_STATE_RECALCULATION_V1"


def _to_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if value is None:
        return []
    return [str(value)]


def _dedupe(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _percent(done_count: int, total_count: int) -> float:
    if total_count <= 0:
        return 0.0
    return round((done_count / total_count) * 100.0, 2)


def _safe_list(payload: PacketResult, key: str) -> list[str]:
    return _dedupe(_to_list(payload.get(key)))


def _choose_next_safe_action(review_state: str, blockers: list[str], safety: dict[str, Any]) -> str:
    if safety.get("safety_gaps"):
        return "resolve_safety_gaps_before_readiness"
    if blockers:
        return blockers[0]
    if review_state == JOURNEY_REVIEW_READY:
        return "prepare_human_review_package"
    return "collect_missing_readiness_artifacts"


def _live_readiness_components(
    *,
    demo_contract_present: bool,
    one_shot_package_present: bool,
    readiness_certificate_present: bool,
) -> dict[str, bool]:
    return {
        "demo_contract": bool(demo_contract_present),
        "one_shot_package": bool(one_shot_package_present),
        "readiness_certificate": bool(readiness_certificate_present),
    }


def run_readiness_state_recalculation_v1(
    candidate_id: str = "c1-eur-buy",
    *,
    write_reports: bool = True,
    proof_bundle_payload: dict[str, Any] | None = None,
) -> PacketResult:
    """Run deterministic recalculation of readiness state for a candidate.

    Returns a derived readiness summary based on existing runtime artifacts.
    """

    bridge_payload = run_proof_bundle_to_candidate_bridge(
        write_reports=False,
        proof_bundle_payload=proof_bundle_payload,
    )

    journey_payload = run_review_chain_end_to_end_candidate_journey(
        candidate_id=candidate_id,
        write_reports=False,
        proof_bundle_payload=bridge_payload,
    )

    selected_candidate_id = bridge_payload.get("selected_candidate_id", candidate_id)

    review_state = journey_payload.get(
        "final_state",
        journey_payload.get("candidate_journey_state", "REVIEW_CHAIN_UNKNOWN"),
    )
    review_chain_ready = review_state == JOURNEY_REVIEW_READY

    demo_contract = journey_payload.get("demo_validation_contract", {}) or {}
    one_shot = journey_payload.get("one_shot_exception_package", {}) or {}
    readiness_certificate = journey_payload.get("live_review_readiness_certificate", {}) or {}
    safety = bridge_payload.get("safety", {}) or {}

    proof_bundle_consumed = (
        bridge_payload.get("proof_bundle_ready_for_candidate_bridge", False)
        and bridge_payload.get("source_proof_bundle_status") == "PROOF_BUNDLE_COMPLETE"
        and bridge_payload.get("candidate_bridge_verdict") == "DEMO_REVIEW_READY"
    )
    demo_contract_present = bool(demo_contract.get("demo_validation_contract_completed", False))
    one_shot_package_present = bool(one_shot.get("exception_package_completed", False))
    readiness_certificate_present = bool(
        readiness_certificate.get("certificate_completed", False)
    )
    live_readiness_components = _live_readiness_components(
        demo_contract_present=demo_contract_present,
        one_shot_package_present=one_shot_package_present,
        readiness_certificate_present=readiness_certificate_present,
    )
    live_readiness_components_complete = sum(
        int(value) for value in live_readiness_components.values()
    )
    live_readiness_components_total = len(live_readiness_components)

    blockers_before = _dedupe(
        _to_list(bridge_payload.get("remaining_blockers"))
        + _to_list(journey_payload.get("remaining_blockers"))
    )
    blockers_after = _dedupe(_to_list(journey_payload.get("remaining_blockers")))

    blockers_cleared = sorted(
        [blocker for blocker in blockers_before if blocker not in blockers_after]
    )
    blockers_before = sorted(blockers_before)
    blockers_after = sorted(blockers_after)

    # Stage progression percentages are computed from actual module outputs.
    # 1/5: Proof bundle, 2/5: demo contract, 3/5: one-shot package,
    # 4/5: live readiness certificate, 5/5: chain reviewed as ready.
    completion_count = sum(
        int(value)
        for value in (
            proof_bundle_consumed,
            demo_contract_present,
            one_shot_package_present,
            readiness_certificate_present,
            review_chain_ready,
        )
    )
    promotion_readiness_pct = _percent(completion_count, 5)

    demo_readiness_pct = _percent(
        int(proof_bundle_consumed) + int(demo_contract_present), 2
    )

    live_readiness_pct = _percent(
        int(readiness_certificate_present) + int(demo_contract_present) + int(one_shot_package_present),
        3,
    )
    if review_chain_ready and not review_payload_has_unsafe(review_payload=journey_payload):
        if not any(safety.get(key) for key in ("broker_connected", "network_used", "live_trading", "order_execution", "live_trading_authorized")):
            live_readiness_pct = max(live_readiness_pct, 75.0)
        if readiness_certificate_present and demo_contract_present and one_shot_package_present:
            live_readiness_pct = 100.0

    evidence_count = sum(
        int(value)
        for value in (
            proof_bundle_consumed,
            demo_contract_present,
            one_shot_package_present,
            readiness_certificate_present,
        )
    )
    evidence_completion_pct = _percent(evidence_count, 4)

    safety_gaps: list[str] = _dedupe(
        _to_list(safety.get("safety_gaps"))
        + [key for key in (
            "broker_connected",
            "network_used",
            "account_id_present",
            "credentials_used",
            "order_execution",
            "demo_trading",
            "live_trading",
            "live_trading_authorized",
        ) if safety.get(key)]
    )
    if safety_gaps:
        # Ensure all blocked states reflect explicit safety constraints.
        review_state = "REVIEW_CHAIN_BLOCKED"

    next_safe_action = journey_payload.get("next_safe_action") or _choose_next_safe_action(
        review_state, _dedupe(_to_list(journey_payload.get("remaining_blockers"))), safety
    )

    payload: PacketResult = {
        "mode": "LOCAL_APPLY",
        "packet_id": PACKET_ID,
        "candidate_id": selected_candidate_id,
        "review_state": review_state,
        "promotion_readiness_pct": float(promotion_readiness_pct),
        "demo_readiness_pct": float(demo_readiness_pct),
        "live_readiness_pct": float(live_readiness_pct),
        "forex_completion_pct": float(promotion_readiness_pct),
        "evidence_completion_pct": float(evidence_completion_pct),
        "blockers_before": blockers_before,
        "blockers_cleared": blockers_cleared,
        "blockers_remaining": blockers_after,
        "proof_bundle_consumed": bool(proof_bundle_consumed),
        "demo_contract_present": bool(demo_contract_present),
        "one_shot_package_present": bool(one_shot_package_present),
        "readiness_certificate_present": bool(readiness_certificate_present),
        "live_readiness_components": live_readiness_components,
        "live_readiness_components_complete": live_readiness_components_complete,
        "live_readiness_components_total": live_readiness_components_total,
        "review_chain_ready": bool(review_chain_ready),
        "next_safe_action": str(next_safe_action),
        "safety": safety,
        "live_trading_authorized": False,
        "bridge_payload": bridge_payload,
        "journey_payload": journey_payload,
    }

    if write_reports:
        payload["report_path"] = _write_readiness_report(payload)
    return payload


def review_payload_has_unsafe(*, review_payload: PacketResult) -> bool:
    safety = review_payload.get("safety", {}) or {}
    if not isinstance(safety, dict):
        return False
    return bool(
        safety.get("broker_connected")
        or safety.get("network_used")
        or safety.get("account_id_present")
        or safety.get("credentials_used")
        or safety.get("order_execution")
        or safety.get("demo_trading")
        or safety.get("live_trading")
        or safety.get("live_trading_authorized")
    )


def _write_readiness_report(payload: PacketResult) -> str:
    report_dir = Path("Reports/forex_delivery")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "readiness_state_recalculation_v1_report.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(report_path)


def main() -> PacketResult:  # pragma: no cover
    return run_readiness_state_recalculation_v1()


if __name__ == "__main__":  # pragma: no cover
    print(run_readiness_state_recalculation_v1())
