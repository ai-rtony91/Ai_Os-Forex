from __future__ import annotations

import argparse
import hmac
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

_SIBLING_CONTRACT_MODULE = "_aios_approval_contract_v2_sibling"


def _module_origin(module: object) -> Path | None:
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, (str, os.PathLike)):
        return None
    return Path(origin).resolve()


def _same_contract_origin(actual: Path | None, expected: Path) -> bool:
    """Admit equivalent local Windows namespaces, never another source file."""
    if actual is None:
        return False
    def key(path):
        value = str(path)
        if os.name == "nt" and re.match(r"^\\\\\?\\[A-Za-z]:\\", value):
            value = value[4:]
        return os.path.normcase(value)
    try:
        return key(actual) == key(expected) and os.path.samefile(actual, expected)
    except OSError:
        return False


def _load_sibling_contract(path: Path):
    expected = path.resolve(strict=True)
    existing = sys.modules.get(_SIBLING_CONTRACT_MODULE)
    if existing is not None:
        if not _same_contract_origin(_module_origin(existing), expected):
            raise RuntimeError("canonical v2 approval contract module collision")
        return existing
    spec = importlib.util.spec_from_file_location(_SIBLING_CONTRACT_MODULE, expected)
    if spec is None or spec.loader is None:
        raise RuntimeError("canonical v2 approval contract cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_SIBLING_CONTRACT_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(_SIBLING_CONTRACT_MODULE) is module:
            sys.modules.pop(_SIBLING_CONTRACT_MODULE, None)
        raise
    return module


sibling_contract = Path(__file__).resolve().with_name("aios_approval_contract_v2.py")
if sibling_contract.is_file():
    # The verifier and contract are one reviewed source pair.  Prefer the exact
    # sibling even when another public-name module is already importable.
    approval_contract_v2 = _load_sibling_contract(sibling_contract)
else:  # Historical candidate layouts used an explicitly named fallback.
    try:
        import aios_approval_contract_v2 as approval_contract_v2
    except ModuleNotFoundError:
        import candidate_aios_approval_contract_v2 as approval_contract_v2


PLACEHOLDER_TIMESTAMPS = {"2026-06-08T00:00:00Z", "2026-06-02T00:00:00Z"}
DEFAULT_APPROVAL_INBOX_PATH = Path("automation/orchestration/approval_inbox/APPROVAL_INBOX_001.json")
DEFAULT_APPROVAL_ROOT = Path("automation/orchestration/approval_inbox")
DEFAULT_APPROVAL_ARCHIVE = DEFAULT_APPROVAL_ROOT / "archive"
DEFAULT_TRUST_METADATA_PATH = DEFAULT_APPROVAL_ROOT / "AIOS_HUMAN_OWNER_APPROVAL_TRUST_ROOT_001.json"
TRUST_ROOT_SCHEMA = "AIOS_HUMAN_OWNER_APPROVAL_TRUST_ROOT.v1"
TRUST_ROOT_ID = "AIOS-HUMAN-OWNER-APPROVAL-TRUST-ROOT-V1"
PAYLOAD_SCHEMA = "AIOS_HUMAN_OWNER_APPROVAL_PAYLOAD.v1"
V2_PAYLOAD_SCHEMA = approval_contract_v2.SCHEMA
FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_APPROVAL_INBOX_FIELDS = (
    "approval_gate_id", "authority_status", "packet_id", "requested_action",
    "requested_mode", "approval_status", "approved_by_human", "risk_level",
    "allowed_paths", "blocked_paths", "validator_chain_required",
    "commit_package_required", "push_blocked_until_final_review",
)


@dataclass(frozen=True)
class ApprovalAuthorityResult:
    status: str
    hardened_approval_verified: bool
    failed_checks: list[str]
    evidence_type: str
    next_safe_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator": "aios_approval_authority_integrity_validator",
            "status": self.status,
            "hardened_approval_verified": self.hardened_approval_verified,
            "failed_checks": self.failed_checks,
            "evidence_type": self.evidence_type,
            "next_safe_action": self.next_safe_action,
        }


def _as_paths(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip().replace("\\", "/").strip("/") for item in value if str(item).strip()]


def _as_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _request_id(gate: dict[str, Any]) -> str:
    return str(gate.get("approval_request_id") or gate.get("request_id") or gate.get("approval_gate_id") or "").strip()


def _approval_timestamp(gate: dict[str, Any]) -> str:
    return str(gate.get("approval_timestamp_utc") or gate.get("bound_at") or gate.get("approval_timestamp_placeholder") or "").strip()


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _is_midnight_placeholder(value: str) -> bool:
    if value in PLACEHOLDER_TIMESTAMPS:
        return True
    parsed = _parse_utc(value)
    return bool(parsed and parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0)


def canonical_payload_fields(gate: dict[str, Any]) -> dict[str, Any]:
    evidence = gate.get("approval_evidence") if isinstance(gate.get("approval_evidence"), dict) else {}
    return {
        "schema": PAYLOAD_SCHEMA,
        "request_id": _request_id(gate),
        "packet_id": str(gate.get("packet_id") or "").strip(),
        "requested_action": str(gate.get("requested_action") or "").strip(),
        "requested_mode": str(gate.get("requested_mode") or "").strip().upper(),
        "allowed_paths": sorted(_as_paths(gate.get("allowed_paths"))),
        "blocked_paths": sorted(_as_paths(gate.get("blocked_paths"))),
        "validator_chain": _as_strings(gate.get("validator_chain")),
        "approval_timestamp_utc": _approval_timestamp(gate),
        "expires_at_utc": str(gate.get("expires_at_utc") or "").strip(),
        "approval_nonce": str(evidence.get("approval_nonce") or gate.get("approval_nonce") or "").strip(),
        "key_id": str(evidence.get("key_id") or "").strip(),
        "key_version": evidence.get("key_version"),
    }


