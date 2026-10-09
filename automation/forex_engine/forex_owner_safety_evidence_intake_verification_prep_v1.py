"""Owner safety evidence intake and verification-prep module for Forex.

This module emits/loads a sanitized owner evidence intake template and classifies
the four required controls into one of MISSING, PRESENT_UNVERIFIED, STALE, INVALID.

No broker API calls, credentials, scheduler/daemon activity, or verification of
control safety logic is performed here. The module never returns VERIFIED.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

ROOT_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT_DIR / "Reports" / "forex_delivery"
REPORTS_DIR_RELATIVE = Path("Reports") / "forex_delivery"
DEFAULT_INPUT_TEMPLATE_PATH = (
    REPORTS_DIR / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json"
)
RELATIVE_INPUT_TEMPLATE_PATH = (
    REPORTS_DIR_RELATIVE / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json"
)
DEFAULT_STATE_OUTPUT_PATH = (
    REPORTS_DIR / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json"
)
RELATIVE_STATE_OUTPUT_PATH = (
    REPORTS_DIR_RELATIVE
    / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json"
)
DEFAULT_REPORT_OUTPUT_PATH = (
    REPORTS_DIR / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md"
)
RELATIVE_REPORT_OUTPUT_PATH = (
    REPORTS_DIR_RELATIVE
    / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md"
)
DEFAULT_NEXT_PACKET_OUTPUT_PATH = (
    REPORTS_DIR
    / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
)
RELATIVE_NEXT_PACKET_OUTPUT_PATH = (
    REPORTS_DIR_RELATIVE
    / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
)


def _format_packet_path(path: Path) -> str:
    """Format a path for generated packets."""
    resolved_path = path.resolve()
    resolved_root = ROOT_DIR.resolve()
    try:
        return str(resolved_path.relative_to(resolved_root)).replace("\\", "/")
    except ValueError:
        return resolved_path.as_posix()


def _paths_equal(left: Path, right: Path) -> bool:
    """Return True when two paths point at the same normalized location."""
    return left.resolve().as_posix() == right.resolve().as_posix()


def _template_has_owner_input(owner_input: dict[str, object]) -> bool:
    """Return True when the template is not the default blank scaffold."""
    default_template = build_input_template()
    return owner_input != default_template


def _write_template_if_safe(
    *,
    input_template_path: Path,
    template_output_path: Path,
    owner_input: dict[str, object],
    input_error_present: bool = False,
) -> str:
    """Preserve input template when it already holds owner-provided evidence."""
    if input_error_present and _paths_equal(input_template_path, template_output_path):
        return "PRESERVED"
    if _paths_equal(input_template_path, template_output_path) and _template_has_owner_input(
        owner_input
    ):
        return "PRESERVED"
    _write_json(template_output_path, build_input_template())
    return "WRITTEN"

PACKET_ID = "PKT-FOREX-OWNER-SAFETY-EVIDENCE-INTAKE-VERIFICATION-PREP-V1"
PACKET_NAME = "Build Owner Safety Evidence Intake Verification Prep V1"
INPUT_INVALID_STATUS = "OWNER_SAFETY_EVIDENCE_INPUT_INVALID"
INPUT_INVALID_ERROR_TYPE = "JSON_DECODE_ERROR"
INPUT_NON_OBJECT_ERROR_TYPE = "JSON_SCHEMA_ERROR"
MISSING = "MISSING"
PRESENT_UNVERIFIED = "PRESENT_UNVERIFIED"
STALE = "STALE"
INVALID = "INVALID"

CONTROL_FIELDS = (
    "kill_switch_state",
    "daily_stop_state",
    "max_loss_state",
    "monitoring_ready",
)


def _read_git_command(command: list[str]) -> str:
    """Return output from a git command, or a fallback string on failure."""

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
        )
    except OSError:
        return "resolve after preflight"

    if result.returncode != 0:
        return "resolve after preflight"

    return result.stdout.strip()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def _to_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_utc_timestamp(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    candidates = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidates)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _serialize_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def build_input_template() -> dict[str, object]:
    """Return the owner-only template used for evidence intake."""

    return {
        "packet_id": PACKET_ID,
        "packet_name": PACKET_NAME,
        "template_version": "V1",
        "required_controls": list(CONTROL_FIELDS),
        "controls": {
            control: {
                "evidence_present": False,
                "evidence_type": "",
                "sanitized_artifact_path": "",
                "owner_attestation": "",
                "evidence_timestamp_utc": "",
                "freshness_window_hours": 24,
                "contains_secret_or_account_identifier": False,
                "notes": "",
            }
            for control in CONTROL_FIELDS
        },
    }


def _normalize_control_block(raw_control: dict[str, Any]) -> dict[str, Any]:
    freshness_hours = _to_int(
        raw_control.get("freshness_window_hours"), default=24
    )
    if freshness_hours <= 0:
        freshness_hours = 24

    return {
        "evidence_present": _to_bool(raw_control.get("evidence_present")),
        "evidence_type": _to_str(raw_control.get("evidence_type")),
        "sanitized_artifact_path": _to_str(raw_control.get("sanitized_artifact_path")),
        "owner_attestation": _to_str(raw_control.get("owner_attestation")),
        "evidence_timestamp_utc": _to_str(raw_control.get("evidence_timestamp_utc")),
        "freshness_window_hours": freshness_hours,
        "contains_secret_or_account_identifier": _to_bool(
            raw_control.get("contains_secret_or_account_identifier")
        ),
        "notes": _to_str(raw_control.get("notes")),
    }


def _classify_single_control(
    control_block: dict[str, Any], *, now_utc: datetime
) -> dict[str, object]:
    evidence_present = control_block["evidence_present"]
    evidence_type = control_block["evidence_type"]
    artifact_path = control_block["sanitized_artifact_path"]
    timestamp_text = control_block["evidence_timestamp_utc"]
    freshness_window_hours = control_block["freshness_window_hours"]
    contains_secret = control_block["contains_secret_or_account_identifier"]

    if not evidence_present:
        return {
            "status": MISSING,
            "reason": "Owner evidence not yet provided for this control.",
        }

    if contains_secret:
        return {
            "status": INVALID,
            "reason": "Evidence contains secret or account-identifying artifact.",
        }

    if not evidence_type or not artifact_path or not timestamp_text:
        return {
            "status": INVALID,
            "reason": "Evidence is claimed but missing required metadata.",
        }

    parsed_timestamp = _parse_utc_timestamp(timestamp_text)
    if parsed_timestamp is None:
        return {
            "status": INVALID,
            "reason": "Evidence timestamp is not valid ISO-8601 UTC text.",
        }

    if parsed_timestamp > now_utc:
        return {
            "status": INVALID,
            "reason": "Evidence timestamp is in the future and cannot be used for validation.",
        }

    age = now_utc - parsed_timestamp
    if age > timedelta(hours=freshness_window_hours):
        return {
            "status": STALE,
            "reason": "Evidence timestamp is outside the freshness window.",
        }

    return {
        "status": PRESENT_UNVERIFIED,
        "reason": "Evidence present with required metadata; not yet verified.",
    }


def _extract_control_payload(
    owner_input: dict[str, object] | None,
) -> dict[str, dict[str, Any]]:
    if not owner_input:
        return {
            control: _normalize_control_block({}) for control in CONTROL_FIELDS
        }
    template = owner_input.get("controls") or owner_input.get("control_sections") or {}
    if not isinstance(template, dict):
        return {
            control: _normalize_control_block({}) for control in CONTROL_FIELDS
        }
    return {
        control: _normalize_control_block(
            template.get(control, {}) if isinstance(template.get(control), dict) else {}
        )
        for control in CONTROL_FIELDS
    }


def _build_input_invalid_result(
    *,
    input_error_type: str,
    input_error_path: Path,
    current_timestamp: datetime,
) -> dict[str, object]:
    template = build_input_template()
    return {
        "packet_id": PACKET_ID,
        "packet_name": PACKET_NAME,
        "mission_id": "MISSION-AIOS-FOREX-FINISH-LINE-V1",
        "mission_name": "Governed Forex Finish Line",
        "program_id": "PROGRAM-FOREX-PROFIT-AUTONOMY-V1",
        "program_name": "Forex Profit Autonomy System",
        "epic_id": "EPC-FOREX-OWNER-SAFETY-EVIDENCE-INTAKE-001",
        "epic_name": "Owner Safety Evidence Intake And Verification Prep",
        "bucket_id": "BKT-FOREX-OWNER-SAFETY-EVIDENCE-INTAKE-001",
        "bucket_name": "Owner Safety Evidence Intake Template And Classifier",
        "status": INPUT_INVALID_STATUS,
        "current_timestamp_utc": _serialize_datetime(current_timestamp),
        "required_controls": list(CONTROL_FIELDS),
        "control_evaluations": {
            control: {
                "status": INVALID,
                "evidence_metadata": template["controls"][control],
            "reason": "Owner safety evidence input JSON is malformed or structurally invalid.",
            }
            for control in CONTROL_FIELDS
        },
        "missing_controls": [],
        "present_unverified_controls": [],
        "stale_controls": [],
        "invalid_controls": list(CONTROL_FIELDS),
        "owner_evidence_completion_percent": 0.0,
        "verification_claimed": False,
        "verification_mechanism_available": False,
        "next_safe_action": "Repair or replace the malformed sanitized intake JSON and rerun verification.",
        "broker_api_used": False,
        "credentials_used": False,
        "order_execution": False,
        "live_trading_authorized": False,
        "input_error_present": True,
        "input_error_type": input_error_type,
        "input_error_path": str(input_error_path),
        "safety_boundary": {
            "broker_api_allowed": False,
            "credentials_allowed": False,
            "order_execution_allowed": False,
            "live_trading_authorized": False,
            "scheduler_allowed": False,
            "daemon_allowed": False,
            "webhook_allowed": False,
            "account_identifier_persistence_allowed": False,
        },
    }


def run_forex_owner_safety_evidence_intake_verification_prep_v1(
    owner_input: dict[str, object] | None = None,
) -> dict[str, object]:
    """Run classification for the four required controls."""

    control_payloads = _extract_control_payload(owner_input)
    now_utc = _now_utc()
    control_evaluations: dict[str, object] = {}
    missing_controls: list[str] = []
    present_unverified_controls: list[str] = []
    stale_controls: list[str] = []
    invalid_controls: list[str] = []

    for control in CONTROL_FIELDS:
        detail = _classify_single_control(control_payloads[control], now_utc=now_utc)
        status = detail["status"]
        control_evaluations[control] = {
            "status": status,
            "evidence_metadata": control_payloads[control],
            "reason": detail["reason"],
        }
        if status == MISSING:
            missing_controls.append(control)
        elif status == PRESENT_UNVERIFIED:
            present_unverified_controls.append(control)
        elif status == STALE:
            stale_controls.append(control)
        else:
            invalid_controls.append(control)

    total_controls = len(CONTROL_FIELDS)
    owner_evidence_completion_percent = (
        100.0 * len(present_unverified_controls) / total_controls
    )

    if len(missing_controls) == total_controls:
        status = "OWNER_SAFETY_EVIDENCE_INTAKE_REQUIRED"
    elif (
        not invalid_controls
        and not stale_controls
        and len(present_unverified_controls) == total_controls
    ):
        status = "OWNER_SAFETY_EVIDENCE_PRESENT_UNVERIFIED"
    else:
        status = "OWNER_SAFETY_EVIDENCE_INTAKE_REVIEW"

    if invalid_controls:
        next_safe_action = (
            "Owner must replace invalid control entries with sanitized evidence metadata."
        )
    elif stale_controls:
        next_safe_action = (
            "Owner must refresh stale evidence entries with current sanitized artifacts."
        )
    elif missing_controls:
        next_safe_action = (
            "Owner must fill the intake template with current sanitized evidence for all controls."
        )
    else:
        next_safe_action = (
            "Sanitized evidence is present for all four controls and currently unverified; "
            "route to later verification only after explicit verification mechanisms are run."
        )

    return {
        "packet_id": PACKET_ID,
        "packet_name": PACKET_NAME,
        "mission_id": "MISSION-AIOS-FOREX-FINISH-LINE-V1",
        "mission_name": "Governed Forex Finish Line",
        "program_id": "PROGRAM-FOREX-PROFIT-AUTONOMY-V1",
        "program_name": "Forex Profit Autonomy System",
        "epic_id": "EPC-FOREX-OWNER-SAFETY-EVIDENCE-INTAKE-001",
        "epic_name": "Owner Safety Evidence Intake And Verification Prep",
        "bucket_id": "BKT-FOREX-OWNER-SAFETY-EVIDENCE-INTAKE-001",
        "bucket_name": "Owner Safety Evidence Intake Template And Classifier",
        "status": status,
        "current_timestamp_utc": _serialize_datetime(now_utc),
        "required_controls": list(CONTROL_FIELDS),
        "control_evaluations": control_evaluations,
        "missing_controls": missing_controls,
        "present_unverified_controls": present_unverified_controls,
        "stale_controls": stale_controls,
        "invalid_controls": invalid_controls,
        "owner_evidence_completion_percent": owner_evidence_completion_percent,
        "verification_claimed": False,
        "verification_mechanism_available": False,
        "next_safe_action": next_safe_action,
        "broker_api_used": False,
        "credentials_used": False,
        "order_execution": False,
        "live_trading_authorized": False,
        "input_error_present": False,
        "input_error_type": None,
        "input_error_path": None,
        "safety_boundary": {
            "broker_api_allowed": False,
            "credentials_allowed": False,
            "order_execution_allowed": False,
            "live_trading_authorized": False,
            "scheduler_allowed": False,
            "daemon_allowed": False,
            "webhook_allowed": False,
            "account_identifier_persistence_allowed": False,
        },
    }


def generate_next_packet_text(
    result: dict[str, object],
    *,
    current_branch: str | None = None,
    current_head: str | None = None,
    input_template_path: Path | None = None,
    template_output_path: Path | None = None,
    state_output_path: Path | None = None,
    report_output_path: Path | None = None,
    next_packet_output_path: Path | None = None,
) -> str:
    """Create the next gated Codex handoff packet."""

    branch = current_branch or _read_git_command(["git", "branch", "--show-current"])
    head = current_head or _read_git_command(["git", "rev-parse", "--short", "HEAD"])
    missing_controls = ", ".join(result["missing_controls"]) if result["missing_controls"] else "none"
    effective_input_template_path = input_template_path or DEFAULT_INPUT_TEMPLATE_PATH
    effective_template_output_path = template_output_path or DEFAULT_INPUT_TEMPLATE_PATH
    effective_state_output_path = state_output_path or DEFAULT_STATE_OUTPUT_PATH
    effective_report_output_path = report_output_path or DEFAULT_REPORT_OUTPUT_PATH
    effective_next_packet_output_path = next_packet_output_path or DEFAULT_NEXT_PACKET_OUTPUT_PATH

    input_template_path_for_validator = _format_packet_path(
        effective_input_template_path
    )
    template_path_for_validator = _format_packet_path(effective_template_output_path)
    state_path_for_validator = _format_packet_path(effective_state_output_path)
    report_path_for_validator = _format_packet_path(effective_report_output_path)
    next_packet_path_for_validator = _format_packet_path(
        effective_next_packet_output_path
    )
    input_template_path_for_allowed = _format_packet_path(effective_input_template_path)
    template_output_path_for_allowed = _format_packet_path(
        effective_template_output_path
    )
    state_output_path_for_allowed = _format_packet_path(effective_state_output_path)
    report_output_path_for_allowed = _format_packet_path(effective_report_output_path)
    next_packet_output_path_for_allowed = _format_packet_path(
        effective_next_packet_output_path
    )

    allowed_paths: list[str] = [
        input_template_path_for_allowed,
        template_output_path_for_allowed,
        state_output_path_for_allowed,
        report_output_path_for_allowed,
        next_packet_output_path_for_allowed,
        "automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py",
        "scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py",
        "tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py",
    ]
    seen_allowed_paths: list[str] = []
    for allowed_path in allowed_paths:
        if allowed_path not in seen_allowed_paths:
            seen_allowed_paths.append(allowed_path)
    allowed_paths_text = "\n".join(seen_allowed_paths)
    validator_chain = "\n".join(
        [
            "python -m py_compile automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py",
            "python -m pytest tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py -q",
            "python scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py --write-template --write-state --write-report "
            f"--input-template-path {input_template_path_for_allowed} "
            f"--template-output-path {template_path_for_validator} "
            f"--state-output-path {state_path_for_validator} "
            f"--report-output-path {report_path_for_validator} "
            f"--next-packet-output-path {next_packet_path_for_validator}",
            f"python -m json.tool {template_path_for_validator}",
            f"python -m json.tool {state_path_for_validator}",
            f"python automation/validators/aios_governance_validator.py --input {next_packet_path_for_validator}",
            "git diff --check -- automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py "
            "scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py "
            "tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py "
            f"{template_path_for_validator} {state_path_for_validator} {report_path_for_validator} {next_packet_path_for_validator}",
            "git status --short --branch",
        ]
    )
    result_status = result["status"]
    completion_percent = result["owner_evidence_completion_percent"]
    next_safe_action = str(result["next_safe_action"])

    return f"""CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

