"""Tests for the no-ready-stage campaign discovery router."""

from pathlib import Path
import json
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
DISCOVERY_SCRIPT = REPO_ROOT / "automation/orchestration/campaign_registry/Get-AiOsCampaignNoReadyStageDiscovery.DRY_RUN.ps1"
ACTION_RECOMMENDATION_SCRIPT = REPO_ROOT / "automation/orchestration/recommendations/Get-AiOsActionRecommendation.DRY_RUN.ps1"
DISCOVERY_COMMAND = (
    "powershell -NoProfile -ExecutionPolicy Bypass -File "
    "automation/orchestration/campaign_registry/Get-AiOsCampaignNoReadyStageDiscovery.DRY_RUN.ps1 -OutputJson"
)
ALLOWED_CLASSIFICATIONS = {
    "COMPLETE_IDLE",
    "NEEDS_NEXT_STAGE_PLANNING",
    "BLOCKED_BY_REGISTRY_INCONSISTENCY",
}


def _run_script_json(script: Path, args: list[str] | None = None) -> dict:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-OutputJson",
        *(args or []),
    ]
    raw = subprocess.check_output(cmd, cwd=str(REPO_ROOT), text=True)
    return json.loads(raw.strip())


def _file_set(root: Path) -> set[str]:
    return {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }


def test_discovery_script_emits_contract_schema() -> None:
    out = _run_script_json(DISCOVERY_SCRIPT)

    assert out["schema"] == "AIOS_CAMPAIGN_NO_READY_STAGE_DISCOVERY.v1"
    assert out["mode"] == "DRY_RUN_READ_ONLY"
    assert out["no_ready_stage_classification"] in ALLOWED_CLASSIFICATIONS


def test_discovery_script_is_dry_run_read_only() -> None:
    out = _run_script_json(DISCOVERY_SCRIPT)

    assert out["safety"]["planning_only"] is True
    assert out["safety"]["writes_files"] is False
    assert out["safety"]["mutates_registry"] is False
    assert out["safety"]["creates_ready_stage"] is False
    assert out["safety"]["runs_workers"] is False
    assert out["safety"]["starts_runtime"] is False


def test_current_registry_reports_no_ready_stage_detected() -> None:
    out = _run_script_json(DISCOVERY_SCRIPT)

    assert out["overall_readiness"] == "READY_FOR_PACKET_PREVIEW"
    assert out["no_ready_stage_detected"] is False
    assert out["candidate_gap_summary"]["supervised_autonomy_no_next_selectable_stage"] is True


def test_current_registry_classifier_state_is_allowed_and_internally_consistent() -> None:
    out = _run_script_json(DISCOVERY_SCRIPT)

    assert out["no_ready_stage_classification"] in ALLOWED_CLASSIFICATIONS
    if out["no_ready_stage_classification"] == "COMPLETE_IDLE":
        assert out["idle_allowed"] is True
        assert out["next_stage_planning_required"] is False
        assert out["registry_inconsistency_detected"] is False
    elif out["no_ready_stage_classification"] == "NEEDS_NEXT_STAGE_PLANNING":
        assert out["idle_allowed"] is False
        assert out["next_stage_planning_required"] is True
        assert out["registry_inconsistency_detected"] is False
    elif out["no_ready_stage_classification"] == "BLOCKED_BY_REGISTRY_INCONSISTENCY":
        assert out["idle_allowed"] is False
        assert out["next_stage_planning_required"] is False
        assert out["registry_inconsistency_detected"] is True


def test_discovery_output_includes_classifier_evidence() -> None:
    out = _run_script_json(DISCOVERY_SCRIPT)

    assert "classifier_evidence" in out
    evidence = out["classifier_evidence"]
    for key in (
        "ready_count",
        "blocked_count",
        "active_high_priority_blocked_count",
        "planned_or_in_progress_candidate_count",
        "last_completed_high_priority_stage_exists",
    ):
        assert key in evidence


def test_discovery_output_includes_campaign_stage_status_counts() -> None:
    out = _run_script_json(DISCOVERY_SCRIPT)
    counts = out["inventory"]["status_counts"]

    for key in ("READY", "COMPLETE", "BLOCKED", "IN_PROGRESS", "PLANNED", "UNKNOWN"):
        assert key in counts
    assert out["inventory"]["total_campaigns"] > 0
    assert out["inventory"]["total_phases"] > 0
    assert out["inventory"]["total_stages"] > 0


def test_discovery_output_includes_safe_planning_recommended_next_action() -> None:
    out = _run_script_json(DISCOVERY_SCRIPT)

    recommended = out["recommended_next_action"].lower()
    assert "campaign next-task selector output" in recommended


def test_discovery_recommended_next_action_omits_forbidden_action_language() -> None:
    out = _run_script_json(DISCOVERY_SCRIPT)
    recommended = out["recommended_next_action"]
    forbidden_patterns = [
        r"\bcommit\b",
        r"\bpush\b",
        r"\bpr\b",
        r"\bmerge\b",
        r"\bapply\b",
        r"\bworker launch\b",
        r"\bruntime start\b",
        r"\bqueue mutation\b",
        r"\bapproval mutation\b",
        r"\bbroker\b",
        r"\boanda\b",
        r"\bwebhook\b",
        r"\border\b",
        r"\blive trading\b",
        r"\bsecret handling\b",
    ]

    for pattern in forbidden_patterns:
        assert re.search(pattern, recommended, flags=re.IGNORECASE) is None


def test_discovery_script_writes_no_files() -> None:
    before = _file_set(REPO_ROOT)
    _run_script_json(DISCOVERY_SCRIPT)
    after = _file_set(REPO_ROOT)

    assert before == after


def test_action_recommendation_surfaces_discovery_router_for_no_ready_stage() -> None:
    out = _run_script_json(ACTION_RECOMMENDATION_SCRIPT)

    assert out["mode"] == "READ_ONLY"
    assert out["packet_status"] == "campaign_ready"
    assert out["campaign_overall_readiness"] == "READY_FOR_PACKET_PREVIEW"
    assert out["no_ready_stage_classification"] == ""
    assert out["recommended_command"] == "powershell -ExecutionPolicy Bypass -File automation/orchestration/health/Test-AiOsRuntimeHealth.DRY_RUN.ps1"
    assert "no command recommended" not in out["orchestration_result_contract"]["next_safe_action"].lower()
