from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from automation.forex_engine import (
    forex_owner_safety_evidence_intake_verification_prep_v1 as intake,
)
from automation.validators import aios_governance_validator

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts" / "forex_delivery" / "run_forex_owner_safety_evidence_intake_verification_prep_v1.py"


def _template() -> dict[str, object]:
    return intake.build_input_template()


def _owner_input_from_controls(control_inputs: dict[str, object]) -> dict[str, object]:
    template = intake.build_input_template()
    controls = template["controls"]
    assert isinstance(controls, dict)
    controls["kill_switch_state"] = dict(controls["kill_switch_state"])
    controls["daily_stop_state"] = dict(controls["daily_stop_state"])
    controls["max_loss_state"] = dict(controls["max_loss_state"])
    controls["monitoring_ready"] = dict(controls["monitoring_ready"])
    if "controls" in control_inputs:
        assert isinstance(control_inputs["controls"], dict)
        controls = control_inputs["controls"]
    return {"controls": controls}


def _base_complete_control_payload() -> dict[str, object]:
    return {
        "evidence_present": True,
        "evidence_type": "sanitized safety-control status export",
        "sanitized_artifact_path": "artifacts/kill-switch-status.json",
        "owner_attestation": "Owner confirms control is currently configured.",
        "evidence_timestamp_utc": (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"
            )
        ),
        "freshness_window_hours": 24,
        "contains_secret_or_account_identifier": False,
        "notes": "Owner provided sanitized evidence.",
    }


def _complete_owner_input_payload() -> dict[str, object]:
    return _owner_input_from_controls(
        {
            "controls": {
                key: _base_complete_control_payload()
                for key in intake.CONTROL_FIELDS
            }
        }
    )


def _run_payload(payload: dict[str, object]) -> dict[str, object]:
    return intake.run_forex_owner_safety_evidence_intake_verification_prep_v1(payload)


def _allowed_paths_block(text: str) -> list[str]:
    marker = "\nALLOWED PATHS\n"
    start = text.index(marker) + len(marker)
    end = text.index("\nFORBIDDEN PATHS\n", start)
    return [line for line in text[start:end].splitlines() if line.strip()]


def test_template_contains_required_controls_with_default_missing_metadata():
    payload = _template()

    controls = payload["controls"]
    assert isinstance(controls, dict)
    assert set(controls.keys()) == set(intake.CONTROL_FIELDS)
    for control in intake.CONTROL_FIELDS:
        section = controls[control]
        assert section["evidence_present"] is False
        assert section["evidence_type"] == ""
        assert section["sanitized_artifact_path"] == ""
        assert section["owner_attestation"] == ""
        assert section["evidence_timestamp_utc"] == ""
        assert section["freshness_window_hours"] == 24
        assert section["contains_secret_or_account_identifier"] is False
        assert section["notes"] == ""


def test_default_run_reports_all_missing_and_zero_completion():
    result = _run_payload({})

    assert result["status"] == "OWNER_SAFETY_EVIDENCE_INTAKE_REQUIRED"
    assert result["owner_evidence_completion_percent"] == 0.0
    assert result["missing_controls"] == list(intake.CONTROL_FIELDS)
    assert result["present_unverified_controls"] == []
    assert result["stale_controls"] == []
    assert result["invalid_controls"] == []
    assert result["verification_claimed"] is False
    assert result["broker_api_used"] is False
    assert result["credentials_used"] is False
    assert result["order_execution"] is False
    assert result["live_trading_authorized"] is False


def test_missing_metadata_is_invalid_when_evidence_present_without_artifact_path():
    control_payload = _base_complete_control_payload()
    control_payload["sanitized_artifact_path"] = ""
    payload = _owner_input_from_controls(
        {
            "controls": {
                "kill_switch_state": control_payload,
                "daily_stop_state": _base_complete_control_payload(),
                "max_loss_state": _base_complete_control_payload(),
                "monitoring_ready": _base_complete_control_payload(),
            }
        }
    )
    result = _run_payload(payload)

    assert "INVALID" in result["control_evaluations"]["kill_switch_state"]["status"]