CONTRACT TITLE
AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1

IDENTITY MARKER
AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1

SUPERVISOR IDENTITY
ChatGPT planning supervisor

WORKER IDENTITY
Codex

MODE
APPLY

ZONE
Trading Lab / Forex

LANE
Forex Owner Safety Evidence Intake Verification Prep

WORKTREE
C:\\Dev\\Ai.Os

BRANCH
{branch}

MISSION / PROGRAM / EPIC / BUCKET / PACKET IDENTITY
Mission ID: MISSION-AIOS-FOREX-FINISH-LINE-V1
Mission Name: Governed Forex Finish Line
Program ID: PROGRAM-FOREX-PROFIT-AUTONOMY-V1
Program Name: Forex Profit Autonomy System
Epic ID: EPC-FOREX-OWNER-SAFETY-EVIDENCE-INTAKE-001
Epic Name: Owner Safety Evidence Intake And Verification Prep
Bucket ID: BKT-FOREX-OWNER-SAFETY-EVIDENCE-INTAKE-001
Bucket Name: Owner Safety Evidence Intake Template And Classifier
Packet ID: PKT-FOREX-OWNER-SAFETY-EVIDENCE-INTAKE-VERIFICATION-PREP-V1
Packet Name: Build Owner Safety Evidence Intake Verification Prep V1

