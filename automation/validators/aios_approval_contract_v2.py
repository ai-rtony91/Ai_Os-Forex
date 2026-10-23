"""Strict canonical Human Owner approval payload contract, version 2.

The contract deliberately has no legacy fallback.  Historical v1 gates may be
validated by the historical validator path, but a v2 lineage must use this
module from registration through runtime admission.
"""
from __future__ import annotations

import hmac
import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


SCHEMA = "AIOS_HUMAN_OWNER_APPROVAL_PAYLOAD.v2"
PURPOSE = "AIOS_APPLY_APPROVAL_RUNTIME_ADMISSION"
ALGORITHM = "HMAC-SHA256"
OWNER = "Anthony, Human Owner"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
NONCE = re.compile(r"^[0-9a-f]{32,128}$")

# Every field below is authenticated.  approval_evidence is excluded because
# it contains the digest and HMAC derived from the canonical message.
REQUIRED = (
    "schema", "purpose", "algorithm", "request_id", "request_revision",
    "gate_id", "approval_request_id", "approval_gate_id", "packet_id",
    "goal_id", "requested_action", "requested_mode", "approved_mode",
    "approval_status", "approved_by_human", "approved_by", "owner_identity",
    "approval_authority", "trust_root_id", "key_id", "key_version",
    "key_fingerprint_sha256", "approval_nonce", "created_at_utc",
    "approval_timestamp_utc", "not_before_utc", "latest_entry_utc",
    "expires_at_utc", "closure_reserve_hours", "worker", "worker_identity",
    "lane", "worktree", "allowed_paths", "blocked_paths", "validator_chain",
    "package_sha256", "authority_bundle_sha256",
    "execution_contract_sha256", "research_scope", "research_scope_sha256",
    "source_hashes", "source_map_sha256", "data_hashes", "strategy_identity",
    "cost_identity", "trial_allocation", "budget_identity_sha256",
    "resource_limits", "output_roots", "capabilities", "resume_policy",
    "stop_point", "validator_chain_required", "commit_package_required",
    "push_blocked_until_final_review",
)


@dataclass(frozen=True)
class Verification:
    passed: bool
    failures: tuple[str, ...]


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def canonical_digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _utc(value: Any, field: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field}_invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(value: Any, field: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    text = str(value or "").lower()
    if not HEX64.fullmatch(text):
        raise ValueError(f"{field}_sha256_invalid")
    return text


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_missing")
    return value


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field}_invalid")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field}_invalid")
    if len(value) != len(set(value)):
        raise ValueError(f"{field}_duplicate")
    return list(value)


def _object(value: Any, field: str, *, nonempty: bool = True) -> dict[str, Any]:
    if not isinstance(value, dict) or (nonempty and not value):
        raise ValueError(f"{field}_invalid")
    return value


def _timing(gate: dict[str, Any]) -> tuple[datetime, datetime, datetime]:
    not_before = datetime.fromisoformat(
        str(_utc(gate["not_before_utc"], "not_before_utc")).replace("Z", "+00:00")
    )
    latest = datetime.fromisoformat(
        str(_utc(gate["latest_entry_utc"], "latest_entry_utc")).replace("Z", "+00:00")
    )
    expiry = datetime.fromisoformat(
        str(_utc(gate["expires_at_utc"], "expires_at_utc")).replace("Z", "+00:00")
    )
    if not not_before < latest < expiry:
        raise ValueError("timing_order_invalid")
    reserve = gate["closure_reserve_hours"]
    if isinstance(reserve, bool) or not isinstance(reserve, (int, float)) or reserve <= 0:
        raise ValueError("closure_reserve_invalid")
    return not_before, latest, expiry


