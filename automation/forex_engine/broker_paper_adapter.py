from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping

from automation.forex_engine import broker_paper_adapter_plan_approval_gate
from automation.forex_engine import schema_contracts as schemas


PACKET_ID = "PKT-AIOS-BROKER-PAPER-ADAPTER-IMPLEMENTATION-V1"
BROKER_PAPER_ADAPTER_READY = "BROKER_PAPER_ADAPTER_READY"
BROKER_PAPER_ADAPTER_BLOCKED = "BROKER_PAPER_ADAPTER_BLOCKED"
ALLOWED_CLASSIFICATIONS = {
    "FAIL",
    "WATCHLIST",
    BROKER_PAPER_ADAPTER_READY,
    BROKER_PAPER_ADAPTER_BLOCKED,
}
FORBIDDEN_CLASSIFICATIONS = {
    "LIVE_READY",
    "BROKER_READY",
    "ORDER_READY",
    "AUTO_TRADE_READY",
}
SUPPORTED_DIRECTIONS = ("BUY", "SHORT", "LONG")
LEGACY_DIRECTION_ALIASES = {"SELL": "SHORT"}
ALLOWED_INSTRUMENTS = ("EUR_USD", "GBP_USD", "USD_JPY")
RECEIPT_TYPES = ("intent", "submission", "acknowledgement", "rejection", "error", "final")
LONG_VALIDATION_PENDING = "LONG_VALIDATION_PENDING"
PAPER_DEMO_FINAL_READY = "PAPER_DEMO_FINAL_READY"
PAPER_DEMO_FINAL_BLOCKED = "PAPER_DEMO_FINAL_BLOCKED"
PAPER_DEMO_FINAL_ERROR = "PAPER_DEMO_FINAL_ERROR"
PAPER_DEMO_SUBMISSION_RECORDED = "PAPER_DEMO_SUBMISSION_RECORDED"
PAPER_DEMO_SUBMISSION_BLOCKED = "PAPER_DEMO_SUBMISSION_BLOCKED"
PAPER_DEMO_ACKNOWLEDGED = "PAPER_DEMO_ACKNOWLEDGED"
PAPER_DEMO_REJECTED = "PAPER_DEMO_REJECTED"
PAPER_DEMO_ERROR = "PAPER_DEMO_ERROR"
PAPER_DEMO_INTENT_RECORDED = "PAPER_DEMO_INTENT_RECORDED"
APPROVED_OWNER = "Anthony Meza"

FORBIDDEN_FIELD_NAMES = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
    "private_key",
    "credential",
    "credentials",
    "broker_credentials",
    "account_id",
    "account_number",
    "live_account_id",
    "broker_order_id",
    "live_payload",
    "raw_live_payload",
}


def build_broker_paper_adapter_contract() -> dict[str, Any]:
    contract = {
        "schema": "AIOS_BROKER_PAPER_ADAPTER_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "mode": "PAPER_ONLY_BROKER_PAPER_ADAPTER",
        "paper_only": True,
        "supported_directions": list(SUPPORTED_DIRECTIONS),
        "legacy_direction_aliases": dict(LEGACY_DIRECTION_ALIASES),
        "supported_instruments": list(ALLOWED_INSTRUMENTS),
        "plan_gate_required": True,
        "paper_demo_verification_required": True,
        "owner_checkpoint_required": True,
        "receipt_chain_required": True,
        "broker_sdk_allowed": False,
        "network_api_allowed": False,
        "credentials_allowed": False,
        "env_secret_read_allowed": False,
        "paper_broker_writes_allowed": False,
        "live_broker_writes_allowed": False,
        "broker_orders_allowed": False,
        "live_execution_allowed": False,
        "execution_allowed": False,
        "broker_request_sent": False,
        "network_used": False,
        "credentials_used": False,
        "broker_writes": 0,
        "live_ready": False,
        "live_trade_ready": False,
        "real_order_ready": False,
        "evidence_storage": "IN_MEMORY_ONLY",
        "next_safe_packet_if_ready": "FOREX-LONG-RUN-PAPER-SUPERVISOR",
        "next_safe_action_if_ready": "RUN_PAPER_LONG_FORM_VALIDATION_CYCLE",
        "next_safe_action_if_blocked": "REPAIR_BROKER_PAPER_ADAPTER_GUARDS",
        "safety_invariants": broker_paper_adapter_boundary_summary(),
    }
    schemas.assert_no_live_permissions(contract)
    return contract


def build_default_broker_paper_adapter_result() -> dict[str, Any]:
    return evaluate_broker_paper_adapter(
        request=_demo_request("BUY"),
        plan_gate_result=_demo_plan_gate_result(),
        paper_demo_verification=_demo_paper_demo_verification(),
        owner_checkpoint=_demo_owner_checkpoint(),
    )