APPROVAL AUTHORITY
Human Owner approval is required before APPLY execution, commit, push, PR creation, broker/API use, credential use, live trading authorization, scheduler activation, daemon activation, webhook activation, dashboard mutation, or order execution.
A later Human Owner message that explicitly approves commit is required before commit.
A later Human Owner message that explicitly approves push is required before push.

PREFLIGHT
cd C:\\Dev\\Ai.Os
git status --short --branch
git branch --show-current
git log -1 --oneline

ALLOWED PATHS
{allowed_paths_text}

FORBIDDEN PATHS
AGENTS.md
README.md
WHITEPAPER.md
RISK_POLICY.md
.env
secrets
credential files
broker account identifiers
broker modules outside allowed files
scheduler files
daemon files
webhook files
dashboard mutation files
unrelated docs
unrelated tests
any path outside C:\\Dev\\Ai.Os

RULES
Do not read .env.
Do not use credentials.
Do not use broker API.
Do not authorize live trading.
Do not place trades.
Do not start schedulers, daemons, loops, webhooks, or background workers.
Do not create PR.
Do not commit.
Do not push.

MISSION
Prepare next owner-facing packet handoff after local, sanitized evidence intake classification.
Do not claim verified evidence unless explicit verification exists.
Do not infer evidence from report text.

