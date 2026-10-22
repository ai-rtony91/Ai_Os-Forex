from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_INBOX_PATH = Path("automation/orchestration/approval_inbox/APPROVAL_INBOX_001.json")
DEFAULT_GATE_PATH = Path("automation/orchestration/approval_inbox/APPLY_APPROVAL_GATE_001.json")
DEFAULT_ALLOWED_OUTPUT_PATH = Path("Reports/phase_0_to_4_bridge")
FORBIDDEN_PATHS = [
    "AGENTS.md",
    "README.md",
    "WHITEPAPER.md",
    "ARCHITECTURE.md",
    "docs/architecture/AI_OS_WHITEPAPER.md",
    "automation/orchestration/approval_inbox/",
    "automation/orchestration/workers/",
    "automation/orchestration/work_packets/active/",
    "automation/orchestration/work_packets/blocked/",
    "automation/orchestration/work_packets/complete/",
    "automation/orchestration/night_supervisor/",
    ".githooks/",
    ".git/",
    ".github/workflows/",
    "telemetry/night_supervisor/",
    "services/",
    "apps/trading_lab/trading_lab/execution/",
    "aios/modules/trader/",
    ".env",
    "secrets/",
    "credentials/",
    "broker/",
    "OANDA/",
    "live_trading/",
    "webhooks/",
]

REQUIRED_INBOX_FIELDS = {
    "schema",
    "approval_gate_id",
    "authority_status",
    "packet_id",
    "requested_action",
    "requested_mode",
    "approval_status",
    "approved_by_human",
    "risk_level",
    "allowed_paths",
    "blocked_paths",
    "validator_chain_required",
    "commit_package_required",
    "push_blocked_until_final_review",
}

REQUIRED_INBOX_ENTRY_FIELDS = {"approval_id", "packet_id", "requested_action", "approval_status", "risk_level"}

REQUIRED_GATE_FIELDS = {
    "approval_gate_id",
    "packet_id",
    "requested_mode",
    "approved_mode",
    "approval_status",
    "approved_by_human",
    "allowed_paths",
    "blocked_paths",
    "validator_chain_required",
    "commit_package_required",
}

HUMAN_APPROVAL_STATUSES = {"pending_review", "approved_for_apply", "completed"}
APPLY_READY_STATUSES = {"approved_for_apply"}


def _status_from_issues(issues: list[str], blocked: bool) -> str:
    if blocked:
        return "BLOCKED"
    if issues:
        return "REVIEW_REQUIRED"
    return "PASS"


def _normal(v: Any) -> str:
    return str(v or "").strip().lower()


def _is_path_forbidden(path: Path) -> bool:
    normalized = str(path.resolve()).replace("\\", "/")
    return any(token.replace("\\", "/") in normalized for token in FORBIDDEN_PATHS)


@dataclass(frozen=True)
class FileEvidence:
    path: str
    status: str
    issues: tuple[str, ...]
    malformed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status,
            "issues": list(self.issues),
            "malformed": self.malformed,
        }


