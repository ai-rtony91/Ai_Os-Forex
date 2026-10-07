from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


if __name__ == "__main__":
    runpy.run_module("automation.forex_engine.forex_frozen_runtime_restore_verifier_v1", run_name="__main__")
