#!/usr/bin/env python3
"""Offline-by-default CLI for one owner-local OANDA Practice history capture."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_p1_eurusd_m5_history_capture_v1 import (  # noqa: E402
    RUNTIME_PATH, build_canonical_history_artifact, extract_canonical_completed_candles,
    load_and_validate_approval, resolve_canonical_practice_transport, stable_json,
    validate_canonical_history_artifact, validate_runtime_capture_request,
)
from automation.forex_engine.oanda_practice_candle_history_transport_v1 import (  # noqa: E402
    OandaPracticeCandleHistoryTransportV1,
)

STATE = ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_EURUSD_M5_HISTORY_CAPTURE_V1_STATE.json"
REPORT = ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_EURUSD_M5_HISTORY_CAPTURE_V1_REPORT.md"
RUNTIME_HISTORY = ROOT / RUNTIME_PATH


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON:{value}")))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     delete=False, newline="\n") as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def _canonical_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if path != RUNTIME_HISTORY.resolve():
        raise ValueError("canonical_runtime_path_required")
    return path


def owner_handoff() -> str:
    return r'''Set-Location 'C:\Dev\Ai_Os'
python --version
if ([string]::IsNullOrWhiteSpace($env:OANDA_API_TOKEN)) { throw 'OANDA_API_TOKEN is not present in this process.' }
Write-Host 'OANDA Practice token is present; its value will not be printed.'
python scripts/forex_delivery/run_forex_p1_eurusd_m5_history_capture_v1.py preflight
python scripts/forex_delivery/run_forex_p1_eurusd_m5_history_capture_v1.py capture --owner-local-runtime --approval-file .aios/runtime/forex_authorizations/owner.json --packet-id AIOS-OANDA-PRACTICE-CANDLE-TRANSPORT-HARDENING-APPLY-V1 --environment practice --instrument EUR_USD --granularity M5 --count 50 --output .aios/runtime/forex_market_history/EUR_USD_latest.json
python scripts/forex_delivery/run_forex_p1_eurusd_m5_history_capture_v1.py validate --output .aios/runtime/forex_market_history/EUR_USD_latest.json
Write-Host '.aios/runtime/forex_market_history/EUR_USD_latest.json'
$now = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
Write-Host "python scripts/forex_delivery/run_forex_p1_eurusd_market_history_signal_v1.py evaluate --history .aios/runtime/forex_market_history/EUR_USD_latest.json --output .aios/runtime/forex_signals/EUR_USD_P1_current.json --as-of-utc $now"
Write-Host 'Capture places no order, generates no signal or candidate, and opens no paper session.'
'''


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    commands = result.add_subparsers(dest="command")
    commands.add_parser("preflight")
    capture = commands.add_parser("capture")
    capture.add_argument("--owner-local-runtime", action="store_true")
    capture.add_argument("--approval-file", required=True)
    capture.add_argument("--packet-id", required=True)
    capture.add_argument("--environment", required=True)
    capture.add_argument("--instrument", required=True)
    capture.add_argument("--granularity", required=True)
    capture.add_argument("--count", type=int, default=50)
    capture.add_argument("--output", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--output", required=True)
    commands.add_parser("status")
    commands.add_parser("report")
    commands.add_parser("print-owner-handoff")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    command = args.command or "preflight"
    if command == "preflight":
        value = {"status": "READY", "network_used": False, "credentials_loaded": False,
                 "runtime_write_performed": False, "capture_requires_owner_local_runtime": True,
                 "environment": "practice", "instrument": "EUR_USD", "granularity": "M5"}
    elif command == "status":
        value = _load(STATE)
    elif command == "report":
        print(REPORT.read_text(encoding="utf-8"), end="")
        return 0
    elif command == "print-owner-handoff":
        print(owner_handoff(), end="")
        return 0
    elif command == "validate":
        history = validate_canonical_history_artifact(_load(_canonical_path(args.output)))
        value = {"status": "VALID", "returned_count": history["returned_count"],
                 "network_used": False, "credentials_loaded": False}
    else:
        request = validate_runtime_capture_request(
            owner_local_runtime=args.owner_local_runtime, environment=args.environment,
            instrument=args.instrument, granularity=args.granularity, count=args.count,
            output=args.output,
        )
        load_and_validate_approval(ROOT / args.approval_file, repository_root=ROOT,
                                   packet_id=args.packet_id)
        token = os.environ.get("OANDA_API_TOKEN", "")
        if not token:
            raise ValueError("OANDA_API_TOKEN_required_in_owner_process")
        client = resolve_canonical_practice_transport(OandaPracticeCandleHistoryTransportV1(token))
        payload = client.fetch_eurusd_m5_midpoint_candles()
        candles = extract_canonical_completed_candles(payload)
        artifact = build_canonical_history_artifact(candles, requested_count=request["count"])
        validate_canonical_history_artifact(artifact, now=datetime.now(timezone.utc))
        _atomic_write(_canonical_path(request["output"]), stable_json(artifact))
        value = {"status": "CAPTURED", "returned_count": len(candles),
                 "runtime_path": RUNTIME_PATH, "read_only": True}
    print(stable_json(value), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
