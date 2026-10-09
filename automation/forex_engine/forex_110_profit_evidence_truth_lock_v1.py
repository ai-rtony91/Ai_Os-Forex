"""Forex 110 profit evidence truth lock.

This module reconciles persistent profitability intake with the profit proof
ledger. It is local-only and creates no trade, broker, money, or compounding
authority.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from automation.forex_engine.persistent_profitability_evidence_v1 import (
    PERSISTENT_PROFITABILITY_READY,
)
from automation.forex_engine.profit_proof_ledger_v1 import (
    PROFIT_PROOF_LEDGER_PROMOTABLE,
    ProfitProofCandidateEvidence,
    evaluate_profit_proof_ledger,
    result_to_jsonable_dict as ledger_result_to_jsonable_dict,
)
from automation.forex_engine.profitability_evidence_intake_v1 import (
    DEFAULT_REPORT_ROOT,
    intake_profitability_evidence,
    result_to_jsonable_dict as intake_result_to_jsonable_dict,
)


PACKET_ID = "PKT-FOREX-110-PROFIT-EVIDENCE-TRUTH-LOCK-V1"
ENGINE_VERSION = "forex_110_profit_evidence_truth_lock_v1"

PROFIT_PROOF_PROVEN = "PROVEN"
PROFIT_PROOF_BLOCKED = "BLOCKED"
PROFIT_PROOF_REVIEW_READY_PERSISTENCE_BLOCKED = (
    "REVIEW_READY_PERSISTENCE_BLOCKED"
)

PROTECTED_PERMISSION_FLAGS = {
    "next_demo_trade_allowed": False,
    "broker_action_allowed": False,
    "real_money_allowed": False,
    "compounding_allowed": False,
    "bank_movement_allowed": False,
    "live_trading_allowed": False,
    "credential_access_allowed": False,
    "order_submission_allowed": False,
    "owner_approval_created": False,
}


def run_profit_evidence_truth_lock(
    report_root: str | Path = DEFAULT_REPORT_ROOT,
    candidates: Sequence[ProfitProofCandidateEvidence | Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the Forex 110 profit proof truth state."""

    intake = intake_result_to_jsonable_dict(intake_profitability_evidence(report_root))
    # Omitted input is missing evidence, never permission to select a sample.
    ledger = ledger_result_to_jsonable_dict(
        evaluate_profit_proof_ledger(() if candidates is None else candidates)
    )

    persistent_ready = intake.get("status") == PERSISTENT_PROFITABILITY_READY
    ledger_promotable = ledger.get("ledger_status") == PROFIT_PROOF_LEDGER_PROMOTABLE
    top_candidate = ledger.get("top_candidate") or {}

    # These parsers and rankers validate supplied summaries, not their custody.
    # No independent candidate/source verifier is connected to this interface.
    # Keep numeric diagnostics and economic blockers without issuing proof.
    profit_proof_status = PROFIT_PROOF_BLOCKED
    truth_lock_status = PROFIT_PROOF_BLOCKED
    blockers = list(dict.fromkeys([
        *(intake.get("blockers") or []),
        *(ledger.get("blockers") or []),
        "NO_INDEPENDENT_VERIFIER_CONNECTED",
    ]))
    owner_answer = (
        "Profit proof is blocked because candidate and report source authenticity "
        "have not been independently verified. Summary metrics are diagnostic only. "
        "No execution or money authority is approved."
    )

    return {
        "packet_id": PACKET_ID,
        "engine_version": ENGINE_VERSION,
        "profit_proof_status": profit_proof_status,
        "source_authentication_status": "UNVERIFIED",
        "diagnostic_persistence_ready": persistent_ready,
        "diagnostic_ledger_promotable": ledger_promotable,
        "truth_lock_status": truth_lock_status,
        "persistent_profitability_status": intake.get("status"),
        "ledger_status": ledger.get("ledger_status"),
        "top_candidate_id": ledger.get("top_candidate_id", "NONE"),
        "top_candidate_classification": top_candidate.get("classification", "NONE"),
        "top_candidate_review_recommendation": top_candidate.get("review_recommendation", "NONE"),
        "persistent_profitability_blockers": list(intake.get("blockers") or []),
        "ledger_blockers": list(ledger.get("blockers") or []),
        "blockers": blockers,
        "normalized_profitability_summary": dict(intake.get("normalized_summary") or {}),
        "source_files": list(intake.get("source_files") or []),
        "permissions": dict(PROTECTED_PERMISSION_FLAGS),
        **PROTECTED_PERMISSION_FLAGS,
        "owner_answer": owner_answer,
        "next_safe_action": _next_safe_action(profit_proof_status, truth_lock_status),
    }


