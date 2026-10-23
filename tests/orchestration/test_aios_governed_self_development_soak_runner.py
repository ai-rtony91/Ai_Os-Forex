from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/self_development/Test-AiOsGovernedSelfDevelopmentSoak.DRY_RUN.ps1"
HARD_GATE_RUNNER = REPO_ROOT / "automation/orchestration/operator_control/Test-AiOsApprovalSosHardGate.DRY_RUN.ps1"
GOVERNED_RUNNER = REPO_ROOT / "automation/orchestration/self_development/Invoke-AiOsGovernedSelfDevelopmentLoop.DRY_RUN.ps1"
DAY_NIGHT_RUNNER = REPO_ROOT / "automation/orchestration/supervisor/Get-AiOsDayNightReadiness.DRY_RUN.ps1"
VALIDATOR_ROUTER_RUNNER = REPO_ROOT / "automation/orchestration/validators/Get-AiOsValidatorEvidenceRouter.DRY_RUN.ps1"
PACKET_ROUTER_RUNNER = REPO_ROOT / "automation/orchestration/self_audit/Get-AiOsSelfDevelopmentPacketRouter.DRY_RUN.ps1"
SELF_AUDIT_RUNNER = REPO_ROOT / "automation/orchestration/self_audit/Invoke-AiOsSelfAuditLoop.DRY_RUN.ps1"
_RUNNER_JSON: dict[str, subprocess.CompletedProcess[str]] = {}
_RUNNER_CONSOLE: dict[str, subprocess.CompletedProcess[str]] = {}


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


