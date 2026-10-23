#!/usr/bin/env python3
"""Run the normalized all-pairs PAPER collector."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_p1_multipair_normalized_paper_campaign_v1 import (
    RUNTIME_ROOT,
    run_normalized_multipair_campaign,
    summarize_campaign_state,
)
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run the normalized all-pairs PAPER collector.")
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument("--runtime-root", type=Path, default=ROOT / RUNTIME_ROOT)
    result.add_argument("--cycles", type=int, default=288)
    result.add_argument("--reviewer", default="Human Owner Anthony")
    result.add_argument("--report-json", action="store_true")
    return result


def _runtime_environment_value(name: str) -> str:
    return os.environ.get(name, "")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    token = _runtime_environment_value("OANDA_API_TOKEN")
    account = _runtime_environment_value("OANDA_ACCOUNT_ID")
    if not token or not account:
        print("RUNTIME_CREDENTIAL_OR_PRACTICE_DATA_REQUIRED")
        return 2
    client = OandaReadOnlyClient(api_token=token, account_id=account, environment="practice")
    state = run_normalized_multipair_campaign(
        client,
        cycles=args.cycles,
        reviewer_identity=args.reviewer,
        runtime_root=args.runtime_root,
    )
    summary = summarize_campaign_state(state)
    if args.report_json:
        import json

        print(json.dumps(summary, indent=2, sort_keys=True), end="\n")
    else:
        for key, value in summary.items():
            print(f"{key}: {value}")
    if str(state.get("segment_status", "")).upper() == "FAILED" or int(state.get("segment_internal_evaluation_errors", 0) or 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
