from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/operator_control/Test-AiOsApprovalSosHardGate.DRY_RUN.ps1"
GOVERNED_RUNNER = REPO_ROOT / "automation/orchestration/self_development/Invoke-AiOsGovernedSelfDevelopmentLoop.DRY_RUN.ps1"
DAY_NIGHT_RUNNER = REPO_ROOT / "automation/orchestration/supervisor/Get-AiOsDayNightReadiness.DRY_RUN.ps1"
VALIDATOR_ROUTER_RUNNER = REPO_ROOT / "automation/orchestration/validators/Get-AiOsValidatorEvidenceRouter.DRY_RUN.ps1"
PACKET_ROUTER_RUNNER = REPO_ROOT / "automation/orchestration/self_audit/Get-AiOsSelfDevelopmentPacketRouter.DRY_RUN.ps1"
SELF_AUDIT_RUNNER = REPO_ROOT / "automation/orchestration/self_audit/Invoke-AiOsSelfAuditLoop.DRY_RUN.ps1"


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


def _run_runner(*args: str, repo_root: Path = REPO_ROOT, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    current_cwd = cwd or repo_root
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repo_root / "automation/orchestration/operator_control/Test-AiOsApprovalSosHardGate.DRY_RUN.ps1"),
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
    ):
        assert forbidden not in param_block


def test_runner_defaults_expected_branch_to_main() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert '[string]$ExpectedBranch = "main"' in text


def test_runner_emits_json_only_with_output_json(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), repo_root=clean_repo_root)
    raw = result.stdout.strip()
    parsed = json.loads(raw)

    assert raw.startswith("{")
    assert "AIOS Approval SOS Hard Gate" not in raw
    assert parsed["schema"] == "AIOS_APPROVAL_SOS_HARD_GATE_RESULT.v1"
    assert parsed["safety"]["status"] == "PASS"


def test_runner_accepts_explicit_current_expected_branch(clean_repo_root: Path) -> None:
    branch = _current_branch(clean_repo_root)
    result = _run_runner("-OutputJson", "-ExpectedBranch", branch, repo_root=clean_repo_root)
    parsed = json.loads(result.stdout)

    assert parsed["repo_state"]["expected_branch"] == branch
    assert parsed["repo_state"]["branch_matches_expected"] is True
    assert parsed["safety"]["status"] == "PASS"


def test_runner_console_mode_includes_expected_sections(clean_repo_root: Path) -> None:
    result = _run_runner(*_expected_branch_args(clean_repo_root), repo_root=clean_repo_root)
    out = result.stdout

    for section in (
        "CURRENT STATE",
        "APPROVAL STATE",
        "SOS STATE",
        "PROTECTED ACTIONS",
        "ALLOWED READ ONLY ACTIONS",
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
    assert parsed["repo_state"]["dirty_allowed_for_approval_sos_hard_gate_validation"] is False


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
        "control",
        "secrets",
    ]
    before = {root: _file_set(REPO_ROOT, root) for root in protected_roots}
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), repo_root=clean_repo_root)
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


def test_runner_blocks_required_protected_actions_without_commands(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), repo_root=clean_repo_root)
    parsed = json.loads(result.stdout)
    blocked = {item["action_id"] for item in parsed["blocked_actions"]}

    for action_id in ("apply", "commit", "push", "pr", "merge", "runtime_start", "worker_launch"):
        assert action_id in blocked
    assert parsed["safety"]["protected_action_recommended"] is False
    assert "git " not in parsed["next_safe_action"].lower()


def test_upstream_runners_allow_exact_hard_gate_files_without_broad_directory() -> None:
    expected = (
        "automation/orchestration/operator_control/Test-AiOsApprovalSosHardGate.DRY_RUN.ps1",
        "automation/orchestration/operator_control/aios_approval_sos_hard_gate.py",
        "schemas/aios/orchestration/AIOS_APPROVAL_SOS_HARD_GATE_RESULT.v1.schema.json",
        "tests/orchestration/test_aios_approval_sos_hard_gate.py",
        "tests/orchestration/test_aios_approval_sos_hard_gate_runner.py",
    )
    for runner, function_name in (
        (GOVERNED_RUNNER, "Test-GovernedLoopValidationDirtyState"),
        (DAY_NIGHT_RUNNER, "Test-DayNightReadinessDirtyState"),
        (VALIDATOR_ROUTER_RUNNER, "Test-ValidatorEvidenceRouterDirtyState"),
        (PACKET_ROUTER_RUNNER, "Test-RouterValidationDirtyState"),
        (SELF_AUDIT_RUNNER, "Test-SelfAuditValidationDirtyState"),
    ):
        text = runner.read_text(encoding="utf-8")
        match = re.search(
            rf"function {function_name} \{{(.*?)function ConvertTo-StableJson",
            text,
            flags=re.DOTALL,
        )
        assert match is not None
        block = match.group(1)
        for path in expected:
            assert path in block
        assert ".StartsWith(" not in block
