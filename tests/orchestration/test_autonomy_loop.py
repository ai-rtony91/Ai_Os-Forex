"""Tests for autonomy loop v0 dry-run script."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "automation/orchestration/autonomy_loop/Invoke-AiOsAutonomyLoop.DRY_RUN.ps1"
PROPOSED_DIR = REPO_ROOT / "Reports/autonomy_loop/proposed"


def run_autonomy_loop(goal_text: str, *, extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        "-GoalText",
        goal_text,
        "-PassThrough",
    ]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def make_fake_validator_script(path: Path) -> Path:
    path.write_text(
        "import json\nimport sys\nprint(json.dumps({\"status\": \"FAIL\", \"errors\": [\"invalid packet\"], \"warnings\": []}))\nsys.exit(1)\n",
        encoding="utf-8",
    )
    return path


def make_fake_packet_runner(path: Path) -> Path:
    path.write_text(
        "param()\nWrite-Output '{}'\n",
        encoding="utf-8",
    )
    return path


def test_autonomy_loop_goal_to_packet_and_report(tmp_path: Path) -> None:
    report_root = tmp_path / "autonomy_reports"
    output_path = report_root / "packet_full.md"
    auto_runner_report = report_root / "packet_auto.report.json"
    report_root.mkdir(parents=True, exist_ok=True)

    result = run_autonomy_loop(
        "Build a minimal paper-only planning lane for DRY_RUN completion",
        extra_args=[
            "-AutonomyReportDirectory",
            str(report_root),
            "-PacketRunnerOutputPath",
            str(output_path),
            "-PacketRunnerReportPath",
            str(auto_runner_report),
        ],
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout.strip())
    assert payload["validator_status"] == "PASS"
    assert payload["auto_runner_status"] == "PASS"
    assert payload["blocked"] is False
    assert payload["packet_output_path"] == str(output_path)
    assert output_path.exists()
    assert auto_runner_report.exists()

    packet_path = Path(payload["packet_path"])
    assert packet_path.exists()
    assert packet_path.parent == PROPOSED_DIR
    packet_text = packet_path.read_text(encoding="utf-8")
    assert "CODEX-ONLY PROMPT" in packet_text
    assert "Build a minimal paper-only planning lane for DRY_RUN completion" in packet_text
    assert "SAFE NEXT ACTION:" in packet_text
    assert "broker execution" not in packet_text.lower()
    assert "merge" not in packet_text.lower()

    validator = subprocess.run(
        [
            "python",
            "automation/validators/aios_governance_validator.py",
            "--input",
            str(packet_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert validator.returncode == 0, validator.stdout + validator.stderr
    validation_payload = json.loads(validator.stdout)
    assert validation_payload["status"] == "PASS"

    packet_path.unlink()


def test_autonomy_loop_stops_on_validator_failure(tmp_path: Path) -> None:
    report_root = tmp_path / "autonomy_reports_fail"
    report_root.mkdir(parents=True, exist_ok=True)
    fake_validator = make_fake_validator_script(tmp_path / "fake_validator.py")
    fake_runner = make_fake_packet_runner(tmp_path / "fake_runner.ps1")

    result = run_autonomy_loop(
        "Intent is intentionally invalid for validator demonstration",
        extra_args=[
            "-AutonomyReportDirectory",
            str(report_root),
            "-ValidatorScriptPath",
            str(fake_validator),
            "-PacketRunnerScriptPath",
            str(fake_runner),
        ],
    )

    assert result.returncode != 0
    stderr = " ".join(result.stderr.split())
    assert "REVIEW_REQUIRED: governance validation failed" in stderr
    failure_reports = list(report_root.glob("*.json"))
    assert len(failure_reports) == 1

    report = json.loads(failure_reports[0].read_text(encoding="utf-8"))
    assert report["blocked"] is True
    assert report["validator_status"] == "FAILED"
