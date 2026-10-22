#!/usr/bin/env python3
"""CLI entrypoint for the deterministic multi-pair M5 replay bridge."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_multipair_m5_replay_v1 import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
