"""Tests for Resolve-AiOsRelayHumanReview.DRY_RUN.ps1."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RELAY_RESOLVER_SCRIPT = REPO_ROOT / "automation/orchestration/relay_bus/Resolve-AiOsRelayHumanReview.DRY_RUN.ps1"
NEW_MESSAGE_SCRIPT = REPO_ROOT / "automation/orchestration/relay_bus/New-AiOsRelayMessage.DRY_RUN.ps1"
REGISTRY_SOURCE = REPO_ROOT / "control/relay_bus/actors/AIOS_RELAY_ACTORS.json"


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


def _seed_relay_message(root: Path) -> dict:
    return _run_script_json(
        NEW_MESSAGE_SCRIPT,
        [
            "-Actor",
            "codex_cli",
            "-TargetActor",
            "powershell_operator",
            "-PacketId",
            "AIOS-RELAY-REVIEW-RESOLVER-01",
            "-Branch",
            "feature/actor-relay-review-resolver-v1",
            "-MessageType",
            "codex_final_report",
            "-Intent",
            "handoff summary",
            "-Status",
            "pending",
            "-PayloadText",
            json.dumps({"message_id": "AIOS-RELAY-REVIEW-RESOLVER-01", "content": "resolve in review"}),
            "-Mode",
            "APPLY",
        ],
        root,
    )


def _list_files(root: Path) -> set[str]:
    return {str(item.relative_to(root)) for item in root.rglob("*") if item.is_file()}


def test_resolver_empty_inbox_returns_empty_state_and_no_mutation(tmp_path: Path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)

    pre_files = _list_files(root)
    out = _run_script_json(RELAY_RESOLVER_SCRIPT, [], root)
    post_files = _list_files(root)

    assert out["schema"] == "AIOS_RELAY_HUMAN_REVIEW_RESOLUTION.v1"
    assert out["mode"] == "DRY_RUN_READ_ONLY"
    assert out["status"] == "EMPTY"
    assert out["latest_message_path"] == ""
    assert out["actor"] == ""
    assert out["target_actor"] == ""
    assert out["packet_id"] == ""
    assert out["message_type"] == ""
    assert out["intent"] == ""
    assert out["status_detail"] == ""
    assert out["why_human_review_needed"] == "No actor relay message found for review."
    assert out["writes_files"] is False
    assert out["execution_allowed"] is False
    assert out["can_continue_without_anthony"] is False
    assert out["requires_human_review"] is True
    assert pre_files == post_files


def test_resolver_pending_human_review_message_returns_summary(tmp_path: Path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)
    seed_result = _seed_relay_message(root)
    relay_file = Path(seed_result["relay_file"])

    out = _run_script_json(RELAY_RESOLVER_SCRIPT, [], root)

    assert out["status"] == "NEEDS_HUMAN_REVIEW"
    assert out["latest_message_path"] == str(relay_file)
    assert out["actor"] == "codex_cli"
    assert out["target_actor"] == "powershell_operator"
    assert out["packet_id"] == "AIOS-RELAY-REVIEW-RESOLVER-01"
    assert out["message_type"] == "codex_final_report"
    assert out["intent"] == "handoff summary"
    assert out["status_detail"] == "pending"
    assert out["safe_next_action"] == (
        "Do not execute; open the actor relay message, resolve concerns, run SOS escalation policy classification with: powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/relay_bus/Get-AiOsSosEscalationPolicy.DRY_RUN.ps1 -OutputJson, then continue only with explicit Anthony approval."
    )
    assert (
        out["sos_policy_next_action"]
        == "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/relay_bus/Get-AiOsSosEscalationPolicy.DRY_RUN.ps1 -OutputJson"
    )
    assert out["requires_human_review"] is True
    assert out["execution_allowed"] is False
    assert out["can_continue_without_anthony"] is False
    assert out["payload_contains_forbidden_secret_pattern"] is False
    assert "requiring human review" in out["why_human_review_needed"]


def test_resolver_does_not_write_any_files(tmp_path: Path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)
    _seed_relay_message(root)
    before = _list_files(root)

    out = _run_script_json(RELAY_RESOLVER_SCRIPT, [], root)
    after = _list_files(root)

    assert out["writes_files"] is False
    assert before == after


def test_resolver_secret_like_payload_stays_review_required(tmp_path: Path) -> None:
    root = tmp_path
    _init_relay_bus_root(root)
    message_path = root / "control" / "relay_bus" / "messages" / "inbox" / "secret_message.json"
    message_path.write_text(
        json.dumps(
            {
                "schema": "AIOS_RELAY_MESSAGE.v1",
                "message_id": "AIOS-RELAY-REVIEW-RESOLVER-SECRET",
                "created_utc": "2026-06-13T00:00:00Z",
                "actor": "codex_cli",
                "target_actor": "powershell_operator",
                "packet_id": "AIOS-RELAY-REVIEW-RESOLVER-SECRET",
                "branch": "feature/actor-relay-review-resolver-v1",
                "message_type": "codex_final_report",
                "intent": "handoff secret payload",
                "status": "pending",
                "payload_text": "AIOS_TG_BOT_TOKEN=abc123",
                "requires_human_review": True,
                "execution_allowed": False,
                "can_continue_without_anthony": False,
                "next_action": "resolve token leakage",
            }
        ),
        encoding="utf-8",
    )

    out = _run_script_json(RELAY_RESOLVER_SCRIPT, [], root)
    serialized = json.dumps(out, sort_keys=True)

    assert out["status"] == "NEEDS_HUMAN_REVIEW"
    assert out["payload_contains_forbidden_secret_pattern"] is True
    assert out["requires_human_review"] is True
    assert "secret-like pattern" in out["why_human_review_needed"]
    assert "Do not execute" in out["safe_next_action"]
    assert "AIOS_TG_BOT_TOKEN" not in serialized
    assert out["execution_allowed"] is False
    assert out["can_continue_without_anthony"] is False
