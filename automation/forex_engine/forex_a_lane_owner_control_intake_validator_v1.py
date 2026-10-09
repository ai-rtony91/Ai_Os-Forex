"""Validate sanitized A-lane owner control intake facts.

This validator is local and structural. It does not read credentials, call brokers,
change Windows policy, sign scripts, execute lock scripts, or authorize trading.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

PACKET_SCHEMA = "AIOS_FOREX_A_LANE_OWNER_CONTROL_INTAKE_PACKET_V1"
VALIDATED = "AIOS_FOREX_A_LANE_OWNER_CONTROL_INTAKE_VALIDATED"
REVIEW_REQUIRED = "AIOS_FOREX_A_LANE_OWNER_CONTROL_INTAKE_REVIEW_REQUIRED"

REQUIRED_SECTIONS = (
    "execution_policy_resolution",
    "daily_loss_authority",
    "kill_switch_authority",
    "broker_permission_boundary",
    "owner_safety_controls_refresh",
)

REQUIRED_FIELDS = {
    "execution_policy_resolution": (
        "approved_execution_policy_route",
        "policy_scope",
        "reviewed_claim_script_sha256",
        "reviewed_release_script_sha256",
        "trusted_signer_name",
        "post_sign_claim_script_sha256",
        "post_sign_release_script_sha256",
        "owner_attestation",
        "evidence_timestamp_utc",
    ),
    "daily_loss_authority": (
        "daily_loss_cap_value",
        "daily_loss_cap_unit",
        "trading_day_timezone",
        "rollover_cutoff_time",
        "owner_attestation",
        "evidence_timestamp_utc",
    ),
    "kill_switch_authority": (
        "manual_operator_stop_path",
        "credential_revoke_path",
        "notification_path",
        "owner_attestation",
        "evidence_timestamp_utc",
    ),
    "broker_permission_boundary": (
        "broker_name_sanitized",
        "broker_environment",
        "asset_class",
        "account_type_sanitized",
        "account_currency",
        "margin_available_confirmed",
        "effective_leverage_limit",
        "long_permission",
        "short_permission",
        "fifo_required",
        "hedging_available",
        "instrument_tradable",
        "max_units",
        "stop_loss_supported",
        "take_profit_supported",
        "order_type_supported",
        "one_order_only_supported",
        "demo_sandbox_order_preview_supported",
        "proof_source_sanitized",
        "evidence_timestamp_utc",
    ),
    "owner_safety_controls_refresh": (
        "kill_switch_state_artifact",
        "daily_stop_state_artifact",
        "max_loss_state_artifact",
        "monitoring_ready_artifact",
        "owner_attestation",
        "evidence_timestamp_utc",
    ),
}

SECRET_MARKERS = (
    "token",
    "password",
    "secret",
    "account_id",
    "account number",
    "authorization",
    "bearer ",
    "sk-",
)


def validate_owner_control_intake(
    payload: Mapping[str, Any] | None,
    *,
    now_utc: datetime | None = None,
    freshness_hours: int = 24,
) -> dict[str, Any]:
    now = now_utc or datetime.now(timezone.utc)
    data = dict(payload or {})
    blockers: list[str] = []
    section_results: dict[str, Any] = {}

    if data.get("packet_schema") != PACKET_SCHEMA:
        blockers.append("packet_schema_invalid")

    sections = data.get("required_sections")
    if not isinstance(sections, Mapping):
        sections = {}
        blockers.append("required_sections_missing")

    for section in REQUIRED_SECTIONS:
        section_payload = sections.get(section) if isinstance(sections, Mapping) else None
        fields = section_payload.get("fields") if isinstance(section_payload, Mapping) else None
        section_blockers: list[str] = []
        if not isinstance(fields, Mapping):
            section_blockers.append("fields_missing")
            fields = {}
        for field in REQUIRED_FIELDS[section]:
            value = fields.get(field)
            if _blank(value):
                section_blockers.append(f"missing:{field}")
            elif _contains_secret_marker(value):
                section_blockers.append(f"secret_marker:{field}")
        timestamp = fields.get("evidence_timestamp_utc")
        parsed = _parse_utc(str(timestamp)) if not _blank(timestamp) else None
        if parsed is None:
            section_blockers.append("invalid:evidence_timestamp_utc")
        elif parsed > now:
            section_blockers.append("future:evidence_timestamp_utc")
        elif now - parsed > timedelta(hours=freshness_hours):
            section_blockers.append("stale:evidence_timestamp_utc")
        section_results[section] = {
            "status": "VALID" if not section_blockers else "REVIEW_REQUIRED",
            "blockers": section_blockers,
        }
        blockers.extend(f"{section}:{item}" for item in section_blockers)

    status = VALIDATED if not blockers else REVIEW_REQUIRED
    return {
        "validator_schema": "AIOS_FOREX_A_LANE_OWNER_CONTROL_INTAKE_VALIDATOR_V1",
        "status": status,
        "ready": status == VALIDATED,
        "blockers": blockers,
        "section_results": section_results,
        "broker_api_used": False,
        "credentials_used": False,
        "order_execution": False,
        "execution_policy_changed": False,
        "script_signing_performed": False,
        "claim_script_executed": False,
    }


def validate_owner_control_intake_path(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_owner_control_intake(payload)


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "unknown", "todo", "tbd", "pending", "n/a", "na", "none", "null"}
    if isinstance(value, list | tuple | set | dict):
        return len(value) == 0
    return False


def _contains_secret_marker(value: Any) -> bool:
    text = json.dumps(value, sort_keys=True, default=str).lower() if isinstance(value, Mapping | list | tuple) else str(value).lower()
    return any(marker in text for marker in SECRET_MARKERS)


def _parse_utc(value: str) -> datetime | None:
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
