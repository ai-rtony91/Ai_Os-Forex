from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/self_development/Test-AiOsFullAutonomyWorkerLaunchGuard.DRY_RUN.ps1"


def _current_branch(repo_root: Path = REPO_ROOT) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _expected_branch_args(repo_root: Path = REPO_ROOT) -> tuple[str, ...]:
    return ("-ExpectedBranch", _current_branch(repo_root))


def _run_runner(*args: str, cwd: Path = REPO_ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            *args,
        ],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"runner failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def _file_set(root: Path, relative: str) -> set[str]:
    target = root / relative
    if not target.exists():
        return set()
    return {
        str(path.relative_to(root)).replace("\\", "/")
        for path in target.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }


def test_runner_has_required_parameters_and_no_forbidden_parameters() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    match = re.search(r"param\((.*?)\)\s*Set-StrictMode", text, flags=re.DOTALL)

    assert match is not None
    param_block = match.group(1)
    for required in (
        "$RepoRoot",
        "$ExpectedBranch",
        "$OutputJson",
        "$CommandDecision",
        "$HumanOwnerWorkerLaunchApproval",
        "$IdentitySpineStatus",
        "$ValidatorChainStatus",
        "$ApprovalSosStatus",
        "$PreflightDecision",
        "$AllowedLanes",
        "$RequestedWorkerCount",
        "$MaxParallelWorkers",
        "$NowUtc",
        "$FailOnDirtyWorktree",
        "$TimeoutSeconds",
    ):
        assert required in param_block
    for forbidden in (
        "$OutputPath",
        "$Mode",
        "$Apply",
        "$Write",
        "$Persist",
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
    ):
        assert forbidden not in param_block


def test_runner_emits_json_only_with_output_json(clean_repo_root: Path) -> None:
    result = _run_runner(
        "-OutputJson",
        *_expected_branch_args(clean_repo_root),
        "-CommandDecision",
        "COMMAND_PREVIEW_READY_AWAITING_APPROVAL",
        "-IdentitySpineStatus",
        "PASS",
        "-ValidatorChainStatus",
        "PASS",
        "-ApprovalSosStatus",
        "PASS",
        "-PreflightDecision",
        "PREFLIGHT_PASS_AWAITING_HUMAN_APPROVAL",
        "-AllowedLanes",
        "validator,self_audit,readiness_review",
        "-RequestedWorkerCount",
        "2",
        "-MaxParallelWorkers",
        "3",
        cwd=clean_repo_root,
    )
    raw = result.stdout.strip()
    parsed = json.loads(raw)

    assert raw.startswith("{")
    assert "AIOS Full Autonomy Worker Launch Guard" not in raw
    assert parsed["schema"] == "AIOS_FULL_AUTONOMY_WORKER_LAUNCH_GUARD_RESULT.v1"
    assert parsed["guard_decision"] == "LAUNCH_AWAITING_HUMAN_APPROVAL"
    assert parsed["launch_executed"] is False


def test_runner_console_summarizes_decision(clean_repo_root: Path) -> None:
    result = _run_runner(*_expected_branch_args(clean_repo_root), "-AllowedLanes", "validator,self_audit,readiness_review", cwd=clean_repo_root)
    out = result.stdout

    for section in (
        "CURRENT STATE",
        "GUARD DECISION",
        "LANES AND WORKERS",
        "SAFETY",
        "NEXT SAFE ACTION",
    ):
        assert section in out
    assert "guard_decision:" in out
    assert "launch_executed:" in out


