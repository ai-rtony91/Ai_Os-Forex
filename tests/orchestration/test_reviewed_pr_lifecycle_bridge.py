"""Tests for Codex-to-ChatGPT report bridge and reviewed PR lifecycle helper."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import secrets
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_SCRIPT = REPO_ROOT / "automation/orchestration/review_bridge/New-AiOsCodexReportForChatGptReview.DRY_RUN.ps1"
LIFECYCLE_SCRIPT = REPO_ROOT / "automation/orchestration/pr_lifecycle/Invoke-AiOsReviewedPrLifecycle.DRY_RUN.ps1"


def _run_powershell_json(script: Path, args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> dict:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-OutputJson",
    ] + args

    raw = subprocess.check_output(cmd, cwd=str(cwd or REPO_ROOT), env=env, text=True)
    return json.loads(raw.strip())


def _init_review_repo(tmp: Path, ahead: bool = False, dirty: bool = False, branch: str = "feature/review-lifecycle") -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-b", "main"], cwd=str(repo), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.name", "AIOS Test"], cwd=str(repo), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "aios-test@example.invalid"], cwd=str(repo), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "base.txt"], cwd=str(repo), stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "commit", "-m", "baseline"], cwd=str(repo), stdout=subprocess.DEVNULL)

    bare = tmp / "origin.git"
    subprocess.check_call(["git", "init", "--bare", str(bare)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "remote", "add", "origin", str(bare)], cwd=str(repo), stdout=subprocess.DEVNULL)

    subprocess.check_call(["git", "checkout", "-b", branch], cwd=str(repo), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "change.txt"], cwd=str(repo), stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "commit", "-m", "feature"], cwd=str(repo), stdout=subprocess.DEVNULL)

    if not ahead:
        subprocess.check_call(["git", "checkout", "main"], cwd=str(repo), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.check_call(["git", "branch", "-f", branch, "main"], cwd=str(repo), stdout=subprocess.DEVNULL)
        subprocess.check_call(["git", "checkout", branch], cwd=str(repo), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if dirty:
        (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    return repo


def _write_fake_gh(bin_dir: Path, include_existing_pr: bool = False, checks_ok: bool = True, merge_ok: bool = True) -> None:
    calls = bin_dir / "gh_calls.log"
    ps1 = bin_dir / "gh.ps1"
    ps1.write_text(
        """param([Parameter(ValueFromRemainingArguments=$true)] [string[]]$Arguments)
$callLog = Join-Path $PSScriptRoot 'gh_calls.log'
$joined = $Arguments -join ' '
Add-Content -Path $callLog -Value $joined

if ($Arguments.Count -ge 2 -and $Arguments[0] -eq 'pr') {
    $sub = $Arguments[1]
    if ($sub -eq 'list') {
        if ('{include_existing}' -eq '1') {
            Write-Output '[{{\"number\":123,\"url\":\"https://github.com/ai-rtony91/Ai_Os/pull/123\"}}]'
        } else {
            Write-Output '[]'
        }
        exit 0
    }
    if ($sub -eq 'create') {
        Write-Output 'https://github.com/ai-rtony91/Ai_Os/pull/123'
        exit 0
    }
    if ($sub -eq 'checks') {
        if ('{checks_ok}' -eq '1') { exit 0 } else { exit 1 }
    }
    if ($sub -eq 'merge') {
        if ('{merge_ok}' -eq '1') { exit 0 } else { exit 1 }
    }
}
exit 0
""".replace(
            "{include_existing}", "1" if include_existing_pr else "0"
        ).replace("{checks_ok}", "1" if checks_ok else "0").replace("{merge_ok}", "1" if merge_ok else "0"),
        encoding="utf-8",
    )
    (bin_dir / "gh.cmd").write_text(
        "@echo off\npowershell -NoProfile -ExecutionPolicy Bypass -File \"%~dp0\\gh.ps1\" %*\n",
        encoding="utf-8",
    )
    calls.write_text("", encoding="utf-8")


def _write_fake_git(bin_dir: Path, real_git: str) -> None:
    ps1 = bin_dir / "git.ps1"
    ps1.write_text(
        f"""param([Parameter(ValueFromRemainingArguments=$true)] [string[]]$Arguments)
