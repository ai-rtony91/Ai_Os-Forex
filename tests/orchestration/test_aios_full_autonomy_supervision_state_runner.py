from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/self_development/Get-AiOsFullAutonomySupervisionState.DRY_RUN.ps1"


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
    branch = _current_branch(repo_root)
    if branch == "main":
        return ()
    return ("-ExpectedBranch", branch)


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


def test_runner_has_no_forbidden_parameters() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    match = re.search(r"param\((.*?)\)\s*Set-StrictMode", text, flags=re.DOTALL)

    assert match is not None
    param_block = match.group(1)
    for forbidden in (
        "OutputPath",
        "$Mode",
        "$Apply",
        "$Write",
        "$Persist",
        "StartRuntime",
        "LaunchWorker",
        "Schedule",
        "$Commit",
        "$Push",
        "$Merge",
        "$Approve",
        "EnableScheduler",
        "StartDaemon",
        "MutateQueue",
        "MutateLocks",
        "MutateApprovals",
        "MutateRegistry",
    ):
        assert forbidden not in param_block


def test_runner_defaults_expected_branch_autonomy_level_and_profile() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert '[string]$ExpectedBranch = "main"' in text
    assert '[string]$RequestedAutonomyLevel = "LEVEL_3_SUPERVISED_AUTONOMY"' in text
    assert '[string]$OperatingProfile = "12H_SUPERVISED"' in text


def test_runner_emits_json_only_with_output_json(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), "-RequestedAutonomyLevel", "LEVEL_5_FULL_AUTONOMY_REQUESTED", "-OperatingProfile", "FULL_AUTONOMY_SUPERVISED", cwd=clean_repo_root)
    raw = result.stdout.strip()
    parsed = json.loads(raw)

    assert raw.startswith("{")
    assert "AIOS Full Autonomy Supervision State" not in raw
    assert parsed["schema"] == "AIOS_FULL_AUTONOMY_SUPERVISION_STATE_RESULT.v1"
    assert parsed["resolved_autonomy_level"] == "FULL_AUTONOMY_REQUESTED_BUT_NOT_APPROVED"
    assert parsed["safety"]["status"] in {"PASS", "REVIEW_REQUIRED"}


def test_runner_accepts_explicit_current_expected_branch(clean_repo_root: Path) -> None:
    branch = _current_branch(clean_repo_root)
    result = _run_runner("-OutputJson", "-ExpectedBranch", branch, "-RecentValidatorStatus", "PASS", cwd=clean_repo_root)
    parsed = json.loads(result.stdout)

    assert parsed["repo_state"]["expected_branch"] == branch
    assert parsed["repo_state"]["branch_matches_expected"] is True
    assert parsed["safety"]["status"] in {"PASS", "REVIEW_REQUIRED"}


def test_runner_console_mode_includes_expected_sections(clean_repo_root: Path) -> None:
    result = _run_runner(*_expected_branch_args(clean_repo_root), "-RequestedAutonomyLevel", "LEVEL_4_CONDITIONAL_FULL_AUTONOMY", "-OperatingProfile", "24H_SUPERVISED", cwd=clean_repo_root)
    out = result.stdout

    for section in (
        "CURRENT STATE",
        "AUTONOMY LEVEL",
        "OPERATING PROFILE",
        "WORKER SUPERVISION",
        "WAKE POLICY",
        "SAFETY",
        "NO-WRITE PROOF",
        "STOP CONDITIONS",
        "NEXT SAFE ACTION",
    ):
        assert section in out


def test_runner_refuses_dirty_worktree_outside_exact_allowed_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=str(tmp_path), text=True, capture_output=True, check=False)
    if subprocess.run(["git", "branch", "--show-current"], cwd=str(tmp_path), text=True, capture_output=True).stdout.strip() != "main":
        subprocess.run(["git", "checkout", "-b", "main"], cwd=str(tmp_path), text=True, capture_output=True, check=False)

    (tmp_path / "AGENTS.md").write_text("authority\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("front door\n", encoding="utf-8")
    (tmp_path / "RISK_POLICY.md").write_text("risk\n", encoding="utf-8")
    contract = tmp_path / "docs/AI_OS/autonomy/AIOS_SELF_AUDIT_LOOP_CONTRACT_V1.md"
    contract.parent.mkdir(parents=True)
    contract.write_text("contract\n", encoding="utf-8")
    governance = tmp_path / "docs/governance"
    governance.mkdir(parents=True)
    (governance / "aios-identity-and-lane-governance.md").write_text("identity\n", encoding="utf-8")
    (governance / "AI_OS_REPO_MEMORY.md").write_text("memory\n", encoding="utf-8")

    result = _run_runner("-RepoRoot", str(tmp_path), "-OutputJson", cwd=tmp_path, check=False)
    parsed = json.loads(result.stdout)

    assert result.returncode != 0
    assert parsed["safety"]["status"] == "BLOCKED"
    assert "DIRTY_WORKTREE" in parsed["stop_conditions"]
    assert parsed["repo_state"]["dirty_allowed_for_full_autonomy_supervision_state_validation"] is False


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
    assert parsed["no_write_proof"]["changed"] is False
    assert before == after


def test_runner_no_write_proof_contains_forbidden_delta_detection() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "forbidden_surface_changed" in text
    assert "Compare-NoWriteState" in text
    assert "automation/orchestration/work_packets" in text
    assert "automation/orchestration/runtime" in text
    assert "automation/orchestration/approval_inbox" in text


def test_runner_blocks_runtime_worker_scheduler_daemon_and_mutation_flags(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), "-RecentValidatorStatus", "PASS", cwd=clean_repo_root)
    parsed = json.loads(result.stdout)
    blocked = {item["action_id"] for item in parsed["protected_actions"]}

    for action_id in ("runtime_start", "worker_launch", "scheduler_enablement", "daemon_launch", "queue_mutation", "lock_mutation", "approval_mutation", "registry_mutation"):
        assert action_id in blocked
    assert parsed["safety"]["starts_runtime"] is False
    assert parsed["safety"]["launches_workers"] is False
    assert parsed["safety"]["enables_scheduler"] is False
    assert parsed["safety"]["starts_daemon"] is False


def test_runner_output_does_not_recommend_protected_or_runtime_commands(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), cwd=clean_repo_root)
    parsed = json.loads(result.stdout)
    encoded = json.dumps(parsed).lower()

    for blocked in ("git add", "git commit", "git push", "gh pr", "git merge", "start-aios", "open-aiosworker"):
        assert blocked not in encoded


def test_runner_expected_approval_and_commit_warns_are_review_required_not_fail(clean_repo_root: Path) -> None:
    approval = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), "-RecentValidatorStatus", "APPROVAL_GATE_WARN", cwd=clean_repo_root)
    commit = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), "-RecentValidatorStatus", "COMMIT_PACKAGE_WARN", cwd=clean_repo_root)

    for raw in (approval.stdout, commit.stdout):
        parsed = json.loads(raw)
        assert parsed["safety"]["status"] == "REVIEW_REQUIRED"
        assert parsed["safety"]["status"] != "FAIL"


def test_runner_sos_hard_stop_returns_blocked_without_retry(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), "-RecentSosStatus", "SOS_HARD_STOP", cwd=clean_repo_root, check=False)
    parsed = json.loads(result.stdout)

    assert result.returncode != 0
    assert parsed["safety"]["status"] == "BLOCKED"
    assert "SOS_HARD_STOP" in parsed["stop_conditions"]