def test_runner_with_approval_approves_future_packet_but_not_execution(clean_repo_root: Path) -> None:
    result = _run_runner(
        "-OutputJson",
        *_expected_branch_args(clean_repo_root),
        "-CommandDecision",
        "COMMAND_PREVIEW_READY_APPROVED_BUT_NOT_EXECUTED",
        "-HumanOwnerWorkerLaunchApproval",
        "APPROVED_FOR_WORKER_LAUNCH",
        "-PreflightDecision",
        "PREFLIGHT_PASS_WORKER_LAUNCH_ELIGIBLE_BUT_NOT_EXECUTED",
        "-AllowedLanes",
        "validator,self_audit,readiness_review",
        "-RequestedWorkerCount",
        "2",
        "-MaxParallelWorkers",
        "3",
        cwd=clean_repo_root,
    )
    parsed = json.loads(result.stdout)

    assert parsed["guard_decision"] == "LAUNCH_APPROVED_FOR_FUTURE_PACKET_NOT_EXECUTED"
    assert parsed["launch_allowed_for_future_packet"] is True
    assert parsed["launch_executed"] is False
    assert parsed["safety"]["launches_workers"] is False


def test_runner_blocks_protected_lanes(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), "-AllowedLanes", "validator,runtime_execution", cwd=clean_repo_root, check=False)
    parsed = json.loads(result.stdout)

    assert result.returncode != 0
    assert parsed["guard_decision"] == "BLOCKED_BY_LANES"
    assert "remove_protected_lane:runtime_execution" in parsed["missing_requirements"]


def test_runner_refuses_dirty_worktree_outside_exact_allowed_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=str(tmp_path), text=True, capture_output=True, check=False)
    if subprocess.run(["git", "branch", "--show-current"], cwd=str(tmp_path), text=True, capture_output=True).stdout.strip() != "main":
        subprocess.run(["git", "checkout", "-b", "main"], cwd=str(tmp_path), text=True, capture_output=True, check=False)

    (tmp_path / "AGENTS.md").write_text("authority\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("front door\n", encoding="utf-8")

    result = _run_runner("-RepoRoot", str(tmp_path), "-OutputJson", cwd=tmp_path, check=False)
    parsed = json.loads(result.stdout)

    assert result.returncode != 0
    assert parsed["guard_decision"] == "BLOCKED_BY_REPO_STATE"
    assert parsed["safety"]["status"] == "BLOCKED"
    assert "DIRTY_WORKTREE" in parsed["stop_conditions"]
    assert parsed["repo_state"]["dirty_allowed_for_full_autonomy_worker_launch_guard_validation"] is False


def test_runner_no_write_proof_does_not_create_forbidden_files(clean_repo_root: Path) -> None:
    protected_roots = [
        "Reports",
        "telemetry",
        "automation/orchestration/work_packets",
        "automation/orchestration/packet_generator",
        "automation/orchestration/queue",
        "automation/orchestration/command_queue",
        "automation/orchestration/locks",
        "automation/orchestration/approval_inbox",
        "automation/orchestration/runtime",
        "automation/orchestration/workers/inbox",
        "automation/orchestration/relay_bus",
        "control/relay_bus/messages",
        "control/review_bridge/codex_reports",
    ]
    before = {root: _file_set(REPO_ROOT, root) for root in protected_roots}
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), cwd=clean_repo_root)
    after = {root: _file_set(REPO_ROOT, root) for root in protected_roots}
    parsed = json.loads(result.stdout)

    assert parsed["safety"]["writes_files"] is False
    assert parsed["safety"]["launches_workers"] is False
    assert parsed["safety"]["starts_runtime"] is False
    assert parsed["safety"]["enables_scheduler"] is False
    assert parsed["safety"]["starts_daemon"] is False
    assert parsed["safety"]["mutates_queue"] is False
    assert parsed["safety"]["mutates_locks"] is False
    assert parsed["safety"]["mutates_approval"] is False
    assert parsed["safety"]["mutates_registry"] is False
    assert parsed["safety"]["writes_reports"] is False
    assert parsed["safety"]["writes_telemetry"] is False
    assert parsed["safety"]["writes_relay"] is False
    assert parsed["safety"]["touches_secrets_or_env"] is False
    assert parsed["safety"]["broker_or_live_trading"] is False
    assert parsed["no_write_proof"]["changed"] is False
    assert before == after
