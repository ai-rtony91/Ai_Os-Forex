#!/usr/bin/env python3
"""Run one local supervised paper-evidence intake cycle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_p1_supervised_paper_evidence_pipeline_v1 import run_pipeline  # noqa: E402

LEDGER = ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_SUPERVISED_PAPER_EVIDENCE_LEDGER_V1.json"
STATE = ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_SUPERVISED_PAPER_EVIDENCE_PIPELINE_V1_STATE.json"
REPORT = ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_SUPERVISED_PAPER_EVIDENCE_PIPELINE_V1_REPORT.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Local JSON containing sanitized records")
    args = parser.parse_args()
    result = run_pipeline(args.input, LEDGER, STATE, REPORT)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
