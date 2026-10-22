#!/usr/bin/env python3
"""Owner-started, GET-only launcher for the isolated PAPER market observer.

The ``start`` command is intentionally explicit: it needs both the owner
PAPER confirmation and existing runtime-only Practice environment variables.
It never displays or writes either credential and cannot create a broker order.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_persistent_all_pairs_m1_m2_observer_v1 import (  # noqa: E402
    DEFAULT_RUNTIME_ROOT,
    OBSERVATION_SECONDS,
    RUNTIME_IDENTITY,
    SAFETY,
    SUPPORTED_GRANULARITIES,
    VERSION,
    ObserverConfig,
    PersistentObserver,
    eligible_forex_instruments,
    render_live_summary,
)
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-universe", help="Validate a sanitized instrument fixture offline.")
    validate.add_argument("--instrument-payload", type=Path, required=True)
    start = commands.add_parser("start", help="Start one observer-only Practice GET process.")
    start.add_argument("--owner-started-paper-only", action="store_true")
    start.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    start.add_argument("--require-m5-regime", action="store_true")
    start.add_argument("--candle-budget", type=int, default=12)
    start.add_argument("--paper-units", type=int, default=100)
    start.add_argument("--stop-file", type=Path)
    return parser


def _read_practice_client() -> OandaReadOnlyClient:
    token, account_id = os.environ.get("OANDA_API_TOKEN"), os.environ.get("OANDA_ACCOUNT_ID")
    if not token or not account_id:
        raise RuntimeError("practice_runtime_credentials_missing")
    return OandaReadOnlyClient(api_token=token, account_id=account_id, environment="practice")


def _compact_cycle(cycle: dict) -> str:
    ny_time = cycle["cycle_timestamp_utc"].replace("Z", "+00:00")
    from datetime import datetime
    local = datetime.fromisoformat(ny_time).astimezone(ZoneInfo("America/New_York"))
    header = f"{local.isoformat(timespec='milliseconds')} | UTC {cycle['cycle_timestamp_utc']}"
    return header + "\n" + render_live_summary(cycle["health"], cycle["decisions"])


def _start(args: argparse.Namespace) -> int:
    if not args.owner_started_paper_only:
        raise RuntimeError("explicit_owner_paper_only_confirmation_required")
    stop_file = args.stop_file or (args.runtime_root / "STOP")
    if stop_file.exists():
        raise RuntimeError("observer_stop_file_active")
    client = _read_practice_client()
    config = ObserverConfig(
        paper_units=args.paper_units, candle_budget=args.candle_budget,
        require_m5_regime=args.require_m5_regime,
    )
    observer = PersistentObserver(client, runtime_root=args.runtime_root, config=config)
    observer.start()
    try:
        for cycle in observer.run_forever(stop_requested=stop_file.exists):
            print(_compact_cycle(cycle), flush=True)
    except KeyboardInterrupt:
        print("OBSERVER STOPPED: OWNER_INTERRUPT", flush=True)
    finally:
        observer.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate-universe":
        payload = json.loads(args.instrument_payload.read_text(encoding="utf-8"))
        print(json.dumps({
            "observer_version": VERSION, "runtime_identity": RUNTIME_IDENTITY,
            "target_observation_seconds": OBSERVATION_SECONDS,
            "completed_candle_timeframes": sorted(SUPPORTED_GRANULARITIES),
            "launch_status": "NOT_LAUNCHED_BY_OFFLINE_VALIDATOR", "universe": eligible_forex_instruments(payload),
            **SAFETY,
        }, indent=2, sort_keys=True))
        return 0
    return _start(args)


if __name__ == "__main__":
    raise SystemExit(main())
