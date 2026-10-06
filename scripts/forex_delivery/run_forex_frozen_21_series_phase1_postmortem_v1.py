from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_frozen_21_series_phase1_postmortem_v1 import run_postmortem


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--next-family-plan-path", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--expected-dataset-id", required=True)
    parser.add_argument("--expected-dataset-hash", required=True)
    args = parser.parse_args()
    receipt = run_postmortem(args.input_root, args.output_root, args.report_path, args.next_family_plan_path, args.source_head, args.expected_dataset_id, args.expected_dataset_hash)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