VALIDATOR CHAIN
{validator_chain}

SAFE NEXT ACTION
{next_safe_action} Then route to later verification packet only when explicit verification mechanism is available.

STOP POINT
Stop after validators and final report.
Do not commit.
Do not push.
Do not create PR.

FINAL REPORT FORMAT
CURRENT_BRANCH:{branch}
CURRENT_HEAD:{head}
MISSING_CONTROLS:{missing_controls}
PRESENT_UNVERIFIED_CONTROLS:{", ".join(result["present_unverified_controls"])}
STALE_CONTROLS:{", ".join(result["stale_controls"])}
INVALID_CONTROLS:{", ".join(result["invalid_controls"])}
OWNER_EVIDENCE_COMPLETION_PERCENT:{completion_percent}
NEXT_RESULT_STATUS:{result_status}
VERIFICATION_CLAIMED:{result["verification_claimed"]}
BROKER_API_USED:{result["broker_api_used"]}
CREDENTIALS_USED:{result["credentials_used"]}
ORDER_EXECUTION:{result["order_execution"]}
LIVE_TRADING_AUTHORIZED:{result["live_trading_authorized"]}
"""


def _build_report_text(
    result: dict[str, object],
    template_output_status: str = "NOT_REQUESTED",
    *,
    input_template_path: Path | None = None,
    template_output_path: Path | None = None,
    state_output_path: Path | None = None,
    report_output_path: Path | None = None,
    next_packet_output_path: Path | None = None,
) -> str:
    effective_input_template_path = input_template_path or DEFAULT_INPUT_TEMPLATE_PATH
    effective_template_output_path = template_output_path or DEFAULT_INPUT_TEMPLATE_PATH
    effective_state_output_path = state_output_path or DEFAULT_STATE_OUTPUT_PATH
    effective_report_output_path = report_output_path or DEFAULT_REPORT_OUTPUT_PATH
    effective_next_packet_output_path = (
        next_packet_output_path or DEFAULT_NEXT_PACKET_OUTPUT_PATH
    )

    input_template_path_for_validator = _format_packet_path(
        effective_input_template_path
    )
    template_path_for_validator = _format_packet_path(effective_template_output_path)
    state_path_for_validator = _format_packet_path(effective_state_output_path)
    report_path_for_validator = _format_packet_path(effective_report_output_path)
    next_packet_path_for_validator = _format_packet_path(effective_next_packet_output_path)
    missing_controls = " ".join(result["missing_controls"]) or "none"
    present_unverified_controls = " ".join(result["present_unverified_controls"]) or "none"
    stale_controls = " ".join(result["stale_controls"]) or "none"
    invalid_controls = " ".join(result["invalid_controls"]) or "none"

    return f"""# AIOS Forex Owner Safety Evidence Intake Verification Prep V1 Report

