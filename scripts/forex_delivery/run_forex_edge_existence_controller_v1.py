"""CLI runner for Packet 031 edge-existence controller."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    sys.argv = ["forex_edge_existence_controller_v1.py", "--execute"]
    runpy.run_module("automation.forex_engine.forex_edge_existence_controller_v1", run_name="__main__")
