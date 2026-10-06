from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/validators/Get-AiOsValidatorEvidenceRouter.DRY_RUN.ps1"
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
    assert "AIOS Validator Evidence Router" not in raw
    assert parsed["schema"] == "AIOS_VALIDATOR_EVIDENCE_ROUTER_RESULT.v1"
    assert parsed["safety"]["console_only"] is True


def test_runner_accepts_explicit_current_expected_branch(clean_repo_root: Path) -> None:
    branch = _current_branch(clean_repo_root)
    result = _run_runner("-OutputJson", "-ExpectedBranch", branch, cwd=clean_repo_root)
    parsed = json.loads(result.stdout)

    assert parsed["repo_state"]["expected_branch"] == branch
    assert parsed["repo_state"]["branch_matches_expected"] is True


def test_runner_passes_expected_branch_to_packet_router() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "automation/orchestration/self_audit/Get-AiOsSelfDevelopmentPacketRouter.DRY_RUN.ps1" in text
    assert '-ExpectedBranch "{2}"' in text


def test_runner_console_mode_includes_expected_sections(clean_repo_root: Path) -> None:
    result = _run_runner(*_expected_branch_args(clean_repo_root), cwd=clean_repo_root)
    out = result.stdout

    for section in (
        "CURRENT STATE",
        "SAFE VALIDATORS",
        "SAFE EVIDENCE",
        "BLOCKED SURFACES",
        "RECOMMENDED CHAINS",
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
    assert parsed["repo_state"]["dirty_allowed_for_validator_evidence_router_validation"] is False


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


def test_packet_router_runner_allows_exact_validator_evidence_files_without_broad_directory() -> None:
    text = PACKET_ROUTER_RUNNER.read_text(encoding="utf-8")
    match = re.search(
        r"function Test-RouterValidationDirtyState \{(.*?)function ConvertTo-StableJson",
        text,
        flags=re.DOTALL,
    )

    assert match is not None
    block = match.group(1)
    for expected in (
        "automation/orchestration/validators/Get-AiOsValidatorEvidenceRouter.DRY_RUN.ps1",
        "automation/orchestration/validators/aios_validator_evidence_router.py",
        "schemas/aios/orchestration/AIOS_VALIDATOR_EVIDENCE_ROUTER_RESULT.v1.schema.json",
        "tests/orchestration/test_aios_validator_evidence_router.py",
        "tests/orchestration/test_aios_validator_evidence_router_runner.py",
    ):
        assert expected in block
    assert ".StartsWith(" not in block


def test_self_audit_runner_allows_exact_validator_evidence_files_without_broad_directory() -> None:
    text = SELF_AUDIT_RUNNER.read_text(encoding="utf-8")
    match = re.search(
        r"function Test-SelfAuditValidationDirtyState \{(.*?)function ConvertTo-StableJson",
        text,
        flags=re.DOTALL,
    )

    assert match is not None
    block = match.group(1)
    for expected in (
        "automation/orchestration/validators/Get-AiOsValidatorEvidenceRouter.DRY_RUN.ps1",
        "automation/orchestration/validators/aios_validator_evidence_router.py",
        "schemas/aios/orchestration/AIOS_VALIDATOR_EVIDENCE_ROUTER_RESULT.v1.schema.json",
        "tests/orchestration/test_aios_validator_evidence_router.py",
        "tests/orchestration/test_aios_validator_evidence_router_runner.py",
    ):
        assert expected in block
    assert ".StartsWith(" not in block