def test_missing_metadata_is_invalid_when_evidence_present_without_evidence_type():
    control_payload = _base_complete_control_payload()
    control_payload["evidence_type"] = ""
    payload = _owner_input_from_controls(
        {
            "controls": {
                "kill_switch_state": control_payload,
                "daily_stop_state": _base_complete_control_payload(),
                "max_loss_state": _base_complete_control_payload(),
                "monitoring_ready": _base_complete_control_payload(),
            }
        }
    )
    result = _run_payload(payload)
    assert result["control_evaluations"]["kill_switch_state"]["status"] == "INVALID"


def test_missing_metadata_is_invalid_when_evidence_present_without_timestamp():
    control_payload = _base_complete_control_payload()
    control_payload["evidence_timestamp_utc"] = ""
    payload = _owner_input_from_controls(
        {
            "controls": {
                "kill_switch_state": control_payload,
                "daily_stop_state": _base_complete_control_payload(),
                "max_loss_state": _base_complete_control_payload(),
                "monitoring_ready": _base_complete_control_payload(),
            }
        }
    )
    result = _run_payload(payload)
    assert result["control_evaluations"]["kill_switch_state"]["status"] == "INVALID"


def test_secret_flag_marks_invalid():
    control_payload = _base_complete_control_payload()
    control_payload["contains_secret_or_account_identifier"] = True
    payload = _owner_input_from_controls(
        {
            "controls": {
                "kill_switch_state": control_payload,
                "daily_stop_state": _base_complete_control_payload(),
                "max_loss_state": _base_complete_control_payload(),
                "monitoring_ready": _base_complete_control_payload(),
            }
        }
    )
    result = _run_payload(payload)
    assert result["control_evaluations"]["kill_switch_state"]["status"] == "INVALID"


