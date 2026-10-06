import subprocess
import sys
from pathlib import Path


def test_runner_help_is_available_and_read_only():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/forex_delivery/run_forex_cross_pair_residual_cointegration_v1.py"), "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--dataset-root" in result.stdout
    assert "--packet-path" in result.stdout


def test_runner_source_has_no_network_or_broker_imports():
    root = Path(__file__).resolve().parents[2]
    source = (root / "scripts/forex_delivery/run_forex_cross_pair_residual_cointegration_v1.py").read_text(encoding="utf-8")
    assert "requests" not in source
    assert "socket" not in source
