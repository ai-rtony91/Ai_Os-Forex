from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/self_development/Invoke-AiOsGovernedSelfDevelopmentLoop.DRY_RUN.ps1"
PACKET_ROUTER_RUNNER = REPO_ROOT / "automation/orchestration/self_audit/Get-AiOsSelfDevelopmentPacketRouter.DRY_RUN.ps1"
SELF_AUDIT_RUNNER = REPO_ROOT / "automation/orchestration/self_audit/Invoke-AiOsSelfAuditLoop.DRY_RUN.ps1"
VALIDATOR_ROUTER_RUNNER = REPO_ROOT / "automation/orchestration/validators/Get-AiOsValidatorEvidenceRouter.DRY_RUN.ps1"
DAY_NIGHT_RUNNER = REPO_ROOT / "automation/orchestration/supervisor/Get-AiOsDayNightReadiness.DRY_RUN.ps1"
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


def _runner_evidence_args() -> tuple[str, ...]:
    day_night = {
        "schema": "AIOS_DAY_NIGHT_READINESS_RESULT.v1",
        "mode": "DRY_RUN_READ_ONLY",
        "readiness": {
            "classification": "SUPERVISED_RECOMMENDATION_ALLOWED",
            "recommendation_allowed": True,
            "execution_allowed": False,
        },
        "approval_state": {
            "status": "CLEAR",
            "approval_required": False,
            "sos_hard_stop": False,
        },
        "runtime_worker_state": {
            "status": "CLEAR",
            "runtime_risk_detected": False,
            "worker_launch_detected": False,
            "scheduler_or_daemon_detected": False,
        },
        "backup_interference_state": {
            "status": "CLEAR",
            "interference_detected": False,
            "repo_local_backup_lock_present": False,
            "backup_in_progress": False,
            "snapshot_restore_candidate_present": False,
        },
        "autonomy_chain_state": {
            "self_audit_status": "PASS",
            "packet_router_status": "PASS",
            "validator_evidence_router_status": "PASS",
        },
        "safety": {
            "status": "PASS",
            "writes_files": False,
            "writes_reports": False,
            "writes_telemetry": False,
            "writes_packet_drafts": False,
            "outputs_packet_body": False,
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
    campaign_no_ready = {
        "schema": "AIOS_CAMPAIGN_NO_READY_STAGE_DISCOVERY.v1",
        "overall_readiness": "NO_READY_STAGE",
        "no_ready_stage_classification": "COMPLETE_IDLE",
    }
    campaign_next_task = {
        "schema": "AIOS_CAMPAIGN_NEXT_TASK_RECOMMENDATION.v1",
        "overall_readiness": "NO_READY_STAGE",
        "next_packet_candidate": None,
    }
    action_recommendation = {
        "recommended_command": "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/campaign_registry/Get-AiOsCampaignNoReadyStageDiscovery.DRY_RUN.ps1 -OutputJson",
    }
    return (
        "-DayNightReadinessJson",
        _json_arg(day_night),
        "-CampaignNoReadyJson",
        _json_arg(campaign_no_ready),
        "-CampaignNextTaskJson",
        _json_arg(campaign_next_task),
        "-ActionRecommendationJson",
        _json_arg(action_recommendation),
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


def test_runner_defaults_expected_branch_to_main() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert '[string]$ExpectedBranch = "main"' in text
    assert "feature/governed-self-development-closure-v1" not in text


def test_runner_emits_json_only_with_output_json(clean_repo_root: Path) -> None:
    result = _runner_json(clean_repo_root)
    raw = result.stdout.strip()
    parsed = json.loads(raw)

    assert raw.startswith("{")
    assert "AIOS Governed Self-Development Loop" not in raw
    assert parsed["schema"] == "AIOS_GOVERNED_SELF_DEVELOPMENT_LOOP_RESULT.v1"
    assert parsed["recommended_next_packet"]["packet_id"] == "AIOS-OPERATOR-CONTROL-SURFACE-CONTRACT-DRYRUN-V1"


def test_runner_accepts_explicit_current_expected_branch(clean_repo_root: Path) -> None:
    branch = _current_branch(clean_repo_root)
    result = _run_runner("-OutputJson", "-ExpectedBranch", branch, *_runner_evidence_args(), cwd=clean_repo_root)
    parsed = json.loads(result.stdout)

    assert parsed["repo_state"]["expected_branch"] == branch
    assert parsed["repo_state"]["branch_matches_expected"] is True
    assert parsed["safety"]["status"] == "PASS"


def test_runner_console_mode_includes_expected_sections(clean_repo_root: Path) -> None:
    result = _runner_console(clean_repo_root)
    out = result.stdout

    for section in (
        "CURRENT STATE",
        "GOVERNED SELF-DEVELOPMENT LOOP",
        "AUTONOMY CHAIN STATE",
        "SAFE SURFACES USED",
        "RECOMMENDED NEXT PACKET",
        "VALIDATOR CHAIN",
        "READINESS",
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
    assert parsed["repo_state"]["dirty_allowed_for_governed_loop_validation"] is False


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
        "automation/orchestration/workers/inbox",
    ]
    before = {root: _file_set(REPO_ROOT, root) for root in protected_roots}
    result = _runner_json(clean_repo_root)
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


def test_prior_routers_allow_exact_governed_loop_files_without_broad_directory() -> None:
    expected = (
        "automation/orchestration/self_development/Invoke-AiOsGovernedSelfDevelopmentLoop.DRY_RUN.ps1",
        "automation/orchestration/self_development/aios_governed_self_development_loop.py",
        "schemas/aios/orchestration/AIOS_GOVERNED_SELF_DEVELOPMENT_LOOP_RESULT.v1.schema.json",
        "tests/orchestration/test_aios_governed_self_development_loop.py",
        "tests/orchestration/test_aios_governed_self_development_loop_runner.py",
    )
    for runner, function_name in (
        (SELF_AUDIT_RUNNER, "Test-SelfAuditValidationDirtyState"),
        (PACKET_ROUTER_RUNNER, "Test-RouterValidationDirtyState"),
        (VALIDATOR_ROUTER_RUNNER, "Test-ValidatorEvidenceRouterDirtyState"),
        (DAY_NIGHT_RUNNER, "Test-DayNightReadinessDirtyState"),
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


def test_runner_does_not_call_excluded_write_capable_scripts() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    surface_block = text.split("$safeSurfaces = ", 1)[1].split("$blockedSurfaces = ", 1)[0]
    excluded = [
        "automation/orchestration/packet_generator/New-AiOsCodexPacket.DRY_RUN.ps1",
        "automation/orchestration/work_packets",
        "automation/orchestration/approval_inbox/New-AiOsPacketApprovalRequest.DRY_RUN.ps1",
        "automation/orchestration/approval_inbox/Invoke-AiOsApprovalChain.DRY_RUN.ps1",
        "automation/orchestration/approval_processor/Invoke-AiOsApprovalProcessor.DRY_RUN.ps1",
        "automation/orchestration/approval_runner/Invoke-AiOsApprovedActionResume.ps1",
        "automation/orchestration/locks/Claim-AiOsFileLock.DRY_RUN.ps1",
        "automation/orchestration/locks/Release-AiOsFileLock.DRY_RUN.ps1",
        "automation/orchestration/relay_bus/New-AiOsRelayMessage.DRY_RUN.ps1",
        "automation/orchestration/runtime/Start-AiOsPersistentRuntimeSupervisor.ps1",
        "automation/orchestration/workers/launcher/Open-AiOsWorkerWindow.DRY_RUN.ps1",
        "automation/orchestration/workers/daemon/Start-AiOsWorkerDaemon.DRY_RUN.ps1",
        "automation/orchestration/commit_packages/Invoke-AiOsExactCommitPackage.ps1",
    ]

    for script in excluded:
        assert script not in surface_block


def test_runner_output_does_not_recommend_protected_or_runtime_commands(clean_repo_root: Path) -> None:
    result = _runner_json(clean_repo_root)
    parsed = json.loads(result.stdout)
    action = parsed["next_safe_action"].lower()

    assert "git add" not in action
    assert "git commit" not in action
    assert "git push" not in action
    assert "git merge" not in action
    assert "start-aios" not in action
    assert "open-aiosworker" not in action
