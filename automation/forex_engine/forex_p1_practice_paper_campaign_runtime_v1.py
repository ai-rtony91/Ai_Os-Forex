"""GET-only OANDA Practice runtime bridge for the bounded P1 paper campaign."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from automation.forex_engine.forex_p1_eurusd_m5_history_capture_v1 import (
    build_canonical_history_artifact,
    extract_canonical_completed_candles,
    resolve_canonical_practice_transport,
    validate_canonical_history_artifact,
)
from automation.forex_engine.forex_p1_eurusd_market_history_signal_v1 import (
    build_signal_state,
)
from automation.forex_engine.forex_p1_paper_autostart_v1 import (
    RuntimeLockOwnership,
    acquire_runtime_lock,
    read_runtime_lock,
    refresh_runtime_lock,
    release_runtime_lock,
    source_fingerprint,
)
from automation.forex_engine.forex_p1_oanda_practice_snapshot_capture_v1 import (
    extract_sanitized_price_snapshot,
)
from automation.forex_engine.forex_p1_cycle_provenance_v1 import (
    append_cycle_record,
    build_cycle_record,
    telemetry_path,
)
from automation.forex_engine.forex_p1_supervised_paper_campaign_v1 import (
    CampaignHalt,
    CampaignWait,
    SUPERTREND_REJECTION_REASONS,
    WAIT_FOR_DATA,
)
from automation.forex_engine.forex_p1_supervised_paper_session_v1 import (
    build_completed_trade_record,
    load_active_session,
    open_paper_session,
    update_paper_session_extremes,
)
from automation.forex_engine.oanda_read_only_client import (
    OandaReadOnlyClient,
    OandaReadOnlyClientError,
)
from automation.forex_engine.models import Candle, Direction
from automation.forex_engine.signal_rules import SPRINT_4_STRATEGY_NAME
from automation.forex_engine.strategies import (
    SUPERTREND_PULLBACK_V1,
    SupertrendPullbackConfig,
    evaluate_supertrend_pullback,
)

VERSION = "forex_p1_practice_paper_campaign_runtime_v1"
INSTRUMENT = "EUR_USD"
GRANULARITY = "M5"
CANDLE_COUNT = 50
POLL_INTERVAL_SECONDS = 300
DATA_UNAVAILABLE_BACKOFF_BASE_SECONDS = 30
DATA_UNAVAILABLE_BACKOFF_MAX_SECONDS = POLL_INTERVAL_SECONDS
SUPER_TREND_LOCK_PATH_SUFFIX = ".supertrend.paper.runtime.lock"
SUPER_TREND_LOCK_TTL_SECONDS = 300
SUPER_TREND_LOCK_SCHEMA = "AIOS_FOREX_SUPERTREND_PRACTICE_SESSION_LOCK.v1"
SUPER_TREND_LOCK_CAMPAIGN_IDENTITY = "FOREX_P1_SUPERTREND_PRACTICE_RUNTIME_V1"
SUPER_TREND_SESSION_STRATEGY = SUPERTREND_PULLBACK_V1
SUPER_TREND_SESSION_GUARD_REASON = "ACTIVE_SESSION_STRATEGY_MISMATCH"
DEFAULT_PAPER_UNITS = 100
SPRINT_4_SIGNAL_SOURCE = "sprint-4"
SUPERTREND_SIGNAL_SOURCE = "supertrend"
SIGNAL_SOURCES = (SPRINT_4_SIGNAL_SOURCE, SUPERTREND_SIGNAL_SOURCE)
SUPERTREND_CONFIG = SupertrendPullbackConfig()
M5_RUNTIME_ROOT_RELATIVE_PATH = Path(
    ".aios/runtime/forex_p1_supertrend_paper_sessions"
)
APPROVED_EXTERNAL_M5_RUNTIME_ROOT = Path(
    r"C:\Dev\Ai.Os\.aios\runtime\forex_p1_supertrend_paper_sessions"
)
SAFETY = {
    "broker_write_performed": False,
    "practice_order_performed": False,
    "live_trade_performed": False,
    "money_movement_performed": False,
    "credentials_persisted": False,
}

_SUPERTREND_RAW_REJECTION_REASON_MAP = {
    "insufficient_data": "insufficient_candles",
    "no_supertrend_direction": "no_supertrend_flip",
    "missing_supertrend_band": "no_supertrend_flip",
    "chop_zone_repeated_flips": "trend_not_aligned",
    "weak_candle_body": "pullback_not_confirmed",
    "close_confirmation_missing": "pullback_not_confirmed",
    "entry_extended_from_band": "pullback_not_confirmed",
    "reward_risk_below_minimum": "pullback_not_confirmed",
    "volatility_below_atr_threshold": "volatility_filter_failed",
}
_SUPERTREND_REJECTION_REASON_SET = frozenset(SUPERTREND_REJECTION_REASONS)


@dataclass(frozen=True)
class M5RuntimePaths:
    """One coherent, validated home for M5 PAPER runtime artifacts."""

    root: Path
    mode: str

    @property
    def active_session(self) -> Path:
        return self.root / "active.json"

    @property
    def lock(self) -> Path:
        return self.root / "active.json.runtime.lock"

    @property
    def heartbeat(self) -> Path:
        return self.root / "heartbeat.json"

    @property
    def campaign_projection(self) -> Path:
        return self.root / "AIOS_FOREX_SUPERTREND_30_TRADE_CAMPAIGN_STATE.json"

    @property
    def telemetry(self) -> Path:
        return self.root / "AIOS_FOREX_SUPERTREND_CYCLE_PROVENANCE.jsonl"

    @property
    def recovery_receipt(self) -> Path:
        return self.lock.with_name(f"{self.lock.name}.recovery.jsonl")


def _normalized_path_text(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def resolve_m5_runtime_paths(
    *, checkout_root: Path, external_runtime_root: Path | None = None,
) -> M5RuntimePaths:
    """Return checkout-local paths or the sole approved external M5 root.

    The external handoff is deliberately path-specific.  It cannot be used as
    a general runtime-root override and is validated before any transport,
    lock, session, or telemetry operation is constructed.
    """
    checkout_root = checkout_root.resolve(strict=True)
    if external_runtime_root is None:
        return M5RuntimePaths(
            root=(checkout_root / M5_RUNTIME_ROOT_RELATIVE_PATH).resolve(strict=False),
            mode="CHECKOUT_LOCAL",
        )
    if not external_runtime_root.is_absolute():
        raise ValueError("external_m5_runtime_root_must_be_absolute")
    if ".." in external_runtime_root.parts:
        raise ValueError("external_m5_runtime_root_path_traversal_forbidden")

    requested_text = _normalized_path_text(external_runtime_root)
    approved_text = _normalized_path_text(APPROVED_EXTERNAL_M5_RUNTIME_ROOT)
    if requested_text != approved_text:
        raise ValueError("external_m5_runtime_root_not_allowlisted")
    try:
        approved_root = APPROVED_EXTERNAL_M5_RUNTIME_ROOT.resolve(strict=True)
        resolved_root = external_runtime_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("external_m5_runtime_root_missing") from exc
    if not resolved_root.is_dir():
        raise ValueError("external_m5_runtime_root_missing")
    if resolved_root != approved_root:
        raise ValueError("external_m5_runtime_root_symlink_escape")
    return M5RuntimePaths(root=resolved_root, mode="APPROVED_EXTERNAL")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _data_unavailable_backoff_seconds(consecutive_failures: int) -> int:
    """Return a capped exponential delay for transient read-only data failures."""
    if consecutive_failures <= 0:
        raise ValueError("positive_consecutive_failure_count_required")
    exponent = min(consecutive_failures - 1, 4)
    return min(
        DATA_UNAVAILABLE_BACKOFF_BASE_SECONDS * (2 ** exponent),
        DATA_UNAVAILABLE_BACKOFF_MAX_SECONDS,
    )


def _lock_path(runtime_path: Path) -> Path:
    return runtime_path.with_name(runtime_path.name + SUPER_TREND_LOCK_PATH_SUFFIX)


def _runtime_source_fingerprint() -> str:
    return source_fingerprint(Path(__file__))


def _read_lock_record(lock_path: Path) -> dict[str, Any] | None:
    return read_runtime_lock(
        lock_path, schema=SUPER_TREND_LOCK_SCHEMA,
        campaign_identity=SUPER_TREND_LOCK_CAMPAIGN_IDENTITY,
        source_fingerprint_value=_runtime_source_fingerprint(),
    )


def _acquire_supertrend_lock(
    lock_path: Path, *, now: datetime, **identity_overrides: Any,
) -> RuntimeLockOwnership | None:
    return acquire_runtime_lock(
        lock_path, schema=SUPER_TREND_LOCK_SCHEMA,
        campaign_identity=SUPER_TREND_LOCK_CAMPAIGN_IDENTITY,
        source_fingerprint_value=_runtime_source_fingerprint(),
        ttl_seconds=SUPER_TREND_LOCK_TTL_SECONDS, now=now,
        **identity_overrides,
    )


def _release_supertrend_lock(lock_path: Path, owner: RuntimeLockOwnership) -> bool:
    return release_runtime_lock(lock_path, owner)


def _touch_supertrend_lock(
    lock_path: Path, owner: RuntimeLockOwnership, *, now: datetime,
) -> bool:
    return refresh_runtime_lock(
        lock_path, owner, ttl_seconds=SUPER_TREND_LOCK_TTL_SECONDS, now=now,
    )


def _close_active_session(runtime_path: Path, *, closed_at_utc: str, exit_reason: str) -> None:
    active = load_active_session(runtime_path)
    state: dict[str, Any] = {
        "schema": "AIOS_P1_SUPERVISED_PAPER_SESSION.v1",
        "status": "CLOSED",
        "closed_at_utc": closed_at_utc,
        "closed_reason": exit_reason,
    }
    if active:
        state["strategy_id"] = active.get("strategy_id")
        state["strategy_name"] = active.get("strategy_name", active.get("strategy_id"))
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps(state, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _supertrend_active_session_guard(active: Mapping[str, Any]) -> str | None:
    strategy_id = str(active.get("strategy_id", "")).strip()
    strategy_name = str(active.get("strategy_name", "")).strip()
    active_strategy = strategy_id or strategy_name
    if active_strategy != SUPER_TREND_SESSION_STRATEGY:
        return SUPER_TREND_SESSION_GUARD_REASON
    return None


def resolve_signal_source(
    signal_source: str = SPRINT_4_SIGNAL_SOURCE,
    *,
    supertrend_paper_demo_only: bool = False,
) -> str:
    """Resolve a bounded source; Supertrend requires an explicit fake-money gate."""
    normalized = str(signal_source).strip().lower()
    if normalized not in SIGNAL_SOURCES:
        raise ValueError("unsupported_signal_source")
    if normalized == SUPERTREND_SIGNAL_SOURCE and supertrend_paper_demo_only is not True:
        raise ValueError("supertrend_paper_demo_only_confirmation_required")
    if normalized != SUPERTREND_SIGNAL_SOURCE and supertrend_paper_demo_only is True:
        raise ValueError("supertrend_paper_demo_only_requires_supertrend_source")
    return normalized


def _normalize_supertrend_rejection_reasons(raw_reasons: Any) -> tuple[str, ...]:
    if isinstance(raw_reasons, str):
        values = [raw_reasons]
    elif isinstance(raw_reasons, (list, tuple)):
        values = list(raw_reasons)
    else:
        values = []

    normalized: list[str] = []
    for raw_reason in values:
        reason = str(raw_reason).strip().lower()
        if reason.startswith("no_trade:"):
            reason = reason.split(":", 1)[1].strip()
        mapped = _SUPERTREND_RAW_REJECTION_REASON_MAP.get(reason)
        if mapped and mapped not in normalized:
            normalized.append(mapped)
    return tuple(normalized or ("unknown_no_signal",))


def _supertrend_wait_reasons(
    signal: dict[str, Any], candidate: dict[str, Any] | None
) -> tuple[str, ...]:
    reasons = tuple(
        str(reason)
        for reason in signal.get("rejection_reasons", [])
        if str(reason) in _SUPERTREND_REJECTION_REASON_SET
    )
    if reasons:
        return reasons
    if signal.get("status") == "BUY" and candidate is None:
        return ("pullback_not_confirmed",)
    return ("unknown_no_signal",)


def _supertrend_signal_state(
    history: dict[str, Any], *, generated_at_utc: str
) -> dict[str, Any]:
    candles = [
        Candle(
            symbol="EURUSD",
            timeframe="5m",
            timestamp=item["observed_at_utc"],
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=float(item.get("volume", 0)),
            source="sanitized_market_history",
        )
        for item in history["candles"]
    ]
    evaluation = evaluate_supertrend_pullback(candles, SUPERTREND_CONFIG)
    signal = evaluation.get("signal")
    identity = {
        "strategy_name": SUPERTREND_PULLBACK_V1,
        "generated_at_utc": generated_at_utc,
        "history_last_utc": history["last_observed_at_utc"],
    }
    result = {
        "status": "NO_SIGNAL",
        "signal_id": "sig-" + hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode("utf-8")
        ).hexdigest()[:24],
        "strategy_id": SUPERTREND_PULLBACK_V1,
        "strategy_name": SUPERTREND_PULLBACK_V1,
        "direction": None,
        "stop_price": None,
        "target_price": None,
        "mode": "PAPER_ONLY",
        "paper_only": True,
        "strategy_config": {
            "atr_period": SUPERTREND_CONFIG.atr_period,
            "multiplier": SUPERTREND_CONFIG.supertrend_multiplier,
        },
        "broker_write_performed": False,
        "order_submission_allowed": False,
        "demo_execution_allowed": False,
        "live_execution_allowed": False,
        "money_movement_allowed": False,
        "latest_rejection_reason": None,
        "rejection_reasons": [],
        "decision_funnel": {},
    }
    evaluated_candidate = evaluation.get("candidate")
    evaluated_metadata = getattr(evaluated_candidate, "metadata", {}) or {}
    result["decision_funnel"] = dict(evaluated_metadata)
    if evaluation.get("accepted") is not True or signal is None:
        rejection_reasons = _normalize_supertrend_rejection_reasons(
            evaluation.get("no_trade_reasons")
        )
        return {
            **result,
            "latest_rejection_reason": rejection_reasons[0],
            "rejection_reasons": list(rejection_reasons),
        }
    # The existing P1 paper-session controller is deliberately long-only.
    # A valid Supertrend SELL remains a no-signal cycle rather than widening scope.
    if signal.direction != Direction.BUY:
        return {
            **result,
            "latest_rejection_reason": "trend_not_aligned",
            "rejection_reasons": ["trend_not_aligned"],
        }
    return {
        **result,
        "status": "BUY",
        "direction": "BUY",
        "stop_price": float(signal.stop_loss),
        "target_price": float(signal.take_profit),
    }


def _build_signal_state(
    history: dict[str, Any],
    *,
    generated_at_utc: str,
    signal_source: str = SPRINT_4_SIGNAL_SOURCE,
) -> dict[str, Any]:
    if signal_source == SUPERTREND_SIGNAL_SOURCE:
        return _supertrend_signal_state(history, generated_at_utc=generated_at_utc)
    signal = build_signal_state(history, generated_at_utc=generated_at_utc)
    return {
        **signal,
        "strategy_name": signal.get("strategy_name", signal.get("strategy_id", SPRINT_4_STRATEGY_NAME)),
        "mode": "PAPER_ONLY",
        "paper_only": True,
    }


def _candidate_from_signal(signal: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Transform only a canonical BUY decision into the session candidate contract."""
    if signal.get("status") != "BUY":
        return None
    stop = float(signal["stop_price"])
    target = float(signal["target_price"])
    entry = float(snapshot["ask"])
    if not stop < entry < target:
        return None
    identity = json.dumps(
        {"signal_id": signal["signal_id"], "observed_at_utc": snapshot["observed_at_utc"]},
        sort_keys=True,
    )
    strategy_id = str(signal["strategy_id"])
    strategy_name = str(signal.get("strategy_name") or strategy_id)
    candidate = {
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "candidate_id": "p1-runtime-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
        "instrument": INSTRUMENT,
        "direction": "BUY",
        "units": DEFAULT_PAPER_UNITS,
        "stop_price": stop,
        "target_price": target,
        "risk_amount": round((entry - stop) * DEFAULT_PAPER_UNITS, 8),
        "entry_rationale": f"genuine observed EUR USD M5 {strategy_name} paper signal",
        "mode": "PAPER_ONLY",
        "paper_only": True,
        "status": "PAPER_ELIGIBLE",
        "sanitized": True,
        "current": True,
        "broker_call_performed": False,
        "broker_write_performed": False,
        "order_submission_allowed": False,
        "demo_execution_allowed": False,
        "live_execution_allowed": False,
        "money_movement_allowed": False,
    }
    if isinstance(signal.get("strategy_config"), dict):
        candidate["strategy_config"] = dict(signal["strategy_config"])
    return candidate