Status: {result["status"]}
Current branch: {_read_git_command(["git", "branch", "--show-current"])}
Current head: {_read_git_command(["git", "rev-parse", "--short", "HEAD"])}

Controller status: OWNER_SAFETY_EVIDENCE_INTAKE_CLASSIFICATION_PENDING
Controller phase: OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP
Packet id: {result["packet_id"]}
Owner evidence completion percent: {result["owner_evidence_completion_percent"]}%

Owner evidence required:
- kill_switch_state
- daily_stop_state
- max_loss_state
- monitoring_ready

Missing controls:
- {missing_controls}

Present-unverified controls:
- {present_unverified_controls}

Stale controls:
- {stale_controls}

Invalid controls:
- {invalid_controls}

Next safe action: {result["next_safe_action"]}

Input error present: {result["input_error_present"]}
Input error type: {result["input_error_type"] or "None"}
Input error path: {result["input_error_path"] or "None"}

Safety boundary:
- order_execution_allowed: {result["safety_boundary"]["order_execution_allowed"]}
- broker_api_allowed: {result["safety_boundary"]["broker_api_allowed"]}
- credentials_allowed: {result["safety_boundary"]["credentials_allowed"]}
- account_identifier_persistence_allowed: {result["safety_boundary"]["account_identifier_persistence_allowed"]}
- scheduler_allowed: {result["safety_boundary"]["scheduler_allowed"]}
- daemon_allowed: {result["safety_boundary"]["daemon_allowed"]}
- webhook_allowed: {result["safety_boundary"]["webhook_allowed"]}
- live_trading_authorized: {result["safety_boundary"]["live_trading_authorized"]}

