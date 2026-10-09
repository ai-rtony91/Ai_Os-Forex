from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from automation.forex_engine import (
    forex_owner_safety_evidence_artifact_verifier_v1 as verifier,
)
from automation.validators import aios_governance_validator


ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    ROOT
    / "scripts"
    / "forex_delivery"
    / "run_forex_owner_safety_evidence_artifact_verifier_v1.py"
)


def _timestamp(hours_ago: int = 1) -> str:
    return (
        datetime.now(timezone.utc)
        - timedelta(hours=hours_ago)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _artifact_text(control: str) -> str:
    return f"""# {control}

Control: {control}
Sanitized: yes
Contains secrets: no
Contains broker account identifiers: no
Broker API used: no
Credentials used: no
Order execution: no
Live trading authorized: no

Owner attestation:
Owner confirms this is sanitized.
"""


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    evidence_dir = tmp_path / "Reports" / "forex_delivery" / "owner_safety_evidence"
    evidence_dir.mkdir(parents=True)
    controls: dict[str, object] = {}
    evaluations: dict[str, object] = {}
    for control in verifier.CONTROL_FIELDS:
        artifact = evidence_dir / f"{control}.md"
        artifact.write_text(_artifact_text(control), encoding="utf-8")
        controls[control] = {
            "evidence_present": True,
            "sanitized_artifact_path": str(artifact),
            "evidence_timestamp_utc": _timestamp(),
            "freshness_window_hours": 24,
            "contains_secret_or_account_identifier": False,
        }
        evaluations[control] = {"status": "PRESENT_UNVERIFIED"}
    intake = tmp_path / "intake.json"
    prep = tmp_path / "prep.json"
    payload = {"controls": controls}
    intake.write_text(json.dumps(payload), encoding="utf-8")
    prep.write_text(json.dumps({"control_evaluations": evaluations}), encoding="utf-8")
    return intake, prep, payload


def _run(intake: Path, prep: Path) -> dict[str, object]:
    return verifier.run_artifact_verifier(
        intake_path=intake,
        prep_state_path=prep,
        now_utc=datetime.now(timezone.utc),
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_all_four_fresh_owner_evidence_artifacts_pass_structural_verification(
    tmp_path: Path,
) -> None:
    intake, prep, _payload = _write_fixture(tmp_path)

    result = _run(intake, prep)

    assert result["artifact_verifier_status"] == verifier.PASS_STATUS
    assert result["artifact_verified_controls"] == list(verifier.CONTROL_FIELDS)
    assert result["artifact_failed_controls"] == []
    assert result["operational_control_verified"] is False
    assert result["broker_api_used"] is False
    assert result["credentials_used"] is False
    assert result["order_execution"] is False
    assert result["live_trading_authorized"] is False


def test_default_checked_in_owner_evidence_uses_current_clock_and_fails_when_stale() -> None:
    result = verifier.run_artifact_verifier()

    assert result["artifact_verifier_status"] == verifier.FAIL_STATUS
    assert result["artifact_verified_controls"] == []
    assert result["artifact_failed_controls"] == list(verifier.CONTROL_FIELDS)
    for control in verifier.CONTROL_FIELDS:
        assert "evidence_timestamp_utc is outside freshness_window_hours" in result[
            "control_results"
        ][control]["failures"]
    assert result["operational_control_verified"] is False
    assert result["broker_api_used"] is False
    assert result["credentials_used"] is False
    assert result["order_execution"] is False
    assert result["live_trading_authorized"] is False


def test_missing_artifact_fails_verification(tmp_path: Path) -> None:
    intake, prep, payload = _write_fixture(tmp_path)
    control = "kill_switch_state"
    Path(payload["controls"][control]["sanitized_artifact_path"]).unlink()

    result = _run(intake, prep)

    assert control in result["artifact_failed_controls"]
    assert "artifact file is missing" in result["control_results"][control]["failures"]


def test_empty_artifact_fails_verification(tmp_path: Path) -> None:
    intake, prep, payload = _write_fixture(tmp_path)
    control = "daily_stop_state"
    Path(payload["controls"][control]["sanitized_artifact_path"]).write_text(
        "", encoding="utf-8"
    )

    result = _run(intake, prep)

    assert control in result["artifact_failed_controls"]
    assert "artifact file is empty" in result["control_results"][control]["failures"]


def test_artifact_outside_owner_safety_evidence_path_fails_verification(
    tmp_path: Path,
) -> None:
    intake, prep, payload = _write_fixture(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text(_artifact_text("max_loss_state"), encoding="utf-8")
    payload["controls"]["max_loss_state"]["sanitized_artifact_path"] = str(outside)
    intake.write_text(json.dumps(payload), encoding="utf-8")

    result = _run(intake, prep)

    assert "max_loss_state" in result["artifact_failed_controls"]
    assert (
        "sanitized_artifact_path is outside owner_safety_evidence path"
        in result["control_results"]["max_loss_state"]["failures"]
    )


def test_future_evidence_timestamp_fails_verification(tmp_path: Path) -> None:
    intake, prep, payload = _write_fixture(tmp_path)
    payload["controls"]["monitoring_ready"]["evidence_timestamp_utc"] = (
        datetime.now(timezone.utc) + timedelta(hours=1)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    intake.write_text(json.dumps(payload), encoding="utf-8")

    result = _run(intake, prep)

    assert "evidence_timestamp_utc is in the future" in result["control_results"][
        "monitoring_ready"
    ]["failures"]


def test_stale_evidence_timestamp_fails_verification(tmp_path: Path) -> None:
    intake, prep, payload = _write_fixture(tmp_path)
    payload["controls"]["kill_switch_state"]["evidence_timestamp_utc"] = _timestamp(48)
    payload["controls"]["kill_switch_state"]["freshness_window_hours"] = 24
    intake.write_text(json.dumps(payload), encoding="utf-8")

    result = _run(intake, prep)

    assert "evidence_timestamp_utc is outside freshness_window_hours" in result[
        "control_results"
    ]["kill_switch_state"]["failures"]


def test_secret_account_identifier_flag_true_fails_verification(tmp_path: Path) -> None:
    intake, prep, payload = _write_fixture(tmp_path)
    payload["controls"]["daily_stop_state"][
        "contains_secret_or_account_identifier"
    ] = True
    intake.write_text(json.dumps(payload), encoding="utf-8")

    result = _run(intake, prep)

    assert "contains_secret_or_account_identifier is not false" in result[
        "control_results"
    ]["daily_stop_state"]["failures"]


def test_artifact_missing_required_declarations_fails_verification(tmp_path: Path) -> None:
    intake, prep, payload = _write_fixture(tmp_path)
    control = "max_loss_state"
    Path(payload["controls"][control]["sanitized_artifact_path"]).write_text(
        f"Control: {control}\nOwner attestation:\n", encoding="utf-8"
    )

    result = _run(intake, prep)

    failures = result["control_results"][control]["failures"]
    assert "artifact file missing declaration: Sanitized: yes" in failures
    assert "artifact file missing declaration: Contains secrets: no" in failures
    assert "artifact file missing declaration: Contains broker account identifiers: no" in failures
    assert "artifact file missing declaration: Broker API used: no" in failures
    assert "artifact file missing declaration: Credentials used: no" in failures
    assert "artifact file missing declaration: Order execution: no" in failures
    assert "artifact file missing declaration: Live trading authorized: no" in failures


def test_verifier_does_not_modify_intake_json_or_artifact_files(tmp_path: Path) -> None:
    intake, prep, payload = _write_fixture(tmp_path)
    watched = [intake] + [
        Path(payload["controls"][control]["sanitized_artifact_path"])
        for control in verifier.CONTROL_FIELDS
    ]
    before = {path: _sha(path) for path in watched}

    _run(intake, prep)

    assert {path: _sha(path) for path in watched} == before


def test_runner_writes_state_report_and_next_packet(tmp_path: Path) -> None:
    intake, prep, _payload = _write_fixture(tmp_path)
    state = tmp_path / "state.json"
    report = tmp_path / "report.md"
    next_packet = tmp_path / "next_packet.md"

    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--intake-path",
            str(intake),
            "--prep-state-path",
            str(prep),
            "--write-state",
            "--state-output-path",
            str(state),
            "--write-report",
            "--report-output-path",
            str(report),
            "--write-next-packet",
            "--next-packet-output-path",
            str(next_packet),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["artifact_verifier_status"] == verifier.PASS_STATUS
    assert state.exists()
    assert report.exists()
    assert next_packet.exists()
    packet_text = next_packet.read_text(encoding="utf-8")
    assert packet_text.startswith("CODEX-ONLY PROMPT")
    validation = aios_governance_validator.validate_packet_text(
        packet_text, str(next_packet)
    )
    assert validation["status"] == "PASS"


def test_generated_next_packet_starts_with_codex_only_prompt_and_passes_validator() -> None:
    packet_text = verifier.build_next_codex_packet({})

    assert packet_text.startswith("CODEX-ONLY PROMPT")
    validation = aios_governance_validator.validate_packet_text(
        packet_text, "generated"
    )
    assert validation["status"] == "PASS"
    forbidden_phrases = [
        "connect broker",
        "OANDA integration",
        "place_order",
        "real_order",
        "live_order",
        "enable live trading",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in packet_text


def test_verifier_never_claims_forbidden_execution_authority() -> None:
    result = verifier.run_artifact_verifier()

    assert result["operational_control_verified"] is False
    assert result["broker_api_used"] is False
    assert result["credentials_used"] is False
    assert result["order_execution"] is False
    assert result["live_trading_authorized"] is False
    assert result["owner_intake_modified"] is False
    assert result["evidence_artifacts_modified"] is False
    assert result["evidence_invented"] is False