def canonical_payload(gate: dict[str, Any]) -> str:
    if gate.get("schema") == V2_PAYLOAD_SCHEMA:
        return approval_contract_v2.canonical_payload(gate)
    return json.dumps(canonical_payload_fields(gate), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_payload(gate: dict[str, Any]) -> str:
    """Compatibility alias for existing repository tests and callers."""
    return canonical_payload(gate)


def key_fingerprint(key: str) -> str:
    return sha256(key.encode("utf-8")).hexdigest()


def approval_hmac(gate: dict[str, Any], key: str) -> str:
    return hmac.new(key.encode("utf-8"), canonical_payload(gate).encode("utf-8"), sha256).hexdigest()


def _valid_hmac(gate: dict[str, Any], key: str | None) -> bool:
    evidence = gate.get("approval_evidence") if isinstance(gate.get("approval_evidence"), dict) else {}
    provided = str(evidence.get("approval_hmac_sha256") or "").lower()
    return bool(key and provided and hmac.compare_digest(provided, approval_hmac(gate, key)))


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def validate_trust_metadata(metadata: dict[str, Any], *, allow_test_trust: bool = False) -> list[str]:
    failed: list[str] = []
    if metadata.get("schema") != TRUST_ROOT_SCHEMA:
        failed.append("trust_metadata_schema_invalid")
    if metadata.get("trust_root_id") != TRUST_ROOT_ID:
        failed.append("trust_root_id_invalid")
    if str(metadata.get("authority") or "") != "Anthony, Human Owner":
        failed.append("trust_authority_invalid")
    environment = str(metadata.get("environment") or "PRODUCTION").upper()
    if environment == "TEST_ONLY" and not allow_test_trust:
        failed.append("test_trust_metadata_not_allowed_for_production")
    elif environment not in {"PRODUCTION", "TEST_ONLY"}:
        failed.append("trust_environment_invalid")
    state = str(metadata.get("state") or "").upper()
    if state not in {"UNPROVISIONED", "ACTIVE", "REVOKED"}:
        failed.append("trust_state_invalid")
    version = metadata.get("current_key_version")
    if not isinstance(version, int) or version < 0:
        failed.append("current_key_version_invalid")
    keys = metadata.get("keys")
    if not isinstance(keys, list):
        return failed + ["trust_keys_not_list"]

    seen: set[tuple[str, int]] = set()
    active_versions: list[int] = []
    for index, record in enumerate(keys):
        prefix = f"trust_key[{index}]"
        if not isinstance(record, dict):
            failed.append(f"{prefix}_not_object")
            continue
        key_id = str(record.get("key_id") or "").strip()
        key_version = record.get("key_version")
        fingerprint = str(record.get("key_fingerprint_sha256") or "").strip().lower()
        status = str(record.get("status") or "").upper()
        if not key_id:
            failed.append(f"{prefix}_key_id_missing")
        if not isinstance(key_version, int) or key_version <= 0:
            failed.append(f"{prefix}_key_version_invalid")
        elif (key_id, key_version) in seen:
            failed.append(f"{prefix}_identity_duplicate")
        else:
            seen.add((key_id, key_version))
        if not FINGERPRINT_PATTERN.fullmatch(fingerprint):
            failed.append(f"{prefix}_fingerprint_invalid")
        if status not in {"ACTIVE", "REVOKED"}:
            failed.append(f"{prefix}_status_invalid")
        if _parse_utc(str(record.get("created_at_utc") or "")) is None:
            failed.append(f"{prefix}_created_at_invalid")
        if status == "ACTIVE" and isinstance(key_version, int):
            active_versions.append(key_version)
        if status == "REVOKED":
            if _parse_utc(str(record.get("revoked_at_utc") or "")) is None:
                failed.append(f"{prefix}_revoked_at_invalid")
            if not str(record.get("revocation_reason") or "").strip():
                failed.append(f"{prefix}_revocation_reason_missing")
    if state == "UNPROVISIONED" and (version != 0 or keys):
        failed.append("unprovisioned_trust_contains_keys")
    if state == "ACTIVE":
        if not active_versions:
            failed.append("active_trust_has_no_active_key")
        elif version != max(active_versions):
            failed.append("current_key_version_not_highest_active")
    if state == "REVOKED" and active_versions:
        failed.append("revoked_trust_has_active_key")
    return failed


def _trusted_key_record(metadata: dict[str, Any], key_id: str, key_version: Any) -> tuple[dict[str, Any] | None, str | None]:
    keys = metadata.get("keys") if isinstance(metadata.get("keys"), list) else []
    same_id = [record for record in keys if isinstance(record, dict) and record.get("key_id") == key_id]
    if not same_id:
        return None, "unknown_key_id"
    exact = [record for record in same_id if record.get("key_version") == key_version]
    if not exact:
        return None, "stale_key_version"
    record = exact[0]
    if str(record.get("status") or "").upper() == "REVOKED":
        return record, "revoked_key"
    if str(record.get("status") or "").upper() != "ACTIVE":
        return record, "trusted_key_status_invalid"
    if key_version != metadata.get("current_key_version"):
        return record, "stale_key_version"
    return record, None


def _iter_approval_records(roots: Iterable[Path]) -> Iterable[tuple[Path, dict[str, Any]]]:
    seen_paths: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else root.rglob("*.json")
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                payload = load_json(candidate)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(payload.get("approval_evidence"), dict):
                yield resolved, payload


def nonce_reused(gate: dict[str, Any], *, approval_roots: Iterable[Path], current_gate_path: Path | None = None) -> bool:
    evidence = gate.get("approval_evidence") if isinstance(gate.get("approval_evidence"), dict) else {}
    nonce = str(evidence.get("approval_nonce") or "").strip()
    if not nonce:
        return False
    current = current_gate_path.resolve() if current_gate_path else None
    skipped_self = False
    for path, other in _iter_approval_records(approval_roots):
        other_evidence = other.get("approval_evidence")
        if str(other_evidence.get("approval_nonce") or "").strip() != nonce:
            continue
        if current is not None and path == current:
            continue
        if current is None and not skipped_self and _request_id(other) == _request_id(gate) and other == gate:
            skipped_self = True
            continue
        return True
    return False


def _validate_v1_approval_gate(
    gate: dict[str, Any], *, hmac_key: str | None = None,
    trust_metadata: dict[str, Any] | None = None, now: datetime | None = None,
    approval_roots: Iterable[Path] = (), current_gate_path: Path | None = None,
    allow_test_trust: bool = False,
) -> ApprovalAuthorityResult:
    failed: list[str] = []
    evidence = gate.get("approval_evidence") if isinstance(gate.get("approval_evidence"), dict) else {}
    evidence_type = str(evidence.get("type") or "MISSING")
    if str(gate.get("approval_status") or "") != "approved_for_apply":
        return ApprovalAuthorityResult(
            "PENDING_REVIEW", False, [], evidence_type,
            "Human Owner approval is pending; do not APPLY.",
        )
    if gate.get("approved_by_human") is not True:
        failed.append("approved_by_human_not_true")
    if not _request_id(gate):
        failed.append("approval_request_id_missing")
    if not str(gate.get("packet_id") or "").strip():
        failed.append("packet_id_missing")
    if not str(gate.get("requested_action") or "").strip():
        failed.append("requested_action_missing")
    if str(gate.get("requested_mode") or "").upper() != "APPLY":
        failed.append("requested_mode_not_apply")
    if not _as_paths(gate.get("allowed_paths")):
        failed.append("allowed_paths_missing")
    if not _as_paths(gate.get("blocked_paths")):
        failed.append("blocked_paths_missing")
    if not _as_strings(gate.get("validator_chain")):
        failed.append("validator_chain_missing")

    approval_timestamp = _approval_timestamp(gate)
    expires_at = str(gate.get("expires_at_utc") or "").strip()
    approved_dt = _parse_utc(approval_timestamp)
    expires_dt = _parse_utc(expires_at)
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not approval_timestamp:
        failed.append("approval_timestamp_missing")
    elif _is_midnight_placeholder(approval_timestamp):
        failed.append("approval_timestamp_placeholder")
    elif approved_dt is None:
        failed.append("approval_timestamp_invalid")
    elif approved_dt > current_time:
        failed.append("approval_timestamp_in_future")
    if expires_dt is None:
        failed.append("approval_expiry_missing_or_invalid")
    elif expires_dt <= current_time:
        failed.append("approval_expired")
    if approved_dt is not None and expires_dt is not None and expires_dt <= approved_dt:
        failed.append("approval_expiry_not_after_approval")

    if str(gate.get("bound_by") or "").strip() and not evidence:
        failed.append("bound_by_free_text_without_hardened_evidence")
    if evidence_type != "HMAC_SHA256":
        failed.append("approval_evidence_type_missing_or_unsupported")
    if str(evidence.get("canonical_payload_schema") or "") != PAYLOAD_SCHEMA:
        failed.append("canonical_payload_schema_missing_or_invalid")
    nonce = str(evidence.get("approval_nonce") or "").strip()
    if not nonce:
        failed.append("approval_nonce_missing")
    elif nonce_reused(gate, approval_roots=approval_roots, current_gate_path=current_gate_path):
        failed.append("approval_nonce_replayed")

    if trust_metadata is None:
        failed.append("trust_metadata_missing")
    else:
        failed.extend(validate_trust_metadata(trust_metadata, allow_test_trust=allow_test_trust))
        if str(trust_metadata.get("state") or "").upper() != "ACTIVE":
            failed.append("trust_root_not_active")
        key_id = str(evidence.get("key_id") or "").strip()
        key_version = evidence.get("key_version")
        record, trust_error = _trusted_key_record(trust_metadata, key_id, key_version)
        if trust_error:
            failed.append(trust_error)
        elif record is not None:
            expected_fingerprint = str(record.get("key_fingerprint_sha256") or "").lower()
            if str(evidence.get("key_fingerprint_sha256") or "").lower() != expected_fingerprint:
                failed.append("approval_key_fingerprint_not_bound")
            if not hmac_key or key_fingerprint(hmac_key) != expected_fingerprint:
                failed.append("key_fingerprint_mismatch")

    payload_hash = str(evidence.get("canonical_payload_sha256") or "").lower()
    expected_payload_hash = sha256(canonical_payload(gate).encode("utf-8")).hexdigest()
    if not hmac.compare_digest(payload_hash, expected_payload_hash):
        failed.append("canonical_payload_hash_mismatch")
    if not _valid_hmac(gate, hmac_key):
        failed.append("approval_hmac_missing_or_invalid")

    failed = list(dict.fromkeys(failed))
    status = "PASS" if not failed else "BLOCKED"
    return ApprovalAuthorityResult(
        status, status == "PASS", failed, evidence_type,
        "Hardened Human Owner approval evidence verified."
        if status == "PASS" else "Do not APPLY; collect exact-scope Human Owner approval evidence.",
    )


def _validate_v2_approval_gate(
    gate: dict[str, Any], *, hmac_key: str | None = None,
    trust_metadata: dict[str, Any] | None = None, now: datetime | None = None,
    approval_roots: Iterable[Path] = (), current_gate_path: Path | None = None,
    allow_test_trust: bool = False,
) -> ApprovalAuthorityResult:
    evidence = gate.get("approval_evidence") if isinstance(gate.get("approval_evidence"), dict) else {}
    evidence_type = str(evidence.get("type") or "MISSING")
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    status = str(gate.get("approval_status") or "")
    if status == "pending_review":
        failed = list(approval_contract_v2.pending_failures(gate, now=current_time))
        return ApprovalAuthorityResult(
            "BLOCKED" if failed else "PENDING_REVIEW", False, failed, evidence_type,
            "Do not APPLY; repair the incomplete v2 pending gate."
            if failed else "Human Owner approval is pending; do not APPLY.",
        )
    failed: list[str] = []
    if status != "approved_for_apply":
        failed.append("approval_status_invalid")
    if gate.get("approved_by_human") is not True:
        failed.append("approved_by_human_not_true")
    timestamp = _parse_utc(str(gate.get("approval_timestamp_utc") or ""))
    if timestamp is None:
        failed.append("approval_timestamp_missing_or_invalid")
    elif timestamp > current_time:
        failed.append("approval_timestamp_in_future")
    if evidence_type != "HMAC_SHA256":
        failed.append("approval_evidence_type_missing_or_unsupported")
    if evidence.get("canonical_payload_schema") != V2_PAYLOAD_SCHEMA:
        failed.append("canonical_payload_schema_missing_or_invalid")
    if nonce_reused(gate, approval_roots=approval_roots, current_gate_path=current_gate_path):
        failed.append("approval_nonce_replayed")

    if trust_metadata is None:
        failed.append("trust_metadata_missing")
    else:
        failed.extend(validate_trust_metadata(trust_metadata, allow_test_trust=allow_test_trust))
        if str(trust_metadata.get("state") or "").upper() != "ACTIVE":
            failed.append("trust_root_not_active")
        key_id = str(gate.get("key_id") or "").strip()
        key_version = gate.get("key_version")
        record, trust_error = _trusted_key_record(trust_metadata, key_id, key_version)
        if trust_error:
            failed.append(trust_error)
        elif record is not None:
            expected = str(record.get("key_fingerprint_sha256") or "").lower()
            if str(gate.get("key_fingerprint_sha256") or "").lower() != expected:
                failed.append("approval_key_fingerprint_not_bound")
            if str(evidence.get("key_fingerprint_sha256") or "").lower() != expected:
                failed.append("approval_evidence_key_fingerprint_not_bound")
            if not hmac_key or key_fingerprint(hmac_key) != expected:
                failed.append("key_fingerprint_mismatch")

    verification = approval_contract_v2.verify(gate, hmac_key, now=current_time)
    failed.extend(verification.failures)
    failed = list(dict.fromkeys(failed))
    return ApprovalAuthorityResult(
        "PASS" if not failed else "BLOCKED", not failed, failed, evidence_type,
        "Hardened Human Owner v2 approval evidence verified."
        if not failed else "Do not APPLY; repair or re-sign the exact v2 approval evidence.",
    )


def validate_approval_gate(
    gate: dict[str, Any], *, hmac_key: str | None = None,
    trust_metadata: dict[str, Any] | None = None, now: datetime | None = None,
    approval_roots: Iterable[Path] = (), current_gate_path: Path | None = None,
    allow_test_trust: bool = False,
) -> ApprovalAuthorityResult:
    schema = str(gate.get("schema") or "")
    kwargs = {
        "hmac_key": hmac_key, "trust_metadata": trust_metadata, "now": now,
        "approval_roots": approval_roots, "current_gate_path": current_gate_path,
        "allow_test_trust": allow_test_trust,
    }
    if schema == V2_PAYLOAD_SCHEMA:
        return _validate_v2_approval_gate(gate, **kwargs)
    if schema in {"", PAYLOAD_SCHEMA}:
        return _validate_v1_approval_gate(gate, **kwargs)
    return ApprovalAuthorityResult(
        "BLOCKED", False, ["approval_payload_schema_unknown"], "MISSING",
        "Do not APPLY; use an installed supported approval schema.",
    )


def validate_approval_inbox(authority: dict[str, Any]) -> list[str]:
    failed: list[str] = []
    for field in REQUIRED_APPROVAL_INBOX_FIELDS:
        if field not in authority:
            failed.append(f"inbox_missing_required_field:{field}")
    if str(authority.get("authority_status") or "").strip() != "active_authority":
        failed.append("inbox_authority_not_active")
    if str(authority.get("approval_status") or "").strip().lower() != "completed":
        failed.append("inbox_authority_not_completed")
    if authority.get("approved_by_human") is not True:
        failed.append("inbox_not_human_approved")
    if not _as_paths(authority.get("allowed_paths")):
        failed.append("inbox_allowed_paths_missing")
    if not _as_paths(authority.get("blocked_paths")):
        failed.append("inbox_blocked_paths_missing")
    if authority.get("validator_chain_required") is not True:
        failed.append("inbox_validator_chain_required_false")
    if authority.get("commit_package_required") is not True:
        failed.append("inbox_commit_package_required_false")
    if authority.get("push_blocked_until_final_review") is not True:
        failed.append("inbox_push_blocked_requirement_not_set")
    return failed


def validate_inbox_gate_alignment(gate: dict[str, Any], authority: dict[str, Any]) -> list[str]:
    failed: list[str] = []
    if str(gate.get("approval_status") or "").strip() == "approved_for_apply":
        if str(authority.get("approval_status") or "").strip().lower() != "completed":
            failed.append("inbox_and_gate_status_inconsistent_for_apply")
        if str(authority.get("authority_status") or "").strip() != "active_authority":
            failed.append("inbox_not_active_authority_for_apply")
    return failed


def validate_authority_bundle(
    gate: dict[str, Any], authority: dict[str, Any], *, hmac_key: str | None = None,
    trust_metadata: dict[str, Any] | None = None, now: datetime | None = None,
    approval_roots: Iterable[Path] = (), current_gate_path: Path | None = None,
    allow_test_trust: bool = False,
) -> ApprovalAuthorityResult:
    gate_result = validate_approval_gate(
        gate, hmac_key=hmac_key, trust_metadata=trust_metadata, now=now,
        approval_roots=approval_roots, current_gate_path=current_gate_path,
        allow_test_trust=allow_test_trust,
    )
    failed = list(gate_result.failed_checks)
    failed.extend(validate_approval_inbox(authority))
    failed.extend(validate_inbox_gate_alignment(gate, authority))
    status = gate_result.status
    next_action = gate_result.next_safe_action
    if status == "PASS" and failed:
        status = "BLOCKED"
        next_action = "Do not APPLY; fix inbox authority and APPLY gate together."
    elif status == "PENDING_REVIEW" and failed:
        status = "BLOCKED"
        next_action = "Do not APPLY; resolve inbox authority validity and APPLY gate evidence first."
    return ApprovalAuthorityResult(
        status, status == "PASS", list(dict.fromkeys(failed)),
        gate_result.evidence_type, next_action,
    )


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def canonical_production_repo_root(implementation_root: Path | None = None) -> Path:
    root = (implementation_root or Path(__file__).resolve().parents[2]).resolve()
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root.as_posix()}",
            "-C",
            str(root),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    common_dir_text = result.stdout.strip()
    if result.returncode != 0 or not common_dir_text or "\n" in common_dir_text:
        raise ValueError("canonical_production_repo_root_unresolved")
    common_dir = Path(common_dir_text).resolve()
    if common_dir.name.lower() != ".git" or not common_dir.is_dir():
        raise ValueError("canonical_production_git_common_dir_invalid")
    canonical_root = common_dir.parent.resolve()
    top_level = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={canonical_root.as_posix()}",
            "-C",
            str(canonical_root),
            "rev-parse",
            "--show-toplevel",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if top_level.returncode != 0 or Path(top_level.stdout.strip()).resolve() != canonical_root:
        raise ValueError("canonical_production_repo_root_invalid")
    return canonical_root


