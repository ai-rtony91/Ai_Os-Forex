"""Tests for the Codex report → ChatGPT review → pasteback relay helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_SCRIPT = REPO_ROOT / "automation/orchestration/review_bridge/New-AiOsCodexReportRelayItem.DRY_RUN.ps1"
PROMPT_SCRIPT = REPO_ROOT / "automation/orchestration/review_bridge/Invoke-AiOsCodexChatGptRelay.DRY_RUN.ps1"
PASTEBACK_SCRIPT = REPO_ROOT / "automation/orchestration/review_bridge/New-AiOsChatGptPastebackItem.DRY_RUN.ps1"


def _run_powershell_json(
    script: Path,
    args: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
) -> dict:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ] + args
    if "-OutputJson" not in args:
        cmd.append("-OutputJson")
    raw = subprocess.check_output(cmd, cwd=str(cwd), env=env, text=True)
    return json.loads(raw.strip())


def _run_powershell_text(script: Path, args: list[str], cwd: Path) -> str:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ] + args
    return subprocess.check_output(cmd, cwd=str(cwd), text=True).strip()


def _build_report_payload(packet_id: str, branch: str) -> dict:
    return {
        "packet_id": packet_id,
        "branch": branch,
        "commit_hash": "abc123",
        "files_changed": ["automation/forex_engine/file.py", "tests/forex_engine/test_file.py"],
        "tests_run": "python -m pytest tests/forex_engine -q -p no:cacheprovider",
        "tests_blocked": ["tests/forex_engine/test_flaky.py"],
        "validation_results": ["git diff --check"],
        "safety_flags": ["no broker/OANDA/webhook/order/secrets actions", "no runtime mutation"],
        "requested_next_action": "Run reviewed PowerShell block after Anthony approval.",
    }


def _init_relay_repo(tmp_root: Path) -> Path:
    repo = tmp_root / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    return repo


def test_relay_report_dry_run_does_not_write(tmp_path: Path) -> None:
    repo = _init_relay_repo(tmp_path)

    payload = _build_report_payload("AIOS-RELAY-DRY-01", "feature/relay-test")
    result = _run_powershell_json(
        REPORT_SCRIPT,
        [
            "-PacketId",
            payload["packet_id"],
            "-Branch",
            payload["branch"],
            "-Mode",
            "DRY_RUN",
            "-CodexReportText",
            json.dumps(payload),
        ],
        repo,
    )

    assert result["schema"] == "AIOS_CODEX_RELAY_REPORT_ITEM.v1"
    assert result["writes_files"] is False
    assert result["mode"] == "DRY_RUN_READ_ONLY"
    assert "write_preview" in result
    assert not (repo / "control" / "review_bridge" / "codex_reports").exists()


def test_relay_report_apply_writes_control_report_item(tmp_path: Path) -> None:
    repo = _init_relay_repo(tmp_path)
    packet_id = "AIOS-RELAY-APPLY-02"

    result = _run_powershell_json(
        REPORT_SCRIPT,
        [
            "-PacketId",
            packet_id,
            "-Branch",
            "feature/relay-test",
            "-Mode",
            "APPLY",
            "-CodexReportText",
            json.dumps(_build_report_payload(packet_id, "feature/relay-test")),
        ],
        repo,
    )

    assert result["writes_files"] is True
    relay_file = Path(result["relay_file"])
    assert relay_file.exists()
    assert relay_file.parent == repo / "control" / "review_bridge" / "codex_reports"
    assert relay_file.suffix == ".json"
    obj = json.loads(relay_file.read_text(encoding="utf-8-sig"))
    assert obj["packet_id"] == packet_id


def test_prompt_bridge_builds_required_phrase_and_fields(tmp_path: Path) -> None:
    repo = _init_relay_repo(tmp_path)
    packet_id = "AIOS-RELAY-PROMPT-03"

    result = _run_powershell_json(
        REPORT_SCRIPT,
        [
            "-PacketId",
            packet_id,
            "-Branch",
            "feature/relay-test",
            "-Mode",
            "APPLY",
            "-CodexReportText",
            json.dumps(_build_report_payload(packet_id, "feature/relay-test")),
        ],
        repo,
    )
    relay_file = Path(result["relay_file"])
    prompt_out = _run_powershell_json(
        PROMPT_SCRIPT,
        ["-PacketId", packet_id, "-OutputJson"],
        repo,
    )

    assert "ChatGPT must review this Codex report and return one PowerShell block only." in prompt_out["requested_chatgpt_review"]
    assert prompt_out["mode"] == "DRY_RUN_READ_ONLY"
    assert prompt_out["packet_id"] == packet_id
    assert prompt_out["branch"] == "feature/relay-test"
    assert "automation/forex_engine/file.py" in prompt_out["prompt_text"]
    assert "python -m pytest tests/forex_engine -q -p no:cacheprovider" in prompt_out["prompt_text"]
    assert "no broker/OANDA/webhook/order/secrets actions" in prompt_out["prompt_text"]
    assert relay_file.exists()
    assert relay_file.is_relative_to(repo / "control" / "review_bridge")


def test_prompt_bridge_as_prompt_block_contains_phrase(tmp_path: Path) -> None:
    repo = _init_relay_repo(tmp_path)
    packet_id = "AIOS-RELAY-PROMPT-04"

    _run_powershell_json(
        REPORT_SCRIPT,
        [
            "-PacketId",
            packet_id,
            "-Branch",
            "main",
            "-Mode",
            "APPLY",
            "-CodexReportText",
            json.dumps(_build_report_payload(packet_id, "main")),
        ],
        repo,
    )
    raw = _run_powershell_text(
        PROMPT_SCRIPT,
        ["-PacketId", packet_id, "-AsPromptBlock"],
        repo,
    )

    assert raw.startswith("```powershell")
    assert raw.rstrip().endswith("```")
    assert "ChatGPT must review this Codex report and return one PowerShell block only." in raw


def test_prompt_bridge_next_action_from_pasteback(tmp_path: Path) -> None:
    repo = _init_relay_repo(tmp_path)
    packet_id = "AIOS-RELAY-NEXT-05"

    _run_powershell_json(
        REPORT_SCRIPT,
        [
            "-PacketId",
            packet_id,
            "-Branch",
            "feature/relay-test",
            "-Mode",
            "APPLY",
            "-CodexReportText",
            json.dumps(_build_report_payload(packet_id, "feature/relay-test")),
        ],
        repo,
    )
    _run_powershell_json(
        PASTEBACK_SCRIPT,
        [
            "-PacketId",
            packet_id,
            "-Mode",
            "APPLY",
            "-ReviewedPowerShellText",
            "powershell -NoProfile -ExecutionPolicy Bypass -Command Write-Output \"ok\"",
        ],
        repo,
    )

    prompt_out = _run_powershell_json(
        PROMPT_SCRIPT,
        ["-PacketId", packet_id, "-ShowNextAction", "-OutputJson"],
        repo,
    )
    assert prompt_out["next_action"]["packet_id"] == packet_id
    assert prompt_out["next_action"]["pasteback_passed_safety_scan"] is True
    assert "powershell -NoProfile -ExecutionPolicy Bypass -File" in prompt_out["next_action"]["exact_next_command"]


def test_pasteback_rejects_force_push(tmp_path: Path) -> None:
    repo = _init_relay_repo(tmp_path)
    result = _run_powershell_json(
        PASTEBACK_SCRIPT,
        [
            "-PacketId",
            "AIOS-RELAY-BLOCK-06",
            "-Mode",
            "DRY_RUN",
            "-ReviewedPowerShellText",
            "git push --force origin feature/relay-test",
        ],
        repo,
    )

    assert result["safety_scan_passed"] is False
    assert any("unsafe command" in item.lower() for item in result["blocked_actions"])


def test_pasteback_rejects_git_add_dot(tmp_path: Path) -> None:
    repo = _init_relay_repo(tmp_path)
    result = _run_powershell_json(
        PASTEBACK_SCRIPT,
        [
            "-PacketId",
            "AIOS-RELAY-BLOCK-07",
            "-Mode",
            "DRY_RUN",
            "-ReviewedPowerShellText",
            "git add .",
        ],
        repo,
    )

    assert result["safety_scan_passed"] is False
    assert any("git add ." in item for item in result["blocked_actions"])


def test_pasteback_rejects_secret_like_strings(tmp_path: Path) -> None:
    repo = _init_relay_repo(tmp_path)
    result = _run_powershell_json(
        PASTEBACK_SCRIPT,
        [
            "-PacketId",
            "AIOS-RELAY-BLOCK-08",
            "-Mode",
            "DRY_RUN",
            "-ReviewedPowerShellText",
            "git push origin feature/relay-test -m \"AIOS_TG_BOT_TOKEN=abc\"",
        ],
        repo,
    )

    assert result["safety_scan_passed"] is False
    assert any("Potential secret token" in item for item in result["blocked_actions"])


def test_pasteback_requires_manual_execution_and_no_runtime_mutation_strings(tmp_path: Path) -> None:
    repo = _init_relay_repo(tmp_path)
    result = _run_powershell_json(
        PASTEBACK_SCRIPT,
        [
            "-PacketId",
            "AIOS-RELAY-MANUAL-09",
            "-Mode",
            "APPLY",
            "-ReviewedPowerShellText",
            "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/review_bridge/Invoke-AiOsCodexChatGptRelay.DRY_RUN.ps1 -Latest",
        ],
        repo,
    )

    assert result["safety_scan_passed"] is True
    assert result["writes_files"] is True
    assert result["exact_next_safe_action"] == "No automatic execution in AI_OS. Paste the reviewed command manually in PowerShell."
    pb_file = Path(result["pasteback_file"])
    assert pb_file.exists()
    assert pb_file.parent == repo / "control" / "review_bridge" / "pasteback"
    source = pb_file.read_text(encoding="utf-8-sig")
    assert "requires_manual_execution" in source
