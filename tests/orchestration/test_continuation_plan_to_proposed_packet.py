"""Tests for the continuation-to-proposed-packet DRY_RUN bridge."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "automation"
    / "orchestration"
    / "continuation"
    / "Convert-AiOsContinuationPlanToProposedPacket.DRY_RUN.ps1"
)


def _run_bridge(*, repo_root: Path, continuation_plan_path: Path | None = None) -> dict:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        "-OutputJson",
    ]
    if continuation_plan_path is not None:
        cmd.extend(["-ContinuationPlanPath", str(continuation_plan_path)])
    cmd.extend(["-RepoRoot", str(repo_root)])

    raw = subprocess.check_output(cmd, text=True)
    return json.loads(raw.strip())


def _write_plan(tmp_dir: Path, status: str = "READY_FOR_APPROVAL", packet_id: str = "AIOS-FOREX-PAPER-LEARNING-ACTION-ROUTER-APPLY-V1") -> Path:
    plan = {
        "schema": "AIOS_SUPERVISED_CONTINUATION_PLAN.v1",
        "mode": "DRY_RUN_READ_ONLY",
        "execution_allowed": False,
        "human_approval_required": True,
        "can_continue_without_anthony": False,
        "continuation_status": status,
        "recommended_next_packet_id": packet_id,
        "recommended_next_packet_title": "feat(forex): add paper learning action router",
        "recommended_lane": "PAPER_LEARNING_ACTION_ROUTER",
        "recommended_files": [
            "automation/forex_engine/paper_learning_action_router.py",
            "automation/forex_engine/run_paper_learning_action_router_demo.py",
            "tests/forex_engine/test_paper_learning_action_router.py",
            "docs/AI_OS/trading/FOREX_ENGINE_V1_PAPER_LEARNING_ACTION_ROUTER.md",
        ],
        "required_validators": [
            "git diff --check",
            "python -m pytest tests/forex_engine -q -p no:cacheprovider",
        ],
        "blocked_actions": [
            "live trading",
            "broker/OANDA",
            "real orders",
            "real webhooks",
            "real market data",
            "API keys/secrets",
            "scheduler/daemon",
            "worker launch",
            "runtime mutation",
            "telemetry mutation",
            "dashboard mutation",
            "Cloudflare",
            "backup sync",
            "push/PR/merge automation",
        ],
    }
    path = tmp_dir / "Get-AiOsSupervisedContinuationPlan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def _init_fake_repo(path: Path, dirty: bool = False) -> None:
    subprocess.check_call(["git", "init"], cwd=str(path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "checkout", "-b", "main"], cwd=str(path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if dirty:
        (path / "dirty.txt").write_text("dirty", encoding="utf-8")


def test_ready_for_approval_continuation_plan_builds_blocking_false_preview(tmp_path: Path):
    repo = tmp_path / "workspace"
    repo.mkdir()
    _init_fake_repo(repo, dirty=False)

    plan = _write_plan(tmp_path / "plan")
    result = _run_bridge(repo_root=repo, continuation_plan_path=plan)

    assert result["schema"] == "AIOS_CONTINUATION_TO_PROPOSED_PACKET_PREVIEW.v1"
    assert result["mode"] == "DRY_RUN_READ_ONLY"
    assert result["source_continuation_status"] == "READY_FOR_APPROVAL"
    assert result["proposed_packet_status"] == "READY_FOR_APPROVAL"
    assert result["proposed_packet_id"] == "AIOS-FOREX-PAPER-LEARNING-ACTION-ROUTER-APPLY-V1"
    assert result["proposed_packet_path"] == "automation/orchestration/work_packets/proposed/AIOS-FOREX-PAPER-LEARNING-ACTION-ROUTER-APPLY-V1.md"
    assert result["proposed_packet_payload"]["packet_id"] == "AIOS-FOREX-PAPER-LEARNING-ACTION-ROUTER-APPLY-V1"
    assert result["proposed_packet_payload"]["title"] == "feat(forex): add paper learning action router"
    assert result["proposed_packet_payload"]["lane"] == "PAPER_LEARNING_ACTION_ROUTER"
    assert result["proposed_packet_payload"]["allowed_write_boundary"] == [
        "automation/forex_engine/paper_learning_action_router.py",
        "automation/forex_engine/run_paper_learning_action_router_demo.py",
        "tests/forex_engine/test_paper_learning_action_router.py",
        "docs/AI_OS/trading/FOREX_ENGINE_V1_PAPER_LEARNING_ACTION_ROUTER.md",
    ]
    assert result["proposed_packet_payload"]["allowed_write_boundary"] == result["proposed_packet_payload"]["recommended_files"]
    assert result["proposed_packet_payload"]["required_validators"] == [
        "git diff --check",
        "python -m pytest tests/forex_engine -q -p no:cacheprovider",
    ]
    assert result["execution_allowed"] is False
    assert result["human_approval_required"] is True
    assert result["can_continue_without_anthony"] is False
    assert result["writes_files"] is False
    assert result["mutates_runtime"] is False
    assert result["mutates_approval"] is False
    assert result["mutates_queue"] is False
    assert result["starts_worker"] is False
    assert result["packet_validation_status"] == "PASS"
    assert result["proposed_packet_id"] != "AIOS-FOREX-PAPER-STUDY-JOURNAL-APPLY-V1"
    assert result["proposed_packet_path"] != "automation/orchestration/work_packets/proposed/AIOS-FOREX-PAPER-STUDY-JOURNAL-APPLY-V1.md"


def test_unsafe_continuation_status_blocks_proposal(tmp_path: Path) -> None:
    repo = tmp_path / "workspace"
    repo.mkdir()
    _init_fake_repo(repo)

    plan = _write_plan(tmp_path / "plan", status="BLOCKED")
    result = _run_bridge(repo_root=repo, continuation_plan_path=plan)

    assert result["proposed_packet_status"] == "BLOCKED"
    assert result["proposed_packet_payload"] is None
    assert result["execution_allowed"] is False
    assert result["human_approval_required"] is True
    assert result["can_continue_without_anthony"] is False
    assert result["writes_files"] is False
    assert result["mutates_runtime"] is False
    assert result["mutates_approval"] is False
    assert result["mutates_queue"] is False
    assert result["starts_worker"] is False


def test_dirty_repo_blocks_recommendation(tmp_path: Path) -> None:
    repo = tmp_path / "dirty_workspace"
    repo.mkdir()
    _init_fake_repo(repo, dirty=True)

    plan = _write_plan(tmp_path / "plan")
    result = _run_bridge(repo_root=repo, continuation_plan_path=plan)

    assert result["proposed_packet_status"] == "BLOCKED"
    assert result["dirty_or_untracked_count"] >= 1
    assert result["proposed_packet_payload"] is None


def test_dry_run_does_not_create_proposed_packet_file(tmp_path: Path) -> None:
    repo = tmp_path / "workspace_write_check"
    repo.mkdir()
    _init_fake_repo(repo)

    expected_path = (
        repo
        / "automation"
        / "orchestration"
        / "work_packets"
        / "proposed"
        / "AIOS-FOREX-PAPER-LEARNING-ACTION-ROUTER-APPLY-V1.md"
    )
    if expected_path.exists():
        expected_path.unlink()

    plan = _write_plan(tmp_path / "plan")
    _run_bridge(repo_root=repo, continuation_plan_path=plan)

    assert not expected_path.exists()