def _ask_geometry(signal: Mapping[str, Any], snapshot: Mapping[str, Any]) -> str:
    """Return the observable ask gate result without creating a candidate."""
    if signal.get("status") != "BUY":
        return "NOT_EVALUATED"
    try:
        stop = float(signal["stop_price"])
        ask = float(snapshot["ask"])
        target = float(signal["target_price"])
    except (KeyError, TypeError, ValueError):
        return "NOT_EVALUATED"
    return "PASS" if stop < ask < target else "FAIL"


def _capture(
    client: OandaReadOnlyClient,
    now: datetime,
    *,
    pricing_now: Callable[[], datetime] | None = None,
    signal_source: str = SPRINT_4_SIGNAL_SOURCE,
) -> tuple[dict[str, Any], dict[str, Any]]:
    transport = resolve_canonical_practice_transport(client)
    history_started = _utc_now()
    candle_payload = transport.candles(INSTRUMENT, granularity=GRANULARITY, count=CANDLE_COUNT)
    candles = extract_canonical_completed_candles(candle_payload)
    history = validate_canonical_history_artifact(
        build_canonical_history_artifact(candles, requested_count=CANDLE_COUNT), now=now
    )
    history_responded = _utc_now()
    signal = _build_signal_state(
        history, generated_at_utc=_stamp(now), signal_source=signal_source
    )
    pricing_started = _utc_now()
    pricing = transport.pricing((INSTRUMENT,))
    pricing_responded = _utc_now()
    pricing_validation_time = (pricing_now or _utc_now)().astimezone(timezone.utc)
    snapshot = extract_sanitized_price_snapshot(
        pricing,
        broker_call_performed=True,
        credentials_loaded_runtime_only=True,
        now=pricing_validation_time,
    )
    # The paper-session controller deliberately receives only its narrower,
    # sanitized snapshot schema; runtime credential metadata never crosses it.
    session_snapshot = {
        key: snapshot[key]
        for key in (
            "schema", "evidence_type", "provenance", "instrument", "observed_at_utc",
            "bid", "ask", "mid", "spread", "source_status", "stale_status",
            "read_only", "broker_write_performed", "account_identifier_included",
            "raw_payload_included",
        )
    }
    session_snapshot["credentials_included"] = False
    latest_open = datetime.fromisoformat(
        (candles[-1]["observed_at_utc"] if candles else history["last_observed_at_utc"]).replace("Z", "+00:00")
    )
    latest_close = latest_open + timedelta(minutes=5)
    snapshot_observed = datetime.fromisoformat(
        session_snapshot["observed_at_utc"].replace("Z", "+00:00")
    )
    signal["provenance"] = {
        **dict(signal.get("decision_funnel") or {}),
        "history_get_count": 1, "pricing_get_count": 1,
        "history_request_start_utc": _stamp(history_started),
        "history_response_utc": _stamp(history_responded),
        "pricing_request_start_utc": _stamp(pricing_started),
        "pricing_response_utc": _stamp(pricing_responded),
        "latest_completed_candle_open_utc": candles[-1].get("observed_at_utc") if candles else None,
        "latest_completed_candle_close_utc": _stamp(latest_close),
        "history_age_seconds": max(0.0, (now - latest_close).total_seconds()),
        "snapshot_age_seconds": max(0.0, (pricing_validation_time - snapshot_observed).total_seconds()),
        "history_freshness_result": "FRESH", "snapshot_freshness_result": "FRESH",
    }
    return signal, session_snapshot


