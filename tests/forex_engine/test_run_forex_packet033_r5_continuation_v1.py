from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


RUNNER = Path("scripts/forex_delivery/run_forex_packet033_r5_continuation_v1.py")


def test_runner_records_task_and_writes_checkpoint_bundle(tmp_path: Path):
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--output-root",
            str(tmp_path),
            "--record-task",
            "T01",
            "--productive-seconds",
            "15",
            "--started-at-utc",
            "2026-08-31T13:00:00Z",
            "--ended-at-utc",
            "2026-08-31T13:00:15Z",
            "--evidence",
            "preflight:PASS",
            "--current-lock",
            "LOCK-A",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(result.stdout)
    assert output["last_completed_task"] == "T01"
    assert output["first_incomplete_task"] == "T02"
    assert output["current_lock"] == "LOCK-A"
    assert (tmp_path / "AIOS_FOREX_PACKET033_R5_TASK_LEDGER.json").exists()


def test_runner_verifies_valid_and_tampered_ledgers_without_writing(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    create = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--output-root",
            str(tmp_path / "checkpoint"),
            "--record-task",
            "T01",
            "--productive-seconds",
            "1",
            "--started-at-utc",
            "2026-08-31T13:00:00Z",
            "--ended-at-utc",
            "2026-08-31T13:00:01Z",
            "--evidence",
            "preflight:PASS",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    checkpoint_ledger = tmp_path / "checkpoint" / "AIOS_FOREX_PACKET033_R5_TASK_LEDGER.json"
    ledger_path.write_text(checkpoint_ledger.read_text(encoding="utf-8"), encoding="utf-8")
    valid = subprocess.run(
        [sys.executable, str(RUNNER), "--task-ledger", str(ledger_path), "--verify-ledger"],
        capture_output=True,
        text=True,
    )
    assert valid.returncode == 0
    assert json.loads(valid.stdout)["status"] == "PASS"

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["entries"][0]["productive_seconds"] = 999
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    invalid = subprocess.run(
        [sys.executable, str(RUNNER), "--task-ledger", str(ledger_path), "--verify-ledger"],
        capture_output=True,
        text=True,
    )
    assert invalid.returncode == 1
    assert json.loads(invalid.stdout)["status"] == "FAIL"
    assert not (tmp_path / "AIOS_FOREX_PACKET033_R5_CHECKPOINT_STATE.json").exists()
