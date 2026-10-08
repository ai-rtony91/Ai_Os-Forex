"""Forex 110 walk-forward/OOS sufficiency truth lock.

This module reconciles local walk-forward/OOS evidence with the current profit
truth-lock top candidate. It is review-only and creates no trading authority.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from automation.forex_engine.profit_proof_ledger_v1 import ProfitProofCandidateEvidence

from automation.forex_engine.forex_110_profit_evidence_truth_lock_v1 import (
    run_profit_evidence_truth_lock,
)
from automation.forex_engine.walk_forward_evidence_intake_v1 import (
    DEFAULT_REPORT_ROOT,
    intake_walk_forward_evidence,
    result_to_jsonable_dict as intake_result_to_jsonable_dict,
)
from automation.forex_engine.walk_forward_oos_evidence_v1 import WALK_FORWARD_OOS_READY


PACKET_ID = "PKT-FOREX-110-WALKFORWARD-OOS-SUFFICIENCY-TRUTH-LOCK-V1"
ENGINE_VERSION = "forex_110_walkforward_oos_sufficiency_truth_lock_v1"

WALK_FORWARD_OOS_PROVEN = "PROVEN"
WALK_FORWARD_OOS_BLOCKED_MISSING_EVIDENCE = "BLOCKED_MISSING_EVIDENCE"
WALK_FORWARD_OOS_BLOCKED_INSUFFICIENT_EVIDENCE = "BLOCKED_INSUFFICIENT_EVIDENCE"
WALK_FORWARD_OOS_BLOCKED_TOP_CANDIDATE_MISMATCH = "BLOCKED_TOP_CANDIDATE_MISMATCH"

TRUTH_LOCK_PROVEN = "PROVEN"
TRUTH_LOCK_REVIEW_READY_WALKFORWARD_OOS_BLOCKED = "REVIEW_READY_WALKFORWARD_OOS_BLOCKED"
TRUTH_LOCK_REVIEW_READY_WALKFORWARD_OOS_CANDIDATE_MISMATCH = (
    "REVIEW_READY_WALKFORWARD_OOS_CANDIDATE_MISMATCH"
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

REQUIRED_SUFFICIENCY_FIELDS = (
    "windows_total",
    "windows_passed",
    "oos_segments_total",
    "oos_segments_passed",
    "min_pass_rate",
    "max_drawdown",
    "max_allowed_drawdown",
    "sanitized",
    "evidence_age_days",
    "max_evidence_age_days",
)

CANONICAL_OWNER_FILE = "automation/forex_engine/walk_forward_evidence_intake_v1.py"
TEST_FILE = "tests/forex_engine/test_forex_110_walkforward_oos_sufficiency_truth_lock_v1.py"
RUNNER_SCRIPT = "scripts/forex_delivery/run_forex_110_walkforward_oos_sufficiency_truth_lock_v1.py"


def run_walkforward_oos_sufficiency_truth_lock(
    report_root: str | Path = DEFAULT_REPORT_ROOT,
    candidates: Sequence[ProfitProofCandidateEvidence | Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the Forex 110 walk-forward/OOS sufficiency truth state."""

    root = Path(report_root)
    intake = intake_result_to_jsonable_dict(intake_walk_forward_evidence(root))
    profit_lock = run_profit_evidence_truth_lock(root, candidates)
    top_candidate_id = str(profit_lock.get("top_candidate_id") or "NONE")
    source_files = list(intake.get("source_files") or [])
    source_candidates = _candidate_ids_from_sources(root, source_files)
    alignment = _top_candidate_alignment(top_candidate_id, source_candidates)
    missing_fields = _missing_sufficiency_fields(intake)
    blockers = _dedupe(
        list(intake.get("blockers") or [])
        + [f"missing evidence field: {field}" for field in missing_fields]
    )

    if intake.get("status") == WALK_FORWARD_OOS_READY and alignment["aligned"]:
        walk_forward_oos_status = WALK_FORWARD_OOS_PROVEN
        truth_lock_status = TRUTH_LOCK_PROVEN
        profit_persistence_unlocked = True
        blockers = []
    elif not alignment["aligned"]:
        walk_forward_oos_status = WALK_FORWARD_OOS_BLOCKED_TOP_CANDIDATE_MISMATCH
        truth_lock_status = TRUTH_LOCK_REVIEW_READY_WALKFORWARD_OOS_CANDIDATE_MISMATCH
        profit_persistence_unlocked = False
        blockers = _dedupe(blockers + [alignment["blocker"]])
    elif missing_fields:
        walk_forward_oos_status = WALK_FORWARD_OOS_BLOCKED_MISSING_EVIDENCE
        truth_lock_status = TRUTH_LOCK_REVIEW_READY_WALKFORWARD_OOS_BLOCKED
        profit_persistence_unlocked = False
    else:
        walk_forward_oos_status = WALK_FORWARD_OOS_BLOCKED_INSUFFICIENT_EVIDENCE
        truth_lock_status = TRUTH_LOCK_REVIEW_READY_WALKFORWARD_OOS_BLOCKED
        profit_persistence_unlocked = False

    missing_evidence_field = _missing_evidence_field(missing_fields, alignment)
    attack_to_finish = _attack_to_finish(
        walk_forward_oos_status=walk_forward_oos_status,
        missing_evidence_field=missing_evidence_field,
        exact_blocker="NONE" if not blockers else "; ".join(blockers),
    )
    return {
        "packet_id": PACKET_ID,
        "engine_version": ENGINE_VERSION,
        "walk_forward_oos_status": walk_forward_oos_status,
        "profit_persistence_unlocked": profit_persistence_unlocked,
        "truth_lock_status": truth_lock_status,
        "top_candidate_alignment": alignment,
        "top_candidate_id": top_candidate_id,
        "walkforward_source_candidate_ids": source_candidates,
        "evidence_missing": missing_fields,
        "blockers": blockers,
        "normalized_walkforward_oos_summary": dict(intake.get("normalized_summary") or {}),
        "walkforward_intake_status": intake.get("status"),
        "walkforward_intake_missing_fields": list(intake.get("missing_fields") or []),
        "walkforward_intake_blockers": list(intake.get("blockers") or []),
        "walkforward_intake_parse_notes": list(intake.get("parse_notes") or []),
        "profit_truth_lock_status": profit_lock.get("truth_lock_status"),
        "profit_proof_status": profit_lock.get("profit_proof_status"),
        "persistent_profitability_status": profit_lock.get("persistent_profitability_status"),
        "source_files": source_files,
        "permissions": dict(PROTECTED_PERMISSION_FLAGS),
        **PROTECTED_PERMISSION_FLAGS,
        "attack_to_finish": attack_to_finish,
        "next_safe_action": _next_safe_action(walk_forward_oos_status),
    }


