import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_currency_factor_regime_allocation_v1 import research, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--packet-path", required=True, type=Path)
    parser.add_argument("--predecessor-rejection", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--rejection-path", required=True, type=Path)
    args = parser.parse_args()
    result = research(args.dataset_root, args.packet_path, args.predecessor_rejection)
    receipt = write_outputs(
        result,
        args.output_root,
        args.report_path,
        args.rejection_path,
        ROOT / "automation/forex_engine/forex_currency_factor_regime_allocation_v1.py",
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
