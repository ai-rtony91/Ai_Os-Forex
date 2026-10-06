from pathlib import Path


def test_runner_exists():
    assert Path("scripts/forex_delivery/run_forex_edge_existence_controller_v1.py").exists()
