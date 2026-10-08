from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/self_development/Start-AiOsApprovedAutonomyWorkerLaunch.APPLY.ps1"
RECOMMENDATION = REPO_ROOT / "automation/orchestration/recommendations/Get-AiOsActionRecommendation.DRY_RUN.ps1"


def _param_block() -> str:
    text = RUNNER.read_text(encoding="utf-8")
    match = re.search(r"param\((.*?)\)\s*Set-StrictMode", text, flags=re.DOTALL)
    assert match is not None
    return match.group(1)


def _current_branch(repo_root: Path = REPO_ROOT) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _run_runner(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            *args,
        ],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def test_runner_has_required_parameters() -> None:
    param_block = _param_block()

    for required in (
        "$RepoRoot",
        "$ExpectedBranch",
        "$OutputJson",
        "$Mode",
        "$HumanOwnerWorkerLaunchApproval",
        "$WorkerPosture",
        "$OperatingProfile",
        "$WorkerCount",
        "$MaxParallelWorkers",
        "$AllowedLanes",
        "$TimeboxMinutes",
        "$StopOnFirstFailure",
        "$IdentitySpineStatus",
        "$ValidatorChainStatus",
        "$ApprovalSosStatus",
        "$PreflightDecision",
        "$LaunchGuardDecision",
        "$ResearchPlan",
        "$OutputRoot",
        "$NowUtc",
        "$FailOnDirtyWorktree",
        "$TimeoutSeconds",
    ):
        assert required in param_block


def test_runner_has_no_forbidden_runtime_or_mutation_parameters() -> None:
    param_block = _param_block()

    for forbidden in (
        "$StartRuntime",
        "$LaunchWorker",
        "$Schedule",
        "$Commit",
        "$Push",
        "$Merge",
        "$Approve",
        "$EnableScheduler",
        "$StartDaemon",
        "$MutateQueue",
        "$MutateLocks",
        "$MutateApprovals",
        "$MutateRegistry",
        "$OutputPath",
    ):
        assert forbidden not in param_block


def test_runner_output_json_branch_is_json_only_surface() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "if ($OutputJson)" in text
    assert "$result | ConvertTo-Json -Depth 90" in text
    assert "Write-ConsoleReport -Result $result" in text


def test_runner_executes_from_repo_root_with_output_json_and_repo_imports(clean_repo_root: Path, tmp_path: Path) -> None:
    output_root = tmp_path / "ledger"
    result = _run_runner(
        "-Mode",
        "DRY_RUN",
        "-OutputJson",
        "-RepoRoot",
        str(clean_repo_root),
        "-ExpectedBranch",
        _current_branch(clean_repo_root),
        "-HumanOwnerWorkerLaunchApproval",
        "APPROVED_SAFE_LOCAL_SIMULATION_WORKERS_ONLY",
        "-WorkerPosture",
        "READ_ONLY_VALIDATOR_CREW",
        "-OperatingProfile",
        "24H_SUPERVISED",
        "-WorkerCount",
        "2",
        "-MaxParallelWorkers",
        "3",
        "-AllowedLanes",
        "validator,self_audit,forex_research",
        "-TimeboxMinutes",
        "30",
        "-IdentitySpineStatus",
        "PASS",
        "-ValidatorChainStatus",
        "PASS",
        "-ApprovalSosStatus",
        "PASS",
        "-PreflightDecision",
        "PREFLIGHT_PASS_WORKER_LAUNCH_ELIGIBLE_BUT_NOT_EXECUTED",
        "-LaunchGuardDecision",
        "LAUNCH_APPROVED_FOR_FUTURE_PACKET_NOT_EXECUTED",
        "-OutputRoot",
        str(output_root),
        cwd=clean_repo_root,
    )

    assert "ModuleNotFoundError" not in result.stderr
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["schema"] == "AIOS_APPROVED_AUTONOMY_WORKER_LAUNCH_RESULT.v1"
    assert parsed["launch_decision"] == "LAUNCH_APPLY_READY"
    assert parsed["run_ledger"]["written"] is False
    assert not output_root.exists()


def test_runner_console_summary_includes_launch_decision_and_next_safe_action() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "LAUNCH DECISION" in text
    assert "launch_decision:" in text
    assert "NEXT SAFE ACTION" in text


def test_runner_safety_text_never_starts_runtime_or_scheduler() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "starts_runtime" in text
    assert "launches_workers" in text
    assert "enables_scheduler" in text
    assert "starts_daemon" in text
    assert "PYTHONPATH" in text
    assert "Start-Process" not in text


def test_status_recommendation_surfaces_controller_availability_without_apply() -> None:
    text = RECOMMENDATION.read_text(encoding="utf-8")

    assert "FULL AUTONOMY WORKER LAUNCH" in text
    assert "approved_launch_controller" in text
    assert "forex_research_pipeline" in text
    assert "worker_launch_allowed_now = $false" in text
    assert "starts_apply = $false" in text
    assert "writes_ledger = $false" in text
    assert "launches_workers = $false" in text
