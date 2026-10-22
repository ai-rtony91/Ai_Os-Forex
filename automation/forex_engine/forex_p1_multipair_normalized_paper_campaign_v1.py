"""Normalized all-pairs LONG-only PAPER collector for the P1 Supertrend lane."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from automation.forex_engine.forex_multipair_m5_replay_v1 import (
    ReplayInstrument,
    _trade_stats as replay_trade_stats,
)
from automation.forex_engine.forex_p1_cycle_provenance_v1 import append_cycle_record
from automation.forex_engine.forex_p1_multipair_normalization_v1 import (
    DEFAULT_CANDLE_COUNT,
    MIN_RR,
    PROTOCOL_VERSION,
    SCHEMA,
    STRATEGY_ID,
    TARGET_RR,
    NormalizedInstrument,
    candles_to_strategy_window,
    candidate_rank_key,
    calibrate_candidate_to_actual_entry,
    discover_fixed_universe,
    fetch_completed_m5_history,
    normalized_strategy_config,
    normalized_trade_outcome,
    quote_mids_from_pricing,
    replay_candidate,
    sanitized_price_snapshot,
)
from automation.forex_engine.forex_p1_paper_autostart_v1 import (
    RuntimeLockOwnership,
    acquire_runtime_lock,
    read_runtime_lock,
    refresh_runtime_lock,
    release_runtime_lock,
    source_fingerprint,
)
from automation.forex_engine.forex_p1_supervised_paper_evidence_pipeline_v1 import (
    run_pipeline,
)
from automation.forex_engine.forex_profit_track_p1_strategy_evidence_v1 import (
    evaluate_strategy_evidence,
)
from automation.forex_engine.forex_p1_supervised_paper_session_v1 import (
    build_completed_trade_record,
    load_active_session,
    open_paper_session,
    update_paper_session_extremes,
)
from automation.forex_engine.models import Direction
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient, OandaReadOnlyClientError
from automation.forex_engine.strategies import evaluate_supertrend_pullback

VERSION = "forex_p1_multipair_normalized_paper_campaign_v1"
CAMPAIGN_SCHEMA = "AIOS_FOREX_MULTIPAIR_NORMALIZED_PAPER_CAMPAIGN_V1"
RUNTIME_ROOT = Path(".aios/runtime/forex_p1_multipair_normalized_paper_campaign_v1")
MAX_CYCLES_PER_SEGMENT = 288
SUPER_TREND_LOCK_SCHEMA = "AIOS_FOREX_MULTIPAIR_PAPER_RUNTIME_LOCK.v1"
SUPER_TREND_LOCK_CAMPAIGN_IDENTITY = "FOREX_P1_MULTIPAIR_NORMALIZED_PAPER_RUNTIME_V1"
SUPER_TREND_LOCK_TTL_SECONDS = 300
SUPER_TREND_LOCK_PATH_SUFFIX = ".multipair.paper.runtime.lock"
POLL_INTERVAL_SECONDS = 300
DATA_UNAVAILABLE_BACKOFF_BASE_SECONDS = 30
DATA_UNAVAILABLE_BACKOFF_MAX_SECONDS = POLL_INTERVAL_SECONDS
MAX_CONSECUTIVE_STARTUP_DATA_FAILURES = 5
DEFAULT_PAPER_UNITS = 100
MARKET_REJECTION_REASONS = {
    "data_unavailable",
    "stale_history",
    "incomplete_history",
    "insufficient_candles",
    "no_supertrend_flip",
    "trend_not_aligned",
    "pullback_not_confirmed",
    "volatility_filter_failed",
    "duplicate_position_guard",
    "pricing_unavailable",
    "ask_geometry_failed",
    "reward_risk_below_minimum",
}
SAFETY = {
    "broker_write_performed": False,
    "practice_order_performed": False,
    "live_trade_performed": False,
    "money_movement_performed": False,
    "credentials_persisted": False,
}


@dataclass(frozen=True)
class CampaignPaths:
    root: Path

    @property
    def active_session(self) -> Path:
        return self.root / "active.json"

    @property
    def lock(self) -> Path:
        return self.root / "active.json.runtime.lock"

    @property
    def telemetry(self) -> Path:
        return self.root / "AIOS_FOREX_MULTIPAIR_NORMALIZED_CYCLE_PROVENANCE.jsonl"

    @property
    def campaign_state(self) -> Path:
        return self.root / "AIOS_FOREX_MULTIPAIR_NORMALIZED_PAPER_CAMPAIGN_STATE.json"

    @property
    def ledger(self) -> Path:
        return self.root / "AIOS_FOREX_MULTIPAIR_NORMALIZED_PAPER_LEDGER.json"

    @property
    def report(self) -> Path:
        return self.root / "AIOS_FOREX_MULTIPAIR_NORMALIZED_PAPER_CAMPAIGN_REPORT.md"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _normalized_path_text(path: Path) -> str:
    return str(path.resolve(strict=False)).lower().replace("/", "\\")


def resolve_runtime_paths(
    *, checkout_root: Path, runtime_root: Path | None = None
) -> CampaignPaths:
    checkout_root = checkout_root.resolve(strict=True)
    root = runtime_root or (checkout_root / RUNTIME_ROOT)
    if not root.is_absolute():
        root = (checkout_root / root).resolve(strict=False)
    if ".." in root.parts:
        raise ValueError("runtime_root_traversal_forbidden")
    root = root.resolve(strict=False)
    return CampaignPaths(root=root)


def _lock_path(runtime_path: Path) -> Path:
    return runtime_path.with_name(runtime_path.name + SUPER_TREND_LOCK_PATH_SUFFIX)


def _runtime_source_fingerprint() -> str:
    return source_fingerprint(Path(__file__))


def _acquire_lock(lock_path: Path, *, now: datetime) -> RuntimeLockOwnership | None:
    return acquire_runtime_lock(
        lock_path,
        schema=SUPER_TREND_LOCK_SCHEMA,
        campaign_identity=SUPER_TREND_LOCK_CAMPAIGN_IDENTITY,
        source_fingerprint_value=_runtime_source_fingerprint(),
        ttl_seconds=SUPER_TREND_LOCK_TTL_SECONDS,
        now=now,
    )


def _touch_lock(lock_path: Path, owner: RuntimeLockOwnership, *, now: datetime) -> bool:
    return refresh_runtime_lock(
        lock_path,
        owner,
        ttl_seconds=SUPER_TREND_LOCK_TTL_SECONDS,
        now=now,
    )


def _release_lock(lock_path: Path, owner: RuntimeLockOwnership) -> bool:
    return release_runtime_lock(lock_path, owner)


def _read_lock(lock_path: Path) -> dict[str, Any] | None:
    return read_runtime_lock(
        lock_path,
        schema=SUPER_TREND_LOCK_SCHEMA,
        campaign_identity=SUPER_TREND_LOCK_CAMPAIGN_IDENTITY,
        source_fingerprint_value=_runtime_source_fingerprint(),
    )


def _data_unavailable_backoff_seconds(consecutive_failures: int) -> int:
    if consecutive_failures <= 0:
        raise ValueError("positive_consecutive_failure_count_required")
    exponent = min(consecutive_failures - 1, 4)
    return min(
        DATA_UNAVAILABLE_BACKOFF_BASE_SECONDS * (2 ** exponent),
        DATA_UNAVAILABLE_BACKOFF_MAX_SECONDS,
    )


def _canonical_no_trade_reason(no_trade_reasons: Sequence[str] | None) -> str:
    if not no_trade_reasons:
        return "unknown_no_signal"
    for reason in no_trade_reasons:
        text = str(reason).strip()
        if not text:
            continue
        if ":" in text:
            text = text.split(":", 1)[1].strip()
        mapping = {
            "insufficient_data": "insufficient_candles",
            "no_supertrend_direction": "trend_not_aligned",
            "missing_supertrend_band": "trend_not_aligned",
            "volatility_below_atr_threshold": "volatility_filter_failed",
            "chop_zone_repeated_flips": "no_supertrend_flip",
            "weak_candle_body": "pullback_not_confirmed",
            "close_confirmation_missing": "pullback_not_confirmed",
            "entry_extended_from_band": "pullback_not_confirmed",
            "reward_risk_below_minimum": "reward_risk_below_minimum",
        }
        if text in mapping:
            return mapping[text]
    return "unknown_no_signal"


def _canonical_pair_value_error_reason(exc: Exception) -> str | None:
    mapping = {
        "insufficient_completed_m5_history": "incomplete_history",
        "candles_list_required": "incomplete_history",
        "no_candles_available": "incomplete_history",
        "explicit_utc_timestamp_required": "stale_history",
        "prices_list_required": "pricing_unavailable",
        "bid_ask_required": "pricing_unavailable",
        "instrument_price_missing": "pricing_unavailable",
        "positive_spread_required": "ask_geometry_failed",
    }
    return mapping.get(str(exc))


def _empty_segment_counters() -> dict[str, int]:
    return {
        "pairs_evaluated": 0,
        "pairs_with_usable_data": 0,
        "pairs_with_unavailable_data": 0,
        "pairs_with_candidates": 0,
        "candidates_accepted": 0,
        "internal_evaluation_errors": 0,
    }


def _segment_status_from_state(state: Mapping[str, Any]) -> str:
    return str(state.get("segment_status") or "UNKNOWN")


def _is_transient_read_failure(exc: OandaReadOnlyClientError) -> bool:
    return exc.public_reason in {"NETWORK_ERROR_SANITIZED", "HTTP_ERROR_SANITIZED"}


def _append_wait_for_data(
    *,
    paths: CampaignPaths,
    cycle_number: int,
    maximum_cycles: int,
    now: datetime,
    next_check_in_seconds: int | None,
    active_position_status: str,
) -> None:
    _append_jsonl(
        paths.telemetry,
        _cycle_record(
            cycle_number=cycle_number,
            maximum_cycles=maximum_cycles,
            action="WAIT_FOR_DATA",
            now=now,
            extra={
                "paper_session_event": "NONE",
                "candidate_status": "NONE",
                "paper_eligible": False,
                "wait_reason": "data_unavailable",
                "active_position_status": active_position_status,
                "universe_fingerprint": None,
            },
            rejection_reasons=("data_unavailable",),
            next_check_in_seconds=next_check_in_seconds,
        ),
    )


def _discover_universe_with_retry(
    client: OandaReadOnlyClient,
    *,
    sleep: Callable[[float], None],
    max_attempts: int = MAX_CONSECUTIVE_STARTUP_DATA_FAILURES,
) -> dict[str, Any]:
    last_error: OandaReadOnlyClientError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return discover_fixed_universe(client)
        except OandaReadOnlyClientError as exc:
            last_error = exc
            if not _is_transient_read_failure(exc):
                raise
            if attempt >= max_attempts:
                raise OandaReadOnlyClientError("PRACTICE_NETWORK_UNAVAILABLE") from exc
            sleep(_data_unavailable_backoff_seconds(attempt))
    raise OandaReadOnlyClientError("PRACTICE_NETWORK_UNAVAILABLE") from last_error


def _candidate_from_replay(
    instrument: NormalizedInstrument,
    candles: Sequence[Any],
    snapshot: Mapping[str, Any],
) -> dict[str, Any] | None:
    candidate = replay_candidate(
        instrument,
        candles,
        snapshot,
    )
    if candidate is None:
        return None
    candidate = dict(candidate)
    candidate["units"] = DEFAULT_PAPER_UNITS
    candidate["entry_rationale"] = (
        f"normalized all-pairs {STRATEGY_ID} paper signal"
    )
    return candidate


def _pair_snapshot(pricing_payload: Mapping[str, Any], instrument: str) -> dict[str, Any]:
    prices = pricing_payload.get("prices")
    if not isinstance(prices, list):
        raise ValueError("prices_list_required")
    for item in prices:
        if not isinstance(item, Mapping) or str(item.get("instrument", "")).upper() != instrument:
            continue
        bids, asks = item.get("bids"), item.get("asks")
        if not isinstance(bids, list) or not bids or not isinstance(asks, list) or not asks:
            raise ValueError("bid_ask_required")
        raw = {
            "prices": [
                {
                    "instrument": instrument,
                    "time": item.get("time"),
                    "bids": bids,
                    "asks": asks,
                }
            ]
        }
        return sanitized_price_snapshot(raw, instrument=instrument, now=_utc_now())
    raise ValueError("instrument_price_missing")


def _cycle_record(
    *,
    cycle_number: int,
    maximum_cycles: int,
    action: str,
    now: datetime,
    signal: Mapping[str, Any] | None = None,
    snapshot: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
    rejection_reasons: Sequence[str] = (),
    next_check_in_seconds: int | None = None,
) -> dict[str, Any]:
    record = {
        "schema": "AIOS_FOREX_MULTIPAIR_NORMALIZED_CYCLE_PROVENANCE.v1",
        "version": VERSION,
        "cycle_number": cycle_number,
        "maximum_cycles": maximum_cycles,
        "cycle_started_utc": _stamp(now),
        "cycle_completed_utc": _stamp(now),
        "action": action,
        "rejection_reasons": list(rejection_reasons),
        "next_check_in_seconds": next_check_in_seconds,
        "signal": dict(signal or {}),
        "snapshot": dict(snapshot or {}),
        "strategy_name": STRATEGY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "paper_only": True,
        "broker_write_performed": False,
        "practice_order_performed": False,
        "live_trade_performed": False,
        "money_movement_performed": False,
    }
    if extra:
        record.update(extra)
    return record


def _append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(json.dumps(_json_safe_value(dict(record)), sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        import os
        os.fsync(stream.fileno())


def _load_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not isinstance(payload.get("records"), list):
        raise ValueError("invalid_campaign_ledger")
    return list(payload["records"])


def _write_ledger(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    payload = {
        "version": VERSION,
        "schema": CAMPAIGN_SCHEMA,
        "records": list(records),
        **SAFETY,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_stable_json(payload), encoding="utf-8")


def _write_report(paths: CampaignPaths, state: Mapping[str, Any]) -> None:
    results = list(state.get("trade_results") or [])
    pair_results = list(state.get("pair_results") or [])
    if not results:
        ledger_records = _load_ledger(paths.ledger)
        results = [
            {
                "trade_id": str(item.get("trade_id", "")),
                "realized_paper_pl": item.get("realized_pl", 0),
            }
            for item in ledger_records
        ]
    report_lines = [
        "# AIOS Forex Multipair Normalized PAPER Campaign V1",
        "",
        f"- CAMPAIGN_STATUS: {state.get('campaign_status', 'UNKNOWN')}",
        f"- SEGMENT_STATUS: {state.get('segment_status', 'UNKNOWN')}",
        f"- SEGMENT_STOP_REASON: {state.get('segment_stop_reason', 'NONE')}",
        f"- SEGMENT_START_UTC: {state.get('segment_started_utc') or 'NONE'}",
        f"- SEGMENT_COMPLETED_UTC: {state.get('segment_completed_utc') or 'NONE'}",
        f"- CYCLES_REQUESTED: {state.get('segment_cycles_requested', 0)}",
        f"- CYCLES_COMPLETED: {state.get('segment_cycles_completed', 0)}",
        f"- ACCEPTED_QUALIFYING_TRADES: {state.get('accepted_qualifying_trades', 0)}",
        f"- LEDGER_COUNT: {len(results)}",
        f"- DATA_UNAVAILABLE_CYCLES: {state.get('data_unavailable_count', 0)}",
        f"- SEGMENT_PAIRS_DISCOVERED: {state.get('segment_pairs_discovered', 0)}",
        f"- SEGMENT_PAIRS_EVALUATED: {state.get('segment_pairs_evaluated', 0)}",
        f"- SEGMENT_PAIRS_WITH_USABLE_DATA: {state.get('segment_pairs_with_usable_data', 0)}",
        f"- SEGMENT_PAIRS_WITH_UNAVAILABLE_DATA: {state.get('segment_pairs_with_unavailable_data', 0)}",
        f"- SEGMENT_PAIRS_WITH_CANDIDATES: {state.get('segment_pairs_with_candidates', 0)}",
        f"- SEGMENT_INTERNAL_EVALUATION_ERRORS: {state.get('segment_internal_evaluation_errors', 0)}",
        f"- LATEST_CYCLE_REASON_COUNTS: {json.dumps(state.get('latest_cycle_reason_counts', {}), sort_keys=True)}",
        f"- SEGMENT_REJECTION_REASON_COUNTS: {json.dumps(state.get('segment_rejection_reason_counts', {}), sort_keys=True)}",
        f"- LATEST_REJECTION_REASON: {state.get('latest_rejection_reason') or 'NONE'}",
        f"- LATEST_ACTION: {state.get('last_action') or 'NONE'}",
        f"- LATEST_CYCLE_SUMMARY_REASON: {state.get('latest_cycle_summary_reason') or 'NONE'}",
        f"- LATEST_CYCLE_CHOSEN_INSTRUMENT: {state.get('latest_cycle_chosen_instrument') or 'NONE'}",
        f"- ACTIVE_POSITION_STATUS: {state.get('active_position_status', 'NONE')}",
        f"- NET_PAPER_PL: {state.get('net_pl')}",
        f"- EXPECTANCY: {state.get('expectancy')}",
        f"- PROFIT_FACTOR: {state.get('profit_factor')}",
        f"- MAX_DRAWDOWN: {state.get('maximum_drawdown')}",
        f"- CONSECUTIVE_LOSSES: {state.get('consecutive_losses')}",
        f"- P1_STATUS: {state.get('p1_status')}",
        f"- PROFITABILITY_PROVEN: {state.get('profitability_proven', False)}",
        f"- READY_FOR_P2: {state.get('ready_for_p2_review', False)}",
        "",
        "## PAIR RESULTS",
        "",
    ]
    if pair_results:
        for item in pair_results:
            report_lines.append(
                "- {instrument}: usable={data_usable} candidate={candidate_produced} reason={reason} internal_error={internal_error}".format(
                    instrument=item.get("instrument", "UNKNOWN"),
                    data_usable=item.get("data_usable", False),
                    candidate_produced=item.get("candidate_produced", False),
                    reason=item.get("first_canonical_failure_reason") or "NONE",
                    internal_error=item.get("internal_error_classification") or "NONE",
                )
            )
    else:
        report_lines.append("- NONE")
    report_lines.extend(
        [
            "",
            "All results are local PAPER evidence only. No broker write, Practice order, LIVE trade, or money movement occurred.",
            "",
        ]
    )
    paths.report.parent.mkdir(parents=True, exist_ok=True)
    paths.report.write_text("\n".join(report_lines), encoding="utf-8")


def _json_safe_value(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(child) for child in value]
    if isinstance(value, tuple):
        return [_json_safe_value(child) for child in value]
    return value


def _runtime_state(
    *,
    universe: Mapping[str, Any],
    ledger_records: Sequence[Mapping[str, Any]],
    active_session: Mapping[str, Any] | None,
    started_utc: str,
    updated_utc: str,
    stop_reason: str | None,
    last_action: str | None,
    last_reason: str | None,
    pair_results: Sequence[Mapping[str, Any]],
    runtime_root: Path,
    segment_started_utc: str,
    segment_completed_utc: str | None,
    segment_status: str,
    segment_stop_reason: str,
    segment_cycles_requested: int,
    segment_cycles_completed: int,
    segment_internal_evaluation_errors: int,
    segment_pairs_evaluated: int,
    segment_pairs_with_usable_data: int,
    segment_pairs_with_unavailable_data: int,
    segment_pairs_with_candidates: int,
    segment_candidates_accepted: int,
    segment_rejection_reason_counts: Mapping[str, int],
    latest_cycle_pairs_evaluated: int,
    latest_cycle_pairs_with_usable_data: int,
    latest_cycle_pairs_with_unavailable_data: int,
    latest_cycle_pairs_with_candidates: int,
    latest_cycle_candidates_accepted: int,
    latest_cycle_internal_evaluation_errors: int,
    latest_cycle_reason_counts: Mapping[str, int],
    latest_cycle_summary_reason: str,
    latest_cycle_chosen_instrument: str | None,
) -> dict[str, Any]:
    stats = replay_trade_stats([dict(item) for item in ledger_records])
    qualifying_count = len(ledger_records)
    profit_factor = stats["profit_factor"]
    if isinstance(profit_factor, float) and math.isinf(profit_factor):
        profit_factor = "INFINITE"
    safe_pair_results: list[dict[str, Any]] = []
    for item in pair_results:
        record = dict(item)
        if "candidate" in record:
            record["candidate"] = _json_safe_value(record["candidate"])
        safe_pair_results.append(record)
    p1_evaluation = evaluate_strategy_evidence(
        [
            {
                "trade_id": record["trade_id"],
                "entry": record["entry_price"],
                "exit": record["exit_price"],
                "realized_pl": record["realized_pl"],
                "timestamp": record["exit_timestamp_utc"],
                "evidence_type": record["evidence_type"],
            }
            for record in ledger_records
        ]
    )
    return {
        "schema": CAMPAIGN_SCHEMA,
        "version": VERSION,
        "campaign_version": VERSION,
        "campaign_status": "COMPLETE" if qualifying_count >= 30 else ("BLOCKED" if stop_reason else "RUNNING"),
        "stop_reason": stop_reason,
        "started_utc": started_utc,
        "updated_utc": updated_utc,
        "completed_utc": updated_utc if qualifying_count >= 30 else None,
        "segment_started_utc": segment_started_utc,
        "segment_completed_utc": segment_completed_utc,
        "segment_status": segment_status,
        "segment_stop_reason": segment_stop_reason,
        "segment_cycles_requested": segment_cycles_requested,
        "segment_cycles_completed": segment_cycles_completed,
        "segment_internal_evaluation_errors": segment_internal_evaluation_errors,
        "segment_pairs_discovered": len(universe.get("discovered_pairs", [])),
        "segment_pairs_evaluated": segment_pairs_evaluated,
        "segment_pairs_with_usable_data": segment_pairs_with_usable_data,
        "segment_pairs_with_unavailable_data": segment_pairs_with_unavailable_data,
        "segment_pairs_with_candidates": segment_pairs_with_candidates,
        "segment_candidates_accepted": segment_candidates_accepted,
        "segment_rejection_reason_counts": dict(sorted(segment_rejection_reason_counts.items())),
        "latest_cycle_pairs_evaluated": latest_cycle_pairs_evaluated,
        "latest_cycle_pairs_with_usable_data": latest_cycle_pairs_with_usable_data,
        "latest_cycle_pairs_with_unavailable_data": latest_cycle_pairs_with_unavailable_data,
        "latest_cycle_pairs_with_candidates": latest_cycle_pairs_with_candidates,
        "latest_cycle_candidates_accepted": latest_cycle_candidates_accepted,
        "latest_cycle_internal_evaluation_errors": latest_cycle_internal_evaluation_errors,
        "latest_cycle_reason_counts": dict(sorted(latest_cycle_reason_counts.items())),
        "latest_cycle_summary_reason": latest_cycle_summary_reason,
        "latest_cycle_chosen_instrument": latest_cycle_chosen_instrument,
        "target_qualifying_trades": 30,
        "accepted_qualifying_trades": qualifying_count,
        "current_trade_number": qualifying_count,
        "remaining_trades": max(0, 30 - qualifying_count),
        "active_position": active_session,
        "active_position_status": "ACTIVE" if active_session else "NONE",
        "last_trade": ledger_records[-1] if ledger_records else None,
        "last_action": last_action,
        "latest_rejection_reason": last_reason,
        "eligible_universe": universe.get("discovered_pairs", []),
        "universe_fingerprint": universe.get("universe_fingerprint"),
        "protocol_version": PROTOCOL_VERSION,
        "strategy_name": STRATEGY_ID,
        "runtime_root": str(runtime_root),
        "pair_results": safe_pair_results,
        "trade_results": [
            {
                "trade_number": index + 1,
                "trade_id": record["trade_id"],
                "instrument": record["instrument"],
                "entry": record["entry_price"],
                "exit": record["exit_price"],
                "realized_pl": record["realized_pl"],
                "cumulative_paper_pl": sum(float(item["realized_pl"]) for item in ledger_records[: index + 1]),
            }
            for index, record in enumerate(ledger_records)
        ],
        "net_pl": stats["net_r"],
        "profit_factor": profit_factor,
        "maximum_drawdown": stats["maximum_drawdown_r"],
        "consecutive_losses": stats["maximum_loss_streak"],
        "expectancy": stats["expectancy_r"],
        "win_rate": stats["win_rate"],
        "average_realized_r": stats["average_realized_r"],
        "positive_r": sum(1 for item in ledger_records if float(item["realized_r"]) > 0),
        "negative_r": sum(1 for item in ledger_records if float(item["realized_r"]) < 0),
        "flat_r": sum(1 for item in ledger_records if float(item["realized_r"]) == 0),
        "p1_status": p1_evaluation["strategy_evidence_status"],
        "profitability_proven": bool(p1_evaluation["profitability_proven"]),
        "ready_for_p2_review": bool(p1_evaluation["ready_for_p2_review"]),
        **SAFETY,
    }


def run_normalized_multipair_campaign(
    client: OandaReadOnlyClient,
    *,
    cycles: int,
    reviewer_identity: str,
    runtime_root: Path = RUNTIME_ROOT,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], None] = time.sleep,
    owner_cancelled: Callable[[], bool] = lambda: False,
    kill_switch_active: Callable[[], bool] = lambda: False,
    risk_halt_active: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles <= 0:
        raise ValueError("positive_cycle_count_required")
    if not reviewer_identity.strip():
        raise ValueError("owner_reviewer_required")
    runtime_root.mkdir(parents=True, exist_ok=True)
    paths = CampaignPaths(runtime_root)
    universe = _discover_universe_with_retry(client, sleep=sleep)
    eligible = [
        NormalizedInstrument(
            instrument=item["instrument"],
            display_precision=int(item["display_precision"]),
            pip_location=int(item["pip_location"]),
            tradeable=True,
            priceable=True,
        )
        for item in universe["eligible_instruments"]
    ]
    lock_owner = _acquire_lock(paths.lock, now=now())
    if lock_owner is None:
        return {
            "schema": CAMPAIGN_SCHEMA,
            "campaign_status": "BLOCKED",
            "stop_reason": "LIVE_WRITER_LOCK_HELD",
            "accepted_qualifying_trades": 0,
            **SAFETY,
        }
    started = _stamp(now())
    ledger_records = _load_ledger(paths.ledger)
    last_action = None
    last_reason = None
    pair_results: list[dict[str, Any]] = []
    segment_counters = _empty_segment_counters()
    latest_cycle_counters = _empty_segment_counters()
    latest_cycle_reason_counts: dict[str, int] = {}
    latest_cycle_summary_reason = "NO_QUALIFYING_CANDIDATE"
    latest_cycle_chosen_instrument: str | None = None
    segment_internal_evaluation_errors = 0
    segment_stop_reason = "BOUNDED_CYCLE_LIMIT"
    segment_status = "RUNNING"
    try:
        for cycle in range(1, cycles + 1):
            current = now().astimezone(timezone.utc)
            first_failure_counts: dict[str, int] = {}
            if not _touch_lock(paths.lock, lock_owner, now=current):
                return {
                    "schema": CAMPAIGN_SCHEMA,
                    "campaign_status": "BLOCKED",
                    "stop_reason": "LIVE_WRITER_LOCK_LOST",
                    **SAFETY,
                }
            if owner_cancelled():
                segment_stop_reason = "OWNER_CANCELLED"
                segment_status = "BLOCKED"
                break
            if kill_switch_active():
                segment_stop_reason = "KILL_SWITCH_ACTIVE"
                segment_status = "BLOCKED"
                break
            if risk_halt_active():
                segment_stop_reason = "RISK_HALT_ACTIVE"
                segment_status = "BLOCKED"
                break
            active = load_active_session(paths.active_session)
            try:
                pricing = client.pricing(tuple(item.instrument for item in eligible))
            except OandaReadOnlyClientError as exc:
                if not _is_transient_read_failure(exc):
                    raise
                latest_cycle_counters["pairs_evaluated"] = 0
                latest_cycle_counters["pairs_with_usable_data"] = 0
                latest_cycle_counters["pairs_with_unavailable_data"] = len(eligible)
                latest_cycle_counters["pairs_with_candidates"] = 0
                latest_cycle_counters["candidates_accepted"] = 0
                latest_cycle_counters["internal_evaluation_errors"] = 0
                latest_cycle_reason_counts = {"data_unavailable": len(eligible)}
                latest_cycle_summary_reason = "WAIT_FOR_DATA"
                next_wait_seconds = _data_unavailable_backoff_seconds(1)
                _append_wait_for_data(
                    paths=paths,
                    cycle_number=cycle,
                    maximum_cycles=cycles,
                    now=current,
                    next_check_in_seconds=next_wait_seconds,
                    active_position_status="ACTIVE" if active else "NONE",
                )
                last_action = "WAIT_FOR_DATA"
                last_reason = "data_unavailable"
                sleep(next_wait_seconds)
                continue
            quote_mids = quote_mids_from_pricing(pricing)
            if active:
                instrument_name = str(active["instrument"])
                snapshot = _pair_snapshot(pricing, instrument_name)
                update_paper_session_extremes(snapshot, paths.active_session)
                active = load_active_session(paths.active_session)
                pair_results.append(
                    {
                        "instrument": instrument_name,
                        "active": True,
                        "data_usable": True,
                        "candidate_produced": False,
                        "first_canonical_failure_reason": "duplicate_position_guard",
                        "internal_error_classification": None,
                        "accepted": False,
                    }
                )
                direction = str(active.get("direction", "BUY")).upper()
                if direction == "BUY":
                    target_hit = float(snapshot["bid"]) >= float(active["target_price"])
                    stop_hit = float(snapshot["bid"]) <= float(active["stop_price"])
                else:
                    target_hit = float(snapshot["ask"]) <= float(active["target_price"])
                    stop_hit = float(snapshot["ask"]) >= float(active["stop_price"])
                if target_hit or stop_hit:
                    exit_reason = "paper_target" if target_hit else "paper_stop"
                    record = build_completed_trade_record(active, snapshot, exit_reason, reviewer_identity, _stamp(now()))
                    normalized_outcome = normalized_trade_outcome(active, snapshot, quote_mids=quote_mids)
                    record.update(normalized_outcome)
                    record.update(
                        {
                            "instrument": active["instrument"],
                            "strategy_name": STRATEGY_ID,
                            "strategy_id": STRATEGY_ID,
                            "protocol_version": PROTOCOL_VERSION,
                            "direction": direction,
                            "mode": "PAPER_ONLY",
                            "paper_only": True,
                            "trade_id": record["trade_id"],
                            "realized_pl": record["realized_pl"],
                            "actual_paper_entry": active.get("entry_price"),
                            "signal_reference_entry": active.get("signal_reference_entry", active.get("entry_price")),
                            "nominal_target_rr": active.get("nominal_target_rr", active.get("planned_reward_risk")),
                            "effective_reward_risk": active.get("effective_reward_risk"),
                            "target_price": active.get("target_price"),
                            "stop_price": active.get("stop_price"),
                            "quote_currency": active["quote_currency"],
                            "display_precision": active.get("display_precision", 5),
                            "pip_location": active.get("pip_location", -4),
                            "pip_size": active.get("pip_size", 0.0001),
                            "base_currency": active.get("base_currency"),
                            "universe_fingerprint": universe["universe_fingerprint"],
                            "canonical_main_sha": "7f7bb22e2d6ddfb6df337588af9600acb91604b4",
                        }
                    )
                    pipeline_paths = {
                        "ledger": paths.ledger,
                        "state": paths.campaign_state,
                        "report": paths.report,
                        "events": paths.telemetry,
                    }
                    temp = paths.ledger.with_suffix(".candidate.tmp.json")
                    temp.write_text(json.dumps(record, sort_keys=True, allow_nan=False), encoding="utf-8")
                    try:
                        run_pipeline(temp, paths.ledger, paths.campaign_state, paths.report)
                    finally:
                        temp.unlink(missing_ok=True)
                    ledger_records = _load_ledger(paths.ledger)
                    _append_jsonl(paths.telemetry, _cycle_record(
                        cycle_number=cycle,
                        maximum_cycles=cycles,
                        action="PAPER_SESSION_CLOSE",
                        now=current,
                        signal=record,
                        snapshot=snapshot,
                        extra={
                            "paper_session_event": "CLOSE",
                            "exit_reason": exit_reason,
                            "realized_paper_pl": record["realized_pl"],
                            "realized_r": record["realized_r"],
                            "roi_class": record["roi_class"],
                            "risk_amount": record["risk_amount"],
                            "planned_reward_risk": record["planned_reward_risk"],
                            "candidate_status": "NONE",
                            "paper_eligible": False,
                            "ask_geometry_status": "NOT_EVALUATED",
                            "universe_fingerprint": universe["universe_fingerprint"],
                        },
                    ))
                    active_path = paths.active_session
                    active_path.write_text(
                        json.dumps({
                            "schema": "AIOS_P1_SUPERVISED_PAPER_SESSION.v1",
                            "status": "CLOSED",
                            "closed_at_utc": _stamp(now()),
                            "closed_reason": exit_reason,
                            "strategy_id": STRATEGY_ID,
                            "strategy_name": STRATEGY_ID,
                        }, sort_keys=True, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8",
                    )
                    last_action = "PAPER_SESSION_CLOSE"
                    last_reason = exit_reason
                    continue
                _append_jsonl(paths.telemetry, _cycle_record(
                    cycle_number=cycle,
                    maximum_cycles=cycles,
                    action="PAPER_SESSION_HELD",
                    now=current,
                    signal=active,
                    snapshot=snapshot,
                    extra={
                        "paper_session_event": "HELD",
                        "active_position_status": "ACTIVE",
                        "universe_fingerprint": universe["universe_fingerprint"],
                    },
                    rejection_reasons=("duplicate_position_guard",),
                    next_check_in_seconds=POLL_INTERVAL_SECONDS,
                ))
                last_action = "PAPER_SESSION_HELD"
                last_reason = "duplicate_position_guard"
                sleep(POLL_INTERVAL_SECONDS)
                continue

            pair_candidates: list[dict[str, Any]] = []
            first_failure_counts: dict[str, int] = {}
            cycle_counters = _empty_segment_counters()
            cycle_reason_counts: dict[str, int] = {}
            cycle_internal_error = False
            cycle_first_reason: str | None = None
            for instrument in eligible:
                cycle_counters["pairs_evaluated"] += 1
                segment_counters["pairs_evaluated"] += 1
                try:
                    history = fetch_completed_m5_history(client, instrument.instrument, candle_count=DEFAULT_CANDLE_COUNT)
                    candles = candles_to_strategy_window(history, instrument=instrument.instrument)
                except OandaReadOnlyClientError:
                    first_failure_counts["data_unavailable"] = first_failure_counts.get("data_unavailable", 0) + 1
                    cycle_counters["pairs_with_unavailable_data"] += 1
                    segment_counters["pairs_with_unavailable_data"] += 1
                    cycle_reason_counts["data_unavailable"] = cycle_reason_counts.get("data_unavailable", 0) + 1
                    if cycle_first_reason is None:
                        cycle_first_reason = "data_unavailable"
                    pair_results.append(
                        {
                            "instrument": instrument.instrument,
                            "data_usable": False,
                            "candidate_produced": False,
                            "first_canonical_failure_reason": "data_unavailable",
                            "internal_error_classification": None,
                            "accepted": False,
                        }
                    )
                    continue
                except ValueError as exc:
                    canonical_reason = _canonical_pair_value_error_reason(exc)
                    if canonical_reason is None:
                        segment_internal_evaluation_errors += 1
                        cycle_internal_error = True
                        cycle_counters["internal_evaluation_errors"] += 1
                        segment_counters["internal_evaluation_errors"] += 1
                        canonical_exc = exc.__class__.__name__
                        cycle_reason_counts["internal_evaluation_error"] = cycle_reason_counts.get("internal_evaluation_error", 0) + 1
                        if cycle_first_reason is None:
                            cycle_first_reason = "internal_evaluation_error"
                        pair_results.append(
                            {
                                "instrument": instrument.instrument,
                                "data_usable": False,
                                "candidate_produced": False,
                                "first_canonical_failure_reason": "internal_evaluation_error",
                                "internal_error_classification": canonical_exc,
                                "accepted": False,
                            }
                        )
                        segment_status = "FAILED"
                        segment_stop_reason = "INTERNAL_EVALUATION_ERROR"
                        continue
                    first_failure_counts[canonical_reason] = first_failure_counts.get(canonical_reason, 0) + 1
                    cycle_reason_counts[canonical_reason] = cycle_reason_counts.get(canonical_reason, 0) + 1
                    if cycle_first_reason is None:
                        cycle_first_reason = canonical_reason
                    pair_results.append(
                        {
                            "instrument": instrument.instrument,
                            "data_usable": False,
                            "candidate_produced": False,
                            "first_canonical_failure_reason": canonical_reason,
                            "internal_error_classification": None,
                            "accepted": False,
                        }
                    )
                    continue
                try:
                    snapshot = _pair_snapshot(pricing, instrument.instrument)
                except ValueError as exc:
                    canonical_reason = _canonical_pair_value_error_reason(exc)
                    if canonical_reason is None:
                        segment_internal_evaluation_errors += 1
                        cycle_internal_error = True
                        cycle_counters["internal_evaluation_errors"] += 1
                        segment_counters["internal_evaluation_errors"] += 1
                        canonical_exc = exc.__class__.__name__
                        cycle_reason_counts["internal_evaluation_error"] = cycle_reason_counts.get("internal_evaluation_error", 0) + 1
                        if cycle_first_reason is None:
                            cycle_first_reason = "internal_evaluation_error"
                        pair_results.append(
                            {
                                "instrument": instrument.instrument,
                                "data_usable": False,
                                "candidate_produced": False,
                                "first_canonical_failure_reason": "internal_evaluation_error",
                                "internal_error_classification": canonical_exc,
                                "accepted": False,
                            }
                        )
                        segment_status = "FAILED"
                        segment_stop_reason = "INTERNAL_EVALUATION_ERROR"
                        continue
                    first_failure_counts[canonical_reason] = first_failure_counts.get(canonical_reason, 0) + 1
                    cycle_reason_counts[canonical_reason] = cycle_reason_counts.get(canonical_reason, 0) + 1
                    if cycle_first_reason is None:
                        cycle_first_reason = canonical_reason
                    pair_results.append(
                        {
                            "instrument": instrument.instrument,
                            "data_usable": False,
                            "candidate_produced": False,
                            "first_canonical_failure_reason": canonical_reason,
                            "internal_error_classification": None,
                            "accepted": False,
                        }
                    )
                    continue
                cycle_counters["pairs_with_usable_data"] += 1
                segment_counters["pairs_with_usable_data"] += 1
                try:
                    evaluation = evaluate_supertrend_pullback(
                        candles,
                        normalized_strategy_config(instrument.instrument),
                    )
                except Exception as exc:
                    segment_internal_evaluation_errors += 1
                    cycle_internal_error = True
                    cycle_counters["internal_evaluation_errors"] += 1
                    segment_counters["internal_evaluation_errors"] += 1
                    canonical_exc = exc.__class__.__name__
                    cycle_reason_counts["internal_evaluation_error"] = cycle_reason_counts.get("internal_evaluation_error", 0) + 1
                    if cycle_first_reason is None:
                        cycle_first_reason = "internal_evaluation_error"
                    pair_results.append(
                        {
                            "instrument": instrument.instrument,
                            "data_usable": True,
                            "candidate_produced": False,
                            "first_canonical_failure_reason": "internal_evaluation_error",
                            "internal_error_classification": canonical_exc,
                            "accepted": False,
                        }
                    )
                    segment_status = "FAILED"
                    segment_stop_reason = "INTERNAL_EVALUATION_ERROR"
                    continue
                if evaluation.get("accepted") is not True:
                    canonical_reason = _canonical_no_trade_reason(list(evaluation.get("no_trade_reasons") or []))
                    first_failure_counts[canonical_reason] = first_failure_counts.get(canonical_reason, 0) + 1
                    cycle_reason_counts[canonical_reason] = cycle_reason_counts.get(canonical_reason, 0) + 1
                    if cycle_first_reason is None:
                        cycle_first_reason = canonical_reason
                    pair_results.append(
                        {
                            "instrument": instrument.instrument,
                            "data_usable": True,
                            "candidate_produced": False,
                            "first_canonical_failure_reason": canonical_reason,
                            "internal_error_classification": None,
                            "accepted": False,
                        }
                    )
                    continue
                candidate = replay_candidate(instrument, candles, snapshot)
                if candidate is None:
                    segment_internal_evaluation_errors += 1
                    cycle_internal_error = True
                    cycle_counters["internal_evaluation_errors"] += 1
                    segment_counters["internal_evaluation_errors"] += 1
                    cycle_reason_counts["internal_evaluation_error"] = cycle_reason_counts.get("internal_evaluation_error", 0) + 1
                    if cycle_first_reason is None:
                        cycle_first_reason = "internal_evaluation_error"
                    pair_results.append(
                        {
                            "instrument": instrument.instrument,
                            "data_usable": True,
                            "candidate_produced": False,
                            "first_canonical_failure_reason": "internal_evaluation_error",
                            "internal_error_classification": "candidate_geometry_rejected",
                            "accepted": False,
                        }
                    )
                    segment_status = "FAILED"
                    segment_stop_reason = "INTERNAL_EVALUATION_ERROR"
                    continue
                candidate = calibrate_candidate_to_actual_entry(
                    candidate,
                    snapshot,
                    reward_risk=TARGET_RR,
                )
                cycle_counters["pairs_with_candidates"] += 1
                segment_counters["pairs_with_candidates"] += 1
                pair_candidates.append({
                    "instrument": instrument.instrument,
                    "candidate": candidate,
                    "snapshot": snapshot,
                    "rank": candidate_rank_key(candidate, snapshot),
                })
                pair_results.append(
                    {
                        "instrument": instrument.instrument,
                        "data_usable": True,
                        "candidate_produced": True,
                        "first_canonical_failure_reason": None,
                        "internal_error_classification": None,
                        "accepted": False,
                        "candidate": candidate,
                    }
                )
            latest_cycle_counters = dict(cycle_counters)
            latest_cycle_reason_counts = dict(sorted(cycle_reason_counts.items()))
            latest_cycle_summary_reason = "INTERNAL_EVALUATION_ERROR" if cycle_internal_error else "NO_QUALIFYING_CANDIDATE"
            if not pair_candidates:
                _append_jsonl(paths.telemetry, _cycle_record(
                    cycle_number=cycle,
                    maximum_cycles=cycles,
                    action=latest_cycle_summary_reason,
                    now=current,
                    extra={
                        "paper_session_event": "NONE",
                        "candidate_status": "NONE",
                        "paper_eligible": False,
                        "first_failure_counts": first_failure_counts,
                        "cycle_reason_counts": dict(sorted(cycle_reason_counts.items())),
                        "cycle_internal_evaluation_errors": cycle_counters["internal_evaluation_errors"],
                        "cycle_pairs_evaluated": cycle_counters["pairs_evaluated"],
                        "cycle_pairs_with_usable_data": cycle_counters["pairs_with_usable_data"],
                        "cycle_pairs_with_unavailable_data": cycle_counters["pairs_with_unavailable_data"],
                        "cycle_pairs_with_candidates": cycle_counters["pairs_with_candidates"],
                        "universe_fingerprint": universe["universe_fingerprint"],
                    },
                    rejection_reasons=(latest_cycle_summary_reason,),
                    next_check_in_seconds=POLL_INTERVAL_SECONDS,
                ))
                last_action = latest_cycle_summary_reason
                last_reason = cycle_first_reason
                sleep(POLL_INTERVAL_SECONDS)
                continue
            pair_candidates.sort(key=lambda item: item["rank"])
            session = None
            chosen = None
            while pair_candidates:
                chosen = pair_candidates[0]
                candidate = chosen["candidate"]
                snapshot = chosen["snapshot"]
                open_snapshot = dict(snapshot)
                open_snapshot["instrument"] = chosen["instrument"]
                open_snapshot["bid"] = snapshot["bid"]
                open_snapshot["ask"] = snapshot["ask"]
                open_snapshot["mid"] = snapshot["mid"]
                open_snapshot["spread"] = snapshot["spread"]
                try:
                    session = open_paper_session(
                        open_snapshot,
                        candidate,
                        reviewer_identity,
                        _stamp(current),
                        paths.active_session,
                    )
                except ValueError as exc:
                    if str(exc) != "unsupported_instrument":
                        raise
                    reason = "unsupported_instrument"
                    first_failure_counts[reason] = first_failure_counts.get(reason, 0) + 1
                    cycle_reason_counts[reason] = cycle_reason_counts.get(reason, 0) + 1
                    if cycle_first_reason is None:
                        cycle_first_reason = reason
                    pair_results.append(
                        {
                            "instrument": chosen["instrument"],
                            "data_usable": True,
                            "candidate_produced": True,
                            "first_canonical_failure_reason": reason,
                            "internal_error_classification": None,
                            "accepted": False,
                            "candidate": candidate,
                        }
                    )
                    pair_candidates.pop(0)
                    chosen = None
                    session = None
                    continue
                latest_cycle_chosen_instrument = chosen["instrument"]
                break
            if session is None or chosen is None:
                latest_cycle_reason_counts = dict(sorted(cycle_reason_counts.items()))
                latest_cycle_summary_reason = "NO_QUALIFYING_CANDIDATE"
                _append_jsonl(paths.telemetry, _cycle_record(
                    cycle_number=cycle,
                    maximum_cycles=cycles,
                    action=latest_cycle_summary_reason,
                    now=current,
                    extra={
                        "paper_session_event": "NONE",
                        "candidate_status": "NONE",
                        "paper_eligible": False,
                        "first_failure_counts": first_failure_counts,
                        "cycle_reason_counts": dict(sorted(cycle_reason_counts.items())),
                        "cycle_internal_evaluation_errors": cycle_counters["internal_evaluation_errors"],
                        "cycle_pairs_evaluated": cycle_counters["pairs_evaluated"],
                        "cycle_pairs_with_usable_data": cycle_counters["pairs_with_usable_data"],
                        "cycle_pairs_with_unavailable_data": cycle_counters["pairs_with_unavailable_data"],
                        "cycle_pairs_with_candidates": cycle_counters["pairs_with_candidates"],
                        "universe_fingerprint": universe["universe_fingerprint"],
                    },
                    rejection_reasons=(latest_cycle_summary_reason,),
                    next_check_in_seconds=POLL_INTERVAL_SECONDS,
                ))
                last_action = latest_cycle_summary_reason
                last_reason = cycle_first_reason
                sleep(POLL_INTERVAL_SECONDS)
                continue
            candidate = chosen["candidate"]
            snapshot = chosen["snapshot"]
            session["display_precision"] = candidate["display_precision"]
            session["pip_location"] = candidate["pip_location"]
            session["pip_size"] = candidate["pip_size"]
            session["base_currency"] = candidate["base_currency"]
            session["quote_currency"] = candidate["quote_currency"]
            session["universe_fingerprint"] = universe["universe_fingerprint"]
            session["strategy_id"] = STRATEGY_ID
            session["strategy_name"] = STRATEGY_ID
            paths.active_session.write_text(_stable_json(session), encoding="utf-8")
            cycle_counters["candidates_accepted"] += 1
            segment_counters["candidates_accepted"] += 1
            for result in reversed(pair_results):
                if result.get("instrument") == chosen["instrument"] and result.get("candidate") == candidate:
                    result["accepted"] = True
                    break
            _append_jsonl(paths.telemetry, _cycle_record(
                cycle_number=cycle,
                maximum_cycles=cycles,
                action="PAPER_SESSION_OPEN",
                now=current,
                signal=candidate,
                snapshot=snapshot,
                extra={
                    "paper_session_event": "OPEN",
                    "candidate_status": "PAPER_ELIGIBLE",
                    "paper_eligible": True,
                    "chosen_instrument": chosen["instrument"],
                    "universe_fingerprint": universe["universe_fingerprint"],
                },
                rejection_reasons=(),
                next_check_in_seconds=POLL_INTERVAL_SECONDS,
            ))
            last_action = "PAPER_SESSION_OPEN"
            last_reason = None
            sleep(POLL_INTERVAL_SECONDS)
        updated = _stamp(now())
        if segment_status != "FAILED":
            segment_status = "COMPLETE"
            segment_stop_reason = "BOUNDED_CYCLE_LIMIT"
        segment_completed = updated
        latest_cycle_reason_counts = dict(sorted(latest_cycle_reason_counts.items())) if latest_cycle_reason_counts else dict(sorted(first_failure_counts.items()))
        segment_rejection_reason_counts: dict[str, int] = {}
        for result in pair_results:
            reason = str(result.get("first_canonical_failure_reason") or "").strip()
            if reason:
                segment_rejection_reason_counts[reason] = segment_rejection_reason_counts.get(reason, 0) + 1
        state = _runtime_state(
            universe=universe,
            ledger_records=ledger_records,
            active_session=load_active_session(paths.active_session),
            started_utc=started,
            updated_utc=updated,
            stop_reason=None if len(ledger_records) < 30 else "TARGET_REACHED",
            last_action=last_action,
            last_reason=last_reason,
            pair_results=pair_results,
            runtime_root=runtime_root,
            segment_started_utc=started,
            segment_completed_utc=segment_completed,
            segment_status=segment_status,
            segment_stop_reason=segment_stop_reason,
            segment_cycles_requested=cycles,
            segment_cycles_completed=cycles,
            segment_internal_evaluation_errors=segment_internal_evaluation_errors,
            segment_pairs_evaluated=segment_counters["pairs_evaluated"],
            segment_pairs_with_usable_data=segment_counters["pairs_with_usable_data"],
            segment_pairs_with_unavailable_data=segment_counters["pairs_with_unavailable_data"],
            segment_pairs_with_candidates=segment_counters["pairs_with_candidates"],
            segment_candidates_accepted=segment_counters["candidates_accepted"],
            segment_rejection_reason_counts=segment_rejection_reason_counts,
            latest_cycle_pairs_evaluated=latest_cycle_counters.get("pairs_evaluated", 0),
            latest_cycle_pairs_with_usable_data=latest_cycle_counters.get("pairs_with_usable_data", 0),
            latest_cycle_pairs_with_unavailable_data=latest_cycle_counters.get("pairs_with_unavailable_data", 0),
            latest_cycle_pairs_with_candidates=latest_cycle_counters.get("pairs_with_candidates", 0),
            latest_cycle_candidates_accepted=latest_cycle_counters.get("candidates_accepted", 0),
            latest_cycle_internal_evaluation_errors=latest_cycle_counters.get("internal_evaluation_errors", 0),
            latest_cycle_reason_counts=latest_cycle_reason_counts,
            latest_cycle_summary_reason=latest_cycle_summary_reason,
            latest_cycle_chosen_instrument=latest_cycle_chosen_instrument,
        )
        paths.campaign_state.write_text(_stable_json(state), encoding="utf-8")
        _write_ledger(paths.ledger, ledger_records)
        _write_report(paths, state)
        return state
    finally:
        if lock_owner is not None:
            _release_lock(paths.lock, lock_owner)


def summarize_campaign_state(state: Mapping[str, Any]) -> dict[str, Any]:
    ledger_records = list(state.get("trade_results", []))
    return {
        "schema": state.get("schema", CAMPAIGN_SCHEMA),
        "protocol_version": state.get("protocol_version", PROTOCOL_VERSION),
        "qualifying_current": state.get("accepted_qualifying_trades", 0),
        "trades_remaining": state.get("remaining_trades", 30),
        "campaign_status": state.get("campaign_status", "UNKNOWN"),
        "segment_status": state.get("segment_status", "UNKNOWN"),
        "segment_stop_reason": state.get("segment_stop_reason"),
        "segment_cycles_requested": state.get("segment_cycles_requested", 0),
        "segment_cycles_completed": state.get("segment_cycles_completed", 0),
        "segment_internal_evaluation_errors": state.get("segment_internal_evaluation_errors", 0),
        "segment_pairs_discovered": state.get("segment_pairs_discovered", 0),
        "segment_pairs_evaluated": state.get("segment_pairs_evaluated", 0),
        "segment_pairs_with_usable_data": state.get("segment_pairs_with_usable_data", 0),
        "segment_pairs_with_unavailable_data": state.get("segment_pairs_with_unavailable_data", 0),
        "segment_pairs_with_candidates": state.get("segment_pairs_with_candidates", 0),
        "active_position_status": state.get("active_position_status", "NONE"),
        "last_action": state.get("last_action", "NONE"),
        "latest_rejection_reason": state.get("latest_rejection_reason"),
        "latest_cycle_summary_reason": state.get("latest_cycle_summary_reason"),
        "latest_cycle_reason_counts": state.get("latest_cycle_reason_counts", {}),
        "segment_rejection_reason_counts": state.get("segment_rejection_reason_counts", {}),
        "net_paper_pl": state.get("net_pl"),
        "expectancy": state.get("expectancy"),
        "profit_factor": state.get("profit_factor"),
        "max_drawdown": state.get("maximum_drawdown"),
        "positive_r": state.get("positive_r"),
        "negative_r": state.get("negative_r"),
        "flat_r": state.get("flat_r"),
        "eligible_universe": state.get("eligible_universe", []),
        "universe_fingerprint": state.get("universe_fingerprint"),
        "broker_writes": False,
        "practice_orders": False,
        "live_authority": False,
    }