def evaluate_broker_paper_adapter(
    request: Mapping[str, Any] | None = None,
    plan_gate_result: Mapping[str, Any] | None = None,
    paper_demo_verification: Mapping[str, Any] | None = None,
    owner_checkpoint: Mapping[str, Any] | None = None,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    active_contract = dict(contract or build_broker_paper_adapter_contract())
    active_request = dict(request or {})
    active_plan_gate = dict(
        plan_gate_result
        or broker_paper_adapter_plan_approval_gate.build_default_broker_paper_adapter_plan_approval_gate_result()
    )
    active_verification = dict(paper_demo_verification or {})
    active_checkpoint = dict(owner_checkpoint or {})

    request_fingerprint = _fingerprint(
        {
            "request": _normalize_request(active_request),
            "plan_gate": _minimal_plan_gate_view(active_plan_gate),
            "paper_demo_verification": _sanitize_verification(active_verification),
            "owner_checkpoint": _sanitize_checkpoint(active_checkpoint),
            "contract": _minimal_contract_view(active_contract),
        }
    )
    intent_id = f"AIOS-BROKER-PAPER-INTENT-{request_fingerprint[:12].upper()}"
    normalized_request = _normalize_request(active_request)

    blockers = _evaluation_blockers(
        normalized_request,
        active_request,
        active_plan_gate,
        active_verification,
        active_checkpoint,
        active_contract,
    )

    final_state = PAPER_DEMO_FINAL_READY
    submission_state = PAPER_DEMO_SUBMISSION_RECORDED
    acknowledgement_state: str | None = PAPER_DEMO_ACKNOWLEDGED
    rejection_state: str | None = None
    error_state: str | None = None
    classification = BROKER_PAPER_ADAPTER_READY
    broker_request_sent = False
    network_used = False
    credentials_used = False
    broker_writes = 0
    long_validation_pending = (
        normalized_request["side"] == "LONG"
        and not normalized_request["flags"].get("long_validation_ready", False)
    )

    if blockers or long_validation_pending:
        submission_state = PAPER_DEMO_SUBMISSION_BLOCKED
        acknowledgement_state = None
        rejection_state = PAPER_DEMO_REJECTED
        classification = BROKER_PAPER_ADAPTER_BLOCKED
        final_state = PAPER_DEMO_FINAL_BLOCKED
        if long_validation_pending and "long_validation_required" not in blockers:
            blockers.append("long_validation_required")
        broker_request_sent = False
    else:
        submission_state = PAPER_DEMO_SUBMISSION_RECORDED
        acknowledgement_state = PAPER_DEMO_ACKNOWLEDGED
        rejection_state = None
        classification = BROKER_PAPER_ADAPTER_READY
        final_state = PAPER_DEMO_FINAL_READY

    intent_receipt = _build_receipt(
        "intent",
        PAPER_DEMO_INTENT_RECORDED,
        intent_id,
        request_fingerprint,
        normalized_request,
        previous_receipt_id=None,
        blockers=blockers,
        broker_request_sent=False,
        network_used=False,
        credentials_used=False,
    )
    submission_receipt = _build_receipt(
        "submission",
        submission_state,
        intent_id,
        request_fingerprint,
        normalized_request,
        previous_receipt_id=intent_receipt["receipt_id"],
        blockers=blockers,
        broker_request_sent=False,
        network_used=False,
        credentials_used=False,
    )

    acknowledgement_receipt = (
        _build_receipt(
            "acknowledgement",
            acknowledgement_state,
            intent_id,
            request_fingerprint,
            normalized_request,
            previous_receipt_id=submission_receipt["receipt_id"],
            blockers=[],
            broker_request_sent=False,
            network_used=False,
            credentials_used=False,
        )
        if acknowledgement_state
        else None
    )
    rejection_receipt = (
        _build_receipt(
            "rejection",
            rejection_state,
            intent_id,
            request_fingerprint,
            normalized_request,
            previous_receipt_id=submission_receipt["receipt_id"],
            blockers=blockers,
            broker_request_sent=False,
            network_used=False,
            credentials_used=False,
        )
        if rejection_state
        else None
    )
    error_receipt = (
        _build_receipt(
            "error",
            error_state or PAPER_DEMO_ERROR,
            intent_id,
            request_fingerprint,
            normalized_request,
            previous_receipt_id=submission_receipt["receipt_id"],
            blockers=["internal_adapter_error"],
            broker_request_sent=False,
            network_used=False,
            credentials_used=False,
        )
        if error_state
        else None
    )

    final_receipt = _build_receipt(
        "final",
        final_state,
        intent_id,
        request_fingerprint,
        normalized_request,
        previous_receipt_id=(
            acknowledgement_receipt["receipt_id"]
            if acknowledgement_receipt is not None
            else rejection_receipt["receipt_id"]
            if rejection_receipt is not None
            else error_receipt["receipt_id"]
            if error_receipt is not None
            else submission_receipt["receipt_id"]
        ),
        blockers=blockers,
        broker_request_sent=False,
        network_used=False,
        credentials_used=False,
        final_state=final_state,
        classification=classification,
    )

    evidence_bundle = {
        "schema": "AIOS_BROKER_PAPER_ADAPTER_EVIDENCE_BUNDLE.v1",
        "packet_id": PACKET_ID,
        "mode": active_contract["mode"],
        "paper_only": True,
        "live_execution_allowed": False,
        "paper_broker_writes_allowed": False,
        "live_broker_writes_allowed": False,
        "broker_writes": 0,
        "request_fingerprint": request_fingerprint,
        "intent_id": intent_id,
        "classification": classification,
        "final_state": final_state,
        "receipt_chain": _receipt_chain(intent_receipt, submission_receipt, acknowledgement_receipt, rejection_receipt, error_receipt, final_receipt),
        "receipt_chain_complete": True,
        "sanitized": True,
        "contains_private_data": False,
        "contains_real_credentials": False,
    }
    _assert_evidence_chain(evidence_bundle)

    result = {
        "schema": "AIOS_BROKER_PAPER_ADAPTER_RESULT.v1",
        "packet_id": PACKET_ID,
        "mode": active_contract["mode"],
        "classification": classification,
        "broker_paper_adapter_ready": classification == BROKER_PAPER_ADAPTER_READY,
        "paper_only": True,
        "live_execution_allowed": False,
        "paper_broker_writes_allowed": False,
        "live_broker_writes_allowed": False,
        "broker_writes": 0,
        "broker_sdk_allowed": False,
        "network_api_allowed": False,
        "credentials_allowed": False,
        "network_used": network_used,
        "credentials_used": credentials_used,
        "broker_request_sent": broker_request_sent,
        "live_ready": False,
        "live_trade_ready": False,
        "real_order_ready": False,
        "plan_gate_ready": _plan_gate_ready(active_plan_gate),
        "paper_demo_verification_ready": _paper_demo_verification_ready(active_verification),
        "owner_checkpoint_ready": _owner_checkpoint_ready(active_checkpoint),
        "normalized_request": normalized_request,
        "request_fingerprint": request_fingerprint,
        "intent_id": intent_id,
        "submission_state": submission_state,
        "acknowledgement_state": acknowledgement_state,
        "rejection_state": rejection_state,
        "error_state": error_state,
        "final_state": final_state,
        "long_validation_pending": long_validation_pending,
        "blockers": blockers,
        "intent_receipt": intent_receipt,
        "submission_receipt": submission_receipt,
        "acknowledgement_receipt": acknowledgement_receipt,
        "rejection_receipt": rejection_receipt,
        "error_receipt": error_receipt,
        "final_receipt": final_receipt,
        "evidence_bundle": evidence_bundle,
        "next_safe_packet": (
            "FOREX-LONG-RUN-PAPER-SUPERVISOR"
            if classification == BROKER_PAPER_ADAPTER_READY
            else PACKET_ID
        ),
        "next_safe_action": (
            "RUN_PAPER_LONG_FORM_VALIDATION_CYCLE"
            if classification == BROKER_PAPER_ADAPTER_READY
            else "REPAIR_BROKER_PAPER_ADAPTER_GUARDS"
        ),
    }
    schemas.assert_no_live_permissions(result)
    return result


def summarize_broker_paper_adapter(result: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(result or build_default_broker_paper_adapter_result())
    summary = {
        "schema": "AIOS_BROKER_PAPER_ADAPTER_SUMMARY.v1",
        "packet_id": PACKET_ID,
        "mode": str(payload.get("mode") or "PAPER_ONLY_BROKER_PAPER_ADAPTER"),
        "classification": str(payload.get("classification") or "WATCHLIST"),
        "broker_paper_adapter_ready": payload.get("broker_paper_adapter_ready") is True,
        "paper_only": payload.get("paper_only") is True,
        "live_execution_allowed": payload.get("live_execution_allowed") is True,
        "paper_broker_writes_allowed": payload.get("paper_broker_writes_allowed") is True,
        "live_broker_writes_allowed": payload.get("live_broker_writes_allowed") is True,
        "broker_writes": int(payload.get("broker_writes", 0) or 0),
        "broker_sdk_allowed": payload.get("broker_sdk_allowed") is True,
        "network_api_allowed": payload.get("network_api_allowed") is True,
        "credentials_allowed": payload.get("credentials_allowed") is True,
        "network_used": payload.get("network_used") is True,
        "credentials_used": payload.get("credentials_used") is True,
        "broker_request_sent": payload.get("broker_request_sent") is True,
        "plan_gate_ready": payload.get("plan_gate_ready") is True,
        "paper_demo_verification_ready": payload.get("paper_demo_verification_ready") is True,
        "owner_checkpoint_ready": payload.get("owner_checkpoint_ready") is True,
        "submission_state": str(payload.get("submission_state") or PAPER_DEMO_SUBMISSION_BLOCKED),
        "acknowledgement_state": payload.get("acknowledgement_state"),
        "rejection_state": payload.get("rejection_state"),
        "error_state": payload.get("error_state"),
        "final_state": str(payload.get("final_state") or PAPER_DEMO_FINAL_BLOCKED),
        "long_validation_pending": payload.get("long_validation_pending") is True,
        "blockers": list(payload.get("blockers") or []),
        "receipt_chain_complete": bool(
            dict(payload.get("evidence_bundle") or {}).get("receipt_chain_complete", False)
        ),
        "next_safe_packet": str(payload.get("next_safe_packet") or PACKET_ID),
        "next_safe_action": str(payload.get("next_safe_action") or "REPAIR_BROKER_PAPER_ADAPTER_GUARDS"),
    }
    summary["classification"] = classify_broker_paper_adapter(summary)
    if summary["classification"] == BROKER_PAPER_ADAPTER_READY:
        summary["next_safe_packet"] = "FOREX-LONG-RUN-PAPER-SUPERVISOR"
        summary["next_safe_action"] = "RUN_PAPER_LONG_FORM_VALIDATION_CYCLE"
    else:
        summary["next_safe_packet"] = PACKET_ID
        summary["next_safe_action"] = "REPAIR_BROKER_PAPER_ADAPTER_GUARDS"
    schemas.assert_no_live_permissions(summary)
    return summary


def classify_broker_paper_adapter(result: Mapping[str, Any] | None = None) -> str:
    if result is None:
        return classify_broker_paper_adapter(summarize_broker_paper_adapter())

    payload = dict(result)
    candidate = str(payload.get("classification") or "WATCHLIST")
    if candidate in FORBIDDEN_CLASSIFICATIONS:
        return "FAIL"
    if candidate not in ALLOWED_CLASSIFICATIONS:
        return "FAIL"
    if _has_forbidden_effect(payload):
        return "FAIL"
    if payload.get("paper_only") is not True:
        return "FAIL"
    if payload.get("live_execution_allowed") is True:
        return "FAIL"
    if payload.get("live_broker_writes_allowed") is True or payload.get("paper_broker_writes_allowed") is True:
        return "FAIL"
    if payload.get("broker_sdk_allowed") is True:
        return "FAIL"
    if payload.get("network_api_allowed") is True or payload.get("network_used") is True:
        return "FAIL"
    if payload.get("credentials_allowed") is True or payload.get("credentials_used") is True:
        return "FAIL"
    blockers = list(payload.get("blockers") or [])
    if blockers or payload.get("final_state") in {PAPER_DEMO_FINAL_BLOCKED, PAPER_DEMO_FINAL_ERROR}:
        return BROKER_PAPER_ADAPTER_BLOCKED
    return BROKER_PAPER_ADAPTER_READY


def broker_paper_adapter_boundary_summary() -> dict[str, Any]:
    return {
        "schema": "AIOS_BROKER_PAPER_ADAPTER_BOUNDARY.v1",
        "mode": "PAPER_ONLY_BROKER_PAPER_ADAPTER",
        "paper_only": True,
        "paper_demo_only": True,
        "contract_only": True,
        "plan_gate_required": True,
        "paper_demo_verification_required": True,
        "owner_checkpoint_required": True,
        "receipt_chain_required": True,
        "broker_integration_active": False,
        "broker_sdk_allowed": False,
        "network_allowed": False,
        "network_api_allowed": False,
        "credentials_allowed": False,
        "credentials_used": False,
        "env_secret_read_allowed": False,
        "paper_broker_writes_allowed": False,
        "live_broker_writes_allowed": False,
        "broker_orders_allowed": False,
        "live_execution_allowed": False,
        "execution_allowed": False,
        "broker_request_sent": False,
        "network_used": False,
        "broker_writes": 0,
        "live_ready": False,
        "live_trade_ready": False,
        "real_order_ready": False,
        "would_place_order": False,
        "order_placed": False,
        "receipt_types": list(RECEIPT_TYPES),
        "supported_directions": list(SUPPORTED_DIRECTIONS),
        "supported_instruments": list(ALLOWED_INSTRUMENTS),
        "next_safe_packet_if_ready": "FOREX-LONG-RUN-PAPER-SUPERVISOR",
    }


def _demo_request(side: str) -> dict[str, Any]:
    return {
        "request_id": f"demo-{side.lower()}-paper-adapter",
        "symbol": "EUR_USD",
        "side": side,
        "quantity_units": 1,
        "stop_loss_pips": 8.0,
        "take_profit_pips": 12.0,
        "max_loss_usd": 10.0,
        "paper_only": True,
        "live_execution_allowed": False,
        "paper_broker_writes_allowed": False,
        "broker_writes_allowed": False,
        "broker_sdk_allowed": False,
        "network_api_allowed": False,
        "credentials_allowed": False,
        "dry_run": True,
        "long_validation_ready": side.upper() != "LONG",
    }


def _demo_plan_gate_result() -> dict[str, Any]:
    approval = broker_paper_adapter_plan_approval_gate.build_example_plan_only_approval()
    return broker_paper_adapter_plan_approval_gate.evaluate_broker_paper_adapter_plan_approval_gate(
        approval=approval
    )


def _demo_paper_demo_verification() -> dict[str, Any]:
    return {
        "paper_only": True,
        "environment": "PAPER",
        "broker_environment": "paper",
        "endpoint_live": False,
        "broker_endpoint_live": False,
        "account_mode": "PAPER_DEMO",
        "verified_by_human_owner": True,
        "live_execution_allowed": False,
        "live_broker_writes_allowed": False,
        "broker_writes_allowed": False,
        "broker_sdk_allowed": False,
        "network_api_allowed": False,
        "credentials_allowed": False,
    }


def _demo_owner_checkpoint() -> dict[str, Any]:
    return {
        "paper_demo_execution_phase": True,
        "human_owner_approved": True,
        "approved_by_human_owner": APPROVED_OWNER,
        "approval_scope": "broker_paper_adapter_implementation_only",
        "mode": "PAPER_ONLY",
        "live_execution_allowed": False,
        "broker_writes_allowed": False,
    }


def _normalize_request(request: Mapping[str, Any]) -> dict[str, Any]:
    raw_side = str(request.get("side") or request.get("direction") or "").strip().upper()
    normalized_side = LEGACY_DIRECTION_ALIASES.get(raw_side, raw_side)
    quantity_units = _int_or_none(request.get("quantity_units") or request.get("units"))
    stop_loss_pips = _float_or_none(request.get("stop_loss_pips"))
    take_profit_pips = _float_or_none(request.get("take_profit_pips"))
    max_loss_usd = _float_or_none(request.get("max_loss_usd"))
    flags = {
        "long_validation_ready": bool(request.get("long_validation_ready", False)),
    }
    return {
        "request_id": str(request.get("request_id") or "").strip(),
        "symbol": str(request.get("symbol") or "").strip().upper(),
        "raw_side": raw_side,
        "side": normalized_side,
        "quantity_units": quantity_units,
        "stop_loss_pips": stop_loss_pips,
        "take_profit_pips": take_profit_pips,
        "max_loss_usd": max_loss_usd,
        "paper_only": bool(request.get("paper_only", True)),
        "live_execution_allowed": bool(request.get("live_execution_allowed", False)),
        "paper_broker_writes_allowed": bool(request.get("paper_broker_writes_allowed", False)),
        "live_broker_writes_allowed": bool(request.get("live_broker_writes_allowed", False)),
        "broker_writes_allowed": bool(request.get("broker_writes_allowed", False)),
        "broker_sdk_allowed": bool(request.get("broker_sdk_allowed", False)),
        "network_api_allowed": bool(request.get("network_api_allowed", False)),
        "credentials_allowed": bool(request.get("credentials_allowed", False)),
        "dry_run": bool(request.get("dry_run", True)),
        "flags": flags,
    }


def _evaluation_blockers(
    normalized_request: Mapping[str, Any],
    raw_request: Mapping[str, Any],
    plan_gate: Mapping[str, Any],
    verification: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []

    if not _plan_gate_ready(plan_gate):
        blockers.append("plan_gate_not_ready")
    if not _paper_demo_verification_ready(verification):
        blockers.append("paper_demo_verification_not_ready")
    if not _owner_checkpoint_ready(checkpoint):
        blockers.append("owner_checkpoint_not_ready")

    if not normalized_request.get("symbol"):
        blockers.append("symbol_required")
    elif str(normalized_request.get("symbol")) not in set(contract.get("supported_instruments") or ALLOWED_INSTRUMENTS):
        blockers.append("instrument_not_allowlisted")

    side = str(normalized_request.get("side") or "")
    if side not in set(contract.get("supported_directions") or SUPPORTED_DIRECTIONS):
        blockers.append("direction_not_supported")

    quantity_units = normalized_request.get("quantity_units")
    if not isinstance(quantity_units, int) or int(quantity_units) <= 0:
        blockers.append("quantity_units_must_be_positive")

    stop_loss_pips = normalized_request.get("stop_loss_pips")
    if not _positive_number(stop_loss_pips):
        blockers.append("stop_loss_pips_required")

    max_loss_usd = normalized_request.get("max_loss_usd")
    if not _positive_number(max_loss_usd):
        blockers.append("max_loss_usd_required")

    take_profit_pips = normalized_request.get("take_profit_pips")
    if take_profit_pips is not None and not _positive_number(take_profit_pips):
        blockers.append("take_profit_pips_must_be_positive_when_provided")

    if not bool(normalized_request.get("paper_only")):
        blockers.append("paper_only_required")
    if bool(normalized_request.get("live_execution_allowed")):
        blockers.append("live_execution_blocked")
    if bool(normalized_request.get("paper_broker_writes_allowed")):
        blockers.append("paper_broker_writes_must_remain_blocked")
    if bool(normalized_request.get("live_broker_writes_allowed")):
        blockers.append("live_broker_writes_blocked")
    if bool(normalized_request.get("broker_writes_allowed")):
        blockers.append("broker_writes_must_remain_blocked")
    if bool(normalized_request.get("broker_sdk_allowed")):
        blockers.append("broker_sdk_blocked")
    if bool(normalized_request.get("network_api_allowed")):
        blockers.append("network_api_blocked")
    if bool(normalized_request.get("credentials_allowed")):
        blockers.append("credentials_blocked")

    if str(side) == "LONG" and not _long_validation_ready(normalized_request, checkpoint):
        blockers.append("long_validation_required")

    blockers.extend(_forbidden_field_paths(raw_request))
    blockers.extend(_forbidden_field_paths(verification))
    blockers.extend(_forbidden_field_paths(checkpoint))
    blockers.extend(_live_boundary_blockers(raw_request))
    blockers.extend(_live_boundary_blockers(verification))
    blockers.extend(_live_boundary_blockers(checkpoint))

    if _has_forbidden_effect(raw_request) or _has_forbidden_effect(verification) or _has_forbidden_effect(checkpoint):
        blockers.append("unsafe_live_permission_attempt_detected")

    if contract.get("live_execution_allowed") is True:
        blockers.append("contract_live_execution_must_remain_false")
    if contract.get("live_broker_writes_allowed") is True or contract.get("paper_broker_writes_allowed") is True:
        blockers.append("contract_broker_writes_must_remain_blocked")

    return _unique(blockers)


def _plan_gate_ready(plan_gate: Mapping[str, Any]) -> bool:
    return bool(
        plan_gate.get("classification") == broker_paper_adapter_plan_approval_gate.ADAPTER_PLAN_APPROVAL_READY
        or plan_gate.get("broker_paper_adapter_plan_approval_gate_ready") is True
    )


def _paper_demo_verification_ready(verification: Mapping[str, Any]) -> bool:
    if not verification:
        return False
    if verification.get("paper_only") is not True:
        return False
    if verification.get("endpoint_live") is True or verification.get("broker_endpoint_live") is True:
        return False
    if str(verification.get("environment") or verification.get("broker_environment") or "").strip().lower() in {
        "live",
        "production",
        "real",
    }:
        return False
    if verification.get("live_execution_allowed") is True:
        return False
    if verification.get("live_broker_writes_allowed") is True or verification.get("broker_writes_allowed") is True:
        return False
    if verification.get("broker_sdk_allowed") is True or verification.get("network_api_allowed") is True:
        return False
    if verification.get("credentials_allowed") is True:
        return False
    if verification.get("verified_by_human_owner") is not True:
        return False
    return True


def _owner_checkpoint_ready(checkpoint: Mapping[str, Any]) -> bool:
    if not checkpoint:
        return False
    if checkpoint.get("paper_demo_execution_phase") is not True:
        return False
    if checkpoint.get("human_owner_approved") is not True:
        return False
    if str(checkpoint.get("approved_by_human_owner") or "") != APPROVED_OWNER:
        return False
    if checkpoint.get("live_execution_allowed") is True:
        return False
    if checkpoint.get("broker_writes_allowed") is True:
        return False
    return True


def _long_validation_ready(normalized_request: Mapping[str, Any], checkpoint: Mapping[str, Any]) -> bool:
    if str(normalized_request.get("side") or "") != "LONG":
        return True
    if normalized_request.get("flags", {}).get("long_validation_ready") is True:
        return True
    return bool(checkpoint.get("long_validation_ready") is True)


def _build_receipt(
    receipt_type: str,
    state: str,
    intent_id: str,
    request_fingerprint: str,
    normalized_request: Mapping[str, Any],
    *,
    previous_receipt_id: str | None,
    blockers: list[str],
    broker_request_sent: bool,
    network_used: bool,
    credentials_used: bool,
    final_state: str | None = None,
    classification: str | None = None,
) -> dict[str, Any]:
    timestamp_utc = _utc_timestamp()
    receipt_id = f"AIOS-BROKER-PAPER-{receipt_type.upper()}-{request_fingerprint[:12].upper()}"
    receipt = {
        "schema": "AIOS_BROKER_PAPER_ADAPTER_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "receipt_type": receipt_type,
        "receipt_id": receipt_id,
        "timestamp_utc": timestamp_utc,
        "intent_id": intent_id,
        "request_fingerprint": request_fingerprint,
        "previous_receipt_id": previous_receipt_id,
        "symbol": normalized_request.get("symbol"),
        "side": normalized_request.get("side"),
        "raw_side": normalized_request.get("raw_side"),
        "quantity_units": normalized_request.get("quantity_units"),
        "stop_loss_pips": normalized_request.get("stop_loss_pips"),
        "take_profit_pips": normalized_request.get("take_profit_pips"),
        "max_loss_usd": normalized_request.get("max_loss_usd"),
        "paper_only": True,
        "live_execution_allowed": False,
        "paper_broker_writes_allowed": False,
        "live_broker_writes_allowed": False,
        "broker_writes": 0,
        "broker_request_sent": broker_request_sent,
        "network_used": network_used,
        "credentials_used": credentials_used,
        "broker_sdk_allowed": False,
        "network_api_allowed": False,
        "credentials_allowed": False,
        "sanitized": True,
        "contains_private_data": False,
        "contains_real_credentials": False,
        "status": state,
        "state": state,
        "blockers": list(blockers),
    }
    if final_state is not None:
        receipt["final_state"] = final_state
    if classification is not None:
        receipt["classification"] = classification
    schemas.assert_no_live_permissions(receipt)
    return receipt


def _receipt_chain(*receipts: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [dict(receipt) for receipt in receipts if receipt is not None]


def _assert_evidence_chain(evidence_bundle: Mapping[str, Any]) -> None:
    chain = list(evidence_bundle.get("receipt_chain") or [])
    if not chain:
        raise ValueError("receipt_chain_required")
    intent, submission, *rest = chain
    if intent.get("receipt_type") != "intent" or submission.get("receipt_type") != "submission":
        raise ValueError("receipt_chain_must_start_with_intent_then_submission")
    previous_id = intent.get("receipt_id")
    if submission.get("previous_receipt_id") != previous_id:
        raise ValueError("submission_receipt_must_link_to_intent_receipt")
    previous_receipt_id = submission.get("receipt_id")
    for current in rest:
        if current.get("previous_receipt_id") != previous_receipt_id:
            raise ValueError("receipt_chain_must_be_linked")
        previous_receipt_id = current.get("receipt_id")
    if evidence_bundle.get("paper_only") is not True:
        raise ValueError("paper_only_required")
    if evidence_bundle.get("live_execution_allowed") is True:
        raise ValueError("live_execution_must_remain_false")
    if evidence_bundle.get("broker_writes") != 0:
        raise ValueError("broker_writes_must_remain_zero")


def _has_forbidden_effect(payload: Any) -> bool:
    if isinstance(payload, Mapping):
        for key, nested in payload.items():
            normalized = _normalize_key(str(key))
            if normalized in {
                "live_execution_allowed",
                "live_broker_writes_allowed",
                "live_orders_allowed",
                "live_ready",
                "live_trade_ready",
                "real_order_ready",
                "execution_allowed",
            } and nested is True:
                return True
            if normalized in {
                "broker_request_sent",
                "network_used",
                "credentials_used",
                "order_placed",
                "broker_writes_allowed",
                "paper_broker_writes_allowed",
            } and nested is True:
                return True
            if _has_forbidden_effect(nested):
                return True
    elif isinstance(payload, list):
        return any(_has_forbidden_effect(item) for item in payload)
    return False


def _forbidden_field_paths(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if _is_forbidden_field_name(key_text):
                paths.append(path)
            paths.extend(_forbidden_field_paths(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            paths.extend(_forbidden_field_paths(nested, f"{prefix}[{index}]"))
    return _unique(paths)


def _live_boundary_blockers(value: Any, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            normalized_key = _normalize_key(key_text)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if normalized_key in {"endpoint_live", "broker_endpoint_live"} and nested is True:
                blockers.append(f"live_boundary_detected:{path}")
            if normalized_key in {"mode", "environment", "broker_environment", "account_mode"}:
                if _contains_live_marker(nested):
                    blockers.append(f"live_boundary_detected:{path}")
            if normalized_key in {"endpoint", "broker_endpoint", "broker_url", "endpoint_url"} and _contains_live_marker(nested):
                blockers.append(f"live_boundary_detected:{path}")
            blockers.extend(_live_boundary_blockers(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            blockers.extend(_live_boundary_blockers(nested, f"{prefix}[{index}]"))
    return _unique(blockers)


def _contains_live_marker(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return any(marker in text for marker in ("live", "production", "real"))


def _is_forbidden_field_name(key: str) -> bool:
    normalized = _normalize_key(key)
    if normalized in FORBIDDEN_FIELD_NAMES:
        return True
    if normalized.endswith("_allowed"):
        return False
    return any(
        marker in normalized
        for marker in (
            "api_key",
            "access_token",
            "refresh_token",
            "password",
            "secret",
            "credential",
            "account_id",
            "account_number",
        )
    )


def _sanitize_verification(verification: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "paper_only": bool(verification.get("paper_only", False)),
        "environment": str(verification.get("environment") or verification.get("broker_environment") or "").strip().lower(),
        "endpoint_live": bool(verification.get("endpoint_live", False)),
        "broker_endpoint_live": bool(verification.get("broker_endpoint_live", False)),
        "account_mode": str(verification.get("account_mode") or "").strip().upper(),
        "verified_by_human_owner": bool(verification.get("verified_by_human_owner", False)),
        "live_execution_allowed": bool(verification.get("live_execution_allowed", False)),
        "live_broker_writes_allowed": bool(verification.get("live_broker_writes_allowed", False)),
        "broker_writes_allowed": bool(verification.get("broker_writes_allowed", False)),
        "broker_sdk_allowed": bool(verification.get("broker_sdk_allowed", False)),
        "network_api_allowed": bool(verification.get("network_api_allowed", False)),
        "credentials_allowed": bool(verification.get("credentials_allowed", False)),
    }


def _sanitize_checkpoint(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "paper_demo_execution_phase": bool(checkpoint.get("paper_demo_execution_phase", False)),
        "human_owner_approved": bool(checkpoint.get("human_owner_approved", False)),
        "approved_by_human_owner": str(checkpoint.get("approved_by_human_owner") or "").strip(),
        "approval_scope": str(checkpoint.get("approval_scope") or "").strip(),
        "mode": str(checkpoint.get("mode") or "").strip().upper(),
        "long_validation_ready": bool(checkpoint.get("long_validation_ready", False)),
        "live_execution_allowed": bool(checkpoint.get("live_execution_allowed", False)),
        "broker_writes_allowed": bool(checkpoint.get("broker_writes_allowed", False)),
    }


def _minimal_plan_gate_view(plan_gate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "classification": str(plan_gate.get("classification") or ""),
        "broker_paper_adapter_plan_approval_gate_ready": bool(
            plan_gate.get("broker_paper_adapter_plan_approval_gate_ready", False)
        ),
        "approval_complete": bool(plan_gate.get("approval_complete", False)),
        "source_evidence_ready": bool(plan_gate.get("source_evidence_ready", False)),
        "paper_demo_adapter_planning_allowed": bool(plan_gate.get("paper_demo_adapter_planning_allowed", False)),
        "live_orders_allowed": bool(plan_gate.get("live_orders_allowed", False)),
        "broker_paper_orders_allowed": bool(plan_gate.get("broker_paper_orders_allowed", False)),
    }


def _minimal_contract_view(contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mode": str(contract.get("mode") or ""),
        "paper_only": bool(contract.get("paper_only", False)),
        "live_execution_allowed": bool(contract.get("live_execution_allowed", False)),
        "paper_broker_writes_allowed": bool(contract.get("paper_broker_writes_allowed", False)),
        "live_broker_writes_allowed": bool(contract.get("live_broker_writes_allowed", False)),
        "broker_orders_allowed": bool(contract.get("broker_orders_allowed", False)),
        "broker_sdk_allowed": bool(contract.get("broker_sdk_allowed", False)),
        "network_api_allowed": bool(contract.get("network_api_allowed", False)),
        "credentials_allowed": bool(contract.get("credentials_allowed", False)),
    }


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and float(value) > 0.0


def _int_or_none(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _fingerprint(payload: Any) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _unique(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        if item and item not in unique:
            unique.append(item)
    return unique


def _demo_paper_demo_verification() -> dict[str, Any]:
    return {
        "paper_only": True,
        "environment": "PAPER",
        "broker_environment": "paper",
        "endpoint_live": False,
        "broker_endpoint_live": False,
        "account_mode": "PAPER_DEMO",
        "verified_by_human_owner": True,
        "live_execution_allowed": False,
        "live_broker_writes_allowed": False,
        "broker_writes_allowed": False,
        "broker_sdk_allowed": False,
        "network_api_allowed": False,
        "credentials_allowed": False,
    }