def _resolve_cli_paths(
    args: argparse.Namespace, *, production_root: Path | None = None,
) -> tuple[Path, Path, Path, Path, Path, bool]:
    gate_path = Path(args.gate).resolve()
    inbox_path = Path(args.inbox).resolve()
    trust_path = Path(args.trust_metadata).resolve()
    approval_root = Path(args.approval_root).resolve()
    archive = Path(args.approval_archive).resolve()
    fixture = bool(args.test_fixture_root)
    if fixture:
        root = Path(args.test_fixture_root).resolve()
        if any(not _within(path, root) for path in (gate_path, inbox_path, trust_path, approval_root, archive)):
            raise ValueError("fixture_path_outside_test_root")
    else:
        repo_root = (production_root or canonical_production_repo_root()).resolve()
        if inbox_path != (repo_root / DEFAULT_APPROVAL_INBOX_PATH).resolve():
            raise ValueError("noncanonical_production_inbox_path")
        if trust_path != (repo_root / DEFAULT_TRUST_METADATA_PATH).resolve():
            raise ValueError("noncanonical_production_trust_path")
        if approval_root != (repo_root / DEFAULT_APPROVAL_ROOT).resolve():
            raise ValueError("noncanonical_production_approval_root")
        if archive != (repo_root / DEFAULT_APPROVAL_ARCHIVE).resolve():
            raise ValueError("noncanonical_production_archive_path")
    return gate_path, inbox_path, trust_path, approval_root, archive, fixture