def build_report_markdown(result: Mapping[str, Any]) -> str:
    """Build an operator-readable truth-lock report."""

    blockers = result.get("blockers") or ["none"]
    attack = result.get("attack_to_finish") or {}
    lines = [
        "# AIOS Forex 110 Walk-Forward/OOS Sufficiency Truth Lock V1",
        "",
        f"Packet ID: `{result.get('packet_id', PACKET_ID)}`",
        f"Walk-forward/OOS status: `{result.get('walk_forward_oos_status')}`",
        f"Profit persistence unlocked: `{str(result.get('profit_persistence_unlocked')).lower()}`",
        f"Truth lock status: `{result.get('truth_lock_status')}`",
        f"Top candidate: `{result.get('top_candidate_id')}`",
        f"Top candidate alignment: `{_alignment_label(result.get('top_candidate_alignment'))}`",
        "",
        "## Evidence Missing",
    ]
    lines.extend(f"- {item}" for item in result.get("evidence_missing") or ["none"])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in blockers)
    lines.extend(["", "## Permission Locks"])
    for key, value in (result.get("permissions") or {}).items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.extend(
        [
            "",
            "## ATTACK_TO_FINISH",
            f"- blocker_id: {attack.get('blocker_id', 'UNKNOWN')}",
            f"- blocker_status: {attack.get('blocker_status', 'UNKNOWN')}",
            f"- exact_blocker: {attack.get('exact_blocker', 'UNKNOWN')}",
            f"- canonical_owner_file: {attack.get('canonical_owner_file', 'UNKNOWN')}",
            f"- test_file: {attack.get('test_file', 'UNKNOWN')}",
            f"- runner_script: {attack.get('runner_script', 'UNKNOWN')}",
            f"- missing_evidence_field: {attack.get('missing_evidence_field', 'UNKNOWN')}",
            f"- unlock_status_required: {attack.get('unlock_status_required', 'UNKNOWN')}",
            f"- next_packet_name: {attack.get('next_packet_name', 'UNKNOWN')}",
            f"- owner_action_required: {attack.get('owner_action_required', 'UNKNOWN')}",
            f"- stop_condition: {attack.get('stop_condition', 'UNKNOWN')}",
            f"- no_bloat_guard: {attack.get('no_bloat_guard', 'UNKNOWN')}",
            "",
            "## Next Safe Action",
            str(result.get("next_safe_action", "")),
            "",
        ]
    )
    return "\n".join(lines)


def _candidate_ids_from_sources(root: Path, source_files: list[str]) -> list[str]:
    candidates: list[str] = []
    for source in source_files:
        path = Path(source)
        if not path.is_absolute():
            path = root.parent.parent / path if source.startswith("Reports/") else root / path
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        candidates.extend(_candidate_ids_from_text(text))
    return _dedupe(candidates)


def _candidate_ids_from_text(text: str) -> list[str]:
    patterns = (
        re.compile(r"(?im)^\s*-\s*(?:candidate|candidate_id|anchor candidate|selected_candidate_id)\s*:\s*`?([^`\n.]+?)`?\s*$"),
        re.compile(r"(?im)\|\s*(c[0-9]+-[a-z0-9-]+)\s*\|"),
    )
    candidates: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = match.group(1).strip()
            if re.fullmatch(r"c[0-9]+-[a-z0-9-]+", value):
                candidates.append(value)
    return _dedupe(candidates)