def completed_paper_records(
    client: OandaReadOnlyClient,
    *,
    cycles: int,
    reviewer_identity: str,
    runtime_path: Path,
    runtime_lock_path: Path | None = None,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], None],
    owner_cancelled: Callable[[], bool] = lambda: False,
    kill_switch_active: Callable[[], bool] = lambda: False,
    risk_halt_active: Callable[[], bool] = lambda: False,
    signal_source: str = SPRINT_4_SIGNAL_SOURCE,
    supertrend_paper_demo_only: bool = False,
    telemetry_output_root: Path | None = None,
) -> Iterator[dict[str, Any] | CampaignHalt | CampaignWait]:
    """Yield closed paper records, bounded waits, or an explicit fail-closed halt."""
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles <= 0:
        raise ValueError("positive_cycle_count_required")
    if not reviewer_identity.strip():
        raise ValueError("owner_reviewer_required")
    selected_signal_source = resolve_signal_source(
        signal_source,
        supertrend_paper_demo_only=supertrend_paper_demo_only,
    )
    if telemetry_output_root is None:
        telemetry_output_root = runtime_path.parent
    resolve_canonical_practice_transport(client)
    consecutive_data_unavailable = 0
    supertrend_lock_path = runtime_lock_path or _lock_path(runtime_path)
    lock_owner: RuntimeLockOwnership | None = None

    if selected_signal_source == SUPERTREND_SIGNAL_SOURCE:
        lock_owner = _acquire_supertrend_lock(
            supertrend_lock_path,
            now=_utc_now(),
        )
        if lock_owner is None:
            yield CampaignHalt("LIVE_WRITER_LOCK_HELD")
            return

    try:
        for index in range(cycles):
            cycle_started = now().astimezone(timezone.utc)
            if lock_owner is not None and not _touch_supertrend_lock(
                supertrend_lock_path, lock_owner, now=_utc_now()
            ):
                yield CampaignHalt("LIVE_WRITER_LOCK_LOST")
                return
            if owner_cancelled():
                yield CampaignHalt("OWNER_CANCELLATION")
                return
            if kill_switch_active():
                yield CampaignHalt("KILL_SWITCH_ACTIVE")
                return
            if risk_halt_active():
                yield CampaignHalt("RISK_HALT")
                return
            current = cycle_started
            active = None
            if selected_signal_source == SUPERTREND_SIGNAL_SOURCE:
                active = load_active_session(runtime_path)
                if (
                    active is not None
                    and (guard_reason := _supertrend_active_session_guard(active))
                ):
                    yield CampaignHalt(guard_reason)
                    return
            try:
                signal, snapshot = _capture(
                    client,
                    current,
                    pricing_now=now,
                    signal_source=selected_signal_source,
                )
            except OandaReadOnlyClientError:
                consecutive_data_unavailable += 1
                next_wait_seconds = _data_unavailable_backoff_seconds(
                    consecutive_data_unavailable
                ) if index + 1 < cycles else None
                yield CampaignWait(
                    index + 1,
                    cycles,
                    action=WAIT_FOR_DATA,
                    observed_at_utc=_stamp(current),
                    next_check_in_seconds=next_wait_seconds,
                    rejection_reasons=("data_unavailable",),
                )
                if telemetry_output_root is not None:
                    append_cycle_record(telemetry_path(telemetry_output_root), build_cycle_record(
                        cycle_number=index + 1, maximum_cycles=cycles,
                        cycle_started_utc=_stamp(cycle_started), cycle_completed_utc=_stamp(_utc_now()),
                        action=WAIT_FOR_DATA, rejection_reasons=("data_unavailable",),
                        next_check_in_seconds=next_wait_seconds))
                if next_wait_seconds is not None:
                    sleep(next_wait_seconds)
                continue
            except ValueError as exc:
                if str(exc) in {"stale_history", "stale_snapshot"}:
                    stale_reason = str(exc)
                    consecutive_data_unavailable += 1
                    next_wait_seconds = _data_unavailable_backoff_seconds(
                        consecutive_data_unavailable
                    ) if index + 1 < cycles else None
                    yield CampaignWait(
                        index + 1, cycles, action=WAIT_FOR_DATA,
                        observed_at_utc=_stamp(current),
                        next_check_in_seconds=next_wait_seconds,
                        rejection_reasons=(stale_reason,),
                    )
                    if telemetry_output_root is not None:
                        append_cycle_record(telemetry_path(telemetry_output_root), build_cycle_record(
                            cycle_number=index + 1, maximum_cycles=cycles,
                            cycle_started_utc=_stamp(cycle_started), cycle_completed_utc=_stamp(_utc_now()),
                            action=WAIT_FOR_DATA, rejection_reasons=(stale_reason,),
                            next_check_in_seconds=next_wait_seconds, stale_reason=stale_reason))
                    if next_wait_seconds is not None:
                        sleep(next_wait_seconds)
                    continue
                # Schema, price, instrument, and strategy invariant failures are
                # terminal.  Only the explicitly classified read failures above
                # may retry.
                yield CampaignHalt("INVALID_MARKET_DATA")
                return

            consecutive_data_unavailable = 0

            if active is None:
                active = load_active_session(runtime_path)
            if active is None:
                candidate = _candidate_from_signal(signal, snapshot)
                if candidate is None:
                    next_wait_seconds = POLL_INTERVAL_SECONDS if index + 1 < cycles else None
                    ask_geometry_status = _ask_geometry(signal, snapshot)
                    reasons = (
                        _supertrend_wait_reasons(signal, candidate)
                        if selected_signal_source == SUPERTREND_SIGNAL_SOURCE else ()
                    )
                    telemetry_reasons = tuple(reasons or signal.get("rejection_reasons", []))
                    if ask_geometry_status == "FAIL" and "ask_geometry_failed" not in telemetry_reasons:
                        telemetry_reasons += ("ask_geometry_failed",)
                    if telemetry_output_root is not None:
                        append_cycle_record(telemetry_path(telemetry_output_root), build_cycle_record(
                            cycle_number=index + 1, maximum_cycles=cycles,
                            cycle_started_utc=_stamp(cycle_started), cycle_completed_utc=_stamp(_utc_now()),
                            action=("ASK_GEOMETRY_FAILED" if ask_geometry_status == "FAIL" else "NO_SIGNAL"), signal=signal, snapshot=snapshot,
                            rejection_reasons=telemetry_reasons,
                            next_check_in_seconds=next_wait_seconds,
                            extra={"paper_session_event": "NONE", "candidate_status": "NONE",
                                   "paper_eligible": False, "ask_geometry_status": ask_geometry_status}))
                    if selected_signal_source == SUPERTREND_SIGNAL_SOURCE:
                        yield CampaignWait(
                            index + 1,
                            cycles,
                            next_check_in_seconds=next_wait_seconds,
                            rejection_reasons=reasons,
                        )
                    else:
                        yield CampaignWait(
                            index + 1,
                            cycles,
                            next_check_in_seconds=next_wait_seconds,
                        )
                else:
                    if telemetry_output_root is not None:
                        append_cycle_record(telemetry_path(telemetry_output_root), build_cycle_record(
                            cycle_number=index + 1, maximum_cycles=cycles,
                            cycle_started_utc=_stamp(cycle_started), cycle_completed_utc=_stamp(_utc_now()),
                            action="PAPER_SESSION_OPEN", signal=signal, snapshot=snapshot,
                            rejection_reasons=(), next_check_in_seconds=(
                                POLL_INTERVAL_SECONDS if index + 1 < cycles else None
                            ), extra={"paper_session_event": "OPEN", "candidate_status": "PAPER_ELIGIBLE",
                                      "paper_eligible": True, "ask_geometry_status": "PASS"}))
                    open_paper_session(
                        snapshot,
                        candidate,
                        reviewer_identity,
                        _stamp(current),
                        runtime_path,
                    )
            else:
                active = update_paper_session_extremes(snapshot, runtime_path)
                bid = float(snapshot["bid"])
                if bid >= float(active["target_price"]) or bid <= float(active["stop_price"]):
                    reason = "paper_target" if bid >= float(active["target_price"]) else "paper_stop"
                    review_utc = _stamp(_utc_now())
                    record = build_completed_trade_record(
                        active, snapshot, reason, reviewer_identity, review_utc
                    )
                    if telemetry_output_root is not None:
                        append_cycle_record(telemetry_path(telemetry_output_root), build_cycle_record(
                            cycle_number=index + 1, maximum_cycles=cycles,
                            cycle_started_utc=_stamp(cycle_started), cycle_completed_utc=_stamp(_utc_now()),
                            action="PAPER_SESSION_CLOSE", signal=signal, snapshot=snapshot,
                            rejection_reasons=(), extra={
                                "paper_session_event": "CLOSE", "exit_reason": reason,
                                "entry_price": active.get("entry_price"),
                                "exit_price": record.get("exit_price"),
                                "realized_paper_pl": record.get("realized_pl"),
                                "win_or_loss": (
                                    "WIN" if float(record.get("realized_pl", 0)) > 0
                                    else ("LOSS" if float(record.get("realized_pl", 0)) < 0 else "FLAT")
                                ),
                                "holding_duration_seconds": record.get("holding_duration_seconds"),
                                "risk_amount": record.get("risk_amount"),
                                "planned_reward_risk": record.get("planned_reward_risk"),
                                "realized_r": (
                                    record.get("realized_r")
                                    if record.get("realized_r") is not None
                                    else (
                                        round(float(record.get("realized_pl", 0.0)) / float(record["risk_amount"]), 8)
                                        if record.get("risk_amount") not in (None, 0) else None
                                    )
                                ),
                                "roi_class": record.get("roi_class"),
                                "mfe_price": record.get("mfe_price"), "mfe_r": record.get("mfe_r"),
                                "mae_price": record.get("mae_price"), "mae_r": record.get("mae_r"),
                                "time_to_mfe": record.get("time_to_mfe_seconds"),
                                "time_to_mae": record.get("time_to_mae_seconds"),
                                "candidate_status": "NONE", "paper_eligible": False,
                                "ask_geometry_status": "NOT_EVALUATED",
                            }))
                    _close_active_session(
                        runtime_path,
                        closed_at_utc=_stamp(current),
                        exit_reason=reason,
                    )
                    yield record
                elif selected_signal_source == SUPERTREND_SIGNAL_SOURCE:
                    next_wait_seconds = POLL_INTERVAL_SECONDS if index + 1 < cycles else None
                    if telemetry_output_root is not None:
                        append_cycle_record(telemetry_path(telemetry_output_root), build_cycle_record(
                            cycle_number=index + 1, maximum_cycles=cycles,
                            cycle_started_utc=_stamp(cycle_started), cycle_completed_utc=_stamp(_utc_now()),
                            action="PAPER_SESSION_HELD", signal=signal, snapshot=snapshot,
                            rejection_reasons=("duplicate_position_guard",),
                            next_check_in_seconds=next_wait_seconds,
                            extra={"paper_session_event": "HELD", "candidate_status": "NONE",
                                   "paper_eligible": False, "ask_geometry_status": "NOT_EVALUATED"}))
                    yield CampaignWait(
                        index + 1,
                        cycles,
                        next_check_in_seconds=next_wait_seconds,
                        rejection_reasons=("duplicate_position_guard",),
                    )
            if index + 1 < cycles:
                sleep(POLL_INTERVAL_SECONDS)
    finally:
        if lock_owner is not None:
            _release_supertrend_lock(supertrend_lock_path, lock_owner)

    yield CampaignHalt("OWNER_SESSION_CYCLE_LIMIT")


