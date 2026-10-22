"""Report-only daily Forex orchestrator artifact helper.

This module reads existing ledger/report inputs and returns summary fields for
the daily orchestrator artifact. It does not place trades, call brokers, read
credentials, read .env, move money, append evidence, clean files, or merge.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SAFETY_STATEMENT = (
    "Report-only artifact summary. No broker calls, no live orders, no credentials, "
    "no .env reads, no money movement, no automatic cleanup, no automatic evidence "
    "append, no automatic merge, no production readiness claim, no trading readiness "
    "claim, no live broker readiness claim, and no profitability claim."
)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _record_date(row: dict[str, Any]) -> str | None:
    for key in ("date", "trade_date", "utc_date"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value[:10]
    value = row.get("freshness_utc") or row.get("exit_time") or row.get("created_utc")
    if isinstance(value, str) and len(value) >= 10:
        return value[:10]
    return None


def _record_type(row: dict[str, Any]) -> str:
    for key in ("record_type", "evidence_type", "type"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return "NO_TYPE"


def _consecutive_count(dates: list[str], today: date) -> int:
    date_set = {_parse_date(item) for item in dates}
    count = 0
    cursor = today
    while cursor in date_set:
        count += 1
        cursor -= timedelta(days=1)
    return count


def _missing_dates(dates: list[str]) -> list[str]:
    if not dates:
        return []
    parsed = sorted({_parse_date(item) for item in dates})
    cursor = parsed[0]
    end = parsed[-1]
    seen = set(parsed)
    missing: list[str] = []
    while cursor <= end:
        if cursor not in seen:
            missing.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return missing


def _window_status(count: int, target: int) -> str:
    if count >= target:
        return "COMPLETE"
    if count > 0:
        return "IN_PROGRESS"
    return "NOT_STARTED"


def _maintenance_summary(repo_root: Path) -> dict[str, Any]:
    try:
        from scripts.forex_delivery.run_forex_runtime_maintenance_workload_execution_plan_v1 import _run
    except Exception as exc:  # pragma: no cover
        return {
            "status": "MAINTENANCE_PLANNER_IMPORT_FAILED",
            "next_best_packet": None,
            "blockers": [str(exc)],
        }

    result = _run("banking false-positive guard")
    return {
        "status": result.get("status"),
        "ready": result.get("ready"),
        "maintenance_plan_enabled": result.get("maintenance_plan_enabled"),
        "current_maintenance_lane": result.get("current_maintenance_lane"),
        "maintenance_window_recommended": result.get("maintenance_window_recommended"),
        "next_best_packet": result.get("next_best_packet"),
        "blockers": result.get("blockers") or [],
    }


def build_artifact_summary(repo_root: Path, today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    ledger_path = repo_root / "telemetry" / "forex" / "demo_proof_ledger.jsonl"
    rows = _load_jsonl(ledger_path)

    real_demo_dates = sorted(
        {
            record_date
            for row in rows
            if _record_type(row) == "REAL_DEMO_DAY"
            for record_date in [_record_date(row)]
            if record_date
        }
    )

    consecutive = _consecutive_count(real_demo_dates, today)
    missing = _missing_dates(real_demo_dates)
    next_required = (today + timedelta(days=1)).isoformat()

    return {
        "ledger_path": ledger_path.relative_to(repo_root).as_posix(),
        "today_utc": today.isoformat(),
        "real_demo_day_dates": real_demo_dates,
        "real_demo_day_count": len(real_demo_dates),
        "consecutive_real_demo_day_count": consecutive,
        "missing_dates": missing,
        "next_required_evidence_date": next_required,
        "five_day_window_status": _window_status(consecutive, 5),
        "thirty_day_window_status": _window_status(consecutive, 30),
        "rolling_continuity_status": (
            "ROLLING_CONTINUITY_IN_PROGRESS"
            if consecutive > 0 and not missing
            else "ROLLING_CONTINUITY_BLOCKED"
        ),
        "maintenance": _maintenance_summary(repo_root),
        "safety_statement": SAFETY_STATEMENT,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--today", default=None)
    args = parser.parse_args()

    today = _parse_date(args.today) if args.today else None
    payload = build_artifact_summary(Path(args.repo_root).resolve(), today=today)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
