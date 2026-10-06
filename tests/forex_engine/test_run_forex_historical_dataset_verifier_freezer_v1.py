from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/forex_delivery/run_forex_historical_dataset_verifier_freezer_v1.py")


def test_cli_wrapper_exposes_verify_and_freeze_help():
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"], text=True, capture_output=True, check=False)
    assert result.returncode == 0
    assert "verify" in result.stdout and "freeze" in result.stdout


def test_cli_wrapper_blocks_invalid_expected_scope_without_writing(tmp_path: Path):
    result = subprocess.run([
        sys.executable, str(SCRIPT), "verify",
        "--source-root", str(tmp_path / "missing"),
        "--expected-scope-fingerprint", "invalid",
        "--expected-start-utc", "2024-01-01T00:00:00Z",
        "--expected-end-utc", "2024-01-02T00:00:00Z",
        "--source-head", "test-head",
        "--output-format", "json",
    ], text=True, capture_output=True, check=False)
    assert result.returncode == 2
    assert '"status":"BLOCKED"' in result.stdout
    assert not (tmp_path / "missing").exists()
