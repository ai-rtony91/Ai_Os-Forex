#!/usr/bin/env python3
"""Owner-started, read-only OANDA Practice M5 capture and signal loop."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_p1_eurusd_m5_history_capture_v1 import (  # noqa: E402
    RUNTIME_PATH, build_canonical_history_artifact, extract_canonical_completed_candles,
    resolve_canonical_practice_transport, stable_json, validate_canonical_history_artifact,
)
from automation.forex_engine.forex_p1_eurusd_market_history_signal_v1 import (  # noqa: E402
    build_signal_state,
)
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient  # noqa: E402

INTERVAL_SECONDS = 300
HISTORY_PATH = ROOT / RUNTIME_PATH
SIGNAL_PATH = ROOT / ".aios/runtime/forex_signals/EUR_USD_P1_current.json"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, newline="\n"
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def run_cycle(client: OandaReadOnlyClient, *, now: datetime | None = None,
              write: Callable[[Path, str], None] = _atomic_write) -> dict:
    """Capture completed M5 candles and atomically publish history then signal."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    transport = resolve_canonical_practice_transport(client)
    payload = transport.candles("EUR_USD", granularity="M5", count=50)
    candles = extract_canonical_completed_candles(payload)
    history = build_canonical_history_artifact(candles, requested_count=50)
    history = validate_canonical_history_artifact(history, now=current)
    generated_at = current.isoformat().replace("+00:00", "Z")
    signal = build_signal_state(history, generated_at_utc=generated_at)
    write(HISTORY_PATH, stable_json(history))
    write(SIGNAL_PATH, stable_json(signal))
    return {
        "status": "CAPTURED_AND_EVALUATED",
        "generated_at_utc": generated_at,
        "candle_count": len(candles),
        "signal_status": signal["status"],
        "history_path": RUNTIME_PATH,
        "signal_path": str(SIGNAL_PATH.relative_to(ROOT)).replace("\\", "/"),
        "read_only": True,
        "broker_write_performed": False,
        "order_submission_allowed": False,
    }


def run_loop(client: OandaReadOnlyClient, *, cycles: int,
             sleep: Callable[[float], None] = time.sleep,
             cycle: Callable[..., dict] = run_cycle) -> list[dict]:
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles <= 0:
        raise ValueError("positive_cycle_count_required")
    results = []
    for index in range(cycles):
        results.append(cycle(client))
        if index + 1 < cycles:
            sleep(INTERVAL_SECONDS)
    return results


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--owner-local-runtime", action="store_true")
    result.add_argument("--cycles", type=int, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.owner_local_runtime:
        raise ValueError("explicit_owner_local_runtime_required")
    token = os.environ.get("OANDA_API_TOKEN", "")
    if not token:
        raise ValueError("OANDA_API_TOKEN_required_in_owner_process")
    client = OandaReadOnlyClient(
        api_token=token, account_id="", environment="practice"
    )
    results = run_loop(client, cycles=args.cycles)
    print(stable_json({"status": "COMPLETE", "interval_seconds": INTERVAL_SECONDS,
                       "cycles_completed": len(results), "results": results}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
