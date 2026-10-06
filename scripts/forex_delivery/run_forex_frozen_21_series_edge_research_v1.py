"""CLI for the frozen 21-series Phase 1 offline research boundary."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine.forex_frozen_21_series_edge_research_v1 import (  # noqa: E402
    EXPECTED_HEAD,
    ResearchBlocked,
    run_phase1,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run bounded offline Phase 1 research on the exact frozen AIOS Forex dataset.")
    sub = result.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--dataset-root", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--source-head", default=EXPECTED_HEAD)
    run.add_argument("--state-path", type=Path, default=Path("Reports/forex_delivery/AIOS_FOREX_FROZEN_21_SERIES_EDGE_RESEARCH_V1_STATE.json"))
    run.add_argument("--report-path", type=Path, default=Path("Reports/forex_delivery/AIOS_FOREX_FROZEN_21_SERIES_EDGE_RESEARCH_V1_REPORT.md"))
    run.add_argument("--skip-file-hashes", action="store_true", help=argparse.SUPPRESS)
    run.add_argument("--restart-invalid-checkpoint", action="store_true", help=argparse.SUPPRESS)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)

    def progress(series: str, completed: int, total: int, candles: int) -> None:
        print(f"PHASE1_PROGRESS series={series} completed={completed}/{total} candles_streamed={candles}", flush=True)

    try:
        state = run_phase1(
            dataset_root=args.dataset_root,
            output_root=args.output_root,
            state_path=args.state_path,
            report_path=args.report_path,
            source_head=args.source_head,
            verify_files=not args.skip_file_hashes,
            restart_invalid_checkpoint=args.restart_invalid_checkpoint,
            progress=progress,
        )
    except ResearchBlocked as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    summary = {
        "status": state["status"], "dataset_id": state["dataset_id"],
        "dataset_sha256": state["dataset_sha256"], "series_processed": state["series_processed"],
        "candles_streamed": state["candles_streamed"], "candidate_count": state["candidate_count"],
        "survivor_count": state["survivor_count"], "survivors": state["survivors"],
        "sealed_holdout_status": state["sealed_holdout_status"],
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if state["status"] != "BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