def _base(gate: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(gate, dict):
        raise ValueError("gate_invalid")
    missing = [field for field in REQUIRED if field not in gate]
    if missing:
        raise ValueError("missing:" + ",".join(missing))
    if gate["schema"] != SCHEMA:
        raise ValueError("schema_invalid")
    if gate["purpose"] != PURPOSE:
        raise ValueError("purpose_invalid")
    if gate["algorithm"] != ALGORITHM:
        raise ValueError("algorithm_invalid")
    request_id = _string(gate["request_id"], "request_id")
    for field in ("gate_id", "approval_request_id", "approval_gate_id"):
        if gate[field] != request_id:
            raise ValueError(f"{field}_mismatch")
    if gate["requested_mode"] != "APPLY" or gate["approved_mode"] != "APPLY":
        raise ValueError("mode_invalid")
    for field in ("owner_identity", "approval_authority"):
        if gate[field] != OWNER:
            raise ValueError(f"{field}_invalid")
    if gate["trust_root_id"] != "AIOS-HUMAN-OWNER-APPROVAL-TRUST-ROOT-V1":
        raise ValueError("trust_root_id_invalid")
    if gate["worker"] != gate["worker_identity"]:
        raise ValueError("worker_identity_mismatch")
    for field in (
        "request_revision", "packet_id", "goal_id", "requested_action", "worker",
        "lane", "worktree", "stop_point",
    ):
        _string(gate[field], field)
    allowed = sorted(_string_list(gate["allowed_paths"], "allowed_paths"))
    blocked = sorted(_string_list(gate["blocked_paths"], "blocked_paths"))
    if set(path.casefold() for path in allowed) & set(path.casefold() for path in blocked):
        raise ValueError("allowed_blocked_path_overlap")
    _string_list(gate["validator_chain"], "validator_chain")
    for field in (
        "package_sha256", "authority_bundle_sha256", "execution_contract_sha256",
        "research_scope_sha256", "source_map_sha256", "budget_identity_sha256",
    ):
        _sha(gate[field], field)
    research_scope = _object(gate["research_scope"], "research_scope")
    source_hashes = _object(gate["source_hashes"], "source_hashes")
    data_hashes = _object(gate["data_hashes"], "data_hashes")
    strategy = _object(gate["strategy_identity"], "strategy_identity")
    _object(gate["trial_allocation"], "trial_allocation")
    _object(gate["resource_limits"], "resource_limits")
    output_roots = _object(gate["output_roots"], "output_roots")
    capabilities = _object(gate["capabilities"], "capabilities")
    _object(gate["resume_policy"], "resume_policy")
    if not isinstance(gate["cost_identity"], (str, dict)) or not gate["cost_identity"]:
        raise ValueError("cost_identity_invalid")
    for name in ("strategy_id", "strategy_version"):
        _string(strategy.get(name), f"strategy_identity_{name}")
    if canonical_digest(research_scope) != gate["research_scope_sha256"]:
        raise ValueError("research_scope_sha256_mismatch")
    if canonical_digest(source_hashes) != gate["source_map_sha256"]:
        raise ValueError("source_map_sha256_mismatch")
    budget_material = {
        "trial_allocation": gate["trial_allocation"],
        "resource_limits": gate["resource_limits"],
    }
    if canonical_digest(budget_material) != gate["budget_identity_sha256"]:
        raise ValueError("budget_identity_sha256_mismatch")
    bound_output = research_scope.get("bindings", {}).get("output_root")
    if bound_output and bound_output not in output_roots.values():
        raise ValueError("research_scope_output_root_unbound")
    for name in ("broker", "paper", "live", "commit", "push", "merge"):
        if capabilities.get(name) is not False:
            raise ValueError(f"capability_{name}_must_be_false")
    for field in (
        "validator_chain_required", "commit_package_required",
        "push_blocked_until_final_review",
    ):
        if gate[field] is not True:
            raise ValueError(f"{field}_must_be_true")
    _utc(gate["created_at_utc"], "created_at_utc")
    _timing(gate)
    result = {key: value for key, value in gate.items() if key != "approval_evidence"}
    result["allowed_paths"] = allowed
    result["blocked_paths"] = blocked
    for field in ("created_at_utc", "not_before_utc", "latest_entry_utc", "expires_at_utc"):
        result[field] = _utc(gate[field], field)
    return result


def pending_failures(gate: dict[str, Any], *, now: datetime | None = None) -> tuple[str, ...]:
    """Validate a complete unsigned v2 gate without accepting it for execution."""
    failures: list[str] = []
    try:
        _base(gate)
        if gate["approval_status"] != "pending_review":
            failures.append("pending_status_invalid")
        if gate["approved_by_human"] is not False or gate["approved_by"] is not None:
            failures.append("pending_owner_state_invalid")
        if gate["approval_timestamp_utc"] is not None:
            failures.append("pending_timestamp_must_be_null")
        if gate["key_id"] is not None or gate["key_version"] != 0:
            failures.append("pending_key_state_invalid")
        if gate["key_fingerprint_sha256"] is not None:
            failures.append("pending_fingerprint_must_be_null")
        nonce = str(gate["approval_nonce"] or "").lower()
        if not NONCE.fullmatch(nonce):
            failures.append("approval_nonce_invalid")
        evidence = _object(gate.get("approval_evidence"), "approval_evidence")
        if evidence != {
            "type": "HMAC_SHA256",
            "status": "UNSIGNED",
            "canonical_payload_schema": SCHEMA,
        }:
            failures.append("pending_approval_evidence_invalid")
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        _, latest, expiry = _timing(gate)
        if current >= latest:
            failures.append("latest_entry_expired")
        if current >= expiry:
            failures.append("approval_expired")
    except (KeyError, TypeError, ValueError) as exc:
        failures.append(str(exc))
    return tuple(dict.fromkeys(failures))


def _signed(gate: dict[str, Any]) -> dict[str, Any]:
    result = _base(gate)
    if gate["approval_status"] != "approved_for_apply" or gate["approved_by_human"] is not True:
        raise ValueError("approval_decision_invalid")
    if gate["approved_by"] != OWNER:
        raise ValueError("approved_by_invalid")
    if not isinstance(gate["key_version"], int) or isinstance(gate["key_version"], bool) or gate["key_version"] < 1:
        raise ValueError("key_version_invalid")
    _string(gate["key_id"], "key_id")
    _sha(gate["key_fingerprint_sha256"], "key_fingerprint")
    if not NONCE.fullmatch(str(gate["approval_nonce"] or "").lower()):
        raise ValueError("approval_nonce_invalid")
    result["approval_timestamp_utc"] = _utc(gate["approval_timestamp_utc"], "approval_timestamp_utc")
    return result


def canonical_payload(gate: dict[str, Any]) -> str:
    """Return deterministic UTF-8 JSON for the complete signed decision."""
    return canonical_json(_signed(gate))


def payload_sha256(gate: dict[str, Any]) -> str:
    return sha256(canonical_payload(gate).encode("utf-8")).hexdigest()


def approval_hmac(gate: dict[str, Any], key: str) -> str:
    if not key:
        raise ValueError("approval_key_missing")
    return hmac.new(
        key.encode("utf-8"), canonical_payload(gate).encode("utf-8"), sha256
    ).hexdigest()


def verify(gate: dict[str, Any], key: str | None, *, now: datetime | None = None) -> Verification:
    failures: list[str] = []
    try:
        evidence = _object(gate.get("approval_evidence"), "approval_evidence")
        if evidence.get("type") != "HMAC_SHA256" or evidence.get("status") != "SIGNED_BY_HUMAN_OWNER":
            failures.append("approval_evidence_status_invalid")
        if evidence.get("canonical_payload_schema") != SCHEMA:
            failures.append("canonical_payload_schema_missing_or_invalid")
        for field in ("key_id", "key_version", "key_fingerprint_sha256", "approval_nonce"):
            if evidence.get(field) != gate.get(field):
                failures.append(f"approval_evidence_{field}_mismatch")
        expected_payload = payload_sha256(gate)
        if evidence.get("canonical_payload_sha256") != expected_payload:
            failures.append("canonical_payload_hash_mismatch")
        if not key:
            failures.append("approval_key_missing")
        else:
            provided = str(evidence.get("approval_hmac_sha256") or "")
            if not hmac.compare_digest(provided, approval_hmac(gate, key)):
                failures.append("approval_hmac_invalid")
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        not_before, latest, expiry = _timing(gate)
        if current < not_before:
            failures.append("not_before_not_reached")
        if current >= latest:
            failures.append("latest_entry_expired")
        if current >= expiry:
            failures.append("approval_expired")
    except (KeyError, TypeError, ValueError) as exc:
        failures.append(str(exc))
    return Verification(not failures, tuple(dict.fromkeys(failures)))


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS approval contract v2 helper")
    parser.add_argument("--canonical-digest-stdin", action="store_true")
    parser.add_argument("--pending-gate-stdin", action="store_true")
    args = parser.parse_args()
    payload = json.load(__import__("sys").stdin)
    if args.canonical_digest_stdin:
        print(canonical_digest(payload))
        return 0
    if args.pending_gate_stdin:
        failures = pending_failures(payload)
        print(canonical_json({"status": "PASS" if not failures else "BLOCKED", "failed_checks": failures}))
        return 0 if not failures else 1
    parser.error("one stdin operation is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
