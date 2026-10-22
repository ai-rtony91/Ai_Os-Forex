"""CLI for one local supervised-paper capture/replay cycle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_p1_supervised_paper_capture_replay_v1 import run_capture_replay


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    result = run_capture_replay(
        args.candidate,
        ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_SUPERVISED_PAPER_CAPTURE_REPLAY_V1_LEDGER.json",
        ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_SUPERVISED_PAPER_CAPTURE_REPLAY_V1_STATE.json",
        ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_SUPERVISED_PAPER_CAPTURE_REPLAY_V1_REPORT.md",
        ROOT / "Reports/orchestration/AIOS_ENGINEERING_VELOCITY_EVENT_LOG_V1.jsonl",
        repository_root=ROOT,
    )
    print(result["capture_status"], result["replay_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