# PKT-045 repair amendments use the existing canonical payload/HMAC format.
# The signed validator_chain binds this complete, immutable plan by digest.
PKT045_REPAIR_ACTION = "RECOVER_EXISTING_PKT045_WITH_SIGNED_REPAIR"
PKT045_REPAIR_SCHEMA = "AIOS_PKT045_REPAIR_PLAN_V1"
PKT045_CHAIN_SCHEMA = "AIOS_PKT045_REPAIR_PLAN_V2"
PKT045_STAGE = ".aios/staging/PKT_FOREX_045/stage1_occ84"


def repair_digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def repair_file_hash(path):
    with Path(path).open("rb") as stream:
        return __import__("hashlib").file_digest(stream, "sha256").hexdigest()


def repair_read(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("repair_json_object_required")
    return value


def repair_consumption_identity(journal):
    return {k: journal[k] for k in ("request_id", "nonce", "bundle_sha256", "created_utc")}


def repair_owner(runtime):
    registry = repair_read(Path(runtime) / "automation/orchestration/locks/FILE_LOCK_REGISTRY.json")
    target = PKT045_STAGE.lower()
    owners = [row for row in registry["locks"] if row.get("status") == "ACTIVE" and any(
        p == target or p.startswith(target + "/") or target.startswith(p + "/")
        for p in (str(x).replace("\\", "/").strip("/").lower() for x in row.get("claimed_paths", [])))]
    if len(owners) != 1:
        raise ValueError("repair_exclusive_owner_required")
    return owners[0]


def repair_acceptance_identity(plan, record):
    identity = {
        "schema": "AIOS_PKT045_REPAIR_ACCEPTANCE_V1",
        "parent_identity": plan["consumption"],
        "parent_journal_sha256": plan["consumption_sha256"],
        "plan_sha256": repair_digest(plan),
        "amendment_id": record["approval_request_id"],
        "amendment_nonce": record["approval_evidence"]["approval_nonce"],
        "amendment_payload_sha256": record["approval_evidence"]["canonical_payload_sha256"],
    }
    if plan["schema"] == PKT045_CHAIN_SCHEMA:
        identity.update(schema="AIOS_PKT045_REPAIR_ACCEPTANCE_V2", generation=plan["generation"],
            parent_amendment_id=plan["parent_amendment_id"], parent_amendment_sha256=plan["parent_amendment_sha256"],
            prior_chain_sha256=plan["prior_chain_sha256"], candidate_sha256=plan["candidate_sha256"])
    return identity


def repair_acceptance_path(plan):
    base = Path(plan["runtime_root"]) / PKT045_STAGE / "checkpoints"
    if plan["schema"] == PKT045_CHAIN_SCHEMA:
        return base / "muscle98_repair_chain" / ("%06d.json" % plan["generation"])
    return base / "muscle98_repair_acceptance.json"


class RepairSignatureSession:
    """Process-local memo of actual HMAC checks; never stores the owner key.

    Sealing prevents admitting any new bytes without a key. Every use still
    checks exact records, trust/revocation metadata, expiry and nonce replay.
    No serialized/session-file form is accepted.
    """
    def __init__(self):
        self._verified = set()
        self._sealed = False
        self._pid = os.getpid()

    def seal(self):
        self._sealed = True

    def verify(self, gate, authority, **inputs):
        if os.getpid() != self._pid:
            raise ValueError("repair_signature_session_wrong_process")
        identity = (repair_digest(gate), repair_digest(authority), repair_digest(inputs["trust_metadata"]),
                    str(Path(inputs["current_gate_path"]).resolve()), inputs["allow_test_trust"])
        if not self._sealed:
            result = validate_authority_bundle(gate, authority, **inputs)
            if result.hardened_approval_verified:
                self._verified.add(identity)
            return result
        if identity not in self._verified:
            raise ValueError("repair_signature_session_binding_changed")
        now = inputs["now"]
        if not _parse_utc(_approval_timestamp(gate)) <= now < _parse_utc(gate["expires_at_utc"]):
            raise ValueError("repair_signature_session_expired")
        if nonce_reused(gate, approval_roots=inputs["approval_roots"], current_gate_path=inputs["current_gate_path"]):
            raise ValueError("repair_signature_session_nonce_replayed")
        return ApprovalAuthorityResult("PASS", True, [], "HMAC_SHA256", "Exact process-local verified signature")


def repair_changed_files(before, after):
    return {p: {"before": before.get(p), "after": after.get(p)}
            for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)}


