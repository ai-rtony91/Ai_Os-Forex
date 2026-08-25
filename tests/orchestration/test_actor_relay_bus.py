"""Tests for V1 file-based actor relay bus envelopes and state readers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_SOURCE = REPO_ROOT / "control/relay_bus/actors/AIOS_RELAY_ACTORS.json"
NEW_MESSAGE_SCRIPT = REPO_ROOT / "automation/orchestration/relay_bus/New-AiOsRelayMessage.DRY_RUN.ps1"
RELAY_BUS_STATE_SCRIPT = REPO_ROOT / "automation/orchestration/relay_bus/Get-AiOsRelayBusState.DRY_RUN.ps1"
RELAY_OPERATOR_STATE_SCRIPT = REPO_ROOT / "automation/orchestration/review_bridge/Get-AiOsRelayOperatorState.DRY_RUN.ps1"
AIOS_PS1 = REPO_ROOT / "aios.ps1"


def _run_script_json(script: Path, args: list[str], cwd: Path) -> dict:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-OutputJson",
    ] + args
    raw = subprocess.check_output(cmd, cwd=str(cwd), text=True)
    return json.loads(raw.strip())


def _init_relay_bus_root(root: Path) -> None:
    control_root = root / "control" / "relay_bus"
    (control_root / "actors").mkdir(parents=True, exist_ok=True)
    (control_root / "messages" / "inbox").mkdir(parents=True, exist_ok=True)
    (control_root / "messages" / "outbox").mkdir(parents=True, exist_ok=True)
    (control_root / "messages" / "archive").mkdir(parents=True, exist_ok=True)
    (control_root / "evidence").mkdir(parents=True, exist_ok=True)
    (control_root / "pasteback").mkdir(parents=True, exist_ok=True)
    for marker in (
        control_root / "messages" / "inbox" / ".gitkeep",
        control_root / "messages" / "outbox" / ".gitkeep",
        control_root / "messages" / "archive" / ".gitkeep",
        control_root / "evidence" / ".gitkeep",
        control_root / "pasteback" / ".gitkeep",
    ):
        marker.write_text("", encoding="utf-8")
    shutil.copy2(REGISTRY_SOURCE, control_root / "actors" / "AIOS_RELAY_ACTORS.json")


def _build_payload(message_id: str) -> str:
    return json.dumps({"message_id": message_id, "content": "relay test"})


def _run_script_filelist(root: Path) -> set[str]:
    return {str(item.relative_to(root)) for item in root.rglob("*") if item.is_file()}


def test_actor_registry_exists_and_starter_actors_are_present(tmp_path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)
    registry = json.loads((root / "control" / "relay_bus" / "actors" / "AIOS_RELAY_ACTORS.json").read_text(encoding="utf-8"))
    actor_ids = [item["actor_id"] for item in registry["actors"]]

    assert "chatgpt_supervisor" in actor_ids
    assert "openai_cli" in actor_ids
    assert "codex_cli" in actor_ids
    assert "powershell_operator" in actor_ids
    assert "aios_relay" in actor_ids


def test_future_actors_present_but_disabled(tmp_path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)
    registry = json.loads((root / "control" / "relay_bus" / "actors" / "AIOS_RELAY_ACTORS.json").read_text(encoding="utf-8"))
    by_id = {item["actor_id"]: item for item in registry["actors"]}

    for actor_id in ("claude_code", "unreal_engine_5", "vscode", "github_actions"):
        assert actor_id in by_id
        assert by_id[actor_id]["enabled"] is False


def test_relay_message_dry_run_does_not_write(tmp_path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)

    result = _run_script_json(
        NEW_MESSAGE_SCRIPT,
        [
            "-Actor",
            "codex_cli",
            "-TargetActor",
            "powershell_operator",
            "-PacketId",
            "AIOS-RELAY-BUS-DRY-01",
            "-Branch",
            "feature/actor-relay-bus-v1",
            "-MessageType",
            "codex_final_report",
            "-Intent",
            "handoff summary",
            "-Status",
            "pending",
            "-PayloadText",
            _build_payload("AIOS-RELAY-BUS-DRY-01"),
            "-Mode",
            "DRY_RUN",
        ],
        root,
    )

    assert result["writes_files"] is False
    assert result["schema"] == "AIOS_RELAY_MESSAGE_RESULT.v1"
    assert result["mode"] == "DRY_RUN_READ_ONLY"
    assert result["message"]["schema"] == "AIOS_RELAY_MESSAGE.v1"


def test_relay_message_apply_writes_only_in_inbox_directory(tmp_path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)

    pre_files = set(root.rglob("*"))
    result = _run_script_json(
        NEW_MESSAGE_SCRIPT,
        [
            "-Actor",
            "codex_cli",
            "-TargetActor",
            "powershell_operator",
            "-PacketId",
            "AIOS-RELAY-BUS-APPLY-01",
            "-Branch",
            "feature/actor-relay-bus-v1",
            "-MessageType",
            "codex_final_report",
            "-Intent",
            "handoff summary",
            "-Status",
            "pending",
            "-PayloadText",
            _build_payload("AIOS-RELAY-BUS-APPLY-01"),
            "-Mode",
            "APPLY",
        ],
        root,
    )

    assert result["writes_files"] is True
    message_file = Path(result["relay_file"])
    assert message_file.exists()
    assert message_file.is_file()
    assert str(message_file).startswith(str(root / "control" / "relay_bus" / "messages" / "inbox"))

    new_files = {item for item in root.rglob("*") if item.is_file()} - pre_files
    assert len(new_files) >= 1
    for created in new_files:
        assert str(created).startswith(str(root / "control" / "relay_bus"))


def test_unknown_actor_is_rejected(tmp_path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)

    result = _run_script_json(
        NEW_MESSAGE_SCRIPT,
        [
            "-Actor",
            "does_not_exist",
            "-TargetActor",
            "powershell_operator",
            "-PacketId",
            "AIOS-RELAY-BUS-ERROR-01",
            "-Branch",
            "feature/actor-relay-bus-v1",
            "-MessageType",
            "codex_final_report",
            "-Intent",
            "handoff summary",
            "-Status",
            "pending",
            "-PayloadText",
            _build_payload("AIOS-RELAY-BUS-ERROR-01"),
            "-Mode",
            "APPLY",
        ],
        root,
    )

    assert result["writes_files"] is False
    assert result["blocked"] is True
    assert any("Unknown actor" in reason for reason in result["message"]["evidence"]["blocked_reasons"])

def test_token_like_payload_is_rejected(tmp_path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)

    result = _run_script_json(
        NEW_MESSAGE_SCRIPT,
        [
            "-Actor",
            "codex_cli",
            "-TargetActor",
            "powershell_operator",
            "-PacketId",
            "AIOS-RELAY-BUS-ERROR-02",
            "-Branch",
            "feature/actor-relay-bus-v1",
            "-MessageType",
            "codex_final_report",
            "-Intent",
            "handoff summary",
            "-Status",
            "pending",
            "-PayloadText",
            "AIOS_TG_BOT_TOKEN=abc123",
            "-Mode",
            "APPLY",
        ],
        root,
    )

    assert result["writes_files"] is False
    assert result["blocked"] is True
    assert any("Forbidden token/secret pattern" in reason for reason in result["message"]["evidence"]["blocked_reasons"])


def test_relay_state_reads_latest_and_tracks_next_action(tmp_path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)

    first_result = _run_script_json(
        NEW_MESSAGE_SCRIPT,
        [
            "-Actor",
            "codex_cli",
            "-TargetActor",
            "powershell_operator",
            "-PacketId",
            "AIOS-RELAY-BUS-STATE-OLD",
            "-Branch",
            "feature/actor-relay-bus-v1",
            "-MessageType",
            "codex_final_report",
            "-Intent",
            "handoff summary",
            "-Status",
            "pending",
            "-PayloadText",
            _build_payload("AIOS-RELAY-BUS-STATE-OLD"),
            "-Mode",
            "APPLY",
        ],
        root,
    )
    first_message_path = Path(first_result["relay_file"])
    older_timestamp = first_message_path.stat().st_mtime - 60.0
    os.utime(first_message_path, (older_timestamp, older_timestamp))
    _run_script_json(
        NEW_MESSAGE_SCRIPT,
        [
            "-Actor",
            "codex_cli",
            "-TargetActor",
            "powershell_operator",
            "-PacketId",
            "AIOS-RELAY-BUS-STATE-LATEST",
            "-Branch",
            "feature/actor-relay-bus-v1",
            "-MessageType",
            "reviewed_powershell",
            "-Intent",
            "apply after review",
            "-Status",
            "pending",
            "-PayloadText",
            _build_payload("AIOS-RELAY-BUS-STATE-LATEST"),
            "-Mode",
            "APPLY",
        ],
        root,
    )

    state = _run_script_json(RELAY_BUS_STATE_SCRIPT, [], root)
    assert state["latest_packet_id"] == "AIOS-RELAY-BUS-STATE-LATEST"
    assert state["latest_message_type"] == "reviewed_powershell"
    assert state["relay_status"] == "READY_FOR_POWERSHELL_PASTEBACK"
    assert "latest actor relay message" not in state["exact_next_action"]
    assert state["actor_count"] == 9
    assert state["execution_allowed"] is False
    assert state["can_continue_without_anthony"] is False


def test_relay_state_empty_inbox_returns_empty_no_crash(tmp_path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)

    pre_files = _run_script_filelist(root)
    state = _run_script_json(RELAY_BUS_STATE_SCRIPT, [], root)
    post_files = _run_script_filelist(root)

    assert state["relay_status"] == "EMPTY"
    assert state["latest_message_path"] == ""
    assert state["latest_actor"] == ""
    assert state["latest_target_actor"] == ""
    assert state["latest_message_type"] == ""
    assert state["latest_packet_id"] == ""
    assert state["actor_count"] == 9
    assert state["pending_human_review_count"] == 0
    assert state["pending_messages"] == []
    assert state["execution_allowed"] is False
    assert state["can_continue_without_anthony"] is False
    assert pre_files == post_files


def test_relay_state_with_single_message_returns_latest(tmp_path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)

    _run_script_json(
        NEW_MESSAGE_SCRIPT,
        [
            "-Actor",
            "codex_cli",
            "-TargetActor",
            "powershell_operator",
            "-PacketId",
            "AIOS-RELAY-BUS-SINGLE-01",
            "-Branch",
            "feature/actor-relay-bus-v1",
            "-MessageType",
            "codex_final_report",
            "-Intent",
            "handoff summary",
            "-Status",
            "pending",
            "-PayloadText",
            _build_payload("AIOS-RELAY-BUS-SINGLE-01"),
            "-Mode",
            "APPLY",
        ],
        root,
    )

    state = _run_script_json(RELAY_BUS_STATE_SCRIPT, [], root)
    assert state["latest_message_type"] == "codex_final_report"
    assert state["latest_actor"] == "codex_cli"
    assert state["latest_target_actor"] == "powershell_operator"
    assert state["latest_packet_id"] == "AIOS-RELAY-BUS-SINGLE-01"
    assert state["relay_status"] == "NEEDS_HUMAN_REVIEW"
    assert state["exact_next_action"] == (
        "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/relay_bus/Resolve-AiOsRelayHumanReview.DRY_RUN.ps1 -OutputJson"
    )
    assert state["pending_human_review_count"] == 1
    assert state["execution_allowed"] is False
    assert state["can_continue_without_anthony"] is False


def test_relay_bus_state_integration_fields_appear_in_operator_state(tmp_path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)

    operator_state = _run_script_json(RELAY_OPERATOR_STATE_SCRIPT, [], root)
    assert operator_state["schema"] == "AIOS_RELAY_OPERATOR_STATE.v1"
    assert "actor_relay_bus_status" in operator_state
    assert "actor_relay_latest_message_path" in operator_state
    assert "actor_relay_latest_actor" in operator_state
    assert "actor_relay_latest_target_actor" in operator_state
    assert "actor_relay_next_action" in operator_state
    assert operator_state["actor_relay_bus_status"] in (
        "EMPTY",
        "NEEDS_HUMAN_REVIEW",
        "READY_FOR_POWERSHELL_PASTEBACK",
        "BLOCKED_NEEDS_OWNER",
        "REVIEW_READY",
    )


def test_aios_mode_relay_outputs_actor_relay_bus_fields() -> None:
    output = subprocess.check_output(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(AIOS_PS1),
            "-Mode",
            "relay",
        ],
        cwd=str(REPO_ROOT),
        text=True,
    )
    start = output.find("{")
    end = output.rfind("}")
    assert start >= 0 and end > start

    relay_state = json.loads(output[start : end + 1])
    assert relay_state["schema"] == "AIOS_RELAY_OPERATOR_STATE.v1"
    assert relay_state["actor_relay_bus_status"] is not None
    assert "actor_relay_latest_message_path" in relay_state
    assert "actor_relay_next_action" in relay_state
