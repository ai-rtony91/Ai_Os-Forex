"""CLI entry point for the historical dataset verifier/freezer."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


if __name__ == "__main__":
    runpy.run_module("automation.forex_engine.forex_historical_dataset_verifier_freezer_v1", run_name="__main__")