Validation:
- No broker API was called.
- No credentials were used.
- No account identifiers were persisted.
- No orders were executed.
- No scheduler, daemon, loop, webhook, live routing, commit, push, or PR action was started.

Owner evidence completion percent: {result["owner_evidence_completion_percent"]}%
verification_claimed: {result["verification_claimed"]}
required verification mechanism available: {result["verification_mechanism_available"]}
Template output status: {template_output_status}

Validators:
python -m py_compile automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py
python -m pytest tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py -q
python scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py --write-template --write-state --write-report --input-template-path {input_template_path_for_validator} --template-output-path {template_path_for_validator} --state-output-path {state_path_for_validator} --report-output-path {report_path_for_validator} --next-packet-output-path {next_packet_path_for_validator}
python -m json.tool {template_path_for_validator}
python -m json.tool {state_path_for_validator}
python automation/validators/aios_governance_validator.py --input {next_packet_path_for_validator}
git diff --check -- automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py {template_path_for_validator} {state_path_for_validator} {report_path_for_validator} {next_packet_path_for_validator}
git status --short --branch

"""


def _load_json_if_exists(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as source:
            payload = json.load(source)
    except json.JSONDecodeError as exc:
        raise ValueError(INPUT_INVALID_ERROR_TYPE) from exc
    if not isinstance(payload, dict):
        raise ValueError(INPUT_NON_OBJECT_ERROR_TYPE)
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as target:
        json.dump(payload, target, indent=2, ensure_ascii=True)


def _write_report(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as target:
        target.write(text)


def run_collection_pipeline(
    *,
    input_template_path: Path | None = None,
    template_output_path: Path | None = None,
    state_output_path: Path | None = None,
    report_output_path: Path | None = None,
    next_packet_output_path: Path | None = None,
) -> dict[str, object]:
    effective_input_template_path = input_template_path or DEFAULT_INPUT_TEMPLATE_PATH
    effective_template_output_path = template_output_path or DEFAULT_INPUT_TEMPLATE_PATH
    effective_state_output_path = state_output_path or DEFAULT_STATE_OUTPUT_PATH
    effective_report_output_path = report_output_path or DEFAULT_REPORT_OUTPUT_PATH
    effective_next_packet_output_path = next_packet_output_path or DEFAULT_NEXT_PACKET_OUTPUT_PATH

    input_error_present = False
    input_error_type: str | None = None
    now_utc = _now_utc()
    try:
        owner_input = _load_json_if_exists(effective_input_template_path)
        owner_input = owner_input or build_input_template()
        result = run_forex_owner_safety_evidence_intake_verification_prep_v1(owner_input)
    except ValueError as exc:
        input_error_present = True
        input_error_type = str(exc)
        owner_input = build_input_template()
        result = _build_input_invalid_result(
            input_error_type=input_error_type,
            input_error_path=effective_input_template_path,
            current_timestamp=now_utc,
        )
    next_packet = generate_next_packet_text(
        result,
        current_branch=_read_git_command(["git", "branch", "--show-current"]),
        current_head=_read_git_command(["git", "rev-parse", "--short", "HEAD"]),
        input_template_path=effective_input_template_path,
        template_output_path=effective_template_output_path,
        state_output_path=effective_state_output_path,
        report_output_path=effective_report_output_path,
        next_packet_output_path=effective_next_packet_output_path,
    )
    payload: dict[str, object] = {
        "status": result["status"],
        "result": result,
    }
    template_output_status = "NOT_REQUESTED"

    if template_output_path is not None:
        template_output_status = _write_template_if_safe(
            input_template_path=effective_input_template_path,
            template_output_path=effective_template_output_path,
            owner_input=owner_input,
            input_error_present=input_error_present,
        )
        payload["template_output_status"] = template_output_status
        payload["template_output_path"] = str(effective_template_output_path)

    if state_output_path is not None:
        _write_json(effective_state_output_path, result)
        payload["state_output_path"] = str(effective_state_output_path)

    if report_output_path is not None:
        _write_report(
            effective_report_output_path,
            _build_report_text(
                result,
                template_output_status,
                input_template_path=effective_input_template_path,
                template_output_path=effective_template_output_path,
                state_output_path=effective_state_output_path,
                report_output_path=effective_report_output_path,
                next_packet_output_path=effective_next_packet_output_path,
            ),
        )
        payload["report_output_path"] = str(effective_report_output_path)

    if next_packet_output_path is not None:
        _write_report(effective_next_packet_output_path, next_packet)
        payload["next_packet_output_path"] = str(effective_next_packet_output_path)

    input_template_path_for_validator = _format_packet_path(effective_input_template_path)
    template_path_for_validator = _format_packet_path(effective_template_output_path)
    state_path_for_validator = _format_packet_path(effective_state_output_path)
    report_path_for_validator = _format_packet_path(effective_report_output_path)
    next_packet_path_for_validator = _format_packet_path(
        effective_next_packet_output_path
    )

    payload["validator_chain"] = [
        "python -m py_compile automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py",
        "python -m pytest tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py -q",
        "python scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py --write-template --write-state --write-report "
        f"--input-template-path {input_template_path_for_validator} "
        f"--template-output-path {template_path_for_validator} "
        f"--state-output-path {state_path_for_validator} "
        f"--report-output-path {report_path_for_validator} "
        f"--next-packet-output-path {next_packet_path_for_validator}",
        f"python -m json.tool {template_path_for_validator}",
        f"python -m json.tool {state_path_for_validator}",
        f"python automation/validators/aios_governance_validator.py --input {next_packet_path_for_validator}",
        "git status --short --branch",
    ]

    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build owner safety evidence intake template and classify filled evidence blocks."
        )
    )
    parser.add_argument(
        "--input-template-path",
        default=None,
        help="Path for owner-filled intake template input",
    )
    parser.add_argument(
        "--write-template",
        action="store_true",
        help="Emit the owner evidence intake template JSON.",
    )
    parser.add_argument(
        "--template-output-path",
        default=str(DEFAULT_INPUT_TEMPLATE_PATH),
        help="Target path for template JSON output.",
    )
    parser.add_argument(
        "--write-state",
        action="store_true",
        help="Emit the output classification state.",
    )
    parser.add_argument(
        "--state-output-path",
        default=str(DEFAULT_STATE_OUTPUT_PATH),
        help="Target path for state JSON output.",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Emit the markdown status report.",
    )
    parser.add_argument(
        "--report-output-path",
        default=str(DEFAULT_REPORT_OUTPUT_PATH),
        help="Target path for status report output.",
    )
    parser.add_argument(
        "--write-next-packet",
        action="store_true",
        help="Emit the next Codex packet.",
    )
    parser.add_argument(
        "--next-packet-output-path",
        default=str(DEFAULT_NEXT_PACKET_OUTPUT_PATH),
        help="Target path for handoff Codex packet output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_template_path)
    template_output = Path(args.template_output_path)
    state_output = Path(args.state_output_path)
    report_output = Path(args.report_output_path)
    next_packet_output = Path(args.next_packet_output_path)

    output = run_collection_pipeline(
        input_template_path=input_path,
        template_output_path=template_output if args.write_template else None,
        state_output_path=state_output if args.write_state else None,
        report_output_path=report_output if args.write_report else None,
        next_packet_output_path=(
            next_packet_output if args.write_next_packet or args.write_report else None
        ),
    )

    print(json.dumps(output, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