def repair_checkpoint_lineage(plan):
    return {"transaction": repair_digest(plan["consumption"]), "population": plan["population_sha256"],
            "checkpoint_path": str(Path(plan["runtime_root"]) / PKT045_STAGE / "checkpoints/raw_acquisition.json")}


def _repair_chain(plan, *, old, bundle, inbox, signature_check, inputs, now):
    ancestors = plan["ancestry"]
    generation = plan["generation"]
    if type(generation) is not int or generation < 1 or not isinstance(ancestors, list) or generation != len(ancestors) + 1:
        raise ValueError("repair_chain_generation_invalid")
    if plan["prior_chain_sha256"] != repair_digest(ancestors):
        raise ValueError("repair_chain_root_changed")
    previous = old
    accepted_paths = set()
    record_paths = set()
    previous_time = _parse_utc(plan["consumption"]["created_utc"])
    for index, entry in enumerate(ancestors, 1):
        if set(entry) != {"plan_path", "plan_sha256", "record_path", "record_sha256", "acceptance_path", "acceptance_sha256"}:
            raise ValueError("repair_chain_entry_invalid")
        prior = repair_read(entry["plan_path"])
        record_path = inbox / ("APPLY_APPROVAL_GATE_" + prior["amendment_id"] + ".json")
        acceptance_path = repair_acceptance_path(prior).resolve()
        if Path(entry["record_path"]).resolve() != record_path or Path(entry["acceptance_path"]).resolve() != acceptance_path:
            raise ValueError("repair_chain_paths_changed")
        for kind in ("plan", "record", "acceptance"):
            if repair_file_hash(entry[kind + "_path"]) != entry[kind + "_sha256"]:
                raise ValueError("repair_chain_ancestor_changed")
        record, accepted = repair_read(record_path), repair_read(acceptance_path)
        expected = repair_acceptance_identity(prior, record)
        if set(accepted) != set(expected) | {"accepted_utc"} or any(accepted.get(k) != v for k, v in expected.items()):
            raise ValueError("repair_chain_acceptance_changed")
        accepted_time = _parse_utc(accepted["accepted_utc"])
        if accepted_time is None or not previous_time <= accepted_time <= now:
            raise ValueError("repair_chain_time_invalid")
        if not _parse_utc(prior["not_before_utc"]) <= accepted_time < _parse_utc(prior["expires_at_utc"]):
            raise ValueError("repair_chain_ancestor_expired")
        previous_time = accepted_time
        expected_chain = ["PKT045_PARENT_APPROVAL_SHA256=" + plan["parent_approval_sha256"],
                          "PKT045_REPAIR_PLAN_SHA256=" + repair_digest(prior)]
        if (record.get("validator_chain") != expected_chain or record.get("repair_plan_sha256") != repair_digest(prior)
                or record.get("repair_parent_request_id") != plan["parent_request_id"]
                or _request_id(record) != prior["amendment_id"] or record.get("requested_action") != PKT045_REPAIR_ACTION
                or record.get("allowed_paths") != plan["allowed_paths"] or record.get("blocked_paths") != plan["blocked_paths"]
                or record.get("expires_at_utc") != prior["expires_at_utc"]):
            raise ValueError("repair_chain_signature_binding_changed")
        checked = signature_check(record, repair_read(inbox / "APPROVAL_INBOX_001.json"),
            **{**inputs, "current_gate_path": record_path, "now": accepted_time})
        if not checked.hardened_approval_verified:
            raise ValueError("repair_chain_ancestor_signature_invalid")
        for field in ("parent_request_id", "parent_approval_sha256", "parent_bundle_path", "parent_bundle_sha256",
                      "original_candidate_sha256", "consumption", "owner", "population_sha256", "runtime_root",
                      "allowed_paths", "blocked_paths", "workers", "resource_limits", "recovery_procedure"):
            if prior[field] != plan[field]:
                raise ValueError("repair_chain_ancestor_scope_changed")
        prior_bundle = repair_read(prior["candidate_bundle_path"])
        if repair_digest(prior_bundle) != prior["candidate_bundle_sha256"] or repair_digest(prior_bundle["candidate"]) != prior["candidate_sha256"]:
            raise ValueError("repair_chain_ancestor_candidate_changed")
        for field in set(old) | set(prior_bundle):
            if field not in {"candidate", "config"} and old.get(field) != prior_bundle.get(field):
                raise ValueError("repair_chain_ancestor_bundle_scope_changed")
        for field in set(old["config"]) | set(prior_bundle["config"]):
            if field not in {"bundle_path", "commands", "command_sha256"} and old["config"].get(field) != prior_bundle["config"].get(field):
                raise ValueError("repair_chain_ancestor_configuration_changed")
        if prior["schema"] == PKT045_REPAIR_SCHEMA:
            if index != 1:
                raise ValueError("repair_chain_legacy_generation_invalid")
        elif prior["schema"] == PKT045_CHAIN_SCHEMA:
            if (prior["generation"] != index or prior["ancestry"] != ancestors[:index-1]
                    or prior["prior_chain_sha256"] != repair_digest(ancestors[:index-1])
                    or prior["previous_candidate_sha256"] != repair_digest(previous["candidate"])
                    or prior["checkpoint_lineage"] != repair_checkpoint_lineage(plan)):
                raise ValueError("repair_chain_ancestry_changed")
            if (prior["changed_files"] != repair_changed_files(previous["candidate"], prior_bundle["candidate"])
                    or prior["nonce"] != record["approval_evidence"]["approval_nonce"]
                    or prior["approved_source_paths"] != plan["approved_source_paths"]
                    or prior["approved_output_paths"] != plan["approved_output_paths"]
                    or prior["acceptance_requirements"] != plan["acceptance_requirements"]
                    or prior["rollback_authority"] != plan["rollback_authority"]):
                raise ValueError("repair_chain_ancestor_repair_scope_changed")
            expected_parent = repair_read(ancestors[index-2]["plan_path"])["amendment_id"] if index > 1 else None
            expected_hash = ancestors[index-2]["record_sha256"] if index > 1 else plan["parent_approval_sha256"]
            if prior["parent_amendment_id"] != expected_parent or prior["parent_amendment_sha256"] != expected_hash:
                raise ValueError("repair_chain_parent_changed")
        else:
            raise ValueError("repair_chain_schema_invalid")
        if any(plan["receipt_lineage"].get(p) != digest for p, digest in prior["receipt_lineage"].items()):
            raise ValueError("repair_chain_checkpoint_regression")
        previous = prior_bundle
        accepted_paths.add(acceptance_path)
        record_paths.add(record_path)
    expected_parent = repair_read(ancestors[-1]["plan_path"])["amendment_id"] if ancestors else None
    expected_hash = ancestors[-1]["record_sha256"] if ancestors else plan["parent_approval_sha256"]
    if plan["parent_amendment_id"] != expected_parent or plan["parent_amendment_sha256"] != expected_hash:
        raise ValueError("repair_chain_stale_parent")
    if plan["previous_candidate_sha256"] != repair_digest(previous["candidate"]):
        raise ValueError("repair_chain_previous_candidate_changed")
    if plan["changed_files"] != repair_changed_files(previous["candidate"], bundle["candidate"]) or not plan["changed_files"]:
        raise ValueError("repair_chain_changed_scope_invalid")
    if plan["checkpoint_lineage"] != repair_checkpoint_lineage(plan):
        raise ValueError("repair_chain_checkpoint_lineage_changed")
    sources = {"dependency_root": bundle["config"]["dependency_root"], "sealed_inputs": bundle["config"]["sealed_inputs"]}
    outputs = {k: bundle["config"][k] for k in ("output", "state_root", "allocation_root")}
    if (plan["approved_source_paths"] != sources or plan["approved_output_paths"] != outputs
            or plan["rollback_authority"] != "STOP_PRESERVE_PROGRESS_NO_OWNER_TRANSFER"
            or plan["acceptance_requirements"] != {"objects": plan["resource_limits"]["acceptance_objects"], "workers": plan["workers"], "continue_automatically": True}):
        raise ValueError("repair_chain_recovery_scope_changed")
    created = _parse_utc(plan["created_utc"])
    if created is None or not previous_time <= created <= now or created > _parse_utc(plan["expires_at_utc"]):
        raise ValueError("repair_chain_creation_time_invalid")
    if not re.fullmatch(r"[0-9a-f]{32}", plan["nonce"]):
        raise ValueError("repair_chain_nonce_invalid")
    base = Path(plan["runtime_root"]) / PKT045_STAGE / "checkpoints"
    actual = set((base / "muscle98_repair_chain").glob("*.json"))
    legacy = base / "muscle98_repair_acceptance.json"
    if legacy.exists(): actual.add(legacy)
    current = repair_acceptance_path(plan)
    if {p.resolve() for p in actual} - {current.resolve()} != accepted_paths:
        raise ValueError("repair_chain_stale_or_forked_head")
    return record_paths


