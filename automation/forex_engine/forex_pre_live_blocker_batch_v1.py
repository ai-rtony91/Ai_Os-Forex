"""Deterministic pre-live Forex blocker batch resolver V1.

This module consolidates the remaining pre-live checks into one local-only
review object. It resolves blocker visibility for owner review without creating
broker, credential, order, scheduler, daemon, webhook, or live-trading authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "AIOS_FOREX_PRE_LIVE_BLOCKER_BATCH_V1"
PRE_LIVE_REVIEW_READY = "FOREX_PRE_LIVE_REVIEW_READY"
PRE_LIVE_BLOCKED = "FOREX_PRE_LIVE_BLOCKED"
PRE_LIVE_INCOMPLETE = "FOREX_PRE_LIVE_INCOMPLETE"

REQUIRED_BATCH_INPUTS = (
    "final_readiness",
    "profit_production_gate",
    "demo_candidate_review",
    "runtime_supervision",
    "risk_controls",
)

READY_STATUS_FIELDS = {
    "final_readiness": {"FOREX_FINAL_READINESS_REVIEW_READY"},
    "profit_production_gate": {"READY_FOR_OWNER_REVIEW", "READY_FOR_DEMO_ONLY_NEXT_STEP"},
    "demo_candidate_review": {"FOREX_DEMO_CANDIDATE_REVIEW_READY", "DEMO_CANDIDATE_REVIEW_READY"},
    "runtime_supervision": {"FOREX_RUNTIME_ACTIVE_SUPERVISION_READY", "RUNTIME_ACTIVE_SUPERVISION_READY"},
    "risk_controls": {"RISK_CONTROLS_READY", "FOREX_RISK_CONTROLS_READY", "PASS"},
}

BLOCKER_KEYS = (
    "blockers",
    "closure_blockers",
    "candidate_blockers",
    "runtime_blockers",
    "risk_blockers",
    "missing_evidence",
    "stale_evidence",
)

FORBIDDEN_TRUE_FLAGS = (
    "live_trading_allowed",
    "live_trading_requested",
    "broker_execution_allowed",
    "broker_connection_allowed",
    "broker_api_call_allowed",
    "order_submission_allowed",
    "credential_access_allowed",
    "account_access_allowed",
    "money_movement_allowed",
    "scheduler_allowed",
    "daemon_allowed",
    "webhook_allowed",
    "owner_approval_created",
)

PERMISSIONS_FALSE = {
    "broker_execution_allowed": False,
    "broker_connection_allowed": False,
    "broker_api_call_allowed": False,
    "live_trading_allowed": False,
    "order_submission_allowed": False,
    "credential_access_allowed": False,
    "account_access_allowed": False,
    "money_movement_allowed": False,
    "scheduler_allowed": False,
    "daemon_allowed": False,
    "webhook_allowed": False,
    "owner_approval_created": False,
}


def build_sample_pre_live_batch_evidence() -> dict[str, Any]:
    """Return a safe passing sample for tests and dry-run demos."""

    return {
        "final_readiness": {"status": "FOREX_FINAL_READINESS_REVIEW_READY", "blockers": []},
        "profit_production_gate": {"status": "READY_FOR_OWNER_REVIEW", "blockers": []},
        "demo_candidate_review": {"status": "FOREX_DEMO_CANDIDATE_REVIEW_READY", "blockers": []},
        "runtime_supervision": {"status": "FOREX_RUNTIME_ACTIVE_SUPERVISION_READY", "blockers": []},
        "risk_controls": {"status": "RISK_CONTROLS_READY", "blockers": []},
        "operator_boundary": {
            "owner_review_required_before_any_execution": True,
            "sanitized_evidence_only": True,
            **PERMISSIONS_FALSE,
        },
    }


def evaluate_forex_pre_live_blocker_batch_v1(
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve pre-live blocker batch status from sanitized local evidence only."""

    data = dict(evidence or {})
    blockers: list[str] = []
    resolved: list[str] = []
    missing_inputs = [key for key in REQUIRED_BATCH_INPUTS if not isinstance(data.get(key), Mapping)]

    if missing_inputs:
        blockers.extend(f"missing_batch_input:{key}" for key in missing_inputs)

    blockers.extend(_forbidden_true_blockers(data, "evidence"))

    for key in REQUIRED_BATCH_INPUTS:
        item = data.get(key)
        if not isinstance(item, Mapping):
            continue
        status = str(item.get("status") or item.get(f"{key}_status") or "")
        if status not in READY_STATUS_FIELDS[key]:
            blockers.append(f"{key}_status_not_ready:{status or 'missing'}")
        child_blockers = _collect_child_blockers(item)
        if child_blockers:
            blockers.extend(f"{key}:{child}" for child in child_blockers)
        elif status in READY_STATUS_FIELDS[key]:
            resolved.append(key)

    boundary = data.get("operator_boundary")
    if not isinstance(boundary, Mapping):
        blockers.append("missing_operator_boundary")
    else:
        if boundary.get("owner_review_required_before_any_execution") is not True:
            blockers.append("owner_review_boundary_not_confirmed")
        if boundary.get("sanitized_evidence_only") is not True:
            blockers.append("sanitized_evidence_only_not_confirmed")

    unique_blockers = _unique(blockers)
    status = PRE_LIVE_INCOMPLETE if missing_inputs else (PRE_LIVE_BLOCKED if unique_blockers else PRE_LIVE_REVIEW_READY)
    return {
        "schema": SCHEMA,
        "status": status,
        "passed": status == PRE_LIVE_REVIEW_READY,
        "review_ready_only": status == PRE_LIVE_REVIEW_READY,
        "resolved_blockers": resolved if status == PRE_LIVE_REVIEW_READY else [],
        "remaining_blockers": unique_blockers,
        "missing_inputs": missing_inputs,
        "permissions": dict(PERMISSIONS_FALSE),
        **PERMISSIONS_FALSE,
        "next_safe_action": (
            "Prepare owner pre-live review brief only; do not execute trades."
            if status == PRE_LIVE_REVIEW_READY
            else "Resolve remaining pre-live blocker evidence before owner review."
        ),
    }


def _collect_child_blockers(item: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for key in BLOCKER_KEYS:
        blockers.extend(str(value) for value in _as_sequence(item.get(key)) if str(value))
    return _unique(blockers)


def _forbidden_true_blockers(value: Any, path: str) -> list[str]:
    blockers: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_TRUE_FLAGS and child is True:
                blockers.append(f"forbidden_true:{child_path}")
            blockers.extend(_forbidden_true_blockers(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            blockers.extend(_forbidden_true_blockers(child, f"{path}[{index}]"))
    return _unique(blockers)


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)):
        return [value]
    if isinstance(value, Sequence):
        return list(value)
    return [value]


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
