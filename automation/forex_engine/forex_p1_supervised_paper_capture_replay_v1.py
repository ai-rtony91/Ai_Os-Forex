"""One-shot, local-only capture and replay for supervised P1 evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from automation.forex_engine.forex_p1_supervised_paper_evidence_pipeline_v1 import (
    SAFETY_FLAGS as PIPELINE_SAFETY_FLAGS,
    run_pipeline,
)

VERSION = "forex_p1_supervised_paper_capture_replay_v1"
PACKET_ID = "AIOS-P1-SUPERVISED-PAPER-CAPTURE-REPLAY-APPLY-V1"
LANE = "FOREX_PROFIT_TRACK_P1_CAPTURE_REPLAY"
SAFETY_FLAGS = {
    **PIPELINE_SAFETY_FLAGS,
    "continuous_execution_allowed": False,
}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def deterministic_trade_id(record: Mapping[str, Any]) -> str:
    """Return a stable ID without retaining private or source-file metadata."""
    material = {key: value for key, value in record.items() if key != "trade_id"}
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return "p1-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _prepare_input(candidate_path: Path, prepared_path: Path) -> int:
    payload = _json(candidate_path)
    if isinstance(payload, list):
        records: list[Any] = list(payload)
    elif isinstance(payload, Mapping) and isinstance(payload.get("records"), list):
        records = list(payload["records"])
    else:
        records = [payload]
    if len(records) > 1:
        raise ValueError("one_bounded_candidate_required")
    if records and isinstance(records[0], Mapping) and not records[0].get("trade_id"):
        records[0] = {**records[0], "trade_id": deterministic_trade_id(records[0])}
    prepared_path.write_text(json.dumps(records, sort_keys=True), encoding="utf-8")
    return len(records)


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    )
    return completed.stdout.strip()


def _markdown(state: Mapping[str, Any]) -> str:
    metrics = state["replay_metrics"]
    lines = [
        "# AIOS Forex P1 Supervised Paper Capture Replay V1",
        "",
        f"- Capture status: {state['capture_status']}",
        f"- Replay status: {state['replay_status']}",
        f"- Input records: {state['input_records']}",
        f"- Accepted records: {state['accepted_records']}",
        f"- Rejected records: {state['rejected_records']}",
        f"- Duplicate records: {state['duplicate_records']}",
        f"- Qualifying trade count: {state['qualifying_trade_count']}",
        f"- P1 status before: {state['p1_status_before']}",
        f"- P1 status after: {state['p1_status_after']}",
        f"- Win rate: {metrics['win_rate']}",
        f"- Gross profit: {metrics['gross_profit']}",
        f"- Gross loss: {metrics['gross_loss']}",
        f"- Net P/L: {metrics['net_pl']}",
        f"- Expectancy: {metrics['expectancy']}",
        f"- Profit factor: {metrics['profit_factor']}",
        f"- Maximum drawdown: {metrics['maximum_drawdown']}",
        f"- Consecutive losses: {metrics['consecutive_losses']}",
        f"- Profitability proven: {str(state['profitability_proven']).lower()}",
        f"- Ready for P2 review: {str(state['ready_for_p2_review']).lower()}",
        "",
        "## Safety flags",
        "",
    ]
    lines.extend(f"- {key}: {str(state[key]).lower()}" for key in SAFETY_FLAGS)
    lines.extend(["", "This was one local capture/replay cycle. It grants no execution authority.", ""])
    return "\n".join(lines)


def _append_event(path: Path, event: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")


def run_capture_replay(
    candidate_path: Path,
    ledger_path: Path,
    state_path: Path,
    report_path: Path,
    event_log_path: Path,
    *,
    repository_root: Path,
    tests_run: int = 0,
    tests_passed: int = 0,
    tests_failed: int = 0,
) -> dict[str, Any]:
    """Capture at most one candidate, trigger the canonical evaluator, and stop."""
    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    starting_head = _git(repository_root, "rev-parse", "HEAD")
    branch = _git(repository_root, "branch", "--show-current")
    prepared_path = state_path.with_suffix(".input.tmp")
    try:
        input_count = _prepare_input(candidate_path, prepared_path)
        pipeline = run_pipeline(prepared_path, ledger_path, state_path, report_path)
    finally:
        prepared_path.unlink(missing_ok=True)

    evaluator = pipeline["p1_evaluator_result"]
    metrics = {
        "trade_count": evaluator["trade_count"],
        "win_rate": evaluator["win_rate"],
        "gross_profit": evaluator["gross_profit"],
        "gross_loss": evaluator["gross_loss"],
        "net_pl": evaluator["net_pl"],
        "expectancy": evaluator["expectancy_per_trade"],
        "profit_factor": evaluator["profit_factor"],
        "maximum_drawdown": evaluator["maximum_drawdown"],
        "consecutive_losses": evaluator["consecutive_losses"],
    }
    state = {
        "version": VERSION,
        "capture_status": "COMPLETE",
        "replay_status": "CANONICAL_P1_EVALUATOR_COMPLETE",
        "input_records": input_count,
        "accepted_records": pipeline["accepted_records"],
        "rejected_records": pipeline["rejected_records"],
        "duplicate_records": pipeline["duplicate_records"],
        "rejections": pipeline["rejections"],
        "qualifying_trade_count": pipeline["qualifying_trade_count"],
        "p1_status_before": pipeline["p1_status_before"],
        "p1_status_after": pipeline["p1_status_after"],
        "profitability_proven": pipeline["profitability_proven"],
        "ready_for_p2_review": pipeline["ready_for_p2_review"],
        "replay_metrics": metrics,
        **SAFETY_FLAGS,
    }
    ledger = _json(ledger_path)
    ledger.update(SAFETY_FLAGS)
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(_markdown(state), encoding="utf-8")

    completed = datetime.now(timezone.utc)
    event = {
        "packet_id": PACKET_ID,
        "lane": LANE,
        "branch": branch,
        "starting_head": starting_head,
        "ending_head": _git(repository_root, "rev-parse", "HEAD"),
        "started_utc": started.isoformat(),
        "completed_utc": completed.isoformat(),
        "elapsed_seconds": round(time.monotonic() - clock, 6),
        "files_changed_count": 4,
        "lines_added": 0,
        "lines_deleted": 0,
        "tests_run": tests_run,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "blockers_found": 0,
        "blockers_closed": 0,
        "blocker_classifications": [],
        "commit_created": False,
        "pr_created": False,
        "final_status": "COMPLETE",
    }
    _append_event(event_log_path, event)
    state["engineering_metadata_event"] = event
    return state
