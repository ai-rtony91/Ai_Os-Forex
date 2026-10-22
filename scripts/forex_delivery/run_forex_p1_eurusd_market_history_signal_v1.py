#!/usr/bin/env python3
"""One-shot, offline runner for the EUR_USD market-history signal contract."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from automation.forex_engine.forex_p1_eurusd_market_history_signal_v1 import (  # noqa: E402
    GRANULARITY, MINIMUM_CANDLES, build_signal_state, stable_json,
    validate_market_history,
)

STATE = ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_EURUSD_MARKET_HISTORY_SIGNAL_V1_STATE.json"
REPORT = ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_EURUSD_MARKET_HISTORY_SIGNAL_V1_REPORT.md"
RUNTIME_HISTORY = ROOT / ".aios/runtime/forex_market_history/EUR_USD_latest.json"
RUNTIME_SIGNAL = ROOT / ".aios/runtime/forex_signals/EUR_USD_P1_current.json"


def load_json(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON: {value}")))


def parser():
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="command")
    sub.add_parser("preflight"); sub.add_parser("status"); sub.add_parser("report"); sub.add_parser("print-next-command")
    q = sub.add_parser("validate-history"); q.add_argument("--history", required=True); q.add_argument("--as-of-utc", required=True)
    q = sub.add_parser("evaluate"); q.add_argument("--history", required=True); q.add_argument("--output", required=True); q.add_argument("--as-of-utc", required=True)
    return p


def safe_path(value: str, expected: Path) -> Path:
    path = Path(value).resolve()
    if path != expected.resolve(): raise ValueError(f"runtime_path_required:{expected.relative_to(ROOT)}")
    return path


def main(argv=None):
    args = parser().parse_args(argv); command = args.command or "preflight"
    if command == "preflight":
        value = {"status": "READY_FOR_READ_ONLY_HISTORY_CAPTURE_PACKET", "network_used": False, "credentials_loaded": False,
                 "writes_performed": False, "instrument": "EUR_USD", "granularity": GRANULARITY, "minimum_candles": MINIMUM_CANDLES}
    elif command == "status": value = load_json(STATE)
    elif command == "report": print(REPORT.read_text(encoding="utf-8"), end=""); return 0
    elif command == "print-next-command":
        print(f"python {Path(__file__).relative_to(ROOT)} evaluate --history {RUNTIME_HISTORY.relative_to(ROOT)} --output {RUNTIME_SIGNAL.relative_to(ROOT)} --as-of-utc <CURRENT_UTC_TIMESTAMP>")
        return 0
    else:
        now = datetime.fromisoformat(args.as_of_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
        history_path = safe_path(args.history, RUNTIME_HISTORY)
        history = validate_market_history(load_json(history_path), now=now)
        if command == "validate-history": value = {"status": "VALID", "candle_count": len(history["candles"])}
        else:
            output = safe_path(args.output, RUNTIME_SIGNAL)
            value = build_signal_state(history, generated_at_utc=args.as_of_utc)
            output.parent.mkdir(parents=True, exist_ok=True); output.write_text(stable_json(value), encoding="utf-8")
    print(stable_json(value), end=""); return 0

if __name__ == "__main__": raise SystemExit(main())