def build_report_markdown(result: Mapping[str, Any]) -> str:
    """Build an operator-readable truth-lock report."""

    # A historical or caller-supplied PROVEN label is not authentication.
    result = dict(result)
    result["profit_proof_status"] = PROFIT_PROOF_BLOCKED
    result["truth_lock_status"] = PROFIT_PROOF_BLOCKED
    for field in ("persistent_profitability_status", "ledger_status", "top_candidate_classification"):
        if result.get(field) == PROFIT_PROOF_PROVEN:
            result[field] = "UNVERIFIED"
    result["permissions"] = dict(PROTECTED_PERMISSION_FLAGS)
    result["owner_answer"] = (
        "Profit proof is blocked: independent candidate and source verification is unavailable. "
        "Summary metrics are diagnostic only. No execution or money authority is approved."
    )
    result["next_safe_action"] = _next_safe_action(PROFIT_PROOF_BLOCKED, PROFIT_PROOF_BLOCKED)
    blockers = list(dict.fromkeys([
        *(result.get("blockers") or []), "NO_INDEPENDENT_VERIFIER_CONNECTED"
    ]))
    lines = [
        "# AIOS Forex 110 Profit Evidence Truth Lock V1",
        "",
        f"Packet ID: `{result.get('packet_id', PACKET_ID)}`",
        f"Profit proof status: `{result.get('profit_proof_status')}`",
        f"Truth lock status: `{result.get('truth_lock_status')}`",
        f"Unverified diagnostic persistent profitability status: `{result.get('persistent_profitability_status')}`",
        f"Unverified diagnostic ledger status: `{result.get('ledger_status')}`",
        f"Top candidate: `{result.get('top_candidate_id')}`",
        f"Unverified diagnostic top candidate classification: `{result.get('top_candidate_classification')}`",
        "",
        "## Owner Answer",
        str(result.get("owner_answer", "")),
        "",
        "## Permission Locks",
    ]
    for key, value in (result.get("permissions") or {}).items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in blockers)
    lines.extend(["", "## Next Safe Action", str(result.get("next_safe_action", "")), ""])
    return "\n".join(lines)


def _next_safe_action(profit_proof_status: str, truth_lock_status: str) -> str:
    if profit_proof_status == PROFIT_PROOF_PROVEN:
        return (
            "Use this as operator review evidence only, then run the next "
            "truth-lock packet. Do not trade, compound, move money, or access "
            "credentials."
        )
    if truth_lock_status == PROFIT_PROOF_REVIEW_READY_PERSISTENCE_BLOCKED:
        return (
            "Collect sanitized persistent profitability period evidence or run "
            "the walk-forward/OOS sufficiency truth-lock. Do not trade, start "
            "runtime services, access credentials, compound, or move money."
        )
    return (
        "Obtain independent candidate/source/custody verification through the existing admitted "
        "evidence owner. Preserve economic blockers; labels and summary metrics are insufficient. "
        "Do not execute research, access proof data, or trade without separate admission."
    )


__all__ = [
    "ENGINE_VERSION",
    "PACKET_ID",
    "PROFIT_PROOF_BLOCKED",
    "PROFIT_PROOF_PROVEN",
    "PROFIT_PROOF_REVIEW_READY_PERSISTENCE_BLOCKED",
    "build_report_markdown",
    "run_profit_evidence_truth_lock",
]
