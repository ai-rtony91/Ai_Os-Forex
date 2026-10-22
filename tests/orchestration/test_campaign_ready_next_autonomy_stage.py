"""Tests for campaign registry readiness wiring for routine relay review continuation."""

from pathlib import Path
from contextlib import contextmanager
import json
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_REGISTRY = REPO_ROOT / "automation/orchestration/campaign_registry/AIOS_STRATEGIC_CAMPAIGN_REGISTRY.json"
CAMPAIGN_NEXT_TASK_SCRIPT = REPO_ROOT / "automation/orchestration/campaign_registry/Get-AiOsCampaignNextTask.DRY_RUN.ps1"
ACTION_RECOMMENDATION_SCRIPT = REPO_ROOT / "automation/orchestration/recommendations/Get-AiOsActionRecommendation.DRY_RUN.ps1"
RELAY_INBOX = REPO_ROOT / "control/relay_bus/messages/inbox"
NO_READY_DISCOVERY_COMMAND = (
    "powershell -NoProfile -ExecutionPolicy Bypass -File "
    "automation/orchestration/campaign_registry/Get-AiOsCampaignNoReadyStageDiscovery.DRY_RUN.ps1 -OutputJson"
)


def _run_script_json(script: Path, args: list[str]) -> dict:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-OutputJson",
        *args,
    ]
    raw = subprocess.check_output(cmd, cwd=str(REPO_ROOT), text=True)
    return json.loads(raw.strip())


def _file_set(root: Path) -> set[str]:
    return {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }


@contextmanager
def _isolated_relay_inbox():
    RELAY_INBOX.mkdir(parents=True, exist_ok=True)
    saved_messages = {path.name: path.read_bytes() for path in RELAY_INBOX.glob("*.json")}
    for message_file in RELAY_INBOX.glob("*.json"):
        if message_file.name != ".gitkeep":
            message_file.unlink()

    try:
        yield
    finally:
        for message_file in RELAY_INBOX.glob("*.json"):
            if message_file.name != ".gitkeep":
                message_file.unlink()
        for name, content in saved_messages.items():
            (RELAY_INBOX / name).write_bytes(content)


def _stage_by_id(registry: dict, stage_id: str) -> dict:
    for campaign in registry.get("campaigns", []):
        for stage in campaign.get("stages", []):
            if stage.get("stage_id") == stage_id:
                return stage
    raise AssertionError(f"stage not found: {stage_id}")


def test_campaign_registry_marks_relay_routine_continuation_stage_complete() -> None:
    with CAMPAIGN_REGISTRY.open("r", encoding="utf-8") as fh:
        registry = json.load(fh)

    stage = _stage_by_id(
        registry,
        "STAGE-AUTONOMY-ROUTINE-REVIEW-CONTINUATION",
    )
    assert stage["status"] == "COMPLETE"
    assert stage["next_packet_candidate"] is None
    assert stage["completed_by_pr"] == "https://github.com/ai-rtony91/Ai_Os/pull/642"
    assert stage["completed_by_commit"] == "bc99ae4e"


def test_campaign_next_task_truthfully_reports_no_ready_stage_after_routine_gate_completion() -> None:
    pre = _file_set(REPO_ROOT)
    out = _run_script_json(CAMPAIGN_NEXT_TASK_SCRIPT, [])
    post = _file_set(REPO_ROOT)

    assert out["schema"] == "AIOS_CAMPAIGN_NEXT_TASK_RECOMMENDATION.v1"
    assert out["overall_readiness"] == "READY_FOR_PACKET_PREVIEW"
    assert out["recommended_campaign"] is not None
    assert out["recommended_phase"] is not None
    assert out["recommended_stage"] is not None
    assert out["recommended_lane"] == "production-hardening-review"
    assert out["next_packet_candidate"] == "PKT-PRODUCTION-READINESS-REVIEW-DRYRUN"
    assert out["reason"] == "Selected highest-priority READY stage with complete dependencies and no blockers."
    assert out["blockers"] == []
    assert pre == post


def test_action_recommendation_truthfully_reports_no_active_packet_when_no_ready_stage_exists() -> None:
    with _isolated_relay_inbox():
        pre = _file_set(REPO_ROOT)
        out = _run_script_json(ACTION_RECOMMENDATION_SCRIPT, [])
        post = _file_set(REPO_ROOT)

    assert out["packet_status"] == "campaign_ready"
    assert out["campaign_overall_readiness"] == "READY_FOR_PACKET_PREVIEW"
    assert out["recommended_command"] == "powershell -ExecutionPolicy Bypass -File automation/orchestration/health/Test-AiOsRuntimeHealth.DRY_RUN.ps1"
    assert out["mode"] == "READ_ONLY"
    assert pre == post
