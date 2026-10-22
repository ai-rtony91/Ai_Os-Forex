#!/usr/bin/env python3
"""Offline-only runner for the dedicated Supertrend 30-trade PAPER campaign.

The runner accepts already-closed, sanitized PAPER records.  It has no market
data client, credential loader, broker adapter, order path, scheduler, or worker
launcher.  Generic P1 capture/replay is reused only as a validation engine; all
campaign identity, files, counts, and reports remain Supertrend-specific.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_p1_supervised_paper_campaign_v1 import (  # noqa: E402
    CampaignPaths,
    TARGET_QUALIFYING_TRADES,
    run_campaign,
)
from automation.forex_engine.forex_p1_supervised_paper_evidence_pipeline_v1 import (  # noqa: E402
    REQUIRED_FIELDS as PIPELINE_REQUIRED_FIELDS,
)
from automation.forex_engine.strategies import (  # noqa: E402
    SUPERTREND_PULLBACK_V1,
    SupertrendPullbackConfig,
)

VERSION = "forex_p1_supertrend_paper_campaign_v1"
CAMPAIGN_ID = "AIOS-FOREX-P1-SUPERTREND-30-TRADE-PAPER-CAMPAIGN-V1"
STRATEGY_NAME = SUPERTREND_PULLBACK_V1
CANONICAL_CONFIG = SupertrendPullbackConfig()
ATR_PERIOD = CANONICAL_CONFIG.atr_period
MULTIPLIER = CANONICAL_CONFIG.supertrend_multiplier
REQUIRED_QUALIFYING_TRADES = TARGET_QUALIFYING_TRADES
MODE = "PAPER_ONLY"

SAFETY = {
    "paper_only": True,
    "live_trading_allowed": False,
    "practice_order_allowed": False,
    "live_order_allowed": False,
    "broker_call_performed": False,
    "broker_write_performed": False,
    "practice_order_performed": False,
    "live_trade_performed": False,
    "money_movement_performed": False,
    "credentials_loaded": False,
    "credentials_persisted": False,
    "network_access_performed": False,
    "runtime_worker_launched": False,
}

FORBIDDEN_TRUE_FIELDS = (
    "broker_call_performed",
    "broker_write_performed",
    "practice_order_performed",
    "live_trade_performed",
    "money_movement_performed",
    "credentials_loaded",
    "credentials_persisted",
    "network_access_performed",
    "order_submission_allowed",
    "demo_execution_allowed",
    "live_execution_allowed",
)

OUTPUT_NAMES = {
    "candidate": ".AIOS_FOREX_SUPERTREND_30_TRADE_CANDIDATE.tmp.json",
    "ledger": "AIOS_FOREX_SUPERTREND_30_TRADE_LEDGER.json",
    "replay_state": "AIOS_FOREX_SUPERTREND_30_TRADE_REPLAY_STATE.json",
    "replay_report": "AIOS_FOREX_SUPERTREND_30_TRADE_REPLAY_REPORT.md",
    "event_log": "AIOS_FOREX_SUPERTREND_30_TRADE_EVENTS.jsonl",
    "campaign_state": "AIOS_FOREX_SUPERTREND_30_TRADE_CAMPAIGN_STATE.json",
    "campaign_report": "AIOS_FOREX_SUPERTREND_30_TRADE_CAMPAIGN_REPORT.md",
    "weekly_report": "AIOS_FOREX_SUPERTREND_WEEKLY_PAPER_EVIDENCE_REPORT.md",
}


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _number_matches(value: Any, expected: float) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number == float(expected)


def validate_supertrend_record(record: Mapping[str, Any]) -> list[str]:
    """Return deterministic fail-closed reasons for one campaign record."""
    reasons: list[str] = []
    strategy = str(record.get("strategy_name") or record.get("strategy_id") or "").strip()
    if strategy != STRATEGY_NAME:
        reasons.append("canonical_strategy_name_required")
    if str(record.get("mode", "")).upper() != MODE:
        reasons.append("paper_only_mode_required")
    if record.get("paper_only") is not True:
        reasons.append("paper_only_true_required")
    if str(record.get("evidence_type", "")).lower() != "paper":
        reasons.append("paper_evidence_type_required")

    config = record.get("strategy_config")
    if not isinstance(config, Mapping):
        reasons.append("strategy_config_required")
    else:
        if not _number_matches(config.get("atr_period"), ATR_PERIOD):
            reasons.append("canonical_atr_period_3_required")
        if not _number_matches(config.get("multiplier"), MULTIPLIER):
            reasons.append("canonical_multiplier_2_required")

    for field in FORBIDDEN_TRUE_FIELDS:
        if record.get(field) is True:
            reasons.append(f"forbidden_{field}")
    return sorted(set(reasons))


def validate_supertrend_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    blockers: list[str] = []
    for index, record in enumerate(records, start=1):
        reasons = validate_supertrend_record(record)
        trade_id = str(record.get("trade_id", "")).strip()
        if not trade_id:
            reasons.append("trade_id_required")
        elif trade_id in seen:
            reasons.append("duplicate_trade_id")
        seen.add(trade_id)
        reasons = sorted(set(reasons))
        results.append({"record_number": index, "trade_id": trade_id or None, "reasons": reasons})
        blockers.extend(f"record_{index}:{reason}" for reason in reasons)
    return {
        "campaign_id": CAMPAIGN_ID,
        "strategy_name": STRATEGY_NAME,
        "mode": MODE,
        "paper_only": True,
        "atr_period": ATR_PERIOD,
        "multiplier": MULTIPLIER,
        "required_qualifying_trades": REQUIRED_QUALIFYING_TRADES,
        "input_records": len(records),
        "validation_status": "PASS" if not blockers else "BLOCKED",
        "record_results": results,
        "blockers": blockers,
        "writes_performed": 0,
        **SAFETY,
    }


def _normalize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    # The shared evidence pipeline rejects credential-shaped field names even
    # when their values are false.  Keep its one-record intake limited to the
    # evidence plus non-sensitive Supertrend identity; campaign safety flags
    # belong on the resulting state, not on an intake record.
    return {
        **{field: record[field] for field in PIPELINE_REQUIRED_FIELDS if field in record},
        "strategy_id": STRATEGY_NAME,
        "strategy_name": STRATEGY_NAME,
        "mode": MODE,
        "paper_only": True,
        "strategy_config": {"atr_period": ATR_PERIOD, "multiplier": MULTIPLIER},
    }


def _add_campaign_identity_to_ledger(path: Path) -> list[dict[str, Any]]:
    """Persist canonical identity on accepted records after shared validation."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not isinstance(payload.get("records"), list):
        raise ValueError("invalid_supertrend_campaign_ledger")
    records = [
        {
            **dict(record),
            "campaign_id": CAMPAIGN_ID,
            "strategy_name": STRATEGY_NAME,
            "mode": MODE,
            "paper_only": True,
            "strategy_config": {"atr_period": ATR_PERIOD, "multiplier": MULTIPLIER},
        }
        for record in payload["records"]
    ]
    path.write_text(stable_json({**dict(payload), "records": records}), encoding="utf-8")
    return records


