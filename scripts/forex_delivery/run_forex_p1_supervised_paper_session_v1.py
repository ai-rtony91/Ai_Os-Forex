#!/usr/bin/env python3
"""One-command local CLI for the supervised P1 paper session."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from automation.forex_engine.forex_p1_supervised_paper_session_v1 import (  # noqa: E402
    abort_paper_session, build_session_state, close_paper_session, open_paper_session,
    render_owner_report, stable_json, validate_market_snapshot,
)

RUNTIME = ROOT / ".aios/runtime/forex_p1_supervised_paper_sessions/active.json"
MAX_BYTES = 1_000_000


def load_json(name: str) -> dict:
    path = Path(name)
    if not path.is_absolute(): path = ROOT / path
    resolved = path.resolve(strict=True)
    if path.is_symlink() or ROOT not in resolved.parents or resolved.stat().st_size > MAX_BYTES:
        raise ValueError("unsafe_input_path")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    return json.loads(resolved.read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid_constant_{value}")))


def pipeline_paths() -> dict[str, Path]:
    base = ROOT / "Reports/forex_delivery"
    return {"ledger": base / "AIOS_FOREX_P1_SUPERVISED_PAPER_EVIDENCE_LEDGER_V1.json", "state": base / "AIOS_FOREX_P1_SUPERVISED_PAPER_EVIDENCE_PIPELINE_V1_STATE.json", "report": base / "AIOS_FOREX_P1_SUPERVISED_PAPER_EVIDENCE_PIPELINE_V1_REPORT.md", "events": ROOT / "Reports/orchestration/AIOS_ENGINEERING_VELOCITY_EVENT_LOG_V1.jsonl"}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(); commands = root.add_subparsers(dest="command", required=True)
    op = commands.add_parser("open"); op.add_argument("snapshot"); op.add_argument("candidate"); op.add_argument("--reviewer", required=True); op.add_argument("--as-of", required=True)
    cl = commands.add_parser("close"); cl.add_argument("snapshot"); cl.add_argument("--exit-reason", required=True); cl.add_argument("--reviewer", required=True); cl.add_argument("--review-utc", required=True)
    commands.add_parser("status"); commands.add_parser("abort"); commands.add_parser("report")
    val = commands.add_parser("validate-snapshot"); val.add_argument("snapshot")
    return root


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.command == "open": result = open_paper_session(load_json(args.snapshot), load_json(args.candidate), args.reviewer, args.as_of, RUNTIME)
    elif args.command == "close": result = close_paper_session(load_json(args.snapshot), args.exit_reason, args.reviewer, args.review_utc, RUNTIME, pipeline_paths(), ROOT)
    elif args.command == "abort": result = abort_paper_session(RUNTIME)
    elif args.command == "validate-snapshot": result = validate_market_snapshot(load_json(args.snapshot))
    else:
        result = build_session_state(RUNTIME)
        if args.command == "report": print(render_owner_report(result), end=""); return 0
    print(stable_json(result), end=""); return 0


if __name__ == "__main__": raise SystemExit(main())