def test_stale_evidence_marked_stale():
    control_payload = _base_complete_control_payload()
    stale_time = (
        datetime.now(timezone.utc) - timedelta(hours=48)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    control_payload["evidence_timestamp_utc"] = stale_time
    payload = _owner_input_from_controls(
        {
            "controls": {
                "kill_switch_state": control_payload,
                "daily_stop_state": _base_complete_control_payload(),
                "max_loss_state": _base_complete_control_payload(),
                "monitoring_ready": _base_complete_control_payload(),
            }
        }
    )
    result = _run_payload(payload)
    assert result["control_evaluations"]["kill_switch_state"]["status"] == "STALE"


def test_future_evidence_timestamp_marked_invalid_and_not_present_unverified():
    control_payload = _base_complete_control_payload()
    control_payload["evidence_timestamp_utc"] = (
        datetime.now(timezone.utc) + timedelta(hours=1)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = _owner_input_from_controls(
        {
            "controls": {
                "kill_switch_state": control_payload,
                "daily_stop_state": _base_complete_control_payload(),
                "max_loss_state": _base_complete_control_payload(),
                "monitoring_ready": _base_complete_control_payload(),
            }
        }
    )
    result = _run_payload(payload)

    assert result["control_evaluations"]["kill_switch_state"]["status"] == "INVALID"
    assert (
        "future"
        in str(result["control_evaluations"]["kill_switch_state"]["reason"]).lower()
    )
    assert result["owner_evidence_completion_percent"] == 75.0
    assert (
        "kill_switch_state"
        not in result["present_unverified_controls"]
    )


def test_complete_metadata_results_present_unverified_not_verified():
    payload = _owner_input_from_controls(
        {
            "controls": {
                key: _base_complete_control_payload()
                for key in intake.CONTROL_FIELDS
            }
        }
    )
    result = _run_payload(payload)

    statuses = {
        entry["status"] for entry in result["control_evaluations"].values()
    }
    assert statuses == {"PRESENT_UNVERIFIED"}
    assert result["owner_evidence_completion_percent"] == 100.0


def test_run_collection_preserves_owner_input_when_input_and_template_output_are_same_path(tmp_path: Path) -> None:
    input_template = tmp_path / "custom_input_template.json"
    owner_input = _complete_owner_input_payload()
    intake._write_json(input_template, owner_input)

    payload = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=input_template,
    )

    assert payload["template_output_status"] == "PRESERVED"
    preserved = json.loads(input_template.read_text(encoding="utf-8"))
    assert preserved == owner_input
    assert (
        payload["result"]["control_evaluations"]["kill_switch_state"]["status"]
        == "PRESENT_UNVERIFIED"
    )


def test_run_collection_malformed_owner_input_does_not_crash_and_returns_input_invalid(
    tmp_path: Path,
) -> None:
    input_template = tmp_path / "malformed_template.json"
    malformed_json = '{"status": "incomplete"'
    input_template.write_text(malformed_json, encoding="utf-8")

    payload = intake.run_collection_pipeline(input_template_path=input_template)
    result = payload["result"]

    assert payload["status"] == intake.INPUT_INVALID_STATUS
    assert result["status"] == intake.INPUT_INVALID_STATUS
    assert result["input_error_present"] is True
    assert result["input_error_type"] in {"JSONDecodeError", "JSON_DECODE_ERROR"}
    assert result["input_error_path"] == str(input_template)
    assert result["owner_evidence_completion_percent"] == 0.0
    assert result["verification_claimed"] is False
    assert result["broker_api_used"] is False
    assert result["credentials_used"] is False
    assert result["order_execution"] is False
    assert result["live_trading_authorized"] is False
    assert "repair or replace the malformed sanitized intake json" in result[
        "next_safe_action"
    ].lower()


def test_run_collection_non_object_owner_input_does_not_crash_and_returns_input_invalid(
    tmp_path: Path,
) -> None:
    input_template = tmp_path / "non_object_template.json"
    input_template.write_text("[1, 2, 3]", encoding="utf-8")

    payload = intake.run_collection_pipeline(input_template_path=input_template)
    result = payload["result"]

    assert payload["status"] == intake.INPUT_INVALID_STATUS
    assert result["status"] == intake.INPUT_INVALID_STATUS
    assert result["input_error_present"] is True
    assert result["input_error_type"] in {"JSON_SCHEMA_ERROR", "NON_OBJECT_JSON"}
    assert result["input_error_path"] == str(input_template)
    assert result["owner_evidence_completion_percent"] == 0.0
    assert result["verification_claimed"] is False
    assert result["broker_api_used"] is False
    assert result["credentials_used"] is False
    assert result["order_execution"] is False
    assert result["live_trading_authorized"] is False
    assert "repair or replace the malformed sanitized intake json" in result[
        "next_safe_action"
    ].lower()
    assert result["status"] != "OWNER_SAFETY_EVIDENCE_INTAKE_REQUIRED"


def test_run_collection_non_object_input_is_not_overwritten_when_input_and_output_match(
    tmp_path: Path,
) -> None:
    input_template = tmp_path / "non_object_template.json"
    input_template_content = "[1, 2, 3]"
    input_template.write_text(input_template_content, encoding="utf-8")

    payload = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=input_template,
    )

    assert payload["template_output_status"] == "PRESERVED"
    assert input_template.read_text(encoding="utf-8") == input_template_content
    assert payload["result"]["status"] == intake.INPUT_INVALID_STATUS


def test_run_collection_malformed_input_is_preserved_when_input_and_output_match(tmp_path: Path) -> None:
    input_template = tmp_path / "malformed_template.json"
    malformed_json = '{"status": "incomplete"'
    input_template.write_text(malformed_json, encoding="utf-8")

    payload = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=input_template,
    )

    assert payload["template_output_status"] == "PRESERVED"
    assert input_template.read_text(encoding="utf-8") == malformed_json
    assert payload["result"]["status"] == intake.INPUT_INVALID_STATUS


def test_run_collection_malformed_input_still_writes_state_report_and_next_packet(
    tmp_path: Path,
) -> None:
    input_template = tmp_path / "malformed_template.json"
    malformed_json = '{"status": "incomplete"'
    input_template.write_text(malformed_json, encoding="utf-8")
    state_output = tmp_path / "state.json"
    report_output = tmp_path / "state_report.md"
    next_packet_output = tmp_path / "next_packet.md"
    template_output = tmp_path / "template_output.json"

    payload = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=template_output,
        state_output_path=state_output,
        report_output_path=report_output,
        next_packet_output_path=next_packet_output,
    )

    assert payload["result"]["status"] == intake.INPUT_INVALID_STATUS
    assert payload["template_output_status"] == "WRITTEN"
    assert payload["state_output_path"] == str(state_output)
    assert payload["report_output_path"] == str(report_output)
    assert payload["next_packet_output_path"] == str(next_packet_output)

    assert state_output.exists()
    state_payload = json.loads(state_output.read_text(encoding="utf-8"))
    assert state_payload["status"] == intake.INPUT_INVALID_STATUS
    assert state_payload["input_error_present"] is True
    assert report_output.exists()
    report_text = report_output.read_text(encoding="utf-8")
    assert intake.INPUT_INVALID_STATUS in report_text
    assert (
        f"git diff --check -- automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py {template_output.as_posix()} {state_output.as_posix()} {report_output.as_posix()} {next_packet_output.as_posix()}"
        in report_text
    )
    next_packet_text = next_packet_output.read_text(encoding="utf-8")
    assert "repair or replace the malformed sanitized intake json" in next_packet_text.lower()
    assert input_template.read_text(encoding="utf-8") == malformed_json


