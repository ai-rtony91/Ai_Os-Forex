from __future__ import annotations

import base64
import json
from pathlib import Path
import re
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "automation/orchestration/self_development/Start-AiOsAutonomousForexResearchRun.APPLY.ps1"


def _param_block() -> str:
    text = RUNNER.read_text(encoding="utf-8")
    match = re.search(r"param\((.*?)\)\s*Set-StrictMode", text, flags=re.DOTALL)
    assert match is not None
    return match.group(1)


def _current_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _run_runner(*args: str, console_encoding: str = "") -> subprocess.CompletedProcess[str]:
    if console_encoding:
        # Reproduce the UTF-8 console inherited from GitHub's pwsh host, or
        # the OEM console on a normal Windows PowerShell terminal.
        encoding = (
            "[Text.UTF8Encoding]::new($true)"
            if console_encoding == "utf8_with_bom"
            else "[Text.Encoding]::GetEncoding(437)"
        )
        quote = lambda value: "'" + value.replace("'", "''") + "'"
        invocation = " ".join(arg if arg.startswith("-") else quote(arg) for arg in args)
        script = f"[Console]::InputEncoding = {encoding}; & {quote(str(RUNNER))} {invocation}"
        command = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand",
            base64.b64encode(script.encode("utf-16-le")).decode("ascii"),
        ]
    else:
        command = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER), *args,
        ]
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_runner_has_required_parameters() -> None:
    param_block = _param_block()

    for required in (
        "$RepoRoot",
        "$ExpectedBranch",
        "$OutputJson",
        "$Mode",
        "$HumanOwnerResearchApproval",
        "$ResearchMode",
        "$Pair",
        "$Timeframe",
        "$StrategyProfile",
        "$BacktestWindow",
        "$SoakCycles",
        "$MaxRuntimeMinutes",
        "$StopOnFirstFailure",
        "$OutputRoot",
        "$NowUtc",
        "$FailOnDirtyWorktree",
        "$TimeoutSeconds",
    ):
        assert required in param_block


def test_runner_has_no_forbidden_runtime_or_mutation_parameters() -> None:
    param_block = _param_block()

    for forbidden in (
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
        "$OutputPath",
    ):
        assert forbidden not in param_block


def test_runner_output_json_branch_is_json_only_surface() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "if ($OutputJson)" in text
    assert "$result | ConvertTo-Json -Depth 90" in text
    assert "Write-ConsoleReport -Result $result" in text


def test_runner_dry_run_executes_from_repo_root_imports_package_and_writes_no_ledger(tmp_path: Path) -> None:
    output_root = tmp_path / "ledger"
    result = _run_runner(
        "-Mode",
        "DRY_RUN",
        "-OutputJson",
        "-ExpectedBranch",
        _current_branch(),
        "-HumanOwnerResearchApproval",
        "APPROVED_LOCAL_FOREX_RESEARCH_ONLY",
        "-ResearchMode",
        "FULL_LOCAL_RESEARCH_STUB",
        "-Pair",
        "EURUSD",
        "-Timeframe",
        "M5",
        "-StrategyProfile",
        "BASELINE_CONFLUENCE",
        "-BacktestWindow",
        "SYNTHETIC_30D",
        "-SoakCycles",
        "3",
        "-MaxRuntimeMinutes",
        "30",
        "-OutputRoot",
        str(output_root),
    )

    assert "ModuleNotFoundError" not in result.stderr
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["schema"] == "AIOS_AUTONOMOUS_FOREX_RESEARCH_RUN_RESULT.v1"
    assert parsed["mode"] == "DRY_RUN"
    assert parsed["run_ledger"]["written"] is False
    assert not output_root.exists()


def test_runner_apply_writes_ledger_only_to_requested_output_root(tmp_path: Path) -> None:
    output_root = tmp_path / "ledger"
    result = _run_runner(
        "-Mode",
        "APPLY",
        "-OutputJson",
        "-ExpectedBranch",
        _current_branch(),
        "-HumanOwnerResearchApproval",
        "APPROVED_LOCAL_FOREX_RESEARCH_ONLY",
        "-ResearchMode",
        "FULL_LOCAL_RESEARCH_STUB",
        "-Pair",
        "EURUSD",
        "-Timeframe",
        "M5",
        "-StrategyProfile",
        "BASELINE_CONFLUENCE",
        "-BacktestWindow",
        "SYNTHETIC_30D",
        "-SoakCycles",
        "3",
        "-MaxRuntimeMinutes",
        "30",
        "-OutputRoot",
        str(output_root),
    )

    assert "ModuleNotFoundError" not in result.stderr
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    ledger_path = Path(parsed["run_ledger"]["path"])
    assert parsed["mode"] == "APPLY"
    assert parsed["run_ledger"]["written"] is True
    assert ledger_path.exists()
    assert output_root.resolve() in ledger_path.resolve().parents
    assert parsed["safety"]["broker_or_live_trading"] is False
    assert parsed["safety"]["touches_secrets_or_env"] is False


def test_runner_console_summary_includes_mode_pair_timeframe_safety_and_next_action() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "research_mode:" in text
    assert "pair:" in text
    assert "timeframe:" in text
    assert "safety_status:" in text
    assert "next_safe_action:" in text


def test_runner_surface_blocks_live_broker_secret_paths() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "aios_autonomous_forex_research_pipeline.py" in text
    assert "Start-Process" not in text
    assert "PYTHONPATH" in text
    assert "OANDA" not in text
    assert "broker" not in text.lower()


@pytest.mark.parametrize("mode", ["DRY_RUN", "APPLY"])
@pytest.mark.parametrize("console_encoding", ["utf8_with_bom", "oem"])
def test_runner_payload_survives_host_console_encoding(
    tmp_path: Path, mode: str, console_encoding: str
) -> None:
    output_root = tmp_path / "ledger_東京"
    result = _run_runner(
        "-Mode", mode,
        "-OutputJson",
        "-ExpectedBranch", _current_branch(),
        "-HumanOwnerResearchApproval", "APPROVED_LOCAL_FOREX_RESEARCH_ONLY",
        "-ResearchMode", "FULL_LOCAL_RESEARCH_STUB",
        "-OutputRoot", str(output_root),
        console_encoding=console_encoding,
    )

    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["mode"] == mode
    assert parsed["run_ledger"]["written"] is (mode == "APPLY")
    if mode == "APPLY":
        # Test the real destination; caller stdout may use an OEM code page.
        assert len(list(output_root.glob("*.json"))) == 1
    else:
        assert not output_root.exists()
    assert parsed["safety"]["broker_or_live_trading"] is False
    assert parsed["safety"]["touches_secrets_or_env"] is False