def _top_candidate_alignment(top_candidate_id: str, source_candidates: list[str]) -> dict[str, Any]:
    if top_candidate_id == "NONE":
        return {
            "aligned": False,
            "status": "MISSING_TOP_CANDIDATE",
            "blocker": "profit truth lock did not provide a top candidate",
        }
    if not source_candidates:
        return {
            "aligned": False,
            "status": "MISSING_WALKFORWARD_CANDIDATE_ID",
            "blocker": "walk-forward/OOS evidence does not name a candidate_id",
        }
    if top_candidate_id in source_candidates:
        return {
            "aligned": True,
            "status": "ALIGNED",
            "blocker": "NONE",
        }
    return {
        "aligned": False,
        "status": "MISMATCHED",
        "blocker": (
            "walk-forward/OOS evidence candidate ids "
            f"{', '.join(source_candidates)} do not match top candidate {top_candidate_id}"
        ),
    }


def _missing_sufficiency_fields(intake: Mapping[str, Any]) -> list[str]:
    normalized = intake.get("normalized_summary")
    if not isinstance(normalized, Mapping):
        normalized = {}
    missing = [field for field in REQUIRED_SUFFICIENCY_FIELDS if field not in normalized]
    for field in intake.get("missing_fields") or []:
        if field not in missing:
            missing.append(str(field))
    return missing


def _missing_evidence_field(missing_fields: list[str], alignment: Mapping[str, Any]) -> str:
    if missing_fields:
        return ",".join(missing_fields)
    if alignment.get("status") == "MISSING_WALKFORWARD_CANDIDATE_ID":
        return "candidate_id"
    if alignment.get("status") == "MISMATCHED":
        return "candidate_alignment"
    if alignment.get("status") == "MISSING_TOP_CANDIDATE":
        return "top_candidate_id"
    return "NONE"


def _attack_to_finish(
    *,
    walk_forward_oos_status: str,
    missing_evidence_field: str,
    exact_blocker: str,
) -> dict[str, str]:
    proven = walk_forward_oos_status == WALK_FORWARD_OOS_PROVEN
    if proven:
        blocker_id = "NO_BLOCKER"
        blocker_status = "PROVEN"
        unlock_status_required = "PROVEN"
        next_packet_name = "NONE"
        owner_action_required = "NONE"
        stop_condition = "NONE"
    else:
        blocker_id = (
            "MISSING_EVIDENCE_FIELD"
            if missing_evidence_field not in {"NONE", "candidate_alignment"}
            else "PACKET_CHAIN_GAP"
        )
        blocker_status = "BLOCKED"
        unlock_status_required = "PROVEN"
        next_packet_name = "PKT-FOREX-110-TOP-CANDIDATE-WALKFORWARD-OOS-EVIDENCE-COLLECTION-V1"
        owner_action_required = "provide missing field " + missing_evidence_field
        stop_condition = "walk-forward/OOS sufficiency not proven"
    return {
        "blocker_id": blocker_id,
        "blocker_status": blocker_status,
        "exact_blocker": exact_blocker,
        "canonical_owner_file": CANONICAL_OWNER_FILE,
        "test_file": TEST_FILE,
        "runner_script": RUNNER_SCRIPT,
        "missing_evidence_field": missing_evidence_field,
        "unlock_status_required": unlock_status_required,
        "next_packet_name": next_packet_name,
        "owner_action_required": owner_action_required,
        "stop_condition": stop_condition,
        "no_bloat_guard": "Reuse walk_forward_evidence_intake_v1 and do not create duplicate walk-forward engines.",
    }


def _next_safe_action(walk_forward_oos_status: str) -> str:
    if walk_forward_oos_status == WALK_FORWARD_OOS_PROVEN:
        return (
            "Use this as review-only evidence for the persistent profitability "
            "period proof chain. Do not trade, access credentials, compound, or move money."
        )
    return (
        "Collect sanitized walk-forward/OOS evidence for the current profit-ledger "
        "top candidate, including candidate_id, OOS segment counts, pass counts, "
        "regime coverage, sample depth, and freshness. Do not trade."
    )


def _alignment_label(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("status", "UNKNOWN"))
    return "UNKNOWN"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


__all__ = [
    "ENGINE_VERSION",
    "PACKET_ID",
    "TRUTH_LOCK_PROVEN",
    "TRUTH_LOCK_REVIEW_READY_WALKFORWARD_OOS_BLOCKED",
    "TRUTH_LOCK_REVIEW_READY_WALKFORWARD_OOS_CANDIDATE_MISMATCH",
    "WALK_FORWARD_OOS_BLOCKED_INSUFFICIENT_EVIDENCE",
    "WALK_FORWARD_OOS_BLOCKED_MISSING_EVIDENCE",
    "WALK_FORWARD_OOS_BLOCKED_TOP_CANDIDATE_MISMATCH",
    "WALK_FORWARD_OOS_PROVEN",
    "build_report_markdown",
    "run_walkforward_oos_sufficiency_truth_lock",
]
