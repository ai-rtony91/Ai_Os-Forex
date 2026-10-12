"""Structural verifier for sanitized owner safety evidence artifacts.

This verifier checks only local artifact structure, metadata, freshness, and
sanitization declarations. It does not verify operational control behavior,
call broker APIs, read credentials, authorize trading, or execute orders.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / "Reports" / "forex_delivery"
OWNER_EVIDENCE_DIR = REPORTS_DIR / "owner_safety_evidence"
OWNER_EVIDENCE_DIR_RELATIVE = "Reports/forex_delivery/owner_safety_evidence"

INTAKE_PATH = REPORTS_DIR / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json"
PREP_STATE_PATH = (
    REPORTS_DIR / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json"
)
PREP_REPORT_PATH = (
    REPORTS_DIR / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md"
)
COLLECTION_STATE_PATH = (
    REPORTS_DIR / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_COLLECTION_V1_STATE.json"
)
COLLECTION_REPORT_PATH = (
    REPORTS_DIR / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_COLLECTION_V1_REPORT.md"
)
STATE_OUTPUT_PATH = (
    REPORTS_DIR / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_STATE.json"
)
REPORT_OUTPUT_PATH = (
    REPORTS_DIR / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_REPORT.md"
)
NEXT_PACKET_OUTPUT_PATH = (
    REPORTS_DIR / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_NEXT_CODEX_PACKET_V1.md"
)

PACKET_ID = "PKT-FOREX-OWNER-SAFETY-EVIDENCE-ARTIFACT-VERIFIER-V1"
PACKET_NAME = "Build Owner Safety Evidence Artifact Verifier V1"
MISSION_ID = "MISSION-AIOS-FOREX-FINISH-LINE-V1"
MISSION_NAME = "Governed Forex Finish Line"
PROGRAM_ID = "PROGRAM-FOREX-PROFIT-AUTONOMY-V1"
PROGRAM_NAME = "Forex Profit Autonomy System"
EPIC_ID = "EPC-FOREX-OWNER-SAFETY-EVIDENCE-VERIFICATION-001"
EPIC_NAME = "Owner Safety Evidence Artifact Verification"
BUCKET_ID = "BKT-FOREX-OWNER-SAFETY-EVIDENCE-VERIFICATION-001"
BUCKET_NAME = "Sanitized Owner Evidence Artifact Verification"

CONTROL_FIELDS = (
    "kill_switch_state",
    "daily_stop_state",
    "max_loss_state",
    "monitoring_ready",
)

PASS_STATUS = "OWNER_SAFETY_EVIDENCE_ARTIFACTS_STRUCTURALLY_VERIFIED"
FAIL_STATUS = "OWNER_SAFETY_EVIDENCE_ARTIFACTS_STRUCTURE_REVIEW_REQUIRED"

SAFETY_BOUNDARY = {
    "broker_api_allowed": False,
    "credentials_allowed": False,
    "order_execution_allowed": False,
    "live_trading_authorized": False,
    "scheduler_allowed": False,
    "daemon_allowed": False,
    "webhook_allowed": False,
    "account_identifier_persistence_allowed": False,
}

VALIDATOR_CHAIN = [
    "python -m py_compile automation/forex_engine/forex_owner_safety_evidence_artifact_verifier_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_artifact_verifier_v1.py",
    "python -m pytest tests/forex_engine/test_forex_owner_safety_evidence_artifact_verifier_v1.py -q",
    "python scripts/forex_delivery/run_forex_owner_safety_evidence_artifact_verifier_v1.py --write-state --write-report --write-next-packet",
    "python -m json.tool Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_STATE.json",
    "python automation/validators/aios_governance_validator.py --input Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_NEXT_CODEX_PACKET_V1.md",
    "git diff --check -- automation/forex_engine/forex_owner_safety_evidence_artifact_verifier_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_artifact_verifier_v1.py tests/forex_engine/test_forex_owner_safety_evidence_artifact_verifier_v1.py Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_STATE.json Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_REPORT.md Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_NEXT_CODEX_PACKET_V1.md",
    "git status --short --branch",
]

REQUIRED_DECLARATIONS = (
    "Sanitized: yes",
    "Contains secrets: no",
    "Contains broker account identifiers: no",
    "Broker API used: no",
    "Credentials used: no",
    "Order execution: no",
    "Live trading authorized: no",
    "Owner attestation",
)


def run_artifact_verifier(
    *,
    intake_path: Path | str = INTAKE_PATH,
    prep_state_path: Path | str = PREP_STATE_PATH,
    now_utc: datetime | None = None,
    write_state: bool = False,
    state_output_path: Path | str = STATE_OUTPUT_PATH,
    write_report: bool = False,
    report_output_path: Path | str = REPORT_OUTPUT_PATH,
    write_next_packet: bool = False,
    next_packet_output_path: Path | str = NEXT_PACKET_OUTPUT_PATH,
) -> dict[str, Any]:
    """Verify all four sanitized owner artifact files structurally."""

    intake = _load_json_mapping(Path(intake_path))
    current_time = now_utc or _default_verification_time(intake)
    prep_state = _load_json_mapping(Path(prep_state_path))

    controls_payload = _mapping(intake.get("controls"))
    prep_evaluations = _mapping(prep_state.get("control_evaluations"))

    control_results: dict[str, dict[str, Any]] = {}
    verified: list[str] = []
    failed: list[str] = []
    warnings: list[str] = []

    for control in CONTROL_FIELDS:
        control_result = _verify_control(
            control=control,
            intake_control=_mapping(controls_payload.get(control)),
            prep_evaluation=_mapping(prep_evaluations.get(control)),
            now_utc=current_time,
        )
        control_results[control] = control_result
        if control_result["status"] == "STRUCTURALLY_VERIFIED":
            verified.append(control)
        else:
            failed.append(control)

    status = PASS_STATUS if not failed else FAIL_STATUS
    next_safe_action = (
        "Route structurally verified sanitized owner artifacts to a finish-line safety-closure consumer update while keeping broker, demo, live micro, live trading, scheduler, daemon, webhook, and order execution locked."
        if not failed
        else "Repair failed sanitized owner artifact metadata or files, then rerun this structural verifier before any safety-closure consumer update."
    )

    result: dict[str, Any] = {
        "packet_id": PACKET_ID,
        "packet_name": PACKET_NAME,
        "mission_id": MISSION_ID,
        "mission_name": MISSION_NAME,
        "program_id": PROGRAM_ID,
        "program_name": PROGRAM_NAME,
        "epic_id": EPIC_ID,
        "epic_name": EPIC_NAME,
        "bucket_id": BUCKET_ID,
        "bucket_name": BUCKET_NAME,
        "artifact_verifier_status": status,
        "artifact_verified_controls": verified,
        "artifact_failed_controls": failed,
        "artifact_warning_controls": warnings,
        "control_results": control_results,
        "artifact_verification_scope": "Local structural verification of owner-sanitized artifact files, metadata freshness, approved path boundary, and no-secret/no-account declarations only.",
        "operational_control_verified": False,
        "owner_intake_modified": False,
        "evidence_artifacts_modified": False,
        "evidence_invented": False,
        "broker_api_used": False,
        "credentials_used": False,
        "order_execution": False,
        "live_trading_authorized": False,
        "safety_boundary": dict(SAFETY_BOUNDARY),
        "next_safe_action": next_safe_action,
        "source_artifacts": {
            "owner_intake_json": _relative_path(Path(intake_path)),
            "intake_verification_prep_state": _relative_path(Path(prep_state_path)),
            "intake_verification_prep_report": _relative_path(PREP_REPORT_PATH),
            "owner_evidence_collection_state": _relative_path(COLLECTION_STATE_PATH),
            "owner_evidence_collection_report": _relative_path(COLLECTION_REPORT_PATH),
            "owner_safety_evidence_dir": OWNER_EVIDENCE_DIR_RELATIVE,
        },
        "validator_chain": list(VALIDATOR_CHAIN),
    }

    if write_state:
        _write_text(Path(state_output_path), json.dumps(result, indent=2, sort_keys=True) + "\n")
    if write_report:
        _write_text(Path(report_output_path), build_report_markdown(result))
    if write_next_packet:
        _write_text(Path(next_packet_output_path), build_next_codex_packet(result))

    return result


def _default_verification_time(intake: Mapping[str, Any]) -> datetime:
    """Use the actual verifier runtime when no review timestamp is supplied."""

    return datetime.now(timezone.utc)


def _verify_control(
    *,
    control: str,
    intake_control: Mapping[str, Any],
    prep_evaluation: Mapping[str, Any],
    now_utc: datetime,
) -> dict[str, Any]:
    failures: list[str] = []
    artifact_path_text = _text(intake_control.get("sanitized_artifact_path"))
    artifact_path = _resolve_repo_path(artifact_path_text)
    artifact_text = ""

    if intake_control.get("evidence_present") is not True:
        failures.append("evidence_present is not true in intake JSON")

    if _text(prep_evaluation.get("status")) != "PRESENT_UNVERIFIED":
        failures.append("control status is not PRESENT_UNVERIFIED in intake verification state")

    if not artifact_path_text:
        failures.append("sanitized_artifact_path is missing")
    elif not _is_under_owner_evidence_dir(artifact_path):
        failures.append("sanitized_artifact_path is outside owner_safety_evidence path")

    if artifact_path_text and _is_under_owner_evidence_dir(artifact_path):
        if not artifact_path.exists():
            failures.append("artifact file is missing")
        elif artifact_path.stat().st_size <= 0:
            failures.append("artifact file is empty")
        else:
            artifact_text = artifact_path.read_text(encoding="utf-8")

    if artifact_text:
        normalized = _normalize_markdown(artifact_text)
        if f"Control: {control}" not in normalized:
            failures.append("artifact file does not contain matching Control line")
        for declaration in REQUIRED_DECLARATIONS:
            if declaration not in normalized:
                failures.append(f"artifact file missing declaration: {declaration}")

    timestamp_text = _text(intake_control.get("evidence_timestamp_utc"))
    freshness_hours = _positive_int(intake_control.get("freshness_window_hours"), 24)
    parsed_timestamp = _parse_utc_timestamp(timestamp_text)
    if not timestamp_text:
        failures.append("evidence_timestamp_utc is missing")
    elif parsed_timestamp is None:
        failures.append("evidence_timestamp_utc is invalid")
    elif parsed_timestamp > now_utc:
        failures.append("evidence_timestamp_utc is in the future")
    elif now_utc - parsed_timestamp > timedelta(hours=freshness_hours):
        failures.append("evidence_timestamp_utc is outside freshness_window_hours")

    if intake_control.get("contains_secret_or_account_identifier") is not False:
        failures.append("contains_secret_or_account_identifier is not false")

    return {
        "status": "STRUCTURALLY_VERIFIED" if not failures else "FAILED",
        "failures": failures,
        "sanitized_artifact_path": artifact_path_text,
        "freshness_window_hours": freshness_hours,
        "evidence_timestamp_utc": timestamp_text,
        "operational_control_verified": False,
        "broker_api_used": False,
        "credentials_used": False,
        "order_execution": False,
        "live_trading_authorized": False,
    }


def build_report_markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# AIOS Forex Owner Safety Evidence Artifact Verifier V1 Report",
        "",
        f"Status: {result.get('artifact_verifier_status')}",
        f"Current branch: {_git_value('branch', '--show-current')}",
        f"Current head: {_git_value('rev-parse', '--short', 'HEAD')}",
        "",
        "Artifact verification scope:",
        str(result.get("artifact_verification_scope")),
        "",
        "Verified controls:",
    ]
    for control in _string_list(result.get("artifact_verified_controls")):
        lines.append(f"- {control}")
    if not _string_list(result.get("artifact_verified_controls")):
        lines.append("- none")

    lines.extend(["", "Failed controls:"])
    for control in _string_list(result.get("artifact_failed_controls")):
        lines.append(f"- {control}")
    if not _string_list(result.get("artifact_failed_controls")):
        lines.append("- none")

    lines.extend(["", "Warning controls:"])
    for control in _string_list(result.get("artifact_warning_controls")):
        lines.append(f"- {control}")
    if not _string_list(result.get("artifact_warning_controls")):
        lines.append("- none")

    lines.extend(["", "Control results:"])
    for control in CONTROL_FIELDS:
        control_result = _mapping(_mapping(result.get("control_results")).get(control))
        lines.append(f"- {control}: {control_result.get('status')}")
        for failure in _string_list(control_result.get("failures")):
            lines.append(f"  - {failure}")

    lines.extend(
        [
            "",
            f"Operational control verified: {result.get('operational_control_verified')}",
            f"Owner intake modified: {result.get('owner_intake_modified')}",
            f"Evidence artifacts modified: {result.get('evidence_artifacts_modified')}",
            f"Evidence invented: {result.get('evidence_invented')}",
            f"Broker API used: {result.get('broker_api_used')}",
            f"Credentials used: {result.get('credentials_used')}",
            f"Order execution: {result.get('order_execution')}",
            f"Live trading authorized: {result.get('live_trading_authorized')}",
            "",
            f"Next safe action: {result.get('next_safe_action')}",
            "",
            "Validators:",
        ]
    )
    for validator in _string_list(result.get("validator_chain")):
        lines.append(f"- {validator}")
    return "\n".join(lines) + "\n"


def build_next_codex_packet(result: Mapping[str, Any]) -> str:
    return (
        "CODEX-ONLY PROMPT\n\n"
        "AI_OS EXECUTION TOKEN\n"
        "AI_OS BOOTSTRAP REQUIRED\n\n"
        "CONTRACT TITLE\n"
        "AIOS_FOREX_FINISH_LINE_SAFETY_CLOSURE_CONSUMER_UPDATE_V1\n\n"
        "IDENTITY MARKER\n"
        "AIOS_FOREX_FINISH_LINE_SAFETY_CLOSURE_CONSUMER_UPDATE_V1\n\n"
        "SUPERVISOR IDENTITY\n"
        "ChatGPT planning supervisor\n\n"
        "WORKER IDENTITY\n"
        "Codex\n\n"
        "PACKET ID\n"
        "PKT-FOREX-FINISH-LINE-SAFETY-CLOSURE-CONSUMER-UPDATE-V1\n\n"
        "MODE\n"
        "APPLY\n\n"
        "ZONE\n"
        "Trading Lab / Forex\n\n"
        "LANE\n"
        "Forex Finish-Line Safety-Closure Consumer Update\n\n"
        "WORKTREE\n"
        "C:\\Dev\\Ai.Os\n\n"
        "BRANCH\n"
        "resolve after preflight\n\n"
        "MISSION ID\n"
        "MISSION-AIOS-FOREX-FINISH-LINE-V1\n\n"
        "MISSION NAME\n"
        "Governed Forex Finish Line\n\n"
        "PROGRAM ID\n"
        "PROGRAM-FOREX-PROFIT-AUTONOMY-V1\n\n"
        "PROGRAM NAME\n"
        "Forex Profit Autonomy System\n\n"
        "EPIC ID\n"
        "EPC-FOREX-FINISH-LINE-SAFETY-CLOSURE-CONSUMER-UPDATE-001\n\n"
        "EPIC NAME\n"
        "Finish-Line Safety-Closure Consumer Update\n\n"
        "BUCKET ID\n"
        "BKT-FOREX-FINISH-LINE-SAFETY-CLOSURE-CONSUMER-UPDATE-001\n\n"
        "BUCKET NAME\n"
        "Consume Structurally Verified Owner Safety Evidence\n\n"
        "PACKET NAME\n"
        "Update Finish-Line Safety-Closure Consumer From Structurally Verified Owner Evidence\n\n"
        "APPROVAL AUTHORITY\n"
        "Anthony is the only authority for APPLY, commit, push, PR, merge, broker action, demo action, live action, credential use, owner evidence attestation, and live trading authorization.\n\n"
        "A later Human Owner message that explicitly approves commit is required before commit.\n"
        "A later Human Owner message that explicitly approves push is required before push.\n"
        "A later Human Owner message that explicitly approves merge is required before merge.\n\n"
        "MISSION\n"
        "Update only the finish-line safety-closure consumer state/report to consume the structurally verified owner safety evidence artifact verifier output. This packet may not verify live operational control, may not claim broker readiness, and may not authorize demo, live micro, live trading, scheduler, daemon, webhook, credentials, broker API, or order execution.\n\n"
        "PREFLIGHT\n"
        "cd C:\\Dev\\Ai.Os\n"
        "git status --short --branch\n"
        "git branch --show-current\n"
        "git log -1 --oneline\n\n"
        "ALLOWED PATHS\n"
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_STATE.json\n"
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_REPORT.md\n"
        "Reports/forex_delivery/AIOS_FOREX_FINISH_LINE_SAFETY_CLOSURE_CONSUMER_V1_STATE.json\n"
        "Reports/forex_delivery/AIOS_FOREX_FINISH_LINE_SAFETY_CLOSURE_CONSUMER_V1_REPORT.md\n\n"
        "FORBIDDEN PATHS\n"
        "AGENTS.md\n"
        "README.md\n"
        "WHITEPAPER.md\n"
        "docs/architecture/AI_OS_WHITEPAPER.md\n"
        "RISK_POLICY.md\n"
        ".env\n"
        "secrets\n"
        "credential files\n"
        "broker account identifiers\n"
        "owner intake JSON modification\n"
        "owner evidence artifact modification\n"
        "broker modules\n"
        "scheduler files\n"
        "daemon files\n"
        "webhook files\n"
        "dashboard mutation files\n"
        "unrelated docs\n"
        "unrelated tests\n"
        "any path outside C:\\Dev\\Ai.Os\n\n"
        "RULES\n"
        "Do not modify owner intake JSON.\n"
        "Do not modify owner evidence artifact files.\n"
        "Do not invent evidence.\n"
        "Do not read .env.\n"
        "Do not use credentials.\n"
        "Do not use broker API.\n"
        "Do not authorize live trading.\n"
        "Do not place trades.\n"
        "Do not start schedulers, daemons, loops, webhooks, or background workers.\n"
        "Do not commit.\n"
        "Do not push.\n"
        "Do not create PR.\n\n"
        "VALIDATOR CHAIN\n"
        "python -m json.tool Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_STATE.json\n"
        "git diff --check -- Reports/forex_delivery/AIOS_FOREX_FINISH_LINE_SAFETY_CLOSURE_CONSUMER_V1_STATE.json Reports/forex_delivery/AIOS_FOREX_FINISH_LINE_SAFETY_CLOSURE_CONSUMER_V1_REPORT.md\n"
        "git status --short --branch\n\n"
        "SAFE NEXT ACTION\n"
        "Consume structural owner evidence verification in the finish-line safety-closure consumer only; keep broker, demo, live micro, live trading, scheduler, daemon, webhook, credentials, broker API, and order execution locked.\n\n"
        "STOP POINT\n"
        "Stop after validators and final report. Do not commit. Do not push. Do not create PR.\n\n"
        "FINAL REPORT FORMAT\n"
        "STATUS:\n"
        "CURRENT_BRANCH:\n"
        "CURRENT_HEAD:\n"
        "SOURCE_ARTIFACT_VERIFIER_STATUS:\n"
        "CONSUMER_STATUS:\n"
        "OPERATIONAL_CONTROL_VERIFIED:\n"
        "BROKER_API_USED:\n"
        "CREDENTIALS_USED:\n"
        "ORDER_EXECUTION:\n"
        "LIVE_TRADING_AUTHORIZED:\n"
        "GIT_STATUS:\n"
    )


def _load_json_mapping(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return loaded


def _resolve_repo_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return ROOT / path


def _is_under_owner_evidence_dir(path: Path) -> bool:
    try:
        path.resolve().relative_to(OWNER_EVIDENCE_DIR.resolve())
    except ValueError:
        normalized = str(path).replace("\\", "/").lower()
        suffix = OWNER_EVIDENCE_DIR_RELATIVE.lower()
        return f"/{suffix}/" in normalized
    return True


def _parse_utc_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_markdown(text: str) -> str:
    return text.replace("\\_", "_").replace("\r\n", "\n")


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git_value(*command: str) -> str:
    try:
        return subprocess.check_output(["git", *command], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


__all__ = [
    "CONTROL_FIELDS",
    "PASS_STATUS",
    "FAIL_STATUS",
    "run_artifact_verifier",
    "build_report_markdown",
    "build_next_codex_packet",
]
