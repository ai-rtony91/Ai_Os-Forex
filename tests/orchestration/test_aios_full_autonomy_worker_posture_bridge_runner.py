from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/self_development/Get-AiOsFullAutonomyWorkerPostureBridge.DRY_RUN.ps1"
RECOMMENDATION = REPO_ROOT / "automation/orchestration/recommendations/Get-AiOsActionRecommendation.DRY_RUN.ps1"


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


def _run_recommendation(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RECOMMENDATION),
            *args,
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"recommendation failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
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
    result = _run_runner("-OutputJson", *_expected_branch_args(clean_repo_root), "-OperatingProfile", "24H_SUPERVISED", cwd=clean_repo_root)
    raw = result.stdout.strip()
    parsed = json.loads(raw)

    assert raw.startswith("{")
    assert "AIOS Full Autonomy Worker Posture Bridge" not in raw
    assert parsed["schema"] == "AIOS_FULL_AUTONOMY_WORKER_POSTURE_BRIDGE_RESULT.v1"
    assert parsed["worker_posture"] == "READ_ONLY_VALIDATOR_CREW"
    assert parsed["worker_launch_allowed"] is False


def test_runner_console_mode_includes_expected_sections(clean_repo_root: Path) -> None:
    result = _run_runner(*_expected_branch_args(clean_repo_root), "-OperatingProfile", "12H_SUPERVISED", cwd=clean_repo_root)
    out = result.stdout

    for section in (
        "CURRENT STATE",
        "ACTIVATION SUMMARY",
        "WORKER POSTURE",
        "LANES",
        "HUMAN WAKE POLICY",
        "SAFETY",
        "NO-WRITE PROOF",
        "NEXT SAFE ACTION",
    ):
        assert section in out


def test_runner_supports_injected_activation_gate_json(clean_repo_root: Path) -> None:
    activation = {
        "schema": "AIOS_FULL_AUTONOMY_ACTIVATION_GATE_RESULT.v1",
        "requested_autonomy_level": "LEVEL_4_CONDITIONAL_FULL_AUTONOMY",
        "operating_profile": "WEEKEND",
        "input_evidence": {"human_owner_approval_evidence_present": True},
        "activation_decision": {"status": "WEEKEND_MONITOR_ALLOWED", "worker_launch_allowed": False},
        "safety": {"status": "PASS"},
        "stop_conditions": [],
    }
    result = _run_runner(
        "-OutputJson",
        *_expected_branch_args(clean_repo_root),
        "-OperatingProfile",
        "WEEKEND",
        "-ActivationGateJson",
        json.dumps(activation),
        cwd=clean_repo_root,
    )
    parsed = json.loads(result.stdout)

    assert parsed["worker_posture"] == "WEEKEND_LOW_TOUCH_CREW"
    assert parsed["max_parallel_workers"] <= 1


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
    assert parsed["repo_state"]["dirty_allowed_for_full_autonomy_worker_posture_bridge_validation"] is False


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


def test_recommendation_output_includes_full_autonomy_summary() -> None:
    result = _run_recommendation("-OutputJson")
    parsed = json.loads(result.stdout)
    summary = parsed["full_autonomy_state"]

    assert summary["requested_level"]
    assert summary["resolved_or_activation_status"]
    assert summary["operating_profile"]
    assert summary["worker_posture"]
    assert summary["worker_launch_allowed"] is False
    assert summary["human_wake_policy"]
    assert summary["next_safe_action"]


def test_recommendation_console_output_includes_full_autonomy_status_lines() -> None:
    result = _run_recommendation()
    out = result.stdout

    for line in (
        "FULL AUTONOMY STATE",
        "requested_level:",
        "resolved_or_activation_status:",
        "operating_profile:",
        "worker_posture:",
        "worker_launch_allowed:",
        "human_wake_policy:",
        "next_safe_action:",
    ):
        assert line in out


def test_recommendation_status_path_stays_read_only_and_does_not_run_workers() -> None:
    result = _run_recommendation("-OutputJson")
    parsed = json.loads(result.stdout)
    summary = parsed["full_autonomy_state"]

    assert parsed["mode"] == "READ_ONLY"
    assert summary["mode"] == "DRY_RUN_READ_ONLY"
    assert summary["worker_launch_allowed"] is False
    assert summary["starts_runtime"] is False
    assert summary["launches_workers"] is False
    assert summary["slow_nested_workers_started"] is False
