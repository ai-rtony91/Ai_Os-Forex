from __future__ import annotations

from datetime import datetime, timezone

from automation.forex_engine import forex_a_lane_owner_control_intake_validator_v1 as validator


def _filled_payload() -> dict:
    timestamp = "2026-10-09T20:00:00Z"
    return {
        "packet_schema": validator.PACKET_SCHEMA,
        "required_sections": {
            "execution_policy_resolution": {
                "fields": {
                    "approved_execution_policy_route": "Owner approved CurrentUser AllSigned with trusted signed scripts",
                    "policy_scope": "CurrentUser",
                    "reviewed_claim_script_sha256": "33a8eb24a4113abb3126a5b0e65ff595dc2f8c16d6857afd185c6a915007f087",
                    "reviewed_release_script_sha256": "9b829a7c292a991f39891594efe5d2d0fd151e9a0a444bc9a85ff07ae2d395b6",
                    "trusted_signer_name": "Owner Trusted Code Signing Certificate",
                    "post_sign_claim_script_sha256": "a" * 64,
                    "post_sign_release_script_sha256": "b" * 64,
                    "owner_attestation": "Owner confirms reviewed signed scripts only.",
                    "evidence_timestamp_utc": timestamp,
                }
            },
            "daily_loss_authority": {
                "fields": {
                    "daily_loss_cap_value": "25",
                    "daily_loss_cap_unit": "USD",
                    "trading_day_timezone": "America/New_York",
                    "rollover_cutoff_time": "17:00",
                    "owner_attestation": "Owner confirms cap.",
                    "evidence_timestamp_utc": timestamp,
                }
            },
            "kill_switch_authority": {
                "fields": {
                    "manual_operator_stop_path": "local app stop button",
                    "credential_revoke_path": "broker portal revoke access page, sanitized",
                    "notification_path": "local desktop alert",
                    "owner_attestation": "Owner confirms kill path.",
                    "evidence_timestamp_utc": timestamp,
                }
            },
            "broker_permission_boundary": {
                "fields": {
                    "broker_name_sanitized": "OANDA",
                    "broker_environment": "practice",
                    "asset_class": "forex",
                    "account_type_sanitized": "practice margin",
                    "account_currency": "USD",
                    "margin_available_confirmed": "yes",
                    "effective_leverage_limit": "2",
                    "long_permission": "yes",
                    "short_permission": "no",
                    "fifo_required": "yes",
                    "hedging_available": "no",
                    "instrument_tradable": "EUR_USD",
                    "max_units": "1000",
                    "stop_loss_supported": "yes",
                    "take_profit_supported": "yes",
                    "order_type_supported": "market",
                    "one_order_only_supported": "yes",
                    "demo_sandbox_order_preview_supported": "yes",
                    "proof_source_sanitized": "owner sanitized broker settings review",
                    "evidence_timestamp_utc": timestamp,
                }
            },
            "owner_safety_controls_refresh": {
                "fields": {
                    "kill_switch_state_artifact": "Reports/forex_delivery/owner_safety_evidence/KILL_SWITCH_STATE_SANITIZED_V2.md",
                    "daily_stop_state_artifact": "Reports/forex_delivery/owner_safety_evidence/DAILY_STOP_STATE_SANITIZED_V2.md",
                    "max_loss_state_artifact": "Reports/forex_delivery/owner_safety_evidence/MAX_LOSS_STATE_SANITIZED_V2.md",
                    "monitoring_ready_artifact": "Reports/forex_delivery/owner_safety_evidence/MONITORING_READY_SANITIZED_V2.md",
                    "owner_attestation": "Owner confirms fresh sanitized artifacts.",
                    "evidence_timestamp_utc": timestamp,
                }
            },
        },
    }


def test_blank_template_is_review_required() -> None:
    result = validator.validate_owner_control_intake({"packet_schema": validator.PACKET_SCHEMA})

    assert result["status"] == validator.REVIEW_REQUIRED
    assert result["ready"] is False
    assert "required_sections_missing" in result["blockers"]
    assert result["broker_api_used"] is False
    assert result["credentials_used"] is False
    assert result["order_execution"] is False


def test_complete_sanitized_payload_validates() -> None:
    result = validator.validate_owner_control_intake(
        _filled_payload(),
        now_utc=datetime(2026, 10, 9, 20, 30, tzinfo=timezone.utc),
    )

    assert result["status"] == validator.VALIDATED
    assert result["ready"] is True
    assert result["blockers"] == []
    assert all(section["status"] == "VALID" for section in result["section_results"].values())


def test_secret_marker_blocks_payload() -> None:
    payload = _filled_payload()
    payload["required_sections"]["broker_permission_boundary"]["fields"]["proof_source_sanitized"] = "account_id 123"

    result = validator.validate_owner_control_intake(
        payload,
        now_utc=datetime(2026, 10, 9, 20, 30, tzinfo=timezone.utc),
    )

    assert result["status"] == validator.REVIEW_REQUIRED
    assert "broker_permission_boundary:secret_marker:proof_source_sanitized" in result["blockers"]


def test_stale_timestamp_blocks_payload() -> None:
    payload = _filled_payload()
    result = validator.validate_owner_control_intake(
        payload,
        now_utc=datetime(2026, 10, 11, 20, 30, tzinfo=timezone.utc),
    )

    assert result["status"] == validator.REVIEW_REQUIRED
    assert any(blocker.endswith("stale:evidence_timestamp_utc") for blocker in result["blockers"])

