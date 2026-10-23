"""Tests for draft capability packet generation."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO_ROOT
    / "automation"
    / "orchestration"
    / "packet_generator"
    / "New-AiOsCapabilityPacketDraft.DRY_RUN.ps1"
)
VALIDATOR = (
    REPO_ROOT
    / "automation"
    / "orchestration"
    / "packet_generator"
    / "Test-AiOsCodexPacket.DRY_RUN.ps1"
)


def _run_capability_draft(**kwargs: str | list[str] | bool) -> dict:
    context = {
        "MissionId": "TEST-MISSION", "MissionName": "Packet compatibility test",
        "ProgramId": "TEST-PROGRAM", "ProgramName": "Development test",
        "EpicId": "TEST-EPIC", "EpicName": "Draft flow test",
        "BucketId": "TEST-BUCKET", "BucketName": "Packet test",
        "LockIdentity": "TEST-LOCK-NOT-ACQUIRED",
        "Worktree": str(REPO_ROOT),
    }
    context.update(kwargs)
    kwargs = context
    args = ["-OutputJson"]
    for key, value in kwargs.items():
        switch = f"-{key}"
        if isinstance(value, bool):
            if value:
                args.append(switch)
        elif isinstance(value, list):
            for item in value:
                args.extend([switch, str(item)])
        else:
            args.extend([switch, str(value)])

    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
    ] + args
    raw = subprocess.check_output(cmd, text=True, cwd=str(REPO_ROOT))
    return json.loads(raw.strip())


def _run_validator(packet_text: str) -> dict:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(VALIDATOR),
        "-PacketText",
        packet_text,
        "-OutputJson",
    ]
    raw = subprocess.check_output(cmd, text=True, cwd=str(REPO_ROOT))
    return json.loads(raw.strip())


def _get_field(packet_text: str, field_name: str) -> str:
    lines = packet_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == f"{field_name}:" and index + 1 < len(lines):
            return lines[index + 1].strip()
    raise AssertionError(f"Missing field '{field_name}' in generated packet.")


def _packet_headers(packet: str) -> None:
    for required in (
        "CODEX-ONLY PROMPT",
        "AI_OS EXECUTION TOKEN",
        "AI_OS BOOTSTRAP REQUIRED",
        "IDENTITY MARKER:",
        "SUPERVISOR IDENTITY:",
        "WORKER IDENTITY:",
        "PACKET ID:",
        "MODE:",
        "ZONE:",
        "LANE:",
        "APPROVAL AUTHORITY:",
        "MISSION ID:", "MISSION NAME:", "PROGRAM ID:", "PROGRAM NAME:",
        "EPIC ID:", "EPIC NAME:", "BUCKET ID:", "BUCKET NAME:",
        "PREFLIGHT:", "READ FIRST:", "ALLOWED PATHS:", "FORBIDDEN PATHS:",
        "VALIDATOR CHAIN:", "STOP POINT:", "FINAL REPORT FORMAT:",
        "STAGING AUTHORITY:", "COMMIT AUTHORITY:", "PUSH AUTHORITY:",
        "PULL REQUEST AUTHORITY:", "MERGE AUTHORITY:",
        "execution_allowed=false", "can_continue_without_anthony=false",
    ):
        assert required in packet


def test_claude_code_intent_becomes_research_scaffold() -> None:
    result = _run_capability_draft(
        CapabilityName="Claude Code",
        CapabilityIntent="connect Claude Code as optional code review actor",
    )

    assert result["schema"] == "AIOS_CAPABILITY_PACKET_DRAFT.v1"
    assert result["capability_type"] in {"cli_tool", "unknown"}
    assert result["safety_tier"] == "DRY_RUN_ONLY"
    assert result["suggested_actor"] == "claude_code"
    assert result["execution_allowed"] is False
    assert result["requires_human_review"] is True
    assert "RESEARCH" in result["exact_next_action"].upper()
    _packet_headers(result["generated_packet_text"])


def test_ue5_build_logs_maps_to_game_engine_style() -> None:
    result = _run_capability_draft(
        CapabilityName="UE5 Logs",
        CapabilityIntent="inspect Unreal Engine 5 build logs and generate fix packet",
    )

    assert result["capability_type"] == "game_engine"
    assert result["suggested_actor"] == "unreal_engine_5"
    assert result["safety_tier"] == "DRY_RUN_ONLY"
    assert result["execution_allowed"] is False
    assert result["generated_packet_id"].startswith("AIOS-CAPABILITY-GAME_ENGINE")


def test_broker_api_is_blocked_high_risk_intent() -> None:
    result = _run_capability_draft(
        CapabilityName="Broker API",
        CapabilityIntent="connect broker API for future sandbox trading",
    )

    assert result["capability_type"] == "broker_sandbox"
    assert result["safety_tier"] in {"REQUIRES_SECRET_REVIEW", "BLOCKED_HIGH_RISK"}
    assert result["execution_allowed"] is False
    assert "No live integration" in result["stop_point"]
    assert "live_integration" in result["exact_next_action"].lower() or "risk review" in result["exact_next_action"].lower()


def test_capability_draft_preserves_scalar_fields_with_arrays() -> None:
    result = _run_capability_draft(
        CapabilityName="Relay Operator Action Router",
        CapabilityIntent="draft packet routing study for local code review",
        SuggestedZone="ORCHESTRATION",
        SuggestedLane="RELAY_OPERATOR_ACTION_ROUTER",
    )

    packet = result["generated_packet_text"]
    assert _get_field(packet, "SUPERVISOR IDENTITY") == "ChatGPT Planning Supervisor under Anthony Human Owner"
    assert _get_field(packet, "WORKER IDENTITY") == "Codex CLI local executor inside C:\\Dev\\Ai.Os"
    assert _get_field(packet, "WORKTREE") == str(REPO_ROOT)
    assert _get_field(packet, "BRANCH") == subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO_ROOT, text=True).strip()
    assert _get_field(packet, "MODE") == "DRY_RUN"
    assert _get_field(packet, "ZONE") == "ORCHESTRATION"
    assert _get_field(packet, "LANE") == "RELAY_OPERATOR_ACTION_ROUTER"

    validated = _run_validator(packet)
    assert validated["packet_valid"] is True


def test_unknown_intent_uses_dry_run_scaffold() -> None:
    result = _run_capability_draft(
        CapabilityName="Quantum Weather Sensor",
        CapabilityIntent="connect a brand new unsupported capability",
    )

    assert result["capability_type"] == "unknown"
    assert result["safety_tier"] == "DRY_RUN_ONLY"
    assert result["suggested_actor"] == "unknown_actor"
    assert result["execution_allowed"] is False
    assert "broker/OANDA/webhook/order/secrets paths" in result["forbidden_paths"]


def test_generated_packet_passes_validator() -> None:
    result = _run_capability_draft(
        CapabilityName="Research Connector",
        CapabilityIntent="draft a study capability",
    )

    validated = _run_validator(result["generated_packet_text"])
    assert validated["schema"] == "AIOS_CODEX_PACKET_VALIDATOR.v2"
    assert validated["packet_valid"] is True
    assert validated["execution_allowed"] is False


def test_dry_run_does_not_write_files() -> None:
    pre = subprocess.check_output(["git", "status", "--short"], text=True, cwd=str(REPO_ROOT))
    _run_capability_draft(
        CapabilityName="No File Write",
        CapabilityIntent="run in dry run mode only",
    )
    post = subprocess.check_output(["git", "status", "--short"], text=True, cwd=str(REPO_ROOT))
    assert pre == post


@pytest.mark.parametrize("field", ["MissionId", "ProgramName", "LockIdentity"])
def test_missing_context_cannot_be_overridden_by_legacy_header_fallback(field):
    result = _run_capability_draft(CapabilityName="Local Review", **{field: ""})
    assert result["packet_valid"] is False
    assert result["generated_packet_text"] == ""
    assert result["missing_required_fields"]
    assert result["execution_allowed"] is False


def test_complete_draft_does_not_claim_owner_approval():
    result = _run_capability_draft(CapabilityName="Local Review")
    assert result["packet_valid"] is True
    packet = result["generated_packet_text"]
    assert "Anthony approves" not in packet
    for field in ("STAGING", "COMMIT", "PUSH", "PULL REQUEST", "MERGE"):
        assert _get_field(packet, f"{field} AUTHORITY") == "NOT AUTHORIZED."
    assert result["execution_allowed"] is False
    assert result["can_continue_without_anthony"] is False


@pytest.mark.parametrize("response", [
    "throw 'validator unavailable'",
    "Write-Output 'invalid json'",
    "Write-Output ''",
    '[ordered]@{packet_valid=$false;missing_required_fields=@("FORCED_REJECTION");validation_defects=@()} | ConvertTo-Json',
])
def test_validator_failure_never_falls_back_to_header_presence(tmp_path, monkeypatch, response):
    copied = tmp_path / SCRIPT.name
    for name in (SCRIPT.name, "New-AiOsCodexPacket.DRY_RUN.ps1", "AiOsCodexPacketContract.ps1"):
        shutil.copyfile(SCRIPT.parent / name, tmp_path / name)
    (tmp_path / VALIDATOR.name).write_text("param([string]$PacketText, [switch]$OutputJson)\n" + response, encoding="utf-8")
    monkeypatch.setitem(globals(), "SCRIPT", copied)
    result = _run_capability_draft(CapabilityName="Local Review")
    assert result["packet_valid"] is False
    assert result["generated_packet_text"] == ""

def _checker_report_case(case):
    record = {"schema": "AIOS_CODEX_PACKET_VALIDATOR.v2", "packet_valid": True,
              "missing_required_fields": [], "validation_defects": [],
              "writes_files": False, "execution_allowed": False,
              "can_continue_without_anthony": False}
    if case == "string_true": record["packet_valid"] = "true"
    elif case == "integer_one": record["packet_valid"] = 1
    elif case == "recorded_missing": record["missing_required_fields"] = ["FORCED_MISSING"]
    elif case == "recorded_defect": record["validation_defects"] = ["FORCED_DEFECT"]
    elif case == "missing_list": del record["validation_defects"]
    elif case == "wrong_schema": record["schema"] = "OTHER_REPORT.v1"
    elif case == "unsafe_flag": record["execution_allowed"] = True
    elif case == "string_list": record["missing_required_fields"] = ""
    return record

@pytest.mark.parametrize("boundary", ["generator", "validator"])
@pytest.mark.parametrize("case", ["string_true", "integer_one", "recorded_missing", "recorded_defect", "missing_list", "wrong_schema", "unsafe_flag", "string_list"])
def test_wrapper_refuses_malformed_or_self_conflicting_reports(tmp_path, monkeypatch, boundary, case):
    accepted = _run_capability_draft(CapabilityName="Local Review")
    assert accepted["packet_valid"] is True
    copied = tmp_path / SCRIPT.name
    shutil.copyfile(SCRIPT, copied)
    shutil.copyfile(SCRIPT.parent / "AiOsCodexPacketContract.ps1", tmp_path / "AiOsCodexPacketContract.ps1")
    good_generator = {"schema": "AIOS_CODEX_PACKET_GENERATOR.v2", "contract_schema": "AIOS_CODEX_PACKET_CONTRACT.v2",
                      "packet_valid": True, "generated_packet_text": accepted["generated_packet_text"],
                      "missing_required_fields": [], "validation_defects": [], "writes_files": False,
                      "execution_allowed": False, "can_continue_without_anthony": False}
    checker = _checker_report_case(case)
    if boundary == "generator":
        checker["schema"] = good_generator["schema"] if case != "wrong_schema" else "OTHER_REPORT.v1"
        checker["generated_packet_text"] = good_generator["generated_packet_text"]
        good_generator = checker
        shutil.copyfile(VALIDATOR, tmp_path / VALIDATOR.name)
    else:
        response = json.dumps(checker).replace("'", "''")
        (tmp_path / VALIDATOR.name).write_text(
            "param([string]$PacketText,[switch]$OutputJson)\nWrite-Output '" + response + "'", encoding="utf-8")
    response = json.dumps(good_generator).replace("'", "''")
    (tmp_path / "New-AiOsCodexPacket.DRY_RUN.ps1").write_text("Write-Output '" + response + "'", encoding="utf-8")
    monkeypatch.setitem(globals(), "SCRIPT", copied)
    result = _run_capability_draft(CapabilityName="Local Review")
    assert result["packet_valid"] is False
    assert result["generated_packet_text"] == ""