def test_run_collection_non_object_input_still_writes_state_report_and_next_packet(
    tmp_path: Path,
) -> None:
    input_template = tmp_path / "non_object_template.json"
    input_template.write_text("[1, 2, 3]", encoding="utf-8")
    state_output = tmp_path / "state.json"
    report_output = tmp_path / "state_report.md"
    next_packet_output = tmp_path / "next_packet.md"
    template_output = tmp_path / "template_output.json"

    payload = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=template_output,
        state_output_path=state_output,
        report_output_path=report_output,
        next_packet_output_path=next_packet_output,
    )

    assert payload["result"]["status"] == intake.INPUT_INVALID_STATUS
    assert payload["template_output_status"] == "WRITTEN"
    assert payload["state_output_path"] == str(state_output)
    assert payload["report_output_path"] == str(report_output)
    assert payload["next_packet_output_path"] == str(next_packet_output)

    assert state_output.exists()
    state_payload = json.loads(state_output.read_text(encoding="utf-8"))
    assert state_payload["status"] == intake.INPUT_INVALID_STATUS
    assert state_payload["input_error_present"] is True
    assert state_payload["input_error_path"] == str(input_template)
    assert report_output.exists()
    report_text = report_output.read_text(encoding="utf-8")
    assert intake.INPUT_INVALID_STATUS in report_text
    assert (
        f"git diff --check -- automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py {template_output.as_posix()} {state_output.as_posix()} {report_output.as_posix()} {next_packet_output.as_posix()}"
        in report_text
    )
    next_packet_text = next_packet_output.read_text(encoding="utf-8")
    assert "repair or replace the malformed sanitized intake json" in next_packet_text.lower()
    assert input_template.read_text(encoding="utf-8") == "[1, 2, 3]"


def test_repeated_run_preserves_owner_evidence_and_status_when_input_and_output_are_same(tmp_path: Path) -> None:
    input_template = tmp_path / "custom_input_template.json"
    owner_input = _complete_owner_input_payload()
    intake._write_json(input_template, owner_input)

    first = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=input_template,
        state_output_path=tmp_path / "state.json",
    )
    second = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=input_template,
        state_output_path=tmp_path / "state.json",
    )

    assert first["template_output_status"] == "PRESERVED"
    assert second["template_output_status"] == "PRESERVED"
    assert (
        first["result"]["control_evaluations"]["kill_switch_state"]["status"]
        == "PRESENT_UNVERIFIED"
    )
    assert (
        second["result"]["control_evaluations"]["kill_switch_state"]["status"]
        == "PRESENT_UNVERIFIED"
    )


def test_template_created_when_paths_match_but_input_template_does_not_exist(tmp_path: Path) -> None:
    input_template = tmp_path / "nonexistent_template.json"

    payload = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=input_template,
    )

    assert payload["template_output_status"] == "WRITTEN"
    blank_template = json.loads(input_template.read_text(encoding="utf-8"))
    assert blank_template == _template()


def test_template_output_file_writes_blank_when_template_output_differs_from_input(tmp_path: Path) -> None:
    input_template = tmp_path / "owner_filled_template.json"
    template_output = tmp_path / "template_output_copy.json"
    owner_input = _complete_owner_input_payload()
    intake._write_json(input_template, owner_input)

    payload = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=template_output,
    )

    assert payload["template_output_status"] == "WRITTEN"
    output_template = json.loads(template_output.read_text(encoding="utf-8"))
    assert output_template == _template()
    preserved_input = json.loads(input_template.read_text(encoding="utf-8"))
    assert preserved_input == owner_input


