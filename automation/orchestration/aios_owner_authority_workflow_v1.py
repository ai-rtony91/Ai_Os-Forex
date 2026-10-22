"""Compatibility facade for the canonical non-authoritative Approval Broker."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Iterable, Mapping

from automation.orchestration.aios_approval_broker_v1 import (
    ALLOWED_AUTHORITIES as ALLOWED_OWNER_AUTHORITIES,
    DEFAULT_MANIFEST_PATH,
    EXPECTED_PHASE_IDS,
    MANIFEST_SCHEMA,
    ApprovalBroker,
    ApprovalBrokerError,
    load_manifest,
    validate_manifest,
)

PLAN_SCHEMA = "aios.owner_authority_plan.v1"
OwnerAuthorityManifestError = ApprovalBrokerError


def build_owner_authority_plan(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Retain the V1 planning projection while using broker validation."""

    validate_manifest(manifest)
    automated_phase_ids: list[int] = []
    owner_phase_ids: list[int] = []
    bundles: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for phase in manifest["phases"]:
        phase_id = int(phase["phase_id"])
        authority = str(phase["owner_authority"])
        if authority == "NONE":
            automated_phase_ids.append(phase_id)
            continue
        owner_phase_ids.append(phase_id)
        bundle_id = str(phase["owner_bundle"])
        bundle = bundles.setdefault(
            bundle_id,
            {"bundle_id": bundle_id, "phase_ids": [], "authorities": [], "actions": []},
        )
        bundle["phase_ids"].append(phase_id)
        if authority not in bundle["authorities"]:
            bundle["authorities"].append(authority)
        action = str(phase["owner_action"])
        if action not in bundle["actions"]:
            bundle["actions"].append(action)
    return {
        "schema": PLAN_SCHEMA,
        "program": manifest["program"],
        "mode": "PREPARE_BEHIND_GATE",
        "phase_count": len(manifest["phases"]),
        "automated_phase_ids": automated_phase_ids,
        "owner_phase_ids": owner_phase_ids,
        "owner_checkpoint_count": len(bundles),
        "maximum_owner_checkpoints": manifest["maximum_owner_checkpoints"],
        "bundles": list(bundles.values()),
        "protected_actions_remain_blocked": True,
    }


def prepare_phase(
    phase_id: int,
    decisions: Iterable[Mapping[str, Any]] = (),
    *,
    verifier=None,
) -> dict[str, Any]:
    """Delegate phase-facing classification and trusted binding to the broker."""

    return ApprovalBroker(verifier=verifier).prepare_phase(phase_id, decisions)


def build_owner_session_queue(
    phase_ids: Iterable[int],
    decisions: Iterable[Mapping[str, Any]] = (),
    *,
    verifier=None,
) -> dict[str, Any]:
    """Delegate the consolidated owner queue to the canonical broker."""

    return ApprovalBroker(verifier=verifier).build_queue(phase_ids, decisions)


def phase_execution_mode(
    phase: Mapping[str, Any], approved_bundle_ids: Iterable[str] = ()
) -> str:
    """Legacy non-authenticating projection; it does not grant resume authority."""

    authority = str(phase.get("owner_authority", ""))
    if authority not in ALLOWED_OWNER_AUTHORITIES:
        raise OwnerAuthorityManifestError("phase owner_authority is invalid")
    if authority == "NONE":
        return "AI_EXECUTE"
    bundle = str(phase.get("owner_bundle", "")).strip()
    if not bundle:
        raise OwnerAuthorityManifestError("owner_bundle must be a non-empty string")
    if bundle in {str(item) for item in approved_bundle_ids}:
        return "AI_EXECUTE_AFTER_OWNER_RECEIPT"
    return "AI_PREPARE_ONLY"


def first_pending_owner_bundle(
    plan: Mapping[str, Any], approved_bundle_ids: Iterable[str] = ()
) -> dict[str, Any] | None:
    if plan.get("schema") != PLAN_SCHEMA:
        raise OwnerAuthorityManifestError("unexpected plan schema")
    approved = {str(item) for item in approved_bundle_ids}
    for bundle in plan.get("bundles", []):
        if str(bundle.get("bundle_id")) not in approved:
            return dict(bundle)
    return None
