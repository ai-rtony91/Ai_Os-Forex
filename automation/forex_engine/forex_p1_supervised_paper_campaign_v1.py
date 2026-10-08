"""Bounded, sequential campaign adapter for canonical P1 paper evidence.

This module does not trade and does not fetch market data.  It accepts completed,
sanitized paper-trade candidates emitted by the existing long-run paper supervisor
and passes them, one at a time, through the canonical capture/replay boundary.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TextIO

from automation.forex_engine.forex_p1_supervised_paper_capture_replay_v1 import (
    run_capture_replay,
)
from automation.forex_engine.forex_profit_track_p1_strategy_evidence_v1 import (
    evaluate_strategy_evidence,
)
from automation.forex_engine.long_run_paper_supervisor import LONG_RUN_PAPER_MODE
from automation.forex_engine.strategies import SUPERTREND_PULLBACK_V1

VERSION = "forex_p1_supervised_paper_campaign_v1"
TARGET_QUALIFYING_TRADES = 30
MAX_OPEN_PAPER_POSITIONS = 1
PAPER_MODE = LONG_RUN_PAPER_MODE
LONG_RUN_LIMITS = {"max_session_trades": TARGET_QUALIFYING_TRADES}

SAFETY_FLAGS = {
    "broker_write_performed": False,
    "practice_order_performed": False,
    "live_trade_performed": False,
    "money_movement_performed": False,
    "credentials_persisted": False,
}

WAIT_FOR_NEXT_CYCLE = "WAIT_FOR_NEXT_CYCLE"
WAIT_FOR_DATA = "WAIT_FOR_DATA"
WAIT_ACTIONS = frozenset({WAIT_FOR_NEXT_CYCLE, WAIT_FOR_DATA})
WAITING_FOR_NEXT_RUN = "WAITING_FOR_NEXT_RUN"
LATEST_BLOCKER_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
LATEST_BLOCKER_MARKET_NOT_ELIGIBLE = "MARKET_NOT_ELIGIBLE"
DATA_UNAVAILABLE_REASONS = frozenset({
    "data_unavailable",
    "insufficient_candles",
    "stale_history",
    "stale_snapshot",
})
SUPERTREND_REJECTION_REASONS = (
    "insufficient_candles",
    "no_supertrend_flip",
    "trend_not_aligned",
    "pullback_not_confirmed",
    "volatility_filter_failed",
    "duplicate_position_guard",
    "data_unavailable",
    "stale_history",
    "stale_snapshot",
    "unknown_no_signal",
)
_SUPERTREND_REJECTION_REASON_SET = frozenset(SUPERTREND_REJECTION_REASONS)
_MARKET_ELIGIBILITY_REASONS = frozenset(
    reason for reason in _SUPERTREND_REJECTION_REASON_SET if reason not in DATA_UNAVAILABLE_REASONS
)


def _new_york_timestamp(value: datetime) -> str:
    """Render UTC using America/New_York rules without an external tzdata file."""
    year = value.year
    march_first = datetime(year, 3, 1, tzinfo=timezone.utc)
    november_first = datetime(year, 11, 1, tzinfo=timezone.utc)
    dst_start = march_first + timedelta(
        days=(6 - march_first.weekday()) % 7 + 7, hours=7
    )
    dst_end = november_first + timedelta(
        days=(6 - november_first.weekday()) % 7, hours=6
    )
    offset = timedelta(hours=-4 if dst_start <= value < dst_end else -5)
    return value.astimezone(timezone(offset)).isoformat()


@dataclass(frozen=True)
class CampaignPaths:
    candidate: Path
    ledger: Path
    replay_state: Path
    replay_report: Path
    event_log: Path
    campaign_state: Path
    campaign_report: Path


@dataclass(frozen=True)
class CampaignHalt:
    """Fail-closed stop emitted by the canonical upstream paper supervisor."""

    reason: str


@dataclass(frozen=True)
class CampaignWait:
    """A bounded market cycle that produced no evidence and must continue."""

    cycle_number: int
    maximum_cycles: int
    action: str = WAIT_FOR_NEXT_CYCLE
    observed_at_utc: str | None = None
    next_check_in_seconds: int | None = field(default=None, compare=False)
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.action not in WAIT_ACTIONS:
            raise ValueError("unsupported_campaign_wait_action")
        if self.action == WAIT_FOR_DATA and not self.observed_at_utc:
            raise ValueError("wait_for_data_observed_at_utc_required")
        if any(
            not isinstance(reason, str)
            or reason not in _SUPERTREND_REJECTION_REASON_SET
            for reason in self.rejection_reasons
        ):
            raise ValueError("unsupported_supertrend_rejection_reason")
        if len(set(self.rejection_reasons)) != len(self.rejection_reasons):
            raise ValueError("duplicate_supertrend_rejection_reason")

    @property
    def rejection_reason(self) -> str | None:
        return self.rejection_reasons[0] if self.rejection_reasons else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_seconds(total_seconds: int) -> str:
    total_seconds = max(0, total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def _safe_utc(value: str | Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _run_age_utc(started_utc: Any) -> str:
    started = _safe_utc(started_utc)
    if started is None:
        return "UNKNOWN"
    elapsed = datetime.now(timezone.utc) - started
    return _format_seconds(int(max(0.0, elapsed.total_seconds())))


def _active_position_snapshot(active_position: Any) -> str:
    if not active_position:
        return "NONE"
    if isinstance(active_position, Mapping):
        return json.dumps(active_position, sort_keys=True)
    return str(active_position)


def _latest_rejection_reasons(state: Mapping[str, Any]) -> list[str]:
    raw = state.get("latest_rejection_reasons")
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        values = []
    return [
        str(reason).strip()
        for reason in values
        if str(reason).strip()
    ]


def latest_paper_blocker_classification(state: Mapping[str, Any]) -> str:
    """Classify the latest blocker without letting historical counts override it."""
    last_action = str(state.get("last_action") or "").strip()
    latest_reason = str(state.get("latest_rejection_reason") or "").strip()
    latest_reasons = _latest_rejection_reasons(state)

    if last_action == WAIT_FOR_DATA:
        return LATEST_BLOCKER_DATA_UNAVAILABLE
    if latest_reason in DATA_UNAVAILABLE_REASONS:
        return LATEST_BLOCKER_DATA_UNAVAILABLE
    if any(reason in DATA_UNAVAILABLE_REASONS for reason in latest_reasons):
        return LATEST_BLOCKER_DATA_UNAVAILABLE
    if latest_reason in _MARKET_ELIGIBILITY_REASONS:
        return LATEST_BLOCKER_MARKET_NOT_ELIGIBLE
    if any(reason in _MARKET_ELIGIBILITY_REASONS for reason in latest_reasons):
        return LATEST_BLOCKER_MARKET_NOT_ELIGIBLE
    return "NONE"


def load_active_position_projection(path: Path | None) -> dict[str, Any] | None:
    """Read-only projection of the runtime's genuine open PAPER session.

    The runtime session is authoritative for an open position; the campaign
    ledger remains authoritative for completed qualifying trades.  Missing or
    non-active sessions project to NONE.  A malformed ACTIVE session fails
    closed so a status surface cannot display partial position evidence.
    """
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("active_paper_session_invalid") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("active_paper_session_invalid")
    if payload.get("status") != "ACTIVE":
        return None
    required = (
        "candidate_id", "strategy_name", "instrument", "direction",
        "entry_timestamp", "entry_price", "stop_price", "target_price", "units",
    )
    if any(key not in payload or payload[key] in (None, "") for key in required):
        raise ValueError("active_paper_session_incomplete")
    entry_utc = _safe_utc(payload["entry_timestamp"])
    if entry_utc is None:
        raise ValueError("active_paper_session_entry_timestamp_invalid")
    return {
        "candidate_id": payload["candidate_id"],
        "strategy": payload["strategy_name"],
        "instrument": payload["instrument"],
        "direction": payload["direction"],
        "entry_timestamp_utc": entry_utc.isoformat().replace("+00:00", "Z"),
        "entry_timestamp_new_york": _new_york_timestamp(entry_utc),
        "entry_price": payload["entry_price"],
        "stop": payload["stop_price"],
        "target": payload["target_price"],
        "units": payload["units"],
    }


def _apply_active_position_projection(
    state: dict[str, Any], active_session_path: Path | None
) -> None:
    projection = load_active_position_projection(active_session_path)
    state["active_position"] = projection
    state["active_position_status"] = "ACTIVE" if projection is not None else "NONE"


def _next_wait_display(wait: CampaignWait) -> tuple[str, str]:
    if (
        wait.next_check_in_seconds is None
        or wait.next_check_in_seconds <= 0
    ):
        return "UNKNOWN", "UNKNOWN"
    seconds = int(wait.next_check_in_seconds)
    eta = (datetime.now().astimezone() + timedelta(seconds=seconds)).strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )
    return eta, f"{seconds} seconds"


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, Mapping) else []
    return list(records) if isinstance(records, list) else []


def _strategy_identity(record: Mapping[str, Any]) -> str:
    return str(record.get("strategy_name") or record.get("strategy_id") or "").strip()


def _campaign_records(
    path: Path, qualifying_strategy_name: str | None
) -> list[dict[str, Any]]:
    records = _load_records(path)
    if qualifying_strategy_name and any(
        _strategy_identity(record) != qualifying_strategy_name for record in records
    ):
        raise ValueError("campaign_ledger_strategy_mismatch")
    return records


def _strategy_counts(records: list[Mapping[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(_strategy_identity(record) for record in records).items()))


def _metrics(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    pnl = [float(record["realized_pl"]) for record in records]
    gross_profit = round(sum(value for value in pnl if value > 0), 8)
    gross_loss = round(abs(sum(value for value in pnl if value < 0)), 8)
    net_pl = round(sum(pnl), 8)
    profit_factor: float | str | None
    if gross_loss:
        profit_factor = round(gross_profit / gross_loss, 8)
    else:
        profit_factor = "INFINITE" if gross_profit else None
    equity = peak = maximum_drawdown = 0.0
    current_streak = maximum_streak = 0
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        maximum_drawdown = max(maximum_drawdown, peak - equity)
        current_streak = current_streak + 1 if value < 0 else 0
        maximum_streak = max(maximum_streak, current_streak)
    return {
        "net_pl": net_pl,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "maximum_drawdown": round(maximum_drawdown, 8),
        "consecutive_losses": maximum_streak,
        "expectancy": round(net_pl / len(pnl), 8) if pnl else 0.0,
    }


def _p1_status(records: list[Mapping[str, Any]]) -> str:
    evaluation = evaluate_strategy_evidence([
        {
            "trade_id": record["trade_id"],
            "entry": record["entry_price"],
            "exit": record["exit_price"],
            "realized_pl": record["realized_pl"],
            "timestamp": record["exit_timestamp_utc"],
            "evidence_type": record["evidence_type"],
        }
        for record in records
    ])
    return str(evaluation["strategy_evidence_status"])


def _initial_state(
    started_utc: str, qualifying_strategy_name: str | None
) -> dict[str, Any]:
    state = {
        "campaign_version": VERSION,
        "campaign_status": "RUNNING",
        "stop_reason": None,
        "target_qualifying_trades": TARGET_QUALIFYING_TRADES,
        "accepted_qualifying_trades": 0,
        "rejected_records": 0,
        "current_trade_number": 0,
        "qualifying_strategy_name": qualifying_strategy_name,
        "strategy_qualifying_trade_counts": {},
        "active_position": None,
        "active_position_status": "NONE",
        "last_trade": None,
        "data_unavailable_count": 0,
        "last_data_unavailable_utc": None,
        "last_action": None,
        "trade_results": [],
        **_metrics([]),
        "p1_status": "NO_EVIDENCE",
        "ready_for_p2_review": False,
        "started_utc": started_utc,
        "updated_utc": started_utc,
        "completed_utc": None,
        **SAFETY_FLAGS,
    }
    if qualifying_strategy_name == SUPERTREND_PULLBACK_V1:
        state.update({
            "latest_rejection_reason": None,
            "latest_rejection_reasons": [],
            "rejection_reason_counts": {},
        })
    return state


def _load_previous_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("campaign_state_invalid") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("campaign_state_invalid")
    return dict(payload)


def _non_negative_count(state: Mapping[str, Any], name: str) -> int:
    value = state.get(name, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"campaign_state_{name}_invalid")
    return value


def _restore_progress_state(
    state: dict[str, Any],
    previous: Mapping[str, Any],
    qualifying_strategy_name: str | None,
) -> None:
    if not previous:
        return
    if previous.get("campaign_version") not in (None, VERSION):
        raise ValueError("campaign_state_version_mismatch")
    if (
        "qualifying_strategy_name" in previous
        and previous["qualifying_strategy_name"] != qualifying_strategy_name
    ):
        raise ValueError("campaign_state_strategy_mismatch")

    state["rejected_records"] = _non_negative_count(previous, "rejected_records")
    state["data_unavailable_count"] = _non_negative_count(
        previous, "data_unavailable_count"
    )
    for name in (
        "started_utc",
        "last_data_unavailable_utc",
        "last_action",
    ):
        value = previous.get(name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"campaign_state_{name}_invalid")
        if value:
            state[name] = value

    if qualifying_strategy_name != SUPERTREND_PULLBACK_V1:
        return

    latest_reason = previous.get("latest_rejection_reason")
    if latest_reason is not None and latest_reason not in _SUPERTREND_REJECTION_REASON_SET:
        raise ValueError("campaign_state_latest_rejection_reason_invalid")
    latest_reasons = previous.get("latest_rejection_reasons", [])
    if (
        not isinstance(latest_reasons, list)
        or len(set(latest_reasons)) != len(latest_reasons)
        or any(reason not in _SUPERTREND_REJECTION_REASON_SET for reason in latest_reasons)
    ):
        raise ValueError("campaign_state_latest_rejection_reasons_invalid")
    counts = previous.get("rejection_reason_counts", {})
    if not isinstance(counts, Mapping) or any(
        reason not in _SUPERTREND_REJECTION_REASON_SET
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        for reason, count in counts.items()
    ):
        raise ValueError("campaign_state_rejection_reason_counts_invalid")
    state["latest_rejection_reason"] = latest_reason
    state["latest_rejection_reasons"] = list(latest_reasons)
    state["rejection_reason_counts"] = dict(sorted(counts.items()))


def _trade_results(records: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    cumulative_paper_pl = 0.0
    results: list[dict[str, Any]] = []
    for trade_number, record in enumerate(records, start=1):
        realized_paper_pl = float(record["realized_pl"])
        cumulative_paper_pl = round(
            cumulative_paper_pl + realized_paper_pl,
            8,
        )
        results.append({
            "trade_number": trade_number,
            "trade_id": record["trade_id"],
            "strategy_name": _strategy_identity(record),
            "entry": record["entry_price"],
            "exit": record["exit_price"],
            "realized_paper_pl": realized_paper_pl,
            "cumulative_paper_pl": cumulative_paper_pl,
            "win_or_loss": (
                "WIN"
                if realized_paper_pl > 0
                else ("LOSS" if realized_paper_pl < 0 else "FLAT")
            ),
        })
    return results


def _sync_trade_evidence(
    state: dict[str, Any], records: list[Mapping[str, Any]]
) -> None:
    results = _trade_results(records)
    status = _p1_status(records)
    state.update(_metrics(records))
    state.update({
        "accepted_qualifying_trades": len(records),
        "current_trade_number": len(records),
        "last_trade": results[-1] if results else None,
        "trade_results": results,
        "p1_status": status,
        "ready_for_p2_review": status == "READY_FOR_P2_REVIEW",
        "strategy_qualifying_trade_counts": _strategy_counts(records),
    })


def _mark_waiting_for_next_run(state: dict[str, Any], updated_utc: str) -> None:
    state.update({
        "campaign_status": WAITING_FOR_NEXT_RUN,
        "stop_reason": None,
        "updated_utc": updated_utc,
        "completed_utc": None,
        "active_position": None,
    })


def _mark_terminal(
    state: dict[str, Any], stop_reason: str, updated_utc: str
) -> None:
    state.update({
        "campaign_status": (
            "COMPLETE" if stop_reason == "TARGET_REACHED" else "STOPPED"
        ),
        "stop_reason": stop_reason,
        "updated_utc": updated_utc,
        "completed_utc": updated_utc,
        "active_position": None,
    })


def _write_outputs(paths: CampaignPaths, state: Mapping[str, Any]) -> None:
    paths.campaign_state.parent.mkdir(parents=True, exist_ok=True)
    paths.campaign_state.write_text(
        json.dumps(state, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    results = list(state.get("trade_results") or [])
    if not results:
        ledger_records = _campaign_records(
            paths.ledger,
            state.get("qualifying_strategy_name"),
        )
        results = _trade_results(ledger_records)
    pnl_lines = [
        f"- {item['trade_id']}: {item['realized_paper_pl']} PAPER P/L"
        for item in results
    ] or ["- NONE"]
    if state["campaign_status"] == WAITING_FOR_NEXT_RUN:
        next_action = (
            "Retry read-only Practice data in the next owner-bounded campaign run."
            if state["last_action"] == WAIT_FOR_DATA
            else "Start the next owner-bounded paper/demo campaign run when ready."
        )
    elif state["campaign_status"] == "RUNNING":
        next_action = "The current owner-bounded paper/demo campaign is active."
    elif state["stop_reason"] == "TARGET_REACHED":
        next_action = "Human owner may review P1 evidence; no promotion is automatic."
    else:
        next_action = "Review the stop reason before a new owner-started campaign."
    report = [
        "# AIOS Forex P1 30-Trade Paper Campaign V1", "",
        f"- CAMPAIGN_STATUS: {state['campaign_status']}",
        f"- TARGET: {state['target_qualifying_trades']}",
        f"- ACCEPTED: {state['accepted_qualifying_trades']}",
        f"- QUALIFYING_STRATEGY: {state['qualifying_strategy_name'] or 'ANY'}",
        f"- STRATEGY_COUNTS: {json.dumps(state['strategy_qualifying_trade_counts'], sort_keys=True)}",
        f"- REJECTED: {state['rejected_records']}",
        f"- CUMULATIVE_PAPER_PNL: {state['net_pl']}",
        f"- PROFIT_FACTOR: {state['profit_factor']}",
        f"- DRAWDOWN: {state['maximum_drawdown']}",
        f"- LOSS_STREAK: {state['consecutive_losses']}",
        f"- EXPECTANCY: {state['expectancy']}",
        f"- P1_STATUS: {state['p1_status']}",
        f"- DATA_UNAVAILABLE_COUNT: {state['data_unavailable_count']}",
        f"- LAST_DATA_UNAVAILABLE_UTC: {state['last_data_unavailable_utc'] or 'NONE'}",
        f"- LAST_ACTION: {state['last_action'] or 'NONE'}",
        f"- LATEST_BLOCKER_CLASSIFICATION: {latest_paper_blocker_classification(state)}",
        f"- LATEST_BLOCKER_REASON: {state.get('latest_rejection_reason') or 'NONE'}",
        f"- HISTORICAL_SIGNAL_REJECTIONS: {json.dumps(state.get('rejection_reason_counts', {}), sort_keys=True)}",
        f"- ACTIVE_POSITION_STATUS: {state.get('active_position_status', 'NONE')}",
        f"- ACTIVE_POSITION: {_active_position_snapshot(state.get('active_position'))}",
        f"- STOP_REASON: {state['stop_reason'] or 'NONE'}",
        f"- COMPLETED_UTC: {state['completed_utc'] or 'NONE'}",
        f"- NEXT_ACTION: {next_action}",
        "", "## PAPER_PNL_BY_TRADE", "", *pnl_lines, "",
        "All results are local PAPER P/L. No broker order, live trade, or money movement occurred.", "",
    ]
    paths.campaign_report.write_text("\n".join(report), encoding="utf-8")


def _progress(state: Mapping[str, Any], stream: TextIO) -> None:
    last = state["last_trade"]
    stream.write(
        f"TRADE: {state['accepted_qualifying_trades']}/30\n"
        f"REALIZED PAPER P/L: {last['realized_paper_pl']}\n"
        f"CUMULATIVE PAPER P/L: {state['net_pl']}\n"
        f"PROFIT FACTOR: {state['profit_factor']}\n"
        f"MAX DRAWDOWN: {state['maximum_drawdown']}\n"
        f"LOSS STREAK: {state['consecutive_losses']}\n"
        f"QUALIFYING: {state['accepted_qualifying_trades']}/30\n"
        f"P1 STATUS: {state['p1_status']}\n"
    )


def _wait_progress(wait: CampaignWait, state: Mapping[str, Any], stream: TextIO) -> None:
    run_age = _run_age_utc(state.get("started_utc"))
    next_eta, next_in = _next_wait_display(wait)
    rejection_line = (
        f"REJECTION REASON: {wait.rejection_reason}\n"
        if wait.rejection_reason
        else ""
    )
    stream.write(
        f"RUN AGE: {run_age}\n"
        f"CYCLE: {wait.cycle_number}/{wait.maximum_cycles}\n"
        f"NEXT CHECK ETA: {next_eta}\n"
        f"NEXT CHECK IN: {next_in}\n"
        "SIGNAL: NONE\n"
        f"ACTION: {wait.action}\n"
        f"{rejection_line}"
        f"ACTIVE POSITION: {_active_position_snapshot(state['active_position'])}\n"
        f"QUALIFYING: {state['accepted_qualifying_trades']}/30\n"
        f"CUMULATIVE PAPER P/L: {state['net_pl']}\n"
        f"P1 STATUS: {state['p1_status']}\n"
    )


def run_campaign(
    candidates: Iterable[Mapping[str, Any]],
    paths: CampaignPaths,
    *,
    repository_root: Path,
    output: TextIO,
    kill_switch_active: bool = False,
    risk_halt_active: bool = False,
    maximum_session_loss: float | None = None,
    qualifying_strategy_name: str | None = None,
    active_session_path: Path | None = None,
) -> dict[str, Any]:
    """Capture up to 30 already-closed paper candidates, sequentially and fail closed."""
    started = _utc_now()
    if qualifying_strategy_name is not None:
        qualifying_strategy_name = str(qualifying_strategy_name).strip()
        if not qualifying_strategy_name:
            raise ValueError("qualifying_strategy_name_required")
    previous_state_exists = paths.campaign_state.exists()
    previous_state = _load_previous_state(paths.campaign_state)
    prior_records = _campaign_records(paths.ledger, qualifying_strategy_name)
    state = _initial_state(started, qualifying_strategy_name)
    _restore_progress_state(state, previous_state, qualifying_strategy_name)
    _sync_trade_evidence(state, prior_records)
    _apply_active_position_projection(state, active_session_path)
    stop_reason: str | None = None
    seen_this_run: set[str] = set()

    if kill_switch_active:
        stop_reason = "KILL_SWITCH_ACTIVE"
    elif risk_halt_active:
        stop_reason = "RISK_HALT"

    if (
        stop_reason is None
        and len(prior_records) < TARGET_QUALIFYING_TRADES
        and (previous_state_exists or prior_records)
    ):
        _mark_waiting_for_next_run(state, started)
        _write_outputs(paths, state)

    iterator = iter(candidates)
    while stop_reason is None:
        prior = _campaign_records(paths.ledger, qualifying_strategy_name)
        if len(prior) >= TARGET_QUALIFYING_TRADES:
            stop_reason = "TARGET_REACHED"
            break
        try:
            candidate = next(iterator)
        except StopIteration:
            break
        except KeyboardInterrupt:
            stop_reason = "OWNER_CANCELLATION"
            break
        if isinstance(candidate, CampaignHalt):
            stop_reason = candidate.reason
            break
        if isinstance(candidate, CampaignWait):
            records = _campaign_records(paths.ledger, qualifying_strategy_name)
            _sync_trade_evidence(state, records)
            state["last_action"] = candidate.action
            if candidate.rejection_reasons:
                if qualifying_strategy_name != SUPERTREND_PULLBACK_V1:
                    raise ValueError(
                        "supertrend_rejection_reason_requires_supertrend_campaign"
                    )
                counts = dict(state["rejection_reason_counts"])
                for reason in candidate.rejection_reasons:
                    counts[reason] = counts.get(reason, 0) + 1
                state["latest_rejection_reason"] = candidate.rejection_reason
                state["latest_rejection_reasons"] = list(
                    candidate.rejection_reasons
                )
                state["rejection_reason_counts"] = dict(sorted(counts.items()))
            updated_utc = _utc_now()
            if candidate.action == WAIT_FOR_DATA:
                state["data_unavailable_count"] += 1
                state["last_data_unavailable_utc"] = (
                    candidate.observed_at_utc or updated_utc
                )
            _mark_waiting_for_next_run(state, updated_utc)
            _apply_active_position_projection(state, active_session_path)
            _write_outputs(paths, state)
            _wait_progress(candidate, state, output)
            continue
        if not isinstance(candidate, Mapping):
            stop_reason = "MALFORMED_EVIDENCE_REJECTED"
            state["rejected_records"] += 1
            break
        if (
            qualifying_strategy_name
            and _strategy_identity(candidate) != qualifying_strategy_name
        ):
            stop_reason = "STRATEGY_MISMATCH_REJECTED"
            state["rejected_records"] += 1
            break
        trade_id = str(candidate.get("trade_id", "")).strip()
        if trade_id and trade_id in seen_this_run:
            stop_reason = "DUPLICATE_TRADE_ID_REJECTED"
            state["rejected_records"] += 1
            break
        realized = candidate.get("realized_pl")
        try:
            finite_realized = float(realized)
        except (TypeError, ValueError):
            finite_realized = float("nan")
        if not math.isfinite(finite_realized):
            stop_reason = "MALFORMED_EVIDENCE_REJECTED"
            state["rejected_records"] += 1
            break

        # The candidate represents an already-closed paper trade. It is the only
        # item inside the canonical one-candidate capture/replay boundary.
        state["active_position"] = {"trade_id": trade_id or "pending-deterministic-id"}
        paths.candidate.parent.mkdir(parents=True, exist_ok=True)
        paths.candidate.write_text(json.dumps(dict(candidate), allow_nan=False), encoding="utf-8")
        replay = run_capture_replay(
            paths.candidate, paths.ledger, paths.replay_state, paths.replay_report,
            paths.event_log, repository_root=repository_root,
        )
        state["active_position"] = None
        state["rejected_records"] += replay["rejected_records"]
        if replay["accepted_records"] != 1:
            reasons = {reason for item in replay["rejections"] for reason in item["reasons"]}
            stop_reason = "DUPLICATE_TRADE_ID_REJECTED" if "duplicate_trade_id" in reasons else "EVIDENCE_VALIDATION_FAILED"
            break

        records = _campaign_records(paths.ledger, qualifying_strategy_name)
        accepted = records[-1]
        seen_this_run.add(str(accepted["trade_id"]))
        _sync_trade_evidence(state, records)
        state["last_action"] = "PAPER_TRADE_RECORDED"
        if maximum_session_loss is not None and state["net_pl"] <= -abs(maximum_session_loss):
            stop_reason = "MAXIMUM_SESSION_LOSS_HIT"
        elif len(records) >= TARGET_QUALIFYING_TRADES:
            stop_reason = "TARGET_REACHED"
        updated_utc = _utc_now()
        if stop_reason is None:
            _mark_waiting_for_next_run(state, updated_utc)
        else:
            _mark_terminal(state, stop_reason, updated_utc)
        _write_outputs(paths, state)
        _progress(state, output)

    final_records = _campaign_records(paths.ledger, qualifying_strategy_name)
    _sync_trade_evidence(state, final_records)
    final_updated_utc = _utc_now()
    if stop_reason is None:
        _mark_waiting_for_next_run(state, final_updated_utc)
    else:
        _mark_terminal(state, stop_reason, final_updated_utc)
    _apply_active_position_projection(state, active_session_path)
    _write_outputs(paths, state)
    paths.candidate.unlink(missing_ok=True)
    return state