def test_pipeline_with_state_report_writes_preserves_owner_evidence_and_marks_present_unverified(tmp_path: Path) -> None:
    input_template = tmp_path / "owner_filled_template.json"
    state_output = tmp_path / "state.json"
    report_output = tmp_path / "state_report.md"
    next_packet_output = tmp_path / "next_packet.md"
    intake._write_json(input_template, _complete_owner_input_payload())

    payload = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=input_template,
        state_output_path=state_output,
        report_output_path=report_output,
        next_packet_output_path=next_packet_output,
    )

    assert payload["template_output_status"] == "PRESERVED"
    assert (
        payload["result"]["status"]
        == "OWNER_SAFETY_EVIDENCE_PRESENT_UNVERIFIED"
    )
    assert payload["result"]["control_evaluations"]["daily_stop_state"]["status"] == "PRESENT_UNVERIFIED"
    result_template = json.loads(input_template.read_text(encoding="utf-8"))
    assert result_template["controls"]["daily_stop_state"]["evidence_present"] is True


def test_run_collection_without_input_path_loads_existing_default_template(
    tmp_path: Path,
    monkeypatch,
) -> None:
    default_template = tmp_path / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json"
    intake._write_json(default_template, _complete_owner_input_payload())
    monkeypatch.setattr(intake, "DEFAULT_INPUT_TEMPLATE_PATH", default_template)

    payload = intake.run_collection_pipeline()

    assert (
        payload["result"]["status"]
        == "OWNER_SAFETY_EVIDENCE_PRESENT_UNVERIFIED"
    )
    assert payload["result"]["present_unverified_controls"] == list(intake.CONTROL_FIELDS)


def test_run_collection_validator_chain_threads_custom_effective_paths(tmp_path: Path) -> None:
    input_template = tmp_path / "custom_input_template.json"
    template_output = tmp_path / "custom_template_output.json"
    state_output = tmp_path / "custom_state_output.json"
    report_output = tmp_path / "custom_report.md"
    next_packet_output = tmp_path / "custom_next_packet.md"
    intake._write_json(input_template, _complete_owner_input_payload())

    payload = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=template_output,
        state_output_path=state_output,
        report_output_path=report_output,
        next_packet_output_path=next_packet_output,
    )
    validator_chain = payload["validator_chain"]
    assert isinstance(validator_chain, list)
    validator_command = validator_chain[2]
    assert (
        f"python scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py --write-template --write-state --write-report --input-template-path {input_template.as_posix()} --template-output-path {template_output.as_posix()} --state-output-path {state_output.as_posix()} --report-output-path {report_output.as_posix()} --next-packet-output-path {next_packet_output.as_posix()}"
        in validator_command
    )
    assert f"python -m json.tool {template_output.as_posix()}" in validator_chain[3]
    assert f"python -m json.tool {state_output.as_posix()}" in validator_chain[4]
    assert (
        f"python automation/validators/aios_governance_validator.py --input {next_packet_output.as_posix()}"
        in validator_chain[5]
    )


