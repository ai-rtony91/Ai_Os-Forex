"""Normalized all-pairs LONG-only PAPER collector for the P1 Supertrend lane."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
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
from automation.forex_engine.forex_p1_supervised_paper_session_v1 import (
    build_completed_trade_record,
    load_active_session,
    open_paper_session,
    update_paper_session_extremes,
)
from automation.forex_engine.models import Direction
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient, OandaReadOnlyClientError

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
        stream.write(json.dumps(dict(record), sort_keys=True, allow_nan=False) + "\n")
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
) -> dict[str, Any]:
    stats = replay_trade_stats([dict(item) for item in ledger_records])
    qualifying_count = len(ledger_records)
    profit_factor = stats["profit_factor"]
    if isinstance(profit_factor, float) and math.isinf(profit_factor):
        profit_factor = "INFINITE"
    return {
        "schema": CAMPAIGN_SCHEMA,
        "version": VERSION,
        "campaign_version": VERSION,
        "campaign_status": "COMPLETE" if qualifying_count >= 30 else ("BLOCKED" if stop_reason else "RUNNING"),
        "stop_reason": stop_reason,
        "started_utc": started_utc,
        "updated_utc": updated_utc,
        "completed_utc": updated_utc if qualifying_count >= 30 else None,
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
        "pair_results": list(pair_results),
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
    try:
        for cycle in range(1, cycles + 1):
            current = now().astimezone(timezone.utc)
            if not _touch_lock(paths.lock, lock_owner, now=current):
                return {
                    "schema": CAMPAIGN_SCHEMA,
                    "campaign_status": "BLOCKED",
                    "stop_reason": "LIVE_WRITER_LOCK_LOST",
                    **SAFETY,
                }
            if owner_cancelled():
                break
            if kill_switch_active():
                break
            if risk_halt_active():
                break
            active = load_active_session(paths.active_session)
            try:
                pricing = client.pricing(tuple(item.instrument for item in eligible))
            except OandaReadOnlyClientError as exc:
                if not _is_transient_read_failure(exc):
                    raise
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
                        "candidate": False,
                        "reason": "duplicate_position_guard",
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
            for instrument in eligible:
                try:
                    history = fetch_completed_m5_history(client, instrument.instrument, candle_count=DEFAULT_CANDLE_COUNT)
                    candles = candles_to_strategy_window(history, instrument=instrument.instrument)
                    snapshot = _pair_snapshot(pricing, instrument.instrument)
                    candidate = _candidate_from_replay(instrument, candles, snapshot)
                    if candidate is not None:
                        candidate = calibrate_candidate_to_actual_entry(
                            candidate,
                            snapshot,
                            reward_risk=TARGET_RR,
                        )
                except OandaReadOnlyClientError:
                    first_failure_counts["data_unavailable"] = first_failure_counts.get("data_unavailable", 0) + 1
                    continue
                except Exception as exc:
                    first_failure_counts["unknown_no_signal"] = first_failure_counts.get("unknown_no_signal", 0) + 1
                    continue
                if candidate is None:
                    first_failure_counts["pullback_not_confirmed"] = first_failure_counts.get("pullback_not_confirmed", 0) + 1
                    pair_results.append({"instrument": instrument.instrument, "accepted": False})
                    continue
                pair_candidates.append({
                    "instrument": instrument.instrument,
                    "candidate": candidate,
                    "snapshot": snapshot,
                    "rank": candidate_rank_key(candidate, snapshot),
                })
                pair_results.append({"instrument": instrument.instrument, "accepted": True, "candidate": candidate})
            if not pair_candidates:
                _append_jsonl(paths.telemetry, _cycle_record(
                    cycle_number=cycle,
                    maximum_cycles=cycles,
                    action="NO_SIGNAL",
                    now=current,
                    extra={
                        "paper_session_event": "NONE",
                        "candidate_status": "NONE",
                        "paper_eligible": False,
                        "first_failure_counts": first_failure_counts,
                        "universe_fingerprint": universe["universe_fingerprint"],
                    },
                    rejection_reasons=("unknown_no_signal",),
                    next_check_in_seconds=POLL_INTERVAL_SECONDS,
                ))
                last_action = "NO_SIGNAL"
                last_reason = "unknown_no_signal"
                sleep(POLL_INTERVAL_SECONDS)
                continue
            pair_candidates.sort(key=lambda item: item["rank"])
            chosen = pair_candidates[0]
            candidate = chosen["candidate"]
            snapshot = chosen["snapshot"]
            open_snapshot = dict(snapshot)
            open_snapshot["instrument"] = chosen["instrument"]
            open_snapshot["bid"] = snapshot["bid"]
            open_snapshot["ask"] = snapshot["ask"]
            open_snapshot["mid"] = snapshot["mid"]
            open_snapshot["spread"] = snapshot["spread"]
            session = open_paper_session(
                open_snapshot,
                candidate,
                reviewer_identity,
                _stamp(current),
                paths.active_session,
            )
            session["display_precision"] = candidate["display_precision"]
            session["pip_location"] = candidate["pip_location"]
            session["pip_size"] = candidate["pip_size"]
            session["base_currency"] = candidate["base_currency"]
            session["quote_currency"] = candidate["quote_currency"]
            session["universe_fingerprint"] = universe["universe_fingerprint"]
            session["strategy_id"] = STRATEGY_ID
            session["strategy_name"] = STRATEGY_ID
            paths.active_session.write_text(_stable_json(session), encoding="utf-8")
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
        )
        paths.campaign_state.write_text(_stable_json(state), encoding="utf-8")
        _write_ledger(paths.ledger, ledger_records)
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
        "active_position_status": state.get("active_position_status", "NONE"),
        "last_action": state.get("last_action", "NONE"),
        "latest_rejection_reason": state.get("latest_rejection_reason"),
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