def campaign_paths(output_root: Path) -> CampaignPaths:
    return CampaignPaths(
        candidate=output_root / OUTPUT_NAMES["candidate"],
        ledger=output_root / OUTPUT_NAMES["ledger"],
        replay_state=output_root / OUTPUT_NAMES["replay_state"],
        replay_report=output_root / OUTPUT_NAMES["replay_report"],
        event_log=output_root / OUTPUT_NAMES["event_log"],
        campaign_state=output_root / OUTPUT_NAMES["campaign_state"],
        campaign_report=output_root / OUTPUT_NAMES["campaign_report"],
    )


def _outside_repository(path: Path, repository_root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(repository_root.resolve())
    except ValueError:
        return resolved
    raise ValueError("campaign_output_root_must_be_outside_repository")


def _week_id(timestamp: str) -> str:
    value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    year, week, _ = value.isocalendar()
    return f"{year}-W{week:02d}"


def weekly_evidence(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_week_id(str(record["exit_timestamp_utc"]))].append(record)
    rows: list[dict[str, Any]] = []
    for week, items in sorted(grouped.items()):
        pnl = [float(item["realized_pl"]) for item in items]
        rows.append({
            "iso_week": week,
            "qualifying_trades": len(items),
            "wins": sum(value > 0 for value in pnl),
            "losses": sum(value < 0 for value in pnl),
            "flat": sum(value == 0 for value in pnl),
            "net_paper_pl": round(sum(pnl), 8),
            "expectancy": round(sum(pnl) / len(pnl), 8),
            "first_exit_utc": min(str(item["exit_timestamp_utc"]) for item in items),
            "last_exit_utc": max(str(item["exit_timestamp_utc"]) for item in items),
        })
    return rows


def _decorate_state(
    state: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    count = len(records)
    weeks = weekly_evidence(records)
    return {
        **dict(state),
        "campaign_version": VERSION,
        "campaign_id": CAMPAIGN_ID,
        "strategy_name": STRATEGY_NAME,
        "mode": MODE,
        "paper_only": True,
        "atr_period": ATR_PERIOD,
        "multiplier": MULTIPLIER,
        "qualifying_trades": count,
        "required_qualifying_trades": REQUIRED_QUALIFYING_TRADES,
        "thirty_trade_campaign_status": "COMPLETE" if count >= REQUIRED_QUALIFYING_TRADES else "IN_PROGRESS",
        "active_position_status": "ACTIVE" if state.get("active_position") else "NONE",
        "validation_status": "PASS",
        "weekly_evidence_status": (
            "COMPLETE" if count >= REQUIRED_QUALIFYING_TRADES
            else ("COLLECTING" if count else "READY_FOR_COLLECTION")
        ),
        "weekly_evidence": weeks,
        "separate_from_generic_p1": True,
        "generic_p1_campaign_state_mutated": False,
        "no_live_order_path": True,
        "files_changed": [],
        "tests_run": [],
        "commit_status": "NO_REPO_ACTION_BY_CAMPAIGN",
        "runtime_launch_status": "NOT_LAUNCHED",
        **SAFETY,
    }


def render_campaign_report(state: Mapping[str, Any]) -> str:
    return "\n".join([
        "# AIOS Forex Supertrend 30-Trade Paper Campaign", "",
        f"- CAMPAIGN_ID: {state['campaign_id']}",
        f"- STRATEGY: {state['strategy_name']}",
        f"- MODE: {state['mode']}",
        f"- PAPER_ONLY: {str(state['paper_only']).lower()}",
        f"- ATR_PERIOD: {state['atr_period']}",
        f"- MULTIPLIER: {state['multiplier']}",
        f"- QUALIFYING_TRADES: {state['qualifying_trades']}/{state['required_qualifying_trades']}",
        f"- ACTIVE_POSITION_STATUS: {state['active_position_status']}",
        f"- VALIDATION_STATUS: {state['validation_status']}",
        f"- CAMPAIGN_STATUS: {state['thirty_trade_campaign_status']}",
        f"- WEEKLY_EVIDENCE_STATUS: {state['weekly_evidence_status']}",
        f"- COMMIT_STATUS: {state['commit_status']}",
        f"- RUNTIME_LAUNCH_STATUS: {state['runtime_launch_status']}", "",
        "This campaign records sanitized, already-closed PAPER evidence only. It has no broker, "
        "credential, network, practice-order, live-order, money-movement, scheduler, or worker-launch path.", "",
    ])


def render_weekly_report(state: Mapping[str, Any]) -> str:
    lines = [
        "# AIOS Forex Supertrend Weekly Paper Evidence", "",
        f"- CAMPAIGN_ID: {state['campaign_id']}",
        f"- STRATEGY: {state['strategy_name']}",
        f"- CONFIGURATION: ATR {state['atr_period']}, multiplier {state['multiplier']}",
        f"- PAPER_ONLY: {str(state['paper_only']).lower()}",
        f"- QUALIFYING_TRADES: {state['qualifying_trades']}/{state['required_qualifying_trades']}",
        f"- WEEKLY_EVIDENCE_STATUS: {state['weekly_evidence_status']}", "",
        "## Weekly rollup", "",
    ]
    if not state["weekly_evidence"]:
        lines.append("- No qualifying PAPER trades have been supplied.")
    else:
        for row in state["weekly_evidence"]:
            lines.append(
                f"- {row['iso_week']}: {row['qualifying_trades']} trades; "
                f"{row['wins']} wins; {row['losses']} losses; "
                f"net PAPER P/L {row['net_paper_pl']}; expectancy {row['expectancy']}"
            )
    lines.extend(["", "No runtime or broker action is authorized by this report.", ""])
    return "\n".join(lines)


def run_supertrend_campaign(
    records: Iterable[Mapping[str, Any]],
    output_root: Path,
    *,
    repository_root: Path,
    output: TextIO,
) -> dict[str, Any]:
    """Replay bounded offline records into a dedicated Supertrend evidence set."""
    items = [dict(item) for item in records]
    validation = validate_supertrend_records(items)
    if validation["validation_status"] != "PASS":
        raise ValueError("supertrend_campaign_validation_blocked:" + ";".join(validation["blockers"]))
    root = _outside_repository(output_root, repository_root)
    root.mkdir(parents=True, exist_ok=True)
    paths = campaign_paths(root)
    state = run_campaign(
        (_normalize_record(item) for item in items),
        paths,
        repository_root=repository_root,
        output=output,
    )
    ledger = _add_campaign_identity_to_ledger(paths.ledger)
    result = _decorate_state(state, ledger)
    paths.campaign_state.write_text(stable_json(result), encoding="utf-8")
    paths.campaign_report.write_text(render_campaign_report(result), encoding="utf-8")
    (root / OUTPUT_NAMES["weekly_report"]).write_text(render_weekly_report(result), encoding="utf-8")
    return result


def _load_input(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, Mapping) and isinstance(payload.get("records"), list):
        records = payload["records"]
    else:
        raise ValueError("records_array_required")
    if not all(isinstance(item, Mapping) for item in records):
        raise ValueError("record_objects_required")
    return [dict(item) for item in records]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Offline Supertrend PAPER campaign validation and replay.")
    commands = result.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate a fixture without writing files.")
    validate.add_argument("--input", type=Path, required=True)
    replay = commands.add_parser("replay", help="Write dedicated PAPER evidence outside the repository.")
    replay.add_argument("--input", type=Path, required=True)
    replay.add_argument("--output-root", type=Path, required=True)
    replay.add_argument("--paper-only-confirmed", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    records = _load_input(args.input)
    if args.command == "validate":
        result = validate_supertrend_records(records)
        print(stable_json(result), end="")
        return 0 if result["validation_status"] == "PASS" else 2
    if not args.paper_only_confirmed:
        raise ValueError("explicit_paper_only_confirmation_required")
    state = run_supertrend_campaign(records, args.output_root, repository_root=ROOT, output=sys.stdout)
    print(stable_json({
        "campaign_id": state["campaign_id"],
        "status": state["thirty_trade_campaign_status"],
        "qualifying_trades": state["qualifying_trades"],
        "required_qualifying_trades": state["required_qualifying_trades"],
        "paper_only": state["paper_only"],
        "runtime_launch_status": state["runtime_launch_status"],
    }), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