def test_run_collection_custom_paths_render_report_validator_section(tmp_path: Path) -> None:
    input_template = tmp_path / "custom_input_template.json"
    template_output = tmp_path / "custom_template_output.json"
    state_output = tmp_path / "custom_state_output.json"
    report_output = tmp_path / "custom_report.md"
    next_packet_output = tmp_path / "custom_next_packet.md"
    intake._write_json(input_template, _complete_owner_input_payload())

    payload = intake.run_collection_pipeline(
        input_template_path=input_template,
        template_output_path=template_output,
        state_output_path=state_output,
        report_output_path=report_output,
        next_packet_output_path=next_packet_output,
    )

    assert payload["report_output_path"] == str(report_output)
    report_text = report_output.read_text(encoding="utf-8")

    assert (
        f"--input-template-path {input_template.as_posix()}" in report_text
    )
    assert (
        f"--template-output-path {template_output.as_posix()}" in report_text
    )
    assert f"--state-output-path {state_output.as_posix()}" in report_text
    assert (
        f"--report-output-path {report_output.as_posix()}" in report_text
    )
    assert (
        f"--next-packet-output-path {next_packet_output.as_posix()}" in report_text
    )
    assert f"python -m json.tool {template_output.as_posix()}" in report_text
    assert f"python -m json.tool {state_output.as_posix()}" in report_text
    assert (
        f"python automation/validators/aios_governance_validator.py --input {next_packet_output.as_posix()}"
        in report_text
    )
    assert (
        f"git diff --check -- automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py {template_output.as_posix()} {state_output.as_posix()} {report_output.as_posix()} {next_packet_output.as_posix()}"
        in report_text
    )

    assert (
        f"--input-template-path Reports/forex_delivery/{intake.RELATIVE_INPUT_TEMPLATE_PATH.name}" not in report_text
    )
    assert (
        f"--template-output-path {intake.RELATIVE_INPUT_TEMPLATE_PATH.as_posix()}"
        not in report_text
    )
    assert (
        f"--state-output-path {intake.RELATIVE_STATE_OUTPUT_PATH.as_posix()}"
        not in report_text
    )
    assert (
        f"--next-packet-output-path {intake.RELATIVE_NEXT_PACKET_OUTPUT_PATH.as_posix()}"
        not in report_text
    )


def test_run_collection_default_effective_paths_in_report_validator_section() -> None:
    payload = _run_payload({})
    report_text = intake._build_report_text(payload)

    assert (
        f"--input-template-path {intake.RELATIVE_INPUT_TEMPLATE_PATH.as_posix()}"
        in report_text
    )
    assert (
        f"--template-output-path {intake.RELATIVE_INPUT_TEMPLATE_PATH.as_posix()}"
        in report_text
    )
    assert (
        f"--state-output-path {intake.RELATIVE_STATE_OUTPUT_PATH.as_posix()}"
        in report_text
    )
    assert (
        f"--report-output-path {intake.RELATIVE_REPORT_OUTPUT_PATH.as_posix()}"
        in report_text
    )
    assert (
        f"--next-packet-output-path {intake.RELATIVE_NEXT_PACKET_OUTPUT_PATH.as_posix()}"
        in report_text
    )
    assert (
        f"git diff --check -- automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py "
        f"scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py "
        f"tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py "
        f"{intake.RELATIVE_INPUT_TEMPLATE_PATH.as_posix()} "
        f"{intake.RELATIVE_STATE_OUTPUT_PATH.as_posix()} "
        f"{intake.RELATIVE_REPORT_OUTPUT_PATH.as_posix()} "
        f"{intake.RELATIVE_NEXT_PACKET_OUTPUT_PATH.as_posix()}"
        in report_text
    )
    assert (
        f"python -m json.tool {intake.RELATIVE_INPUT_TEMPLATE_PATH.as_posix()}" in report_text
    )
    assert (
        f"python -m json.tool {intake.RELATIVE_STATE_OUTPUT_PATH.as_posix()}"
        in report_text
    )
    assert (
        f"python automation/validators/aios_governance_validator.py --input {intake.RELATIVE_NEXT_PACKET_OUTPUT_PATH.as_posix()}"
        in report_text
    )


