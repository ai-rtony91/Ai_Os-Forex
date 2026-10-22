"""Deterministic, non-authoritative approval routing for the 17-phase workflow.

The broker consumes sanitized decision records and an injected trusted verifier.
It never creates decisions, authenticates an owner, or executes protected work.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

MANIFEST_SCHEMA = "aios.owner_authority_phases.v1"
QUEUE_SCHEMA = "aios.approval_broker_queue.v1"
BROKER_MODE = "NON_AUTHORITATIVE_APPROVAL_ROUTER"
EXPECTED_PHASE_IDS = tuple(range(1, 18))
DEFAULT_MANIFEST_PATH = Path(__file__).with_name("AIOS_OWNER_AUTHORITY_PHASES_V1.json")

BUNDLE_ORDER = (
    "OWNER-BUNDLE-1-POLICY",
    "OWNER-BUNDLE-2-DEVICE-IDENTITY",
    "OWNER-BUNDLE-3-RUNTIME-SECRETS",
    "OWNER-BUNDLE-4-LOCATION-PRIVACY",
)
BUNDLE_TITLES = {
    "OWNER-BUNDLE-1-POLICY": "Policy Bundle",
    "OWNER-BUNDLE-2-DEVICE-IDENTITY": "Device / Identity Bundle",
    "OWNER-BUNDLE-3-RUNTIME-SECRETS": "Runtime / Secrets Bundle",
    "OWNER-BUNDLE-4-LOCATION-PRIVACY": "Location / Privacy Bundle",
}
EXPECTED_BUNDLE_PHASES = {
    "OWNER-BUNDLE-1-POLICY": (2, 3, 6, 7, 8, 10, 11),
    "OWNER-BUNDLE-2-DEVICE-IDENTITY": (4, 5, 9),
    "OWNER-BUNDLE-3-RUNTIME-SECRETS": (14, 15, 16),
    "OWNER-BUNDLE-4-LOCATION-PRIVACY": (17,),
}
ALLOWED_AUTHORITIES = frozenset(
    {
        "NONE",
        "POLICY_ACCEPTANCE",
        "RISK_ACCEPTANCE",
        "EXTERNAL_ACCOUNT",
        "PHYSICAL_DEVICE",
        "DEPLOYMENT",
        "AUTHORITY_BOUNDARY",
        "SECRET_ACCESS",
        "PRIVACY_CONSENT",
    }
)
SECRET_LIKE_TERMS = frozenset(
    {
        "token",
        "password",
        "private_key",
        "secret",
        "passkey",
        "yubikey",
        "phone_number",
        "exact_location",
        "account_id",
        "credential",
        "raw_payload",
    }
)


class ApprovalBrokerError(ValueError):
    """Raised when manifest or broker input cannot be handled safely."""


class TrustedDecisionVerifier(Protocol):
    """External trust boundary; True means the supplied record was verified."""

    def __call__(self, decision: Mapping[str, Any]) -> bool: ...


Verifier = Callable[[Mapping[str, Any]], bool]


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApprovalBrokerError(f"{field} must be a non-empty string")
    return value.strip()


def _parse_time(value: Any, field: str) -> datetime:
    text = _nonempty(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApprovalBrokerError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ApprovalBrokerError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Fail closed unless the canonical V1 manifest has its exact safe shape."""

    if not isinstance(manifest, Mapping) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ApprovalBrokerError("unexpected manifest schema")
    if manifest.get("program") != "AIOS_17_PHASE_OWNER_AUTHORITY_WORKFLOW":
        raise ApprovalBrokerError("unexpected program identity")
    if manifest.get("mode") != "PREPARE_BEHIND_GATE":
        raise ApprovalBrokerError("unexpected workflow mode")
    if manifest.get("maximum_owner_checkpoints") != 4:
        raise ApprovalBrokerError("V1 requires exactly four maximum owner checkpoints")
    phases = manifest.get("phases")
    if not isinstance(phases, list):
        raise ApprovalBrokerError("phases must be a list")

    ids: list[int] = []
    actual_bundles: dict[str, list[int]] = {bundle: [] for bundle in BUNDLE_ORDER}
    for phase in phases:
        if not isinstance(phase, Mapping):
            raise ApprovalBrokerError("each phase must be an object")
        phase_id = phase.get("phase_id")
        if not isinstance(phase_id, int) or isinstance(phase_id, bool):
            raise ApprovalBrokerError("phase_id must be an integer")
        ids.append(phase_id)
        _nonempty(phase.get("name"), f"phase {phase_id} name")
        authority = _nonempty(phase.get("owner_authority"), f"phase {phase_id} authority")
        if authority not in ALLOWED_AUTHORITIES:
            raise ApprovalBrokerError(f"phase {phase_id} has unknown authority")
        bundle = phase.get("owner_bundle")
        action = phase.get("owner_action")
        if authority == "NONE":
            if bundle is not None or action is not None:
                raise ApprovalBrokerError(f"phase {phase_id} cannot define owner metadata")
            continue
        bundle_id = _nonempty(bundle, f"phase {phase_id} bundle")
        if bundle_id not in actual_bundles:
            raise ApprovalBrokerError(f"phase {phase_id} has unknown bundle ID")
        _nonempty(action, f"phase {phase_id} owner action")
        actual_bundles[bundle_id].append(phase_id)

    if len(ids) != len(set(ids)):
        raise ApprovalBrokerError("duplicate phase number")
    if tuple(sorted(ids)) != EXPECTED_PHASE_IDS:
        raise ApprovalBrokerError("phases must be exactly 1 through 17")
    normalized = {key: tuple(value) for key, value in actual_bundles.items()}
    if normalized != EXPECTED_BUNDLE_PHASES:
        raise ApprovalBrokerError("manifest bundle assignments do not match canonical V1")


