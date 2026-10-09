#!/usr/bin/env python3
"""Run the repo-safe Forex edge autopilot."""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from automation.forex_engine.forex_edge_autopilot_v1 import (  # noqa: E402
    build_report_markdown,
    run_forex_edge_autopilot_v1,
)
STATE_NAME = "AIOS_FOREX_EDGE_AUTOPILOT_V1_STATE.json"
REPORT_NAME = "AIOS_FOREX_EDGE_AUTOPILOT_V1_REPORT.md"
DEFAULT_OUTPUT_ROOT = ROOT / "Reports" / "forex_delivery"
def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--report-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    result.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    result.add_argument("--target-candidates", type=int, default=3)
    result.add_argument("--cycles", type=int, default=1)
    result.add_argument("--sleep-seconds", type=float, default=0.0)
    result.add_argument("--write-state", action="store_true")
    result.add_argument("--write-report", action="store_true")
    return result
def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.cycles < 1 or args.target_candidates < 1 or args.sleep_seconds < 0:
        print("invalid positive cycle, target, or sleep value", file=sys.stderr)
        return 2
    result = run_forex_edge_autopilot_v1(
        args.report_root,
        target_candidate_count=args.target_candidates,
        cycles=args.cycles,
    )
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    if args.write_state:
        (output_root / STATE_NAME).write_text(
            json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.write_report:
        (output_root / REPORT_NAME).write_text(build_report_markdown(result), encoding="utf-8")
    if args.sleep_seconds:
        time.sleep(args.sleep_seconds)
    print(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