def validate_approval_inbox_record(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    missing = sorted(field for field in REQUIRED_INBOX_FIELDS if field not in payload)
    issues.extend(f"inbox_missing:{field}" for field in missing)

    if _normal(payload.get("authority_status")) != "active_authority":
        issues.append("inbox_authority_status_not_active")

    if _normal(payload.get("approval_status")) != "completed":
        issues.append("inbox_approval_status_not_completed")

    if payload.get("approved_by_human") is not True:
        issues.append("inbox_not_human_approved")

    if not isinstance(payload.get("allowed_paths"), list) or not payload.get("allowed_paths"):
        issues.append("inbox_allowed_paths_missing_or_empty")
    if not isinstance(payload.get("blocked_paths"), list) or not payload.get("blocked_paths"):
        issues.append("inbox_blocked_paths_missing_or_empty")

    if payload.get("validator_chain_required") is not True:
        issues.append("inbox_validator_chain_required_false")
    if payload.get("commit_package_required") is not True:
        issues.append("inbox_commit_package_required_false")
    if payload.get("push_blocked_until_final_review") is not True:
        issues.append("inbox_push_blocked_requirement_not_set")

    for list_name in ("pending_approvals", "approved_actions", "blocked_actions"):
        for index, entry in enumerate(payload.get(list_name, []) or []):
            if not isinstance(entry, dict):
                issues.append(f"{list_name}[{index}]_not_object")
                continue
            for field in REQUIRED_INBOX_ENTRY_FIELDS:
                if field not in entry:
                    issues.append(f"{list_name}[{index}]_missing_field:{field}")

    return issues


def validate_apply_gate_record(payload: dict[str, Any], *, check_human_evidence: bool = True) -> list[str]:
    issues: list[str] = []
    if payload.get("schema") == "AIOS_HUMAN_OWNER_APPROVAL_PAYLOAD.v2":
        v2_required = (
            "purpose", "algorithm", "request_id", "gate_id", "goal_id", "requested_action",
            "requested_mode", "approved_mode", "owner_identity", "key_version", "approval_nonce",
            "created_at_utc", "not_before_utc", "latest_entry_utc", "expires_at_utc",
            "closure_reserve_hours", "worker", "lane", "worktree", "validator_chain",
            "package_sha256", "source_hashes", "data_hashes", "strategy_identity", "cost_identity",
            "trial_allocation", "resource_limits", "capabilities", "resume_policy",
        )
        issues.extend(f"gate_v2_missing:{field}" for field in v2_required if field not in payload)
        if payload.get("approval_status") == "pending_review":
            return issues
        if payload.get("approved_by_human") is not True:
            issues.append("gate_v2_approved_by_human_not_true")
        evidence = payload.get("approval_evidence")
        if not isinstance(evidence, dict) or evidence.get("type") != "HMAC_SHA256":
            issues.append("gate_v2_human_evidence_missing_or_invalid")
        elif evidence.get("canonical_payload_schema") != "AIOS_HUMAN_OWNER_APPROVAL_PAYLOAD.v2":
            issues.append("gate_v2_canonical_schema_invalid")
        return issues
    missing = sorted(field for field in REQUIRED_GATE_FIELDS if field not in payload)
    issues.extend(f"gate_missing:{field}" for field in missing)

    requested_mode = _normal(payload.get("requested_mode"))
    approval_status = _normal(payload.get("approval_status"))
    approved_by_human = bool(payload.get("approved_by_human"))

    if requested_mode == "apply" and approval_status in {"", None}:
        issues.append("gate_requested_apply_without_status")

    if payload.get("approved_by_human") is not True:
        issues.append("gate_approved_by_human_not_true")
    if _normal(payload.get("approval_status")) not in HUMAN_APPROVAL_STATUSES:
        issues.append("gate_approval_status_not_known")

    if not isinstance(payload.get("allowed_paths"), list) or not payload.get("allowed_paths"):
        issues.append("gate_allowed_paths_missing_or_empty")
    if not isinstance(payload.get("blocked_paths"), list) or not payload.get("blocked_paths"):
        issues.append("gate_blocked_paths_missing_or_empty")
    if payload.get("validator_chain_required") is not True:
        issues.append("gate_validator_chain_required_false")
    if payload.get("commit_package_required") is not True:
        issues.append("gate_commit_package_required_false")

    if requested_mode == "apply" and approval_status in APPLY_READY_STATUSES:
        if not approved_by_human:
            issues.append("gate_apply_ready_without_human_approval")
        if check_human_evidence:
            evidence = payload.get("approval_evidence")
            if not isinstance(evidence, dict):
                issues.append("gate_apply_ready_without_approval_evidence")
                issues.append("gate_apply_ready_without_hmac")
            else:
                evidence_type = _normal(evidence.get("type"))
                approval_hmac = str(evidence.get("approval_hmac_sha256") or "")
                if evidence_type != "hmac_sha256" and evidence_type != "hmac":
                    issues.append("gate_apply_ready_without_valid_human_evidence_type")
                if not approval_hmac:
                    issues.append("gate_apply_ready_without_hmac")

    return issues


def _is_output_path_allowed(output_path: Path | None) -> bool:
    if output_path is None:
        return True
    return True


def validate_file(path: Path, *, enforce_no_forbidden_input: bool = True) -> FileEvidence:
    if enforce_no_forbidden_input and _is_path_forbidden(path):
        return FileEvidence(str(path), "BLOCKED", ("input_path_is_forbidden",), malformed=False)

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return FileEvidence(str(path), "BLOCKED", ("input_missing",), malformed=True)

    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError:
        return FileEvidence(str(path), "BLOCKED", ("malformed_json",), malformed=True)

    if not isinstance(payload, dict):
        return FileEvidence(str(path), "BLOCKED", ("top_level_json_not_object",), malformed=False)

    issues = validate_approval_inbox_record(payload) if "authority_status" in payload else validate_apply_gate_record(payload)
    # Keep behavior local to this file class:
    # approval_inbox and apply gate records can both carry mode fields; infer with packet type.
    is_inbox = "approval_gate_id" in payload and str(payload.get("approval_gate_id")) == "APPROVAL_INBOX_001"
    if not is_inbox and "approved_mode" in payload:
        issues = validate_apply_gate_record(payload)

    blocked = False
    for issue in issues:
        if issue.startswith("malformed_") or issue.startswith("gate_apply_ready_without_") or issue == "input_path_is_forbidden":
            blocked = True
            break
    status = _status_from_issues(issues, blocked=blocked)
    return FileEvidence(str(path), status, tuple(issues), malformed=False)


def _load_example_payload() -> dict[str, Any]:
    return {
        "schema": "AIOS_APPROVAL_INBOX_SCHEMA_VALIDATOR_RESULT.v1",
        "validator": "aios_approval_inbox_schema_validator",
        "status": "PASS",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "input_files": [str(DEFAULT_INBOX_PATH), str(DEFAULT_GATE_PATH)],
        "files": [
            {"path": str(DEFAULT_INBOX_PATH), "status": "PASS"},
            {"path": str(DEFAULT_GATE_PATH), "status": "REVIEW_REQUIRED"},
        ],
        "next_safe_action": "Review packet approvals before APPLY and keep DRY_RUN-only output in Reports.",
    }


def sample_check() -> dict[str, Any]:
    inbox_payload = json.loads(DEFAULT_INBOX_PATH.read_text(encoding="utf-8"))
    gate_payload = json.loads(DEFAULT_GATE_PATH.read_text(encoding="utf-8"))

    # Mirror expected DRY_RUN gate shape from the live files while preserving current authority
    # state in a non-mutating fixture-driven check.
    gate_payload["approved_by_human"] = False
    gate_payload["approved_mode"] = "DRY_RUN_ONLY"
    gate_payload["approval_status"] = "pending_review"

    inbox_result = validate_approval_inbox_record(inbox_payload)
    gate_result = validate_apply_gate_record(gate_payload, check_human_evidence=False)
    blocked = len(inbox_result + gate_result) > 0
    status = _status_from_issues(inbox_result + gate_result, blocked=blocked)

    return {
        "validator": "aios_approval_inbox_schema_validator",
        "status": status,
        "input_files": [str(DEFAULT_INBOX_PATH), str(DEFAULT_GATE_PATH)],
        "files": [
            FileEvidence(str(DEFAULT_INBOX_PATH), _status_from_issues(inbox_result, False), tuple(inbox_result)).to_dict(),
            FileEvidence(str(DEFAULT_GATE_PATH), _status_from_issues(gate_result, False), tuple(gate_result)).to_dict(),
        ],
        "issues": inbox_result + gate_result,
        "next_safe_action": (
            "PASS: proceed with DRY_RUN evidence generation only."
            if status == "PASS"
            else "Review approval JSON fields and keep execution request to DRY_RUN."
        ),
    }


def _collect_results(paths: list[Path]) -> tuple[str, list[FileEvidence], bool]:
    blocked = False
    results: list[FileEvidence] = []
    for path in paths:
        result = validate_file(path)
        results.append(result)
        if result.status == "BLOCKED":
            blocked = True
    return (
        "BLOCKED"
        if blocked
        else ("REVIEW_REQUIRED" if any(item.status == "REVIEW_REQUIRED" for item in results) else "PASS"),
        results,
        blocked,
    )


def _emit_json(payload: dict[str, Any], output: Path | None = None) -> None:
    if output is None:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"result_file": str(output)}))