def validate_pkt045_repair(plan, *, approval_root, key, allow_test=False,
                          record=None, record_path=None, for_signing=False, now=None, signature_session=None):
    """Read-only exact binding checks shared by human signer and recovery.

    Original approval, consumption identity and owner generation remain immutable.
    No signature, approval, acceptance, journal, lock or runtime state is written.
    """
    now = now or datetime.now(timezone.utc)
    required = {"schema", "amendment_id", "parent_request_id", "parent_approval_sha256",
        "parent_bundle_path", "parent_bundle_sha256", "original_candidate_sha256",
        "candidate_bundle_path", "candidate_bundle_sha256", "candidate_sha256",
        "runtime_root", "consumption", "consumption_sha256", "owner",
        "starting_phase", "population_sha256", "checkpoint_sha256", "receipt_lineage",
        "allowed_paths", "blocked_paths", "workers", "resource_limits",
        "action", "not_before_utc", "expires_at_utc", "reason", "recovery_procedure",
        "continuation_command", "working_directory"}
    chained = plan.get("schema") == PKT045_CHAIN_SCHEMA
    if chained:
        required |= {"generation", "parent_amendment_id", "parent_amendment_sha256", "prior_chain_sha256",
                     "ancestry", "previous_candidate_sha256", "changed_files", "checkpoint_lineage",
                     "approved_source_paths", "approved_output_paths", "acceptance_requirements",
                     "rollback_authority", "created_utc", "nonce"}
    if set(plan) != required or plan["schema"] not in {PKT045_REPAIR_SCHEMA, PKT045_CHAIN_SCHEMA}:
        raise ValueError("repair_plan_schema_invalid")
    if not re.fullmatch(r"PKT045-REPAIR-[A-Za-z0-9-]{8,100}", plan["amendment_id"]):
        raise ValueError("repair_amendment_id_invalid")
    if plan["action"] != "recover" or plan["starting_phase"] not in ({"OWNER_ACQUIRED", "STOPPED", "STOPPED_RECOVERABLE"} if chained else {"OWNER_ACQUIRED"}):
        raise ValueError("repair_action_or_start_phase_invalid")
    if not isinstance(plan["reason"], str) or not plan["reason"].strip() or plan["recovery_procedure"] != "SAME_TRANSACTION_PRESERVE_OWNER_AND_RECEIPTS":
        raise ValueError("repair_reason_or_procedure_invalid")
    start, end = _parse_utc(plan["not_before_utc"]), _parse_utc(plan["expires_at_utc"])
    if start is None or end is None or not start <= now < end:
        raise ValueError("repair_validity_period_invalid")
    root = Path(plan["runtime_root"]).resolve()
    inbox = Path(approval_root).resolve()
    if inbox != root / "automation/orchestration/approval_inbox":
        raise ValueError("repair_runtime_inbox_mismatch")
    if allow_test:
        if root == canonical_production_repo_root():
            raise ValueError("repair_test_root_is_production")
        if not (root / "automation/orchestration/.aios-human-owner-approval-test-fixture").is_file():
            raise ValueError("repair_test_marker_missing")
    elif root != canonical_production_repo_root():
        raise ValueError("repair_noncanonical_runtime")
    parent_id = plan["parent_request_id"]
    if not re.fullmatch(r"[A-Za-z0-9-]{8,128}", parent_id) or parent_id == plan["amendment_id"]:
        raise ValueError("repair_parent_request_invalid")
    parent_path = inbox / ("APPLY_APPROVAL_GATE_" + parent_id + ".json")
    parent = repair_read(parent_path)
    if repair_file_hash(parent_path) != plan["parent_approval_sha256"] or _request_id(parent) != parent_id:
        raise ValueError("repair_parent_approval_changed")
    trust = repair_read(inbox / "AIOS_HUMAN_OWNER_APPROVAL_TRUST_ROOT_001.json")
    authority = repair_read(inbox / "APPROVAL_INBOX_001.json")
    inputs = dict(hmac_key=key, trust_metadata=trust, approval_roots=[inbox, inbox / "archive"],
                  allow_test_trust=allow_test, now=now)
    if signature_session is not None and type(signature_session) is not RepairSignatureSession:
        raise ValueError("repair_signature_session_invalid")
    signature_check = signature_session.verify if signature_session is not None else validate_authority_bundle
    verified = signature_check(parent, authority, current_gate_path=parent_path, **inputs)
    if verified.status != "PASS" or not verified.hardened_approval_verified:
        raise ValueError("repair_parent_signature_invalid")
    if end > _parse_utc(parent["expires_at_utc"]):
        raise ValueError("repair_extends_parent_expiry")
    old = repair_read(plan["parent_bundle_path"])
    bundle = repair_read(plan["candidate_bundle_path"])
    if repair_digest(old) != plan["parent_bundle_sha256"] or repair_digest(bundle) != plan["candidate_bundle_sha256"]:
        raise ValueError("repair_bundle_digest_mismatch")
    if parent.get("validator_chain", []).count("PKT045_HANDOFF_BUNDLE_SHA256=" + repair_digest(old)) != 1:
        raise ValueError("repair_parent_bundle_not_signed")
    if repair_digest(old["candidate"]) != plan["original_candidate_sha256"] or repair_digest(bundle["candidate"]) != plan["candidate_sha256"]:
        raise ValueError("repair_candidate_digest_mismatch")
    if old["request_id"] != parent_id or bundle["request_id"] != parent_id or old["packet_id"] != "PKT-FOREX-045":
        raise ValueError("repair_wrong_transaction")
    # Only executable identities and their exact launch interfaces can change.
    for field in set(old) | set(bundle):
        if field not in {"candidate", "config"} and old.get(field) != bundle.get(field):
            raise ValueError("repair_bundle_scope_changed")
    for field in set(old["config"]) | set(bundle["config"]):
        if field not in {"bundle_path", "commands", "command_sha256"} and old["config"].get(field) != bundle["config"].get(field):
            raise ValueError("repair_configuration_changed")
    if Path(bundle["config"]["bundle_path"]).resolve() != Path(plan["candidate_bundle_path"]).resolve():
        raise ValueError("repair_bundle_path_mismatch")
    if Path(bundle["config"]["runtime_root"]).resolve() != root:
        raise ValueError("repair_bundle_runtime_mismatch")
    if bundle["config"]["mode"] != ("TEST_ONLY" if allow_test else "PRODUCTION"):
        raise ValueError("repair_trust_environment_mismatch")
    for field in ("allowed_paths", "blocked_paths", "workers", "resource_limits", "population_sha256"):
        if plan[field] != old[field] or plan[field] != bundle[field]:
            raise ValueError("repair_limits_or_scope_changed")
    engineering_root = Path(__file__).resolve().parents[2].parent / "pkt-aios-adaptive-workforce-v1"
    command = [bundle["config"]["python"], "-B", "-m",
        "automation.orchestration.adaptive_workforce.pkt045_activation",
        "--bundle", plan["candidate_bundle_path"], "--operation", "recover",
        "--repair-plan", str(Path(plan["candidate_bundle_path"]).with_name("repair_plan.json")),
        "--repair-amendment", str(inbox / ("APPLY_APPROVAL_GATE_" + plan["amendment_id"] + ".json"))]
    if chained:
        command += ["--owner-key-stdin"]
    if allow_test:
        command += ["--test-fixture-root", str(root.parent if chained else Path(plan["candidate_bundle_path"]).parent)]
    if (plan["continuation_command"] != command or Path(plan["working_directory"]).resolve() != engineering_root.resolve()
            or bundle["config"].get("commands") != {"recover": command}
            or bundle["config"].get("command_sha256") != {"recover": repair_digest(command)}):
        raise ValueError("repair_continuation_interface_invalid")
    if plan["resource_limits"]["acceptance_objects"] != (40 if not allow_test else old["resource_limits"]["acceptance_objects"]):
        raise ValueError("repair_acceptance_requirement_changed")
    for path, digest in bundle["candidate"].items():
        if repair_file_hash(path) != digest:
            raise ValueError("repair_candidate_file_changed")
    # Verifier and signer themselves must be in the final signed candidate.
    for path in (Path(__file__).resolve(), Path(__file__).resolve().parents[1] / "orchestration/approval_inbox/Set-AiOsHumanApprovalDecision.HUMAN_ONLY.ps1"):
        if bundle["candidate"].get(str(path)) != repair_file_hash(path):
            raise ValueError("repair_signer_or_verifier_not_pinned")
    for path, digest in bundle["config"]["sealed_inputs"].items():
        if repair_file_hash(path) != digest:
            raise ValueError("repair_sealed_input_changed")
    output = root / PKT045_STAGE
    if repair_file_hash(output / "inventory/PKT045_PAIRED_TICK_OBJECT_INVENTORY.json") != plan["population_sha256"]:
        raise ValueError("repair_population_changed")
    journal_path = output / "checkpoints/muscle98_activation.json"
    journal = repair_read(journal_path)
    if repair_consumption_identity(journal) != plan["consumption"]:
        raise ValueError("repair_consumption_changed")
    consumed = plan["consumption"]
    if consumed["request_id"] != parent_id or consumed["nonce"] != parent["approval_evidence"]["approval_nonce"] or consumed["bundle_sha256"] != repair_digest(old):
        raise ValueError("repair_parent_consumption_mismatch")
    owner = repair_owner(root)
    if owner != plan["owner"] or owner.get("worker_id") != "EAST_OCC_84" or owner.get("approval_packet_id") != parent_id:
        raise ValueError("repair_owner_generation_changed")
    if _parse_utc(owner["expires_at_utc"]) <= now or end > _parse_utc(owner["expires_at_utc"]):
        raise ValueError("repair_owner_expiry_invalid")
    expected_chain = ["PKT045_PARENT_APPROVAL_SHA256=" + plan["parent_approval_sha256"],
                      "PKT045_REPAIR_PLAN_SHA256=" + repair_digest(plan)]
    if record is not None:
        if (_request_id(record) != plan["amendment_id"] or record.get("packet_id") != "PKT-FOREX-045"
                or record.get("requested_action") != PKT045_REPAIR_ACTION
                or record.get("requested_mode") != "APPLY"
                or record.get("allowed_paths") != plan["allowed_paths"]
                or record.get("blocked_paths") != plan["blocked_paths"]
                or record.get("validator_chain") != expected_chain
                or record.get("expires_at_utc") != plan["expires_at_utc"]
                or record.get("repair_parent_request_id") != parent_id
                or record.get("repair_plan_sha256") != repair_digest(plan)
                or record["approval_evidence"].get("approval_nonce") == consumed["nonce"]):
            raise ValueError("repair_signed_envelope_mismatch")
        verified = signature_check(record, authority, current_gate_path=record_path, **inputs)
        if verified.status != "PASS" or not verified.hardened_approval_verified:
            raise ValueError("repair_amendment_signature_invalid")
    ancestor_records = _repair_chain(plan, old=old, bundle=bundle, inbox=inbox,
        signature_check=signature_check, inputs=inputs, now=now) if chained else set()
    if chained and record is not None and record["approval_evidence"]["approval_nonce"] != plan["nonce"]:
        raise ValueError("repair_chain_nonce_mismatch")
    accepted_path = repair_acceptance_path(plan)
    if chained:
        allowed_bindings = [None]
        if plan["ancestry"]:
            e = plan["ancestry"][-1]
            prior = repair_read(e["plan_path"])
            if prior["schema"] == PKT045_CHAIN_SCHEMA:
                allowed_bindings = [dict(generation=prior["generation"], amendment_id=prior["amendment_id"],
                    plan_sha256=repair_digest(prior), acceptance_sha256=e["acceptance_sha256"], candidate_sha256=prior["candidate_sha256"])]
        if accepted_path.exists():
            allowed_bindings.append(dict(generation=plan["generation"], amendment_id=plan["amendment_id"],
                plan_sha256=repair_digest(plan), acceptance_sha256=repair_file_hash(accepted_path), candidate_sha256=plan["candidate_sha256"]))
        if journal.get("repair_binding") not in allowed_bindings:
            raise ValueError("repair_chain_activation_binding_changed")
    if accepted_path.exists():
        if for_signing or record is None:
            raise ValueError("repair_amendment_already_accepted")
        accepted = repair_read(accepted_path)
        expected = repair_acceptance_identity(plan, record)
        if set(accepted) != set(expected) | {"accepted_utc"} or any(accepted.get(k) != v for k, v in expected.items()):
            raise ValueError("repair_competing_amendment_or_acceptance_changed")
        accepted_time = _parse_utc(accepted["accepted_utc"])
        if accepted_time is None or not start <= accepted_time <= now:
            raise ValueError("repair_acceptance_time_invalid")
        if journal["phase"] not in {"OWNER_ACQUIRED", "RECONCILED", "ACCEPTED", "RUNNING", "STOPPED", "STOPPED_RECOVERABLE", "COMPLETE"}:
            raise ValueError("repair_accepted_transaction_phase_invalid")
    else:
        if journal["phase"] != plan["starting_phase"] or repair_file_hash(journal_path) != plan["consumption_sha256"]:
            raise ValueError("repair_start_phase_or_history_changed")
        if repair_file_hash(output / "checkpoints/raw_acquisition.json") != plan["checkpoint_sha256"]:
            raise ValueError("repair_checkpoint_lineage_changed")
    lineage = plan["receipt_lineage"]
    if not isinstance(lineage, dict):
        raise ValueError("repair_receipt_lineage_missing")
    if not accepted_path.exists():
        actual = {p.relative_to(output).as_posix() for p in (output / "receipts/raw_object_receipts").rglob("*.json")}
        if set(lineage) != actual:
            raise ValueError("repair_receipt_lineage_incomplete")
    for rel, digest in lineage.items():
        p = (output / rel).resolve()
        if not _within(p, output / "receipts/raw_object_receipts") or repair_file_hash(p) != digest:
            raise ValueError("repair_receipt_lineage_changed")
    for other_path in inbox.glob("APPLY_APPROVAL_GATE_*.json"):
        if other_path in ancestor_records | {parent_path, Path(record_path) if record_path else None}:
            continue
        other = repair_read(other_path)
        if other.get("repair_parent_request_id") == parent_id and other.get("approval_status") == "approved_for_apply":
            raise ValueError("repair_competing_signed_amendment")
    pending = {
        "schema": "AIOS_PACKET_APPROVAL_REQUEST.v1", "approval_gate_id": plan["amendment_id"],
        "approval_request_id": plan["amendment_id"], "packet_id": "PKT-FOREX-045",
        "requested_action": PKT045_REPAIR_ACTION, "requested_mode": "APPLY",
        "approved_mode": "DRY_RUN_ONLY", "approval_status": "pending_review", "approved_by_human": False,
        "approval_timestamp_utc": "", "expires_at_utc": plan["expires_at_utc"],
        "allowed_paths": plan["allowed_paths"], "blocked_paths": plan["blocked_paths"],
        "validator_chain": expected_chain, "validator_chain_required": True, "commit_package_required": True,
        "repair_parent_request_id": parent_id, "repair_plan_sha256": repair_digest(plan),
        "approval_evidence": {"type": "MISSING", "status": "NOT_SIGNED"},
    }
    return {"pending_gate": pending, "parent_gate": parent, "bundle": bundle, "plan_sha256": repair_digest(plan)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", default="automation/orchestration/approval_inbox/APPLY_APPROVAL_GATE_001.json")
    parser.add_argument("--inbox", default=str(DEFAULT_APPROVAL_INBOX_PATH))
    parser.add_argument("--trust-metadata", default=str(DEFAULT_TRUST_METADATA_PATH))
    parser.add_argument("--approval-root", default=str(DEFAULT_APPROVAL_ROOT))
    parser.add_argument("--approval-archive", default=str(DEFAULT_APPROVAL_ARCHIVE))
    parser.add_argument("--test-fixture-root")
    parser.add_argument("--print-canonical-payload", action="store_true")
    parser.add_argument("--print-canonical-payload-stdin", action="store_true")
    parser.add_argument("--print-canonical-payload-env", action="store_true")
    parser.add_argument("--validate-trust-metadata-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repair-plan")
    parser.add_argument("--repair-record")
    parser.add_argument("--prepare-repair", action="store_true")
    args = parser.parse_args()
    try:
        if args.print_canonical_payload_env:
            payload = json.loads(os.environ.get("AIOS_APPROVAL_CANONICAL_PAYLOAD_INPUT", ""))
            if not isinstance(payload, dict):
                raise ValueError("environment_gate_not_object")
            print(canonical_payload(payload))
            return 0
        if args.print_canonical_payload_stdin:
            payload = json.load(__import__("sys").stdin)
            if not isinstance(payload, dict):
                raise ValueError("stdin_gate_not_object")
            print(canonical_payload(payload))
            return 0
        gate_path, inbox_path, trust_path, approval_root, archive, fixture = _resolve_cli_paths(args)
        if args.repair_plan:
            record_path = Path(args.repair_record).resolve() if args.repair_record else None
            if record_path is not None and not _within(record_path, approval_root):
                raise ValueError("repair_record_outside_inbox")
            result = validate_pkt045_repair(repair_read(args.repair_plan),
                approval_root=approval_root, key=os.environ.get("AIOS_HUMAN_APPROVAL_HMAC_KEY"),
                allow_test=fixture, record=repair_read(record_path) if record_path else None,
                record_path=record_path, for_signing=args.prepare_repair)
            print(json.dumps(result["pending_gate"] if args.prepare_repair else {"status":"PASS"}, sort_keys=True))
            return 0
        if args.validate_trust_metadata_only:
            trust_issues = validate_trust_metadata(load_json(trust_path), allow_test_trust=fixture)
            trust_payload = {
                "validator": "aios_approval_authority_integrity_validator",
                "status": "PASS" if not trust_issues else "BLOCKED",
                "failed_checks": trust_issues,
            }
            print(json.dumps(trust_payload, indent=2, sort_keys=True) if args.json else f"status={trust_payload['status']}")
            return 0 if not trust_issues else 1
        gate = load_json(gate_path)
        if args.print_canonical_payload:
            print(canonical_payload(gate))
            return 0
        result = validate_authority_bundle(
            gate, load_json(inbox_path),
            hmac_key=os.environ.get("AIOS_HUMAN_APPROVAL_HMAC_KEY"),
            trust_metadata=load_json(trust_path),
            approval_roots=(approval_root, archive), current_gate_path=gate_path,
            allow_test_trust=fixture,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = ApprovalAuthorityResult(
            "BLOCKED", False, [str(exc)], "MISSING", "Do not APPLY; repair approval inputs."
        )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"status={result.status}")
        print(f"hardened_approval_verified={str(result.hardened_approval_verified).lower()}")
        print(f"failed_checks={','.join(result.failed_checks)}")
    return 0 if result.status in {"PASS", "PENDING_REVIEW"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
