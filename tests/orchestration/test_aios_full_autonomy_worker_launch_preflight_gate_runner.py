from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/self_development/Test-AiOsFullAutonomyWorkerLaunchPreflightGate.DRY_RUN.ps1"


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
        "$RequestedAutonomyLevel",
        "$OperatingProfile",
        "$RequestedWorkerPosture",
        "$HumanOwnerWorkerLaunchApproval",
        "$IdentitySpineStatus",
        "$ValidatorChainStatus",
        "$ApprovalSosStatus",
        "$GovernedSoakStatus",
        "$ActivationGateStatus",
        "$WorkerPostureBridgeStatus",
        "$LockCollisionStatus",
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
        "-RequestedAutonomyLevel",
        "LEVEL_4_CONDITIONAL_FULL_AUTONOMY",
        "-OperatingProfile",
        "24H_SUPERVISED",
        "-RequestedWorkerPosture",
        "READ_ONLY_VALIDATOR_CREW",
        "-IdentitySpineStatus",
        "PASS",
        "-ValidatorChainStatus",
        "PASS",
        "-ApprovalSosStatus",
        "PASS",
        "-GovernedSoakStatus",
        "PASS",
        "-ActivationGateStatus",
        "PASS",
        "-WorkerPostureBridgeStatus",
        "PASS",
        "-LockCollisionStatus",
        "CLEAR",
        "-AllowedLanes",
        "validator,self_audit,readiness_review",
        cwd=clean_repo_root,
    )
    raw = result.stdout.strip()
    parsed = json.loads(raw)

    assert raw.startswith("{")
    assert "AIOS Full Autonomy Worker Launch Preflight Gate" not in raw
    assert parsed["schema"] == "AIOS_FULL_AUTONOMY_WORKER_LAUNCH_PREFLIGHT_GATE_RESULT.v1"
    assert parsed["preflight_decision"]["decision"] == "PREFLIGHT_PASS_AWAITING_HUMAN_APPROVAL"
    assert parsed["worker_launch_executed"] is False


def test_runner_console_output_includes_preflight_decision_and_next_safe_action(clean_repo_root: Path) -> None:
    result = _run_runner(
        *_expected_branch_args(clean_repo_root),
        "-RequestedAutonomyLevel",
        "LEVEL_4_CONDITIONAL_FULL_AUTONOMY",
        "-OperatingProfile",
        "24H_SUPERVISED",
        "-RequestedWorkerPosture",
        "READ_ONLY_VALIDATOR_CREW",
        "-AllowedLanes",
        "validator,self_audit,readiness_review",
        cwd=clean_repo_root,
    )
    out = result.stdout

    for section in (
        "CURRENT STATE",
        "PREFLIGHT DECISION",
        "WORKER POSTURE",
        "MISSING REQUIREMENTS",
        "NEXT SAFE ACTION",
    ):
        assert section in out
    assert "decision:" in out
    assert "worker_posture:" in out


def test_runner_pass_with_approval_is_eligible_but_not_executed(clean_repo_root: Path) -> None:
    result = _run_runner(
        "-OutputJson",
        *_expected_branch_args(clean_repo_root),
        "-HumanOwnerWorkerLaunchApproval",
        "APPROVED_FOR_WORKER_LAUNCH_PREFLIGHT",
        "-AllowedLanes",
        "validator,self_audit,readiness_review",
        cwd=clean_repo_root,
    )
    parsed = json.loads(result.stdout)

    assert parsed["preflight_decision"]["decision"] == "PREFLIGHT_PASS_WORKER_LAUNCH_ELIGIBLE_BUT_NOT_EXECUTED"
    assert parsed["worker_launch_allowed_for_future_step"] is True
    assert parsed["worker_launch_executed"] is False
    assert parsed["safety"]["launches_workers"] is False


def test_runner_sos_active_blocks_launch_without_retry(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), "-ApprovalSosStatus", "SOS_ACTIVE", cwd=clean_repo_root, check=False)
    parsed = json.loads(result.stdout)

    assert result.returncode != 0
    assert parsed["preflight_decision"]["decision"] == "BLOCKED_BY_SOS"
    assert parsed["safety"]["status"] == "BLOCKED"
    assert parsed["human_wake_policy"]["wake_required"] is True


def test_runner_empty_allowed_lanes_blocks_launch(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), "-AllowedLanes", "", cwd=clean_repo_root, check=False)
    parsed = json.loads(result.stdout)

    assert result.returncode != 0
    assert parsed["preflight_decision"]["decision"] == "BLOCKED_BY_EMPTY_ALLOWED_LANES"
    assert parsed["worker_launch_allowed_for_future_step"] is False


def test_runner_refuses_dirty_worktree_outside_exact_allowed_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=str(tmp_path), text=True, capture_output=True, check=False)
    if subprocess.run(["git", "branch", "--show-current"], cwd=str(tmp_path), text=True, capture_output=True).stdout.strip() != "main":
        subprocess.run(["git", "checkout", "-b", "main"], cwd=str(tmp_path), text=True, capture_output=True, check=False)

    (tmp_path / "AGENTS.md").write_text("authority\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("front door\n", encoding="utf-8")

    result = _run_runner("-RepoRoot", str(tmp_path), "-OutputJson", cwd=tmp_path, check=False)
    parsed = json.loads(result.stdout)

    assert result.returncode != 0
    assert parsed["preflight_decision"]["decision"] == "BLOCKED_BY_REPO_STATE"
    assert parsed["safety"]["status"] == "BLOCKED"
    assert "DIRTY_WORKTREE" in parsed["stop_conditions"]
    assert parsed["repo_state"]["dirty_allowed_for_full_autonomy_worker_launch_preflight_gate_validation"] is False


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


def test_runner_output_does_not_recommend_protected_or_runtime_commands(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), cwd=clean_repo_root)
    parsed = json.loads(result.stdout)
    encoded = json.dumps(parsed).lower()

    for blocked in ("git add", "git commit", "git push", "gh pr", "git merge", "start-aios", "open-aiosworker"):
        assert blocked not in encoded