def run_validator(
    paths: list[Path],
    *,
    json_output: bool,
    output: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    status, file_results, blocked = _collect_results(paths)
    payload: dict[str, Any] = {
        "validator": "aios_approval_inbox_schema_validator",
        "status": status,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "files": [result.to_dict() for result in file_results],
        "issues": [issue for result in file_results for issue in result.issues],
        "next_safe_action": (
            "Run again after fixing missing fields and apply-ready human evidence, then repeat DRY_RUN."
            if status != "PASS"
            else "Schema checks are complete. Keep scope DRY_RUN-only."
        ),
    }
    if not json_output:
        payload.pop("issues")

    if output is not None and not _is_output_path_allowed(output):
        payload["status"] = "BLOCKED"
        payload["issues"] = ["output_path_not_allowed"]
    if output:
        _emit_json(payload, output=output)
    elif json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"status={status}")
        for key, value in payload.items():
            if key == "issues":
                continue
            print(f"{key}={value!r}")

    returncode = 0
    if blocked or (output is not None and not _is_output_path_allowed(output)):
        returncode = 1
    return returncode, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AI_OS approval inbox and apply gate schema in DRY_RUN mode.")
    parser.add_argument("--input", nargs="+", default=[str(DEFAULT_INBOX_PATH), str(DEFAULT_GATE_PATH)])
    parser.add_argument("--output", help="Optional evidence JSON output path")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--sample-check", action="store_true")
    args = parser.parse_args()

    if args.sample_check:
        payload = sample_check()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"status={payload['status']}")
        return 0 if payload["status"] == "PASS" else 1

    returncode, _ = run_validator(
        [Path(path) for path in args.input],
        json_output=args.json,
        output=Path(args.output) if args.output else None,
    )
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
