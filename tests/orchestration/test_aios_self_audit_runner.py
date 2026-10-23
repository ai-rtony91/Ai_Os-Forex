from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/self_audit/Invoke-AiOsSelfAuditLoop.DRY_RUN.ps1"


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


def test_runner_has_no_outputpath_or_write_parameters() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    match = re.search(r"param\((.*?)\)\s*Set-StrictMode", text, flags=re.DOTALL)

    assert match is not None
    param_block = match.group(1)
    for forbidden in ("OutputPath", "$Mode", "$Apply", "$Write", "$Persist"):
        assert forbidden not in param_block


def test_runner_defaults_expected_branch_to_main() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert '[string]$ExpectedBranch = "main"' in text
    assert "feature/governed-self-development-closure-v1" not in text


def test_runner_emits_json_only_with_output_json(clean_repo_root: Path) -> None:
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), cwd=clean_repo_root)
    raw = result.stdout.strip()
    parsed = json.loads(raw)

    assert raw.startswith("{")
    assert "AIOS Self-Audit Loop" not in raw
    assert parsed["schema"] == "AIOS_SELF_AUDIT_LOOP_RESULT.v1"
    assert parsed["recommended_next_packet"]["packet_id"] == "AIOS-SELF-DEVELOPMENT-PACKET-ROUTER-DRYRUN-V1"


def test_runner_accepts_explicit_current_expected_branch(clean_repo_root: Path) -> None:
    branch = _current_branch(clean_repo_root)
    result = _run_runner("-OutputJson", "-ExpectedBranch", branch, cwd=clean_repo_root)
    parsed = json.loads(result.stdout)

    assert parsed["repo_state"]["expected_branch"] == branch
    assert parsed["repo_state"]["branch_matches_expected"] is True


def test_runner_console_mode_includes_expected_sections(clean_repo_root: Path) -> None:
    result = _run_runner(*_expected_branch_args(clean_repo_root), cwd=clean_repo_root)
    out = result.stdout

    for section in (
        "CURRENT STATE",
        "AUTHORITY CONTEXT",
        "COMPLETE IDLE STATE",
        "SAFE SURFACES USED",
        "GAP CLASSIFICATIONS",
        "CANDIDATE PACKETS",
        "RECOMMENDED NEXT PACKET",
        "NO-WRITE PROOF",
        "STOP CONDITIONS",
        "NEXT SAFE ACTION",
    ):
        assert section in out


def test_runner_refuses_dirty_worktree_when_fail_on_dirty_is_true(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=str(tmp_path), text=True, capture_output=True, check=False)
    if subprocess.run(["git", "branch", "--show-current"], cwd=str(tmp_path), text=True, capture_output=True).stdout.strip() != "main":
        subprocess.run(["git", "checkout", "-b", "main"], cwd=str(tmp_path), text=True, capture_output=True, check=False)

    (tmp_path / "AGENTS.md").write_text("authority\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("front door\n", encoding="utf-8")
    (tmp_path / "RISK_POLICY.md").write_text("risk\n", encoding="utf-8")
    contract = tmp_path / "docs/AI_OS/autonomy/AIOS_SELF_AUDIT_LOOP_CONTRACT_V1.md"
    contract.parent.mkdir(parents=True)
    contract.write_text("contract\n", encoding="utf-8")

    result = _run_runner("-RepoRoot", str(tmp_path), "-OutputJson", cwd=tmp_path, check=False)
    parsed = json.loads(result.stdout)

    assert result.returncode != 0
    assert parsed["safety"]["status"] == "BLOCKED"
    assert "DIRTY_WORKTREE" in parsed["stop_conditions"]


def test_runner_no_write_proof_does_not_create_forbidden_files(clean_repo_root: Path) -> None:
    protected_roots = [
        "Reports",
        "telemetry",
        "automation/orchestration/work_packets",
        "control/relay_bus/messages",
        "automation/orchestration/queue",
        "automation/orchestration/command_queue",
        "automation/orchestration/locks",
        "automation/orchestration/approval_inbox",
        "automation/orchestration/runtime",
    ]
    before = {root: _file_set(REPO_ROOT, root) for root in protected_roots}
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), cwd=clean_repo_root)
    after = {root: _file_set(REPO_ROOT, root) for root in protected_roots}
    parsed = json.loads(result.stdout)

    assert parsed["safety"]["writes_files"] is False
    assert parsed["safety"]["no_write_proof"]["changed"] is False
    assert before == after


def test_runner_does_not_call_excluded_write_capable_scripts() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    safe_block = text.split("$safeSurfaces = ", 1)[1].split("$blockedSurfaces = ", 1)[0]
    excluded = [
        "automation/self_build/aios_self_build_cycle.py",
        "automation/self_build/aios_self_build_inspector.py",
        "automation/orchestration/autonomy_control_plane/Invoke-AiOsAutonomyControlPlane.DRY_RUN.ps1",
        "automation/orchestration/autonomy_router/Get-AiOsAutonomyNextAction.DRY_RUN.ps1",
        "automation/orchestration/autonomy_loop/Invoke-AiOsAutonomyLoop.DRY_RUN.ps1",
        "automation/orchestration/autonomy_discovery/Get-AiOsAutonomyInventory.DRY_RUN.ps1",
        "automation/orchestration/review_bridge/New-AiOsCodexReportRelayItem.DRY_RUN.ps1",
        "automation/orchestration/reports/New-AiOsMorningBrief.ps1",
        "automation/telemetry/Update-AiOsProductionReadout.ps1",
        "automation/reporting/New-AiOsReport.ps1",
        "automation/orchestration/commit_packages/Invoke-AiOsExactCommitPackage.ps1",
        "automation/orchestration/relay_bus/New-AiOsRelayMessage.DRY_RUN.ps1",
    ]

    for script in excluded:
        assert script not in safe_block