def runtime_safety_state(
    signal_source: str = SPRINT_4_SIGNAL_SOURCE,
    *,
    supertrend_paper_demo_only: bool = False,
) -> dict[str, Any]:
    selected = resolve_signal_source(
        signal_source,
        supertrend_paper_demo_only=supertrend_paper_demo_only,
    )
    return {
        "version": VERSION,
        "environment": "PRACTICE",
        "http_methods": ["GET"],
        "instrument": INSTRUMENT,
        "granularity": GRANULARITY,
        "default_signal_source": SPRINT_4_SIGNAL_SOURCE,
        "selected_signal_source": selected,
        "strategy_name": (
            SUPERTREND_PULLBACK_V1
            if selected == SUPERTREND_SIGNAL_SOURCE
            else SPRINT_4_STRATEGY_NAME
        ),
        "paper_demo_only": True,
        "supertrend_requires_explicit_paper_demo_flag": True,
        "supertrend_data_unavailable_action": WAIT_FOR_DATA,
        "data_unavailable_backoff_base_seconds": DATA_UNAVAILABLE_BACKOFF_BASE_SECONDS,
        "data_unavailable_backoff_max_seconds": DATA_UNAVAILABLE_BACKOFF_MAX_SECONDS,
        "maximum_open_paper_positions": 1,
        **SAFETY,
    }
