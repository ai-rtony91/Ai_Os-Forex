"""Static safety-contract tests for Forex and validator DRY_RUN scripts.

These tests inspect source and JSON only. They never launch a PowerShell script.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FOREX_PLAN = REPO_ROOT / "automation/orchestration/forex_builder_lane/New-AiOsForexBuilderPlan.DRY_RUN.ps1"
VALIDATOR_RUNNER = REPO_ROOT / "automation/orchestration/validator_chain_runner/Invoke-AiOsValidatorChain.DRY_RUN.ps1"
VALIDATOR_README = REPO_ROOT / "automation/orchestration/validator_chain_runner/README.md"
VALIDATOR_CONFIG = REPO_ROOT / "automation/orchestration/validators/VALIDATOR_CHAIN_CONFIG_001.json"
TRADER_TEST_SCRIPTS = [
    REPO_ROOT / "automation/trader/Test-AiOsTraderModuleSafety.DRY_RUN.ps1",
    REPO_ROOT / "automation/trader/Test-AiOsTraderModuleV02OutcomesScorecard.DRY_RUN.ps1",
    REPO_ROOT / "automation/trader/Test-AiOsTraderModuleV03RiskHardening.DRY_RUN.ps1",
    REPO_ROOT / "automation/trader/Test-AiOsTraderModuleV04ExecutionQuality.DRY_RUN.ps1",
]
TRADING_LAB_REPORTS = [
    REPO_ROOT / "automation/trading_lab/New-AiOsTradingLabCore.DRY_RUN.ps1",
    REPO_ROOT / "automation/trading_lab/New-AiOsTradingLabLedgerValidation.DRY_RUN.ps1",
]

FILE_MUTATION = re.compile(
    r"\b(?:Set-Content|Add-Content|Out-File|Export-Csv|Export-Clixml|"
    r"New-Item|Remove-Item|Move-Item|Copy-Item|Rename-Item|Clear-Content)\b",
    re.IGNORECASE,
)
DOTNET_FILE_MUTATION = re.compile(
    r"\[System\.IO\.File\]::(?:WriteAllText|WriteAllBytes|AppendAllText|Delete|Move|Copy)\b",
    re.IGNORECASE,
)


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_no_file_mutators(text: str) -> None:
    assert FILE_MUTATION.search(text) is None
    assert DOTNET_FILE_MUTATION.search(text) is None


def test_forex_builder_dry_run_is_stdout_only() -> None:
    text = source(FOREX_PLAN)

    assert_no_file_mutators(text)
    assert "Write-TextAtomic" not in text
    assert "proposed_json_path" in text
    assert "proposed_markdown_path" in text
    assert "proposed_packet_path" in text
    assert "generated_json_path" not in text
    assert "generated_markdown_path" not in text
    assert "Write-Output ($report | ConvertTo-Json" in text


def test_forex_builder_does_not_offer_actions_for_blocked_goals() -> None:
    text = source(FOREX_PLAN)

    assert re.search(
        r"\$nextActions\s*=\s*if\s*\(\$isBlocked\)\s*\{\s*@\(\)\s*\}\s*else\s*\{\s*@\(\$categoryActions\)\s*\}",
        text,
        re.IGNORECASE,
    )
    assert re.search(r"next_actions\s*=\s*\$nextActions", text, re.IGNORECASE)


def test_trader_dry_run_wrappers_avoid_temp_files_and_policy_bypasses() -> None:
    for path in TRADER_TEST_SCRIPTS:
        text = source(path)
        assert_no_file_mutators(text)
        assert "New-TemporaryFile" not in text
        assert "python -B -" in text
        assert re.search(r"-ExecutionPolicy\s+Bypass", text, re.IGNORECASE) is None


def test_trading_lab_dry_runs_print_reports_without_writing_files() -> None:
    for path in TRADING_LAB_REPORTS:
        text = source(path)
        assert_no_file_mutators(text)
        assert "Proposed report path:" in text
        assert "Write-Output ($Report -join [Environment]::NewLine)" in text


def test_validator_chain_is_registered_and_read_only() -> None:
    runner = source(VALIDATOR_RUNNER)
    readme = source(VALIDATOR_README)
    config = json.loads(VALIDATOR_CONFIG.read_text(encoding="utf-8"))

    assert_no_file_mutators(runner)
    assert "WriteEvidence" not in runner
    assert "ExecutionPolicy" not in runner
    assert re.search(r"\bBypass\b", runner, re.IGNORECASE) is None
    assert "ExecutionPolicy Bypass" not in readme

    assert config["mode"] == "DRY_RUN_READ_ONLY"
    assert len(config["validators"]) == 12
    assert all(item["required"] is True for item in config["validators"])
    for item in config["validators"]:
        assert f'"{item["name"]}"' in runner