if ($Arguments -contains 'push') {{
    exit 0
}}
& "{real_git}" @Arguments
exit $LASTEXITCODE
""",
        encoding="utf-8",
    )
    (bin_dir / "git.cmd").write_text(
        "@echo off\npowershell -NoProfile -ExecutionPolicy Bypass -File \"%~dp0\\git.ps1\" %*\n",
        encoding="utf-8",
    )
    return ps1


def _workspace_dir(prefix: str) -> Path:
    base = Path(tempfile.gettempdir()) / "aios_pytest_workspace" / prefix
    base.mkdir(parents=True, exist_ok=True)
    path = base / secrets.token_hex(8)
    path.mkdir(parents=True, exist_ok=False)
    return path


def _run_lifecycle(
    repo: Path,
    args: list[str],
    fake_bin: Path | None = None,
    env_extra: dict[str, str] | None = None,
) -> dict:
    env = os.environ.copy()
    extra_args: list[str] = []
    if fake_bin is not None:
        real_git = shutil.which("git")
        if real_git:
            fake_git = _write_fake_git(fake_bin, real_git)
            extra_args.extend(["-GitCommand", str(fake_git)])
        env["PATH"] = f"{fake_bin}{os.pathsep}" + env.get("PATH", "")
    if env_extra:
        env.update(env_extra)

    return _run_powershell_json(
        LIFECYCLE_SCRIPT,
        [
            "-Title",
            "feat: test",
            "-Body",
            "test body",
            "-RepoRoot",
            str(repo),
        ]
        + extra_args
        + args,
        cwd=REPO_ROOT,
        env=env,
    )


def test_review_bridge_generates_chatgpt_review_prompt_payload() -> None:
    result = _run_powershell_json(
        REVIEW_SCRIPT,
        [
            "-PacketId",
            "AIOS-FOREX-PAPER-LEARNING-ACTION-ROUTER-APPLY-V1",
            "-Branch",
            "main",
            "-CommitHash",
            "abc123",
            "-FilesChanged",
            "automation/forex_engine/file.py",
            "-TestsRun",
            "python -m pytest tests/forex_engine -q -p no:cacheprovider",
            "-SafetyFlags",
            "no broker/OANDA",
            "-ValidationResults",
            "git diff --check",
        ],
    )

    assert result["schema"] == "AIOS_CODEX_REPORT_CHATGPT_REVIEW_REQUEST.v1"
    assert result["can_continue_without_anthony"] is False
    assert result["must_not_execute_without_anthony"] is True
    assert result["writes_files"] is False
    assert result["packet_id"] == "AIOS-FOREX-PAPER-LEARNING-ACTION-ROUTER-APPLY-V1"
    assert result["branch"] == "main"
    assert "ChatGPT must review this report" in result["requested_chatgpt_review"]


def test_review_bridge_supports_prompt_block_output() -> None:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(REVIEW_SCRIPT),
        "-PacketId",
        "AIOS-FOREX-PAPER-LEARNING-ACTION-ROUTER-APPLY-V1",
        "-Branch",
        "main",
        "-AsPromptBlock",
    ]
    raw = subprocess.check_output(cmd, text=True).strip()
    assert "ChatGPT must review this report and return a PowerShell block only after checking safety and repo state." in raw


def test_lifecycle_blocks_without_anthony_reviewed_flag() -> None:
    repo = _init_review_repo(_workspace_dir("reviewed_pr_lifecycle"))
    result = _run_lifecycle(repo=repo, args=[])

    assert result["anthony_reviewed"] is False
    assert result["checks_status"] == "BLOCKED_NO_ANTHONY_REVIEW"
    assert "AnthonyReviewed" in result["exact_next_safe_action"]


def test_lifecycle_blocks_on_main_branch() -> None:
    repo = _init_review_repo(_workspace_dir("reviewed_pr_lifecycle"), ahead=False)
    subprocess.check_call(["git", "checkout", "main"], cwd=str(repo), stdout=subprocess.DEVNULL)
    result = _run_lifecycle(repo=repo, args=["-AnthonyReviewed"])

    assert result["checks_status"] == "NOT_RUN"
    assert result["reason"].startswith("Blocked")
    assert result["blocked_actions"]


def test_lifecycle_blocks_on_dirty_tree() -> None:
    repo = _init_review_repo(_workspace_dir("reviewed_pr_lifecycle"), dirty=True)
    result = _run_lifecycle(repo=repo, args=["-AnthonyReviewed"])

    assert result["reason"] == "Blocked: working tree is dirty."
    assert result["execution_allowed"] is False


def test_lifecycle_blocks_not_ahead_of_base() -> None:
    repo = _init_review_repo(_workspace_dir("reviewed_pr_lifecycle"), ahead=False)
    result = _run_lifecycle(repo=repo, args=["-AnthonyReviewed"])

    assert result["reason"] == "Blocked: no commits ahead of base."
    assert result["ahead_of_base"] is False


def test_lifecycle_stops_before_merge_without_merge_flag() -> None:
    repo = _init_review_repo(_workspace_dir("reviewed_pr_lifecycle"), ahead=True)
    bin_dir = _workspace_dir("reviewed_pr_lifecycle_bin") / "bin"
    bin_dir.mkdir()
    _write_fake_gh(bin_dir, include_existing_pr=False, checks_ok=True, merge_ok=True)
    result = _run_lifecycle(repo=repo, args=["-AnthonyReviewed", "-WatchChecks"], fake_bin=bin_dir)

    assert result["pushed"] is True
    assert result["checks_status"] == "PASS"
    assert result["merged"] is False
    assert result["merge_allowed"] is False
    assert result["requires_anthony_for_merge"] is True
    assert result["execution_allowed"] is False
    assert "merge requires" in result["reason"]
    gh_calls = (bin_dir / "gh_calls.log").read_text(encoding="utf-8").strip().splitlines()
    assert any("pr create" in line for line in gh_calls)
    assert not any("--force" in line for line in gh_calls)


def test_merge_requires_approved_flag() -> None:
    repo = _init_review_repo(_workspace_dir("reviewed_pr_lifecycle"), ahead=True)
    bin_dir = _workspace_dir("reviewed_pr_lifecycle_bin") / "bin"
    bin_dir.mkdir()
    _write_fake_gh(bin_dir, include_existing_pr=False, checks_ok=True, merge_ok=True)
    result = _run_lifecycle(repo=repo, args=["-AnthonyReviewed"], fake_bin=bin_dir)
    assert result["merge_requested"] is False
    assert result["merged"] is False
    assert result["checks_status"] == "NOT_WATCHED"
    assert "merge requires" in result["reason"]


def test_post_merge_read_only_fields_and_placeholders() -> None:
    script_text = LIFECYCLE_SCRIPT.read_text(encoding="utf-8")
    assert "git commit" not in script_text.lower()
    assert "--force" not in script_text.lower()
    assert "MergeAfterChecks" in script_text
    assert "aios.ps1 -Mode status" in script_text
    assert "Get-AiOsSupervisedContinuationPlan.DRY_RUN.ps1" in script_text
    assert "Convert-AiOsContinuationPlanToProposedPacket.DRY_RUN.ps1" in script_text

    repo = _init_review_repo(_workspace_dir("reviewed_pr_lifecycle"), ahead=True)
    bin_dir = _workspace_dir("reviewed_pr_lifecycle_bin") / "bin"
    bin_dir.mkdir()
    _write_fake_gh(bin_dir)
    result = _run_lifecycle(repo=repo, args=["-AnthonyReviewed", "-WatchChecks"], fake_bin=bin_dir)
    assert "pr_number" in result
    assert "pr_url" in result
    assert "checks_status" in result
