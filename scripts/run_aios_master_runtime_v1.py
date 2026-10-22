#!/usr/bin/env python3
"""Compatibility runner for the root AI_OS command."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aios import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