def test_next_packet_contains_required_markers_and_no_fillers():
    payload = _run_payload({})
    next_packet = intake.generate_next_packet_text(payload)

    expected_runner_command = (
        "python scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py --write-template --write-state --write-report "
        "--input-template-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json "
        "--template-output-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json "
        "--state-output-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json "
        "--report-output-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md "
        "--next-packet-output-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
    )
    expected_template_command = (
        "python -m json.tool "
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json"
    )
    expected_state_command = (
        "python -m json.tool "
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json"
    )
    expected_validator_command = (
        "python automation/validators/aios_governance_validator.py --input "
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
    )
    expected_diff_command = (
        "git diff --check -- automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py "
        "scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py "
        "tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py "
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json "
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json "
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md "
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
    )

    assert next_packet.startswith("CODEX-ONLY PROMPT")
    assert "AI_OS EXECUTION TOKEN" in next_packet
    assert "AI_OS BOOTSTRAP REQUIRED" in next_packet
    assert "\nPREFLIGHT\n" in next_packet
    assert "\nALLOWED PATHS\n" in next_packet
    assert "\nFORBIDDEN PATHS\n" in next_packet
    assert "\nVALIDATOR CHAIN\n" in next_packet
    assert "\nSAFE NEXT ACTION\n" in next_packet
    assert "\nFINAL REPORT FORMAT\n" in next_packet
    assert expected_runner_command in next_packet
    assert "Implement {feature}" not in next_packet
    assert "Write tests for @filename" not in next_packet
    assert "Summarize recent commits" not in next_packet
    assert expected_template_command in next_packet
    assert expected_state_command in next_packet
    assert expected_validator_command in next_packet
    assert expected_diff_command in next_packet
    assert (
        "C:\\Dev\\Ai.Os\\Reports\\forex_delivery\\AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json"
        not in next_packet
    )
    assert (
        "C:\\Dev\\Ai.Os\\Reports\\forex_delivery\\AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json"
        not in next_packet
    )
    assert (
        "C:\\Dev\\Ai.Os\\Reports\\forex_delivery\\AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
        not in next_packet
    )
    assert "python -m json.tool AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json" not in next_packet
    assert "python -m json.tool AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json" not in next_packet
    assert "python automation/validators/aios_governance_validator.py --input AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md" not in next_packet
    assert "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json" in next_packet
    assert "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json" in next_packet
    assert "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md" in next_packet
    assert "/skills" not in next_packet

    validation = aios_governance_validator.validate_packet_text(
        next_packet,
        str(
            RUNNER_PATH.with_name(
                "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
            )
        ),
    )
    assert validation["status"] == "PASS"


def test_next_packet_default_generated_paths_are_repo_relative():
    payload = _run_payload({})
    next_packet = intake.generate_next_packet_text(payload)

    assert (
        "python scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py --write-template --write-state --write-report"
        in next_packet
    )
    assert (
        "python -m json.tool Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json"
        in next_packet
    )
    assert (
        "python -m json.tool Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json"
        in next_packet
    )
    assert (
        "python automation/validators/aios_governance_validator.py --input Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
        in next_packet
    )
    assert (
        "git diff --check -- automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py "
        "scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py "
        "tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py "
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json "
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json "
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md "
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
        in next_packet
    )
    allowed_paths = _allowed_paths_block(next_packet)
    assert "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json" in allowed_paths
    assert "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json" in allowed_paths
    assert "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md" in allowed_paths
    assert "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md" in allowed_paths
    assert (
        "C:\\Dev\\Ai.Os\\Reports\\forex_delivery\\AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json"
        not in next_packet
    )
    assert (
        "C:\\Dev\\Ai.Os\\Reports\\forex_delivery\\AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json"
        not in next_packet
    )
    assert (
        "C:\\Dev\\Ai.Os\\Reports\\forex_delivery\\AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
        not in next_packet
    )


def test_next_packet_with_all_custom_output_paths_reflects_effective_diff_paths(
    tmp_path: Path,
) -> None:
    payload = _run_payload({})
    template_output = tmp_path / "custom_template_output.json"
    state_output = tmp_path / "custom_state_output.json"
    report_output = tmp_path / "custom_report.md"
    next_packet_output = tmp_path / "custom_next_packet.md"

    next_packet = intake.generate_next_packet_text(
        payload,
        template_output_path=template_output,
        state_output_path=state_output,
        report_output_path=report_output,
        next_packet_output_path=next_packet_output,
    )

    assert (
        f"git diff --check -- automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py {template_output.as_posix()} {state_output.as_posix()} {report_output.as_posix()} {next_packet_output.as_posix()}"
        in next_packet
    )
    assert (
        f"python -m json.tool {template_output.as_posix()}"
        in next_packet
    )
    assert (
        f"python -m json.tool {state_output.as_posix()}"
        in next_packet
    )
    assert (
        f"python automation/validators/aios_governance_validator.py --input {next_packet_output.as_posix()}"
        in next_packet
    )


