import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cli_runs_and_emits_pass_receipt(tmp_path):
    command = [
        sys.executable,
        str(ROOT / "scripts/forex_delivery/run_forex_frozen_21_series_phase1_postmortem_v1.py"),
        "--input-root", str(ROOT / ".aios/runtime/forex_frozen_21_series_edge_research_v1"),
        "--output-root", str(tmp_path / "out"),
        "--report-path", str(tmp_path / "report.md"),
        "--next-family-plan-path", str(tmp_path / "plan.md"),
        "--source-head", "b86c65140ed03d53d6c8d6c3618e50da0502f51b",
        "--expected-dataset-id", "AIOS-FX-HIST-V1-b6a62a1175398354580b",
        "--expected-dataset-hash", "b6a62a1175398354580be3f242cdb67aa3134988b7448c1e1fa11d8abcfb1e7d",
    ]
    result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    assert json.loads(result.stdout)["status"] == "PASS"
    assert (tmp_path / "out/AIOS_FOREX_PHASE1_POSTMORTEM_RECEIPT.json").is_file()


def test_cli_rejects_wrong_dataset(tmp_path):
    command = [sys.executable, str(ROOT / "scripts/forex_delivery/run_forex_frozen_21_series_phase1_postmortem_v1.py"), "--input-root", str(ROOT / ".aios/runtime/forex_frozen_21_series_edge_research_v1"), "--output-root", str(tmp_path / "out"), "--report-path", str(tmp_path / "r"), "--next-family-plan-path", str(tmp_path / "p"), "--source-head", "head", "--expected-dataset-id", "wrong", "--expected-dataset-hash", "wrong"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