def load_manifest(path: str | Path | None = None) -> dict[str, Any]:
    manifest_path = Path(path) if path is not None else DEFAULT_MANIFEST_PATH
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    validate_manifest(manifest)
    return manifest


class ApprovalBroker:
    """Canonical phase-facing router that reports, but never grants, authority."""

    def __init__(
        self,
        manifest: Mapping[str, Any] | None = None,
        verifier: TrustedDecisionVerifier | None = None,
    ) -> None:
        self.manifest = dict(manifest) if manifest is not None else load_manifest()
        validate_manifest(self.manifest)
        self.verifier = verifier
        self._phases = {int(p["phase_id"]): dict(p) for p in self.manifest["phases"]}

    def classify_phase(self, phase_id: int) -> dict[str, Any]:
        phase = self._phase(phase_id)
        if phase["owner_authority"] == "NONE":
            return {
                "phase_id": phase_id,
                "status": "CONTINUE_AUTONOMOUSLY",
                "owner_bundle": None,
                "protected_action_blocked": False,
                "continue_unblocked_preparation": True,
                "blocked_scope": None,
            }
        return {
            "phase_id": phase_id,
            "status": "PREPARE_BEHIND_GATE",
            "owner_bundle": phase["owner_bundle"],
            "protected_action_blocked": True,
            "continue_unblocked_preparation": True,
            "blocked_scope": "PROTECTED_TRANSITION_ONLY",
        }

    def prepare_phase(
        self,
        phase_id: int,
        decisions: Iterable[Mapping[str, Any]] = (),
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        base = self.classify_phase(phase_id)
        if base["status"] == "CONTINUE_AUTONOMOUSLY":
            return base
        queue = self.build_queue([phase_id], decisions, now=now)
        bundle_id = base["owner_bundle"]
        if phase_id in queue["resumable_phases"]:
            return {
                **base,
                "status": "RESUME_AUTHORIZED",
                "protected_action_blocked": False,
                "approved_phases": list(EXPECTED_BUNDLE_PHASES[bundle_id]),
                "downstream_execution": "REMAINS_GOVERNED_BY_RECEIVING_COMPONENT",
            }
        if bundle_id in queue["rejected_bundles"]:
            return {**base, "status": "REJECTED"}
        if bundle_id in queue["expired_bundles"]:
            return {**base, "status": "EXPIRED"}
        if queue["problems"]:
            return {**base, "status": "BLOCKED", "problems": queue["problems"]}
        return base

    def build_queue(
        self,
        phase_ids: Iterable[int],
        decisions: Iterable[Mapping[str, Any]] = (),
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        requested = sorted(set(phase_ids))
        for phase_id in requested:
            self._phase(phase_id)
        current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        decision_states, problems = self._bind_decisions(decisions, current_time)

        pending: list[dict[str, Any]] = []
        resumable: list[int] = []
        blocked: list[int] = []
        rejected: list[str] = []
        expired: list[str] = []
        requested_bundles = {
            self._phases[phase_id].get("owner_bundle")
            for phase_id in requested
            if self._phases[phase_id]["owner_authority"] != "NONE"
        }
        for bundle_id in BUNDLE_ORDER:
            if bundle_id not in requested_bundles:
                continue
            bundle_phases = list(EXPECTED_BUNDLE_PHASES[bundle_id])
            state = decision_states.get(bundle_id, "PENDING")
            if state == "APPROVED":
                resumable.extend(bundle_phases)
                continue
            blocked.extend(phase for phase in requested if phase in bundle_phases)
            if state == "REJECTED":
                rejected.append(bundle_id)
                continue
            if state == "EXPIRED":
                expired.append(bundle_id)
                continue
            pending.append(self._pending_item(bundle_id))

        queue = {
            "schema": QUEUE_SCHEMA,
            "mode": BROKER_MODE,
            "generated_status": self._queue_status(pending, resumable, rejected, expired, problems),
            "continue_unblocked_preparation": True,
            "pending_approvals": pending,
            "resumable_phases": sorted(resumable),
            "blocked_phases": sorted(blocked),
            "rejected_bundles": rejected,
            "expired_bundles": expired,
            "problems": problems,
        }
        self._reject_secret_like_content(queue)
        return queue

    def _bind_decisions(
        self, decisions: Iterable[Mapping[str, Any]], now: datetime
    ) -> tuple[dict[str, str], list[str]]:
        records = sorted(
            list(decisions),
            key=lambda record: json.dumps(
                dict(record) if isinstance(record, Mapping) else record,
                sort_keys=True,
                default=str,
            ),
        )
        states: dict[str, str] = {}
        problems: list[str] = []
        receipt_counts = Counter(
            record.get("receipt_id")
            for record in records
            if isinstance(record, Mapping)
            and isinstance(record.get("receipt_id"), str)
            and record.get("receipt_id", "").strip()
        )
        for index, record in enumerate(records):
            prefix = f"decision[{index}]"
            try:
                if not isinstance(record, Mapping):
                    raise ApprovalBrokerError("record must be an object")
                receipt_id = _nonempty(record.get("receipt_id"), "receipt_id")
                if receipt_counts[receipt_id] > 1:
                    raise ApprovalBrokerError("duplicate receipt ID")
                bundle_id = _nonempty(record.get("bundle_id"), "bundle_id")
                authority_source = _nonempty(record.get("authority_source"), "authority_source")
                if bundle_id not in EXPECTED_BUNDLE_PHASES:
                    raise ApprovalBrokerError("unknown bundle ID")
                phases = record.get("phases")
                if not isinstance(phases, list) or any(
                    not isinstance(p, int) or isinstance(p, bool) for p in phases
                ):
                    raise ApprovalBrokerError("phases must be an integer list")
                expected_phases = EXPECTED_BUNDLE_PHASES[bundle_id]
                if len(phases) != len(set(phases)) or set(phases) != set(expected_phases):
                    raise ApprovalBrokerError("decision phases must exactly match bundle")
                decision = _nonempty(record.get("decision"), "decision")
                if decision not in {"APPROVE", "REJECT"}:
                    raise ApprovalBrokerError("unknown decision")
                issued_at = _parse_time(record.get("issued_at"), "issued_at")
                if issued_at > now:
                    raise ApprovalBrokerError("issued_at cannot be in the future")
                expiry = record.get("expires_at")
                if expiry is not None:
                    expires_at = _parse_time(expiry, "expires_at")
                    if expires_at <= issued_at:
                        raise ApprovalBrokerError("expires_at must be after issued_at")
                    if expires_at <= now:
                        states[bundle_id] = "EXPIRED"
                        continue
                if bundle_id in states:
                    raise ApprovalBrokerError("multiple decisions for one bundle")
                if self.verifier is None:
                    raise ApprovalBrokerError("approval decision has no trusted verifier")
                try:
                    verified = self.verifier(record)
                except Exception:  # verifier failures are data, never authority
                    raise ApprovalBrokerError("trusted verifier raised an exception") from None
                if verified is not True:
                    raise ApprovalBrokerError("trusted verifier rejected decision")
                states[bundle_id] = "APPROVED" if decision == "APPROVE" else "REJECTED"
                _ = authority_source
            except ApprovalBrokerError as exc:
                problems.append(f"{prefix}: {exc}")
        if any("duplicate receipt ID" in problem for problem in problems):
            states.clear()
        return states, problems

    def _pending_item(self, bundle_id: str) -> dict[str, Any]:
        phases = EXPECTED_BUNDLE_PHASES[bundle_id]
        actions = [
            str(self._phases[phase_id]["owner_action"])
            for phase_id in phases
        ]
        return {
            "bundle_id": bundle_id,
            "title": BUNDLE_TITLES[bundle_id],
            "phases": list(phases),
            "owner_actions": actions,
            "state": "PENDING_TRUSTED_DECISION",
            "protected_action_blocked": True,
            "continue_unblocked_preparation": True,
            "receipt_binding_requirements": [
                "non_empty_receipt_id",
                "exact_bundle_id",
                "exact_bundle_phase_set",
                "allowed_decision",
                "authority_source",
                "timezone_aware_issuance_time",
                "external_trusted_verification",
            ],
        }

    def _phase(self, phase_id: int) -> dict[str, Any]:
        if not isinstance(phase_id, int) or isinstance(phase_id, bool) or phase_id not in self._phases:
            raise ApprovalBrokerError("unknown phase ID")
        return self._phases[phase_id]

    @staticmethod
    def _queue_status(
        pending: list[dict[str, Any]],
        resumable: list[int],
        rejected: list[str],
        expired: list[str],
        problems: list[str],
    ) -> str:
        if problems:
            return "BLOCKED"
        if rejected:
            return "REJECTED"
        if expired:
            return "EXPIRED"
        if pending:
            return "PREPARE_BEHIND_GATE"
        if resumable:
            return "RESUME_AUTHORIZED"
        return "CONTINUE_AUTONOMOUSLY"

    @classmethod
    def _reject_secret_like_content(cls, value: Any, path: str = "queue") -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                normalized = str(key).lower()
                if normalized in SECRET_LIKE_TERMS or any(
                    term in normalized for term in ("password", "private_key", "phone_number", "account_id", "raw_payload")
                ):
                    raise ApprovalBrokerError(f"secret-like queue field rejected at {path}.{key}")
                cls._reject_secret_like_content(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                cls._reject_secret_like_content(item, f"{path}[{index}]")