def test_next_packet_with_custom_template_output_path_reflects_allowed_paths(tmp_path: Path) -> None:
    payload = _run_payload({})
    template_output = tmp_path / "custom_template_output.json"

    next_packet = intake.generate_next_packet_text(
        payload,
        template_output_path=template_output,
    )

    expected_template_command = (
        f"python scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py --write-template --write-state --write-report "
        "--input-template-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json "
        f"--template-output-path {template_output.as_posix()} "
        "--state-output-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json "
        "--report-output-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md "
        "--next-packet-output-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
    )
    assert expected_template_command in next_packet
    assert f"python -m json.tool {template_output.as_posix()}" in next_packet
    allowed_paths = _allowed_paths_block(next_packet)
    assert str(template_output.as_posix()) in allowed_paths


def test_next_packet_with_custom_state_output_path_reflects_validator_and_allowed_paths(tmp_path: Path) -> None:
    payload = _run_payload({})
    state_output = tmp_path / "custom_state_output.json"

    next_packet = intake.generate_next_packet_text(
        payload,
        state_output_path=state_output,
    )

    assert f"--state-output-path {state_output.as_posix()}" in next_packet
    assert f"python -m json.tool {state_output.as_posix()}" in next_packet
    allowed_paths = _allowed_paths_block(next_packet)
    assert str(state_output.as_posix()) in allowed_paths


def test_next_packet_with_custom_report_output_path_reflects_allowed_paths(tmp_path: Path) -> None:
    payload = _run_payload({})
    report_output = tmp_path / "custom_report.md"

    next_packet = intake.generate_next_packet_text(
        payload,
        report_output_path=report_output,
    )

    assert f"--report-output-path {report_output.as_posix()}" in next_packet
    allowed_paths = _allowed_paths_block(next_packet)
    assert str(report_output.as_posix()) in allowed_paths
    assert (
        "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md"
        not in allowed_paths
    )


def test_next_packet_with_custom_next_packet_output_path_reflects_allowed_and_validator(tmp_path: Path) -> None:
    payload = _run_payload({})
    next_packet_output = tmp_path / "custom_next_packet.md"

    next_packet = intake.generate_next_packet_text(
        payload,
        next_packet_output_path=next_packet_output,
    )

    assert (
        f"python automation/validators/aios_governance_validator.py --input {next_packet_output.as_posix()}"
        in next_packet
    )
    assert f"--next-packet-output-path {next_packet_output.as_posix()}" in next_packet
    allowed_paths = _allowed_paths_block(next_packet)
    assert str(next_packet_output.as_posix()) in allowed_paths


def test_next_packet_with_custom_input_template_path_not_silently_defaulted(tmp_path: Path) -> None:
    payload = _run_payload({})
    custom_input_template = tmp_path / "custom_input_template.json"
    intake._write_json(custom_input_template, intake.build_input_template())
    next_packet = intake.generate_next_packet_text(
        payload,
        input_template_path=custom_input_template,
    )

    assert (
        f"--input-template-path {custom_input_template.as_posix()}" in next_packet
    )
    allowed_paths = _allowed_paths_block(next_packet)
    assert str(custom_input_template.as_posix()) in allowed_paths
    validation = aios_governance_validator.validate_packet_text(
        next_packet,
        str(
            RUNNER_PATH.with_name(
                "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"
            )
        ),
    )
    assert validation["status"] == "PASS"


def test_cli_writes_template_state_report_and_next_packet(tmp_path: Path) -> None:
    template_output = tmp_path / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json"
    state_output = tmp_path / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json"
    report_output = tmp_path / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md"
    next_packet_output = tmp_path / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md"

    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--write-template",
            "--write-state",
            "--write-report",
            "--template-output-path",
            str(template_output),
            "--state-output-path",
            str(state_output),
            "--report-output-path",
            str(report_output),
            "--next-packet-output-path",
            str(next_packet_output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["template_output_status"] == "WRITTEN"
    assert payload["template_output_path"] == str(template_output)
    assert payload["state_output_path"] == str(state_output)
    assert payload["report_output_path"] == str(report_output)
    assert payload["next_packet_output_path"] == str(next_packet_output)

    report_text = report_output.read_text(encoding="utf-8")
    next_packet_text = next_packet_output.read_text(encoding="utf-8")
    assert "Status: OWNER_SAFETY_EVIDENCE_INTAKE_REVIEW" in report_text
    assert "Owner evidence completion percent: 0.0%" in report_text
    assert "Stale controls:" in report_text
    assert next_packet_text.startswith("CODEX-ONLY PROMPT")
