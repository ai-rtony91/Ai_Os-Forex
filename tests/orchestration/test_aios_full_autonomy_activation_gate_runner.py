from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/self_development/Test-AiOsFullAutonomyActivationGate.DRY_RUN.ps1"


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


def _run_runner(*args: str, repo_root: Path = REPO_ROOT, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    current_cwd = cwd or repo_root
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repo_root / "automation/orchestration/self_development/Test-AiOsFullAutonomyActivationGate.DRY_RUN.ps1"),
            *args,
        ],
        cwd=str(current_cwd),
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
        "$HumanOwnerApprovalEvidence",
        "$IdentitySpineStatus",
        "$ValidatorChainStatus",
        "$ApprovalSosStatus",
        "$GovernedSoakStatus",
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
        "LEVEL_5_FULL_AUTONOMY_REQUESTED",
        "-OperatingProfile",
        "FULL_AUTONOMY_SUPERVISED",
        repo_root=clean_repo_root,
    )
    raw = result.stdout.strip()
    parsed = json.loads(raw)

    assert raw.startswith("{")
    assert "AIOS Full Autonomy Activation Gate" not in raw
    assert parsed["schema"] == "AIOS_FULL_AUTONOMY_ACTIVATION_GATE_RESULT.v1"
    assert parsed["activation_decision"]["status"] == "FULL_AUTONOMY_REQUESTED_NOT_APPROVED"
    assert parsed["safety"]["status"] == "REVIEW_REQUIRED"


def test_runner_accepts_console_mode(clean_repo_root: Path) -> None:
    result = _run_runner(
        *_expected_branch_args(clean_repo_root),
        "-RequestedAutonomyLevel",
        "LEVEL_4_CONDITIONAL_FULL_AUTONOMY",
        "-OperatingProfile",
        "24H_SUPERVISED",
        repo_root=clean_repo_root,
    )
    out = result.stdout

    for section in (
        "CURRENT STATE",
        "ACTIVATION",
        "INPUT EVIDENCE",
        "PROTECTED ACTIONS",
        "MISSING REQUIREMENTS",
        "SAFETY",
        "NO-WRITE PROOF",
        "NEXT SAFE ACTION",
    ):
        assert section in out


def test_runner_identity_status_review_required(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), "-IdentitySpineStatus", "UNKNOWN", repo_root=clean_repo_root)
    parsed = json.loads(result.stdout)

    assert parsed["activation_decision"]["status"] == "REVIEW_REQUIRED"
    assert "identity_spine" in parsed["missing_requirements"]


def test_runner_sos_active_returns_blocked_without_retry(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), "-ApprovalSosStatus", "SOS_ACTIVE", repo_root=clean_repo_root, check=False)
    parsed = json.loads(result.stdout)

    assert result.returncode != 0
    assert parsed["activation_decision"]["status"] == "DENIED"
    assert parsed["safety"]["status"] == "BLOCKED"
    assert "SOS_ACTIVE" in parsed["stop_conditions"]


def test_runner_refuses_dirty_worktree_outside_exact_allowed_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=str(tmp_path), text=True, capture_output=True, check=False)
    if subprocess.run(["git", "branch", "--show-current"], cwd=str(tmp_path), text=True, capture_output=True).stdout.strip() != "main":
        subprocess.run(["git", "checkout", "-b", "main"], cwd=str(tmp_path), text=True, capture_output=True, check=False)

    (tmp_path / "AGENTS.md").write_text("authority\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("front door\n", encoding="utf-8")

    result = _run_runner("-RepoRoot", str(tmp_path), "-OutputJson", cwd=tmp_path, check=False)
    parsed = json.loads(result.stdout)

    assert result.returncode != 0
    assert parsed["safety"]["status"] == "BLOCKED"
    assert "DIRTY_WORKTREE" in parsed["stop_conditions"]
    assert parsed["repo_state"]["dirty_allowed_for_full_autonomy_activation_gate_validation"] is False


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
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), repo_root=clean_repo_root)
    after = {root: _file_set(REPO_ROOT, root) for root in protected_roots}
    parsed = json.loads(result.stdout)

    assert parsed["safety"]["writes_files"] is False
    assert parsed["no_write_proof"]["changed"] is False
    assert before == after


def test_runner_output_does_not_recommend_protected_or_runtime_commands(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), repo_root=clean_repo_root)
    parsed = json.loads(result.stdout)
    encoded = json.dumps(parsed).lower()

    for blocked in ("git add", "git commit", "git push", "gh pr", "git merge", "start-aios", "open-aiosworker"):
        assert blocked not in encoded
