from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_frozen_candidate_paper30_v1 import (
    DEFAULT_REPORT_PATH,
    DEFAULT_RUNTIME_ROOT,
    PRACTICE_NETWORK_TIMEOUT_SECONDS,
    run_campaign_segment,
)
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen forward PAPER30 candidate")
    parser.add_argument("--cycles", type=int, default=288)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--reviewer", default="Human Owner Anthony")
    parser.add_argument("--report-json", action="store_true")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    token = os.environ.get("OANDA_API_TOKEN")
    account_id = os.environ.get("OANDA_ACCOUNT_ID")
    if not token or not account_id:
        print("PAPER30_READY_OWNER_CREDENTIAL_ACTION_REQUIRED")
        return 2

    client = OandaReadOnlyClient(
        api_token=token,
        account_id=account_id,
        environment="practice",
        timeout_seconds=PRACTICE_NETWORK_TIMEOUT_SECONDS,
    )
    result = run_campaign_segment(
        client,
        cycles=args.cycles,
        runtime_root=args.runtime_root,
        reviewer=args.reviewer,
        report_path=args.report_path,
    )
    if args.report_json:
        print(json.dumps(result, sort_keys=True, allow_nan=False))
    else:
        print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
