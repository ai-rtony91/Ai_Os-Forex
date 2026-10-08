#!/usr/bin/env python3
"""Run the repo-safe Forex bait factory."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from automation.forex_engine.forex_bait_factory_v1 import (  # noqa: E402
    build_report_markdown,
    run_forex_bait_factory_v1,
)
STATE_NAME = "AIOS_FOREX_BAIT_FACTORY_V1_STATE.json"
REPORT_NAME = "AIOS_FOREX_BAIT_FACTORY_V1_REPORT.md"
DEFAULT_OUTPUT_ROOT = ROOT / "Reports" / "forex_delivery"
def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    result.add_argument("--target-bait", type=int, default=3)
    result.add_argument("--cycles", type=int, default=1)
    result.add_argument("--write-state", action="store_true")
    result.add_argument("--write-report", action="store_true")
    return result
def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.cycles < 1 or args.target_bait < 1:
        print("invalid positive cycle or target value", file=sys.stderr)
        return 2
    result = run_forex_bait_factory_v1(
        target_bait_count=args.target_bait,
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
    print(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