def _json_arg(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"))


def _governed_loop_evidence() -> dict:
    return {
        "schema": "AIOS_GOVERNED_SELF_DEVELOPMENT_LOOP_RESULT.v1",
        "safety": {
            "status": "PASS",
            "writes_files": False,
            "writes_reports": False,
            "writes_telemetry": False,
            "writes_packet_drafts": False,
            "writes_proposed_packets": False,
            "outputs_packet_body": False,
            "creates_ready_stage": False,
            "mutates_registry": False,
            "mutates_queue": False,
            "mutates_locks": False,
            "mutates_approvals": False,
            "writes_relay": False,
            "starts_runtime": False,
            "launches_workers": False,
            "scheduler_or_daemon": False,
            "protected_action_recommended": False,
            "secrets_or_env_access": False,
            "broker_or_live_trading": False,
        },
        "stop_conditions": [],
    }


def _hard_gate_evidence() -> dict:
    return {
        "schema": "AIOS_APPROVAL_SOS_HARD_GATE_RESULT.v1",
        "safety": {
            "status": "PASS",
            "writes_files": False,
            "writes_reports": False,
            "writes_telemetry": False,
            "writes_packet_drafts": False,
            "writes_proposed_packets": False,
            "outputs_packet_body": False,
            "creates_ready_stage": False,
            "mutates_registry": False,
            "mutates_queue": False,
            "mutates_locks": False,
            "mutates_approvals": False,
            "writes_relay": False,
            "starts_runtime": False,
            "launches_workers": False,
            "scheduler_or_daemon": False,
            "protected_action_recommended": False,
            "secrets_or_env_access": False,
            "broker_or_live_trading": False,
        },
        "stop_conditions": [],
    }


def _runner_evidence_args() -> tuple[str, ...]:
    return (
        "-GovernedLoopJson",
        _json_arg(_governed_loop_evidence()),
        "-ApprovalSosHardGateJson",
        _json_arg(_hard_gate_evidence()),
    )


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


def _runner_json(repo_root: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    key = str(repo_root)
    if key not in _RUNNER_JSON:
        _RUNNER_JSON[key] = _run_runner("-OutputJson", *_expected_branch_args(repo_root), *_runner_evidence_args(), cwd=repo_root)
    return _RUNNER_JSON[key]


def _runner_console(repo_root: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    key = str(repo_root)
    if key not in _RUNNER_CONSOLE:
        _RUNNER_CONSOLE[key] = _run_runner(*_expected_branch_args(repo_root), *_runner_evidence_args(), cwd=repo_root)
    return _RUNNER_CONSOLE[key]


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
    ):
        assert forbidden not in param_block


def test_runner_defaults_cycles_and_expected_branch() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert '[string]$ExpectedBranch = "main"' in text
    assert "[int]$Cycles = 3" in text
    assert "[int]$MaxCycles = 10" in text


def test_runner_emits_json_only_with_output_json(clean_repo_root: Path) -> None:
    result = _runner_json(clean_repo_root)
    raw = result.stdout.strip()
    parsed = json.loads(raw)

    assert raw.startswith("{")
    assert "AIOS Governed Self-Development Soak" not in raw
    assert parsed["schema"] == "AIOS_GOVERNED_SELF_DEVELOPMENT_SOAK_RESULT.v1"
    assert parsed["aggregate_status"] == "PASS"
    assert parsed["cycles_completed"] == 3


def test_runner_console_mode_includes_expected_sections(clean_repo_root: Path) -> None:
    result = _runner_console(clean_repo_root)
    out = result.stdout

    for section in (
        "CURRENT STATE",
        "SOAK SIMULATION",
        "CYCLE RESULTS",
        "FORBIDDEN SURFACE DELTAS",
        "APPROVAL REQUIRED",
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

    result = _run_runner("-RepoRoot", str(tmp_path), "-OutputJson", *_runner_evidence_args(), cwd=tmp_path, check=False)
    parsed = json.loads(result.stdout)

    assert result.returncode != 0
    assert parsed["aggregate_status"] == "BLOCKED"
    assert "DIRTY_WORKTREE" in parsed["stop_conditions"]
    assert parsed["cycles_completed"] == 0


def test_runner_no_write_proof_detects_forbidden_deltas() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "forbidden_surface_changed" in text
    assert "Compare-NoWriteState" in text
    assert "automation/orchestration/work_packets" in text
    assert "automation/orchestration/runtime" in text
    assert "automation/orchestration/approval_inbox" in text
    assert "AIOS_BACKUP_IN_PROGRESS.lock" in text


def test_runner_no_write_proof_does_not_create_forbidden_files(clean_repo_root: Path) -> None:
    protected_roots = [
        "Reports",
        "telemetry",
        "automation/orchestration/work_packets",
        "automation/orchestration/queue",
        "automation/orchestration/command_queue",
        "automation/orchestration/locks",
        "automation/orchestration/approval_inbox",
        "automation/orchestration/runtime",
        "automation/orchestration/workers/inbox",
        "automation/orchestration/relay_bus",
    ]
    before = {root: _file_set(REPO_ROOT, root) for root in protected_roots}
    result = _runner_json(clean_repo_root)
    after = {root: _file_set(REPO_ROOT, root) for root in protected_roots}
    parsed = json.loads(result.stdout)

    assert parsed["safety"]["writes_files"] is False
    assert parsed["no_write_proof"]["changed"] is False
    assert before == after


def test_runner_output_does_not_recommend_protected_or_runtime_commands(clean_repo_root: Path) -> None:
    result = _runner_json(clean_repo_root)
    parsed = json.loads(result.stdout)
    encoded = json.dumps(parsed).lower()

    for blocked in ("git add", "git commit", "git push", "gh pr", "git merge", "start-aios", "open-aiosworker"):
        assert blocked not in encoded


def test_upstream_runners_allow_exact_soak_files_without_broad_directory() -> None:
    expected = (
        "automation/orchestration/self_development/Test-AiOsGovernedSelfDevelopmentSoak.DRY_RUN.ps1",
        "automation/orchestration/self_development/aios_governed_self_development_soak.py",
        "schemas/aios/orchestration/AIOS_GOVERNED_SELF_DEVELOPMENT_SOAK_RESULT.v1.schema.json",
        "tests/orchestration/test_aios_governed_self_development_soak.py",
        "tests/orchestration/test_aios_governed_self_development_soak_runner.py",
    )
    for runner, function_name in (
        (HARD_GATE_RUNNER, "Test-ApprovalSosHardGateDirtyState"),
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
