"""PAPER-only all-pairs M1/M2 market observer.

This module is deliberately separate from the bounded EUR_USD M5 campaign.
It permits OANDA Practice GET observations only and writes sanitized observer
evidence to its own runtime root when a future, separately authorized launcher
invokes it.  It cannot submit, simulate, or count a broker order.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from automation.forex_engine.forex_p1_paper_autostart_v1 import (
    RuntimeLockOwnership,
    acquire_runtime_lock,
    read_runtime_lock,
    refresh_runtime_lock,
    release_runtime_lock,
    source_fingerprint,
)
from automation.forex_engine.models import Candle, Direction
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient
from automation.forex_engine.strategies import (
    SUPERTREND_PULLBACK_V1,
    SupertrendPullbackConfig,
    evaluate_supertrend_pullback,
)


VERSION = "forex_persistent_all_pairs_m1_m2_observer_v1"
SCHEMA = "AIOS_FOREX_PERSISTENT_OBSERVER_RECORD.v1"
RUNTIME_SCHEMA = "AIOS_FOREX_PERSISTENT_OBSERVER_LOCK.v1"
RUNTIME_IDENTITY = "FOREX_PERSISTENT_ALL_PAIRS_M1_M2_OBSERVER_V1"
DEFAULT_RUNTIME_ROOT = Path(".aios/runtime/forex_persistent_all_pairs_m1_m2_observer_v1")
OBSERVATION_SECONDS = 1.0
UNIVERSE_REFRESH_SECONDS = 3600
MAX_BATCH_SIZE = 25
LOCK_TTL_SECONDS = 30
DEFAULT_EVIDENCE_MAX_BYTES = 4 * 1024 * 1024
DEFAULT_EVIDENCE_RETENTION_FILES = 14
SUPPORTED_GRANULARITIES = frozenset({"M1", "M2", "M5"})
FOREX_INSTRUMENT = re.compile(r"^[A-Z]{3}_[A-Z]{3}$")
FORBIDDEN_ARTIFACT_KEYS = re.compile(
    r"(?i)(token|secret|password|authorization|account[_ -]?id|raw[_ -]?(payload|response))"
)
SAFETY = {
    "paper_only": True,
    "broker_write_performed": False,
    "practice_order_performed": False,
    "live_trade_performed": False,
    "money_movement_performed": False,
    "credentials_persisted": False,
}
CANONICAL_CONFIG = SupertrendPullbackConfig()


@dataclass(frozen=True)
class ObserverConfig:
    """Versioned observer controls; these do not alter Supertrend parameters."""
    paper_units: int = 100
    candle_budget: int = 12
    require_m5_regime: bool = False
    max_quote_age_seconds: float = 3.0
    max_spread_to_stop_ratio: float = 0.10
    max_entry_deviation_atr: float = 0.50
    evidence_max_bytes: int = DEFAULT_EVIDENCE_MAX_BYTES
    evidence_retention_files: int = DEFAULT_EVIDENCE_RETENTION_FILES

    def fingerprint(self) -> str:
        payload = {
            "version": VERSION, "paper_units": self.paper_units, "candle_budget": self.candle_budget,
            "require_m5_regime": self.require_m5_regime, "max_quote_age_seconds": self.max_quote_age_seconds,
            "max_spread_to_stop_ratio": self.max_spread_to_stop_ratio,
            "max_entry_deviation_atr": self.max_entry_deviation_atr,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name}_must_be_numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name}_must_be_finite")
    return number


def _assert_safe_artifact(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key) == "raw_payload_included" and nested is False:
                continue
            if FORBIDDEN_ARTIFACT_KEYS.search(str(key)):
                raise ValueError("sensitive_or_raw_artifact_field_forbidden")
            _assert_safe_artifact(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_safe_artifact(nested)


def validate_observer_client(client: OandaReadOnlyClient) -> None:
    """Require the existing GET-only transport in the Practice environment."""
    if not isinstance(client, OandaReadOnlyClient):
        raise ValueError("oanda_read_only_client_required")
    if client.environment != "practice":
        raise ValueError("practice_environment_required")
    for method in ("discover_instruments", "observation_candles", "pricing"):
        if not callable(getattr(client, method, None)):
            raise ValueError(f"observer_client_method_required:{method}")


def eligible_forex_instruments(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize account instruments and classify only enabled, priceable FX pairs."""
    raw = payload.get("instruments") if isinstance(payload, Mapping) else None
    if not isinstance(raw, list):
        raise ValueError("instruments_list_required")
    eligible: list[str] = []
    excluded: list[dict[str, Any]] = []
    included: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            excluded.append({"instrument": "UNKNOWN", "reason": "invalid_instrument_record"})
            continue
        name = str(item.get("name", "")).upper()
        if not FOREX_INSTRUMENT.fullmatch(name) or str(item.get("type", "")).upper() != "CURRENCY":
            excluded.append({"instrument": name or "UNKNOWN", "reason": "not_forex_classified"})
        elif item.get("tradeable") is False:
            excluded.append({"instrument": name, "reason": "not_tradeable"})
        elif item.get("halted") is True:
            excluded.append({"instrument": name, "reason": "halted"})
        elif item.get("displayPrecision") is None or item.get("pipLocation") is None:
            excluded.append({"instrument": name, "reason": "missing_precision_metadata"})
        else:
            eligible.append(name)
            included.append({
                "instrument": name, "instrument_type": "CURRENCY", "display_precision": item.get("displayPrecision"),
                "pip_location": item.get("pipLocation"), "tradeable": item.get("tradeable") is not False,
                "priceable": True,
            })
    return {
        "eligible_instruments": sorted(set(eligible)),
        "included_instruments": sorted(included, key=lambda item: item["instrument"]),
        "excluded_instruments": sorted(excluded, key=lambda item: (item["instrument"], item["reason"])),
        "universe_status": "VALID" if eligible else "UNAVAILABLE",
        "raw_payload_included": False,
        **SAFETY,
    }


def discover_observer_universe(client: OandaReadOnlyClient) -> dict[str, Any]:
    """Discover the actual configured Practice-account Forex universe safely."""
    validate_observer_client(client)
    return eligible_forex_instruments(client.discover_instruments())


def pip_size(instrument: str) -> float:
    if not FOREX_INSTRUMENT.fullmatch(instrument):
        raise ValueError("forex_instrument_required")
    return 0.01 if instrument.endswith("_JPY") else 0.0001


def quote_currency_to_usd(instrument: str, mids: Mapping[str, float]) -> float | None:
    quote = instrument.split("_", 1)[1]
    if quote == "USD":
        return 1.0
    direct = mids.get(f"{quote}_USD")
    if direct and direct > 0:
        return float(direct)
    inverse = mids.get(f"USD_{quote}")
    if inverse and inverse > 0:
        return 1.0 / float(inverse)
    return None


def build_quote_snapshot(
    price: Mapping[str, Any], *, instrument: str, collected_at: datetime, now: datetime | None = None,
    max_quote_age_seconds: float = OBSERVATION_SECONDS * 3,
) -> dict[str, Any]:
    """Convert one OANDA price record to the sanitized observer quote shape."""
    if str(price.get("instrument")) != instrument:
        raise ValueError("instrument_price_mismatch")
    bids, asks = price.get("bids"), price.get("asks")
    if not isinstance(bids, list) or not bids or not isinstance(asks, list) or not asks:
        raise ValueError("price_sides_required")
    bid = _finite(bids[0].get("price") if isinstance(bids[0], Mapping) else None, "bid")
    ask = _finite(asks[0].get("price") if isinstance(asks[0], Mapping) else None, "ask")
    if ask <= bid:
        raise ValueError("positive_spread_required")
    quote_time = _parse_utc(str(price.get("time")))
    reference = now or collected_at
    age = max(0.0, (reference - quote_time).total_seconds())
    return {
        "instrument": instrument,
        "quote_timestamp_utc": _stamp(quote_time),
        "collection_timestamp_utc": _stamp(collected_at),
        "quote_age_seconds": round(age, 6),
        "bid": bid,
        "ask": ask,
        "mid": round((bid + ask) / 2.0, 10),
        "spread_price": round(ask - bid, 10),
        "spread_pips": round((ask - bid) / pip_size(instrument), 6),
        "data_status": "FRESH" if age <= max_quote_age_seconds else "STALE",
        "raw_payload_included": False,
        **SAFETY,
    }


def spread_gate(
    *, instrument: str, quote: Mapping[str, Any], stop: float, target: float,
    direction: str, units: int, mids: Mapping[str, float], max_spread_to_risk: float = 0.10,
    atr_value: float | None = None,
) -> dict[str, Any]:
    """Apply the spread-first gate without inventing a USD conversion rate."""
    bid, ask = _finite(quote.get("bid"), "bid"), _finite(quote.get("ask"), "ask")
    selected_entry = ask if direction == "BUY" else bid
    risk_distance = selected_entry - stop if direction == "BUY" else stop - selected_entry
    reward_distance = target - selected_entry if direction == "BUY" else selected_entry - target
    spread = ask - bid
    conversion = quote_currency_to_usd(instrument, mids)
    cost_quote = spread * int(units)
    cost_usd = None if conversion is None else round(cost_quote * conversion, 8)
    reasons: list[str] = []
    if quote.get("data_status") != "FRESH":
        reasons.append("stale_quote")
    if risk_distance <= 0 or reward_distance <= 0:
        reasons.append("invalid_price_geometry")
    elif spread / risk_distance > max_spread_to_risk:
        reasons.append("spread_too_large_relative_to_stop")
    if conversion is None:
        reasons.append("usd_spread_conversion_unavailable")
    return {
        "entry_price": selected_entry,
        "spread_cost_quote_currency": round(cost_quote, 8),
        "estimated_spread_cost_usd": cost_usd,
        "spread_usd_status": "AVAILABLE" if cost_usd is not None else "CONVERSION_UNAVAILABLE",
        "spread_to_stop_ratio": None if risk_distance <= 0 else round(spread / risk_distance, 8),
        "spread_to_target_ratio": None if reward_distance <= 0 else round(spread / reward_distance, 8),
        "spread_to_atr_ratio": None if not atr_value or atr_value <= 0 else round(spread / atr_value, 8),
        "spread_percent_of_expected_reward": None if reward_distance <= 0 else round(100 * spread / reward_distance, 6),
        "reward_risk": None if risk_distance <= 0 else round(reward_distance / risk_distance, 8),
        "eligible": not reasons,
        "rejection_reasons": reasons,
    }


def completed_candles(payload: Mapping[str, Any], *, instrument: str, granularity: str) -> list[Candle]:
    """Use only explicitly completed broker candles; incomplete data never enters a decision."""
    if granularity not in SUPPORTED_GRANULARITIES:
        raise ValueError("unsupported_observer_granularity")
    if payload.get("instrument") != instrument or payload.get("granularity") != granularity:
        raise ValueError("candle_payload_identity_mismatch")
    raw = payload.get("candles")
    if not isinstance(raw, list):
        raise ValueError("candles_list_required")
    result: list[Candle] = []
    for item in raw:
        if not isinstance(item, Mapping) or item.get("complete") is not True:
            continue
        mid = item.get("mid")
        if not isinstance(mid, Mapping):
            continue
        result.append(Candle(
            symbol=instrument.replace("_", ""), timeframe=granularity.lower(),
            timestamp=_stamp(_parse_utc(str(item.get("time")))), open=_finite(mid.get("o"), "open"),
            high=_finite(mid.get("h"), "high"), low=_finite(mid.get("l"), "low"),
            close=_finite(mid.get("c"), "close"), volume=float(item.get("volume", 0.0)),
            source="oanda_practice_completed_candle",
        ))
    if not result:
        raise ValueError("no_completed_candles")
    if any(later.timestamp <= earlier.timestamp for earlier, later in zip(result, result[1:])):
        raise ValueError("completed_candles_must_be_chronological")
    return result


def _m1_confirmation(candles: Sequence[Candle], direction: str) -> tuple[bool, str]:
    last = candles[-1]
    if direction == "BUY" and last.close > last.open:
        return True, "m1_bullish_close_confirmation"
    if direction == "SELL" and last.close < last.open:
        return True, "m1_bearish_close_confirmation"
    return False, "m1_close_confirmation_missing"


def _m5_regime(candles: Sequence[Candle], direction: str) -> tuple[bool, str]:
    result = evaluate_supertrend_pullback(candles, CANONICAL_CONFIG)
    candidate = result.get("candidate")
    regime = getattr(candidate, "regime_trend", "BLOCKED")
    expected = "SUPERTREND_UP" if direction == "BUY" else "SUPERTREND_DOWN"
    return regime == expected, str(regime)


def candidate_evidence(
    *, instrument: str, quote: Mapping[str, Any], m1: Sequence[Candle], m2: Sequence[Candle],
    m5: Sequence[Candle] | None, units: int = 100, require_m5_regime: bool = False,
    mids: Mapping[str, float] | None = None, observer_config: ObserverConfig | None = None,
) -> dict[str, Any]:
    """Make one deterministic M2-first decision with M1 confirmation and optional M5 regime."""
    config = observer_config or ObserverConfig(paper_units=units, require_m5_regime=require_m5_regime)
    evaluation = evaluate_supertrend_pullback(m2, CANONICAL_CONFIG)
    identity = {
        "instrument": instrument, "m2_completed_at_utc": m2[-1].timestamp,
        "strategy": SUPERTREND_PULLBACK_V1, "config": {"atr_period": 3, "multiplier": 2.0},
    }
    candidate_id = "observer-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    base = {
        "schema": SCHEMA, "record_type": "CANDIDATE_DECISION", "candidate_id": candidate_id,
        "instrument": instrument, "m1_completed_at_utc": m1[-1].timestamp,
        "m2_completed_at_utc": m2[-1].timestamp, "m5_completed_at_utc": m5[-1].timestamp if m5 else None,
        "strategy_id": SUPERTREND_PULLBACK_V1, "strategy_config": {"atr_period": 3, "multiplier": 2.0},
        "observer_config_fingerprint": config.fingerprint(),
        "decision_timeframe": "M2", "confirmation_timeframe": "M1", "regime_timeframe": "M5",
        "lookahead_used": False, "paper_eligible": False, "candidate_status": "REJECTED",
        "quote": dict(quote), "rejection_reasons": [], **SAFETY,
    }
    if evaluation.get("accepted") is not True:
        base["rejection_reasons"] = [str(reason).lower().replace("no_trade: ", "") for reason in evaluation.get("no_trade_reasons", [])]
        return base
    candidate = evaluation["candidate"]
    direction = str(candidate.direction).upper()
    metadata = getattr(candidate, "metadata", {}) or {}
    atr_value = _finite(metadata.get("atr", 0.0), "candidate_atr") if metadata.get("atr") is not None else None
    m1_pass, m1_reason = _m1_confirmation(m1, direction)
    m5_pass, m5_reason = _m5_regime(m5, direction) if m5 else (not require_m5_regime, "m5_not_supplied")
    gate = spread_gate(
        instrument=instrument, quote=quote, stop=float(candidate.stop_loss), target=float(candidate.take_profit),
        direction=direction, units=config.paper_units, mids=mids or {},
        max_spread_to_risk=config.max_spread_to_stop_ratio, atr_value=atr_value,
    )
    reasons = list(gate["rejection_reasons"])
    proposed_entry = _finite(getattr(candidate, "entry_price", m2[-1].close), "proposed_entry")
    entry_window = (atr_value or abs(float(candidate.stop_loss) - proposed_entry)) * config.max_entry_deviation_atr
    if abs(gate["entry_price"] - proposed_entry) > entry_window:
        reasons.append("entry_moved_beyond_window")
    candidate_age_seconds = max(0.0, (_parse_utc(str(quote["collection_timestamp_utc"])) - _parse_utc(m2[-1].timestamp)).total_seconds())
    if candidate_age_seconds > config.max_quote_age_seconds:
        reasons.append("candidate_stale")
    if not m1_pass:
        reasons.append(m1_reason)
    if require_m5_regime and not m5_pass:
        reasons.append("m5_regime_not_aligned:" + m5_reason)
    return {
        **base, "direction": direction, "entry": gate["entry_price"], "stop": float(candidate.stop_loss),
        "target": float(candidate.take_profit), "units": int(config.paper_units), "m1_confirmation": m1_reason,
        "m5_regime": m5_reason, "m5_regime_required": require_m5_regime, "spread_gate": gate,
        "proposed_entry": proposed_entry, "candidate_age_seconds": round(candidate_age_seconds, 6),
        "candidate_status": "PAPER_ELIGIBLE" if not reasons else "REJECTED", "paper_eligible": not reasons,
        "rejection_reasons": reasons,
    }


@dataclass(frozen=True)
class Deadline:
    scheduled_at_monotonic: float
    observed_at_monotonic: float

    @property
    def missed_seconds(self) -> float:
        return max(0.0, self.observed_at_monotonic - self.scheduled_at_monotonic)


class MonotonicCadence:
    """Deadline calculator that prevents `sleep(1)` accumulation drift."""
    def __init__(self, *, interval_seconds: float = OBSERVATION_SECONDS, monotonic: Callable[[], float] = time.monotonic) -> None:
        if interval_seconds <= 0:
            raise ValueError("positive_interval_required")
        self.interval_seconds, self._monotonic = interval_seconds, monotonic
        self._next = monotonic()

    def next_deadline(self) -> Deadline:
        scheduled = self._next
        observed = self._monotonic()
        while self._next <= observed:
            self._next += self.interval_seconds
        return Deadline(scheduled, observed)


def fair_batches(instruments: Sequence[str], *, batch_size: int = MAX_BATCH_SIZE, rotation: int = 0) -> list[tuple[str, ...]]:
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError("batch_size_out_of_bounds")
    normalized = sorted(set(instruments))
    if not normalized:
        return []
    offset = rotation % len(normalized)
    rotated = normalized[offset:] + normalized[:offset]
    return [tuple(rotated[index:index + batch_size]) for index in range(0, len(rotated), batch_size)]


def _pricing_records(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = payload.get("prices")
    if not isinstance(raw, list):
        raise ValueError("prices_list_required")
    result: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        instrument = str(item.get("instrument", "")).upper()
        if FOREX_INSTRUMENT.fullmatch(instrument):
            result[instrument] = item
    return result


def observer_cycle(
    client: OandaReadOnlyClient,
    *,
    universe: Sequence[str],
    rotation: int = 0,
    candle_budget: int = 12,
    now: datetime | None = None,
    monotonic_now: float | None = None,
    require_m5_regime: bool = False,
    units: int = 100,
    observer_config: ObserverConfig | None = None,
) -> dict[str, Any]:
    """Collect one bounded, fair observer cycle without creating a session.

    Quotes are requested in bounded batches.  Candle requests are intentionally
    budgeted because the broker may not sustain three REST candle calls for
    every pair each second.  Pairs outside that fair rotation are explicitly
    recorded as ``DEGRADED_RATE_LIMIT`` instead of being silently omitted.
    """
    validate_observer_client(client)
    if candle_budget < 1:
        raise ValueError("positive_candle_budget_required")
    config = observer_config or ObserverConfig(paper_units=units, candle_budget=candle_budget, require_m5_regime=require_m5_regime)
    collected_at = now or _utc_now()
    deadline = Deadline(
        scheduled_at_monotonic=monotonic_now if monotonic_now is not None else time.monotonic(),
        observed_at_monotonic=time.monotonic(),
    )
    instruments = sorted(set(universe))
    if any(not FOREX_INSTRUMENT.fullmatch(item) for item in instruments):
        raise ValueError("forex_instrument_required")
    raw_prices: dict[str, Mapping[str, Any]] = {}
    errors: list[dict[str, str]] = []
    request_started_monotonic = time.monotonic()
    for batch in fair_batches(instruments, rotation=rotation):
        try:
            raw_prices.update(_pricing_records(client.pricing(batch)))
        except Exception as exc:  # sanitized error only; never retain broker payload
            errors.append({"scope": "pricing_batch", "reason": type(exc).__name__})
    quotes: dict[str, dict[str, Any]] = {}
    for instrument in instruments:
        raw = raw_prices.get(instrument)
        if raw is None:
            quotes[instrument] = {
                "instrument": instrument, "data_status": "UNAVAILABLE", "rejection_reason": "price_missing",
                "raw_payload_included": False, **SAFETY,
            }
            continue
        try:
            quotes[instrument] = build_quote_snapshot(
                raw, instrument=instrument, collected_at=collected_at, now=collected_at,
                max_quote_age_seconds=config.max_quote_age_seconds,
            )
        except ValueError as exc:
            quotes[instrument] = {
                "instrument": instrument, "data_status": "UNAVAILABLE", "rejection_reason": str(exc),
                "raw_payload_included": False, **SAFETY,
            }
    mids = {instrument: float(quote["mid"]) for instrument, quote in quotes.items() if quote.get("data_status") == "FRESH"}
    decisions: list[dict[str, Any]] = []
    scheduled_for_candles = [instrument for batch in fair_batches(instruments, rotation=rotation) for instrument in batch][:candle_budget]
    for instrument in instruments:
        quote = quotes[instrument]
        if quote.get("data_status") != "FRESH":
            decisions.append({
                "schema": SCHEMA, "record_type": "CANDIDATE_DECISION", "instrument": instrument,
                "candidate_status": "REJECTED", "paper_eligible": False, "quote": quote,
                "rejection_reasons": [str(quote.get("rejection_reason", "stale_or_unavailable_quote"))],
                "lookahead_used": False, **SAFETY,
            })
            continue
        if instrument not in scheduled_for_candles:
            decisions.append({
                "schema": SCHEMA, "record_type": "CANDIDATE_DECISION", "instrument": instrument,
                "candidate_status": "DEGRADED_RATE_LIMIT", "paper_eligible": False, "quote": quote,
                "rejection_reasons": ["DEGRADED_RATE_LIMIT:candle_budget"], "lookahead_used": False, **SAFETY,
            })
            continue
        try:
            m1 = completed_candles(client.observation_candles(instrument, granularity="M1", count=50), instrument=instrument, granularity="M1")
            m2 = completed_candles(client.observation_candles(instrument, granularity="M2", count=50), instrument=instrument, granularity="M2")
            m5 = completed_candles(client.observation_candles(instrument, granularity="M5", count=50), instrument=instrument, granularity="M5")
            decisions.append(candidate_evidence(
                instrument=instrument, quote=quote, m1=m1, m2=m2, m5=m5, units=units,
                require_m5_regime=require_m5_regime, mids=mids, observer_config=config,
            ))
        except Exception as exc:  # fail closed and record only the public error category
            errors.append({"scope": f"candles:{instrument}", "reason": type(exc).__name__})
            decisions.append({
                "schema": SCHEMA, "record_type": "CANDIDATE_DECISION", "instrument": instrument,
                "candidate_status": "UNAVAILABLE", "paper_eligible": False, "quote": quote,
                "rejection_reasons": ["UNAVAILABLE:completed_candle_fetch"], "lookahead_used": False, **SAFETY,
            })
    health = observer_health(
        eligible=instruments, quotes=list(quotes.values()), deadline=deadline, api_errors=len(errors),
        lock_owner=None,
    )
    processing_completed_monotonic = time.monotonic()
    return {
        "schema": SCHEMA, "record_type": "OBSERVER_CYCLE", "observer_version": VERSION,
        "cycle_timestamp_utc": _stamp(collected_at), "rotation": rotation, "candle_budget": candle_budget,
        "universe_recheck_due_utc": _stamp(collected_at + timedelta(seconds=UNIVERSE_REFRESH_SECONDS)),
        "quotes": list(quotes.values()), "decisions": decisions, "health": health, "api_errors": errors,
        "request_started_monotonic": request_started_monotonic,
        "processing_completed_monotonic": processing_completed_monotonic,
        "request_duration_seconds": round(processing_completed_monotonic - request_started_monotonic, 6),
        "backoff_state": "NONE" if not errors else "EXPONENTIAL_BACKOFF_REQUIRED",
        "paper_sessions_opened": 0, "qualifying_trades_incremented": 0, **SAFETY,
    }


def write_cycle_evidence(
    runtime_root: Path, cycle: Mapping[str, Any], *, owner: RuntimeLockOwnership,
    config: ObserverConfig | None = None,
) -> Path:
    """Persist sanitized evidence only in the observer's dedicated runtime root."""
    if owner.campaign_identity != RUNTIME_IDENTITY:
        raise ValueError("observer_lock_owner_required")
    settings = config or ObserverConfig()
    cycle_at = _parse_utc(str(cycle["cycle_timestamp_utc"]))
    path = append_rotating_evidence(
        runtime_root, cycle, now=cycle_at, max_bytes=settings.evidence_max_bytes,
        retention_files=settings.evidence_retention_files,
    )
    heartbeat = {
        "schema": SCHEMA, "record_type": "OBSERVER_HEARTBEAT", "status": "ACTIVE",
        "heartbeat_at_utc": cycle.get("cycle_timestamp_utc"), "pid": owner.pid,
        "lock_id": owner.lock_id, "source_fingerprint": source_fingerprint(Path(__file__)),
        "latest_cycle_timestamp_utc": cycle.get("cycle_timestamp_utc"),
        "next_check_utc": _stamp(_parse_utc(str(cycle["cycle_timestamp_utc"])) + timedelta(seconds=OBSERVATION_SECONDS)),
        "active_paper_session": None, "qualifying_trades": 0, "evidence_file": path.name,
        "latest_healthy_scan_utc": cycle.get("cycle_timestamp_utc") if cycle.get("health", {}).get("coverage_status") == "HEALTHY_ONE_SECOND" else None,
        **SAFETY,
    }
    _assert_safe_artifact(heartbeat)
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "heartbeat.json").write_text(json.dumps(heartbeat, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


class PersistentObserver:
    """Owner-startable observer service with isolated state and fair cycles.

    Constructing this object performs no network or filesystem action.  Calling
    ``start`` is intentionally left to a future owner-authorized launch packet.
    """
    def __init__(
        self,
        client: OandaReadOnlyClient,
        *,
        runtime_root: Path = DEFAULT_RUNTIME_ROOT,
        candle_budget: int = 12,
        require_m5_regime: bool = False,
        units: int = 100,
        config: ObserverConfig | None = None,
    ) -> None:
        validate_observer_client(client)
        self.client = client
        self.runtime_root = Path(runtime_root)
        self.config = config or ObserverConfig(
            paper_units=units, candle_budget=candle_budget, require_m5_regime=require_m5_regime,
        )
        self.candle_budget = self.config.candle_budget
        self.require_m5_regime = self.config.require_m5_regime
        self.units = self.config.paper_units
        self.owner: RuntimeLockOwnership | None = None
        self.universe: tuple[str, ...] = ()
        self.universe_refreshed_at: datetime | None = None
        self.rotation = 0

    def start(self, *, now: datetime | None = None) -> RuntimeLockOwnership:
        if self.owner is not None:
            return self.owner
        owner = acquire_observer_lock(self.runtime_root, now=now)
        if owner is None:
            raise RuntimeError("observer_lock_conflict")
        self.owner = owner
        return owner

    def refresh_universe(self, *, now: datetime | None = None) -> dict[str, Any]:
        result = discover_observer_universe(self.client)
        self.universe = tuple(result["eligible_instruments"])
        self.universe_refreshed_at = now or _utc_now()
        return result

    def cycle(self, *, now: datetime | None = None) -> dict[str, Any]:
        if self.owner is None:
            raise RuntimeError("observer_not_started")
        observed_now = now or _utc_now()
        if self.universe_refreshed_at is None or (observed_now - self.universe_refreshed_at).total_seconds() >= UNIVERSE_REFRESH_SECONDS:
            self.refresh_universe(now=observed_now)
        cycle = observer_cycle(
            self.client, universe=self.universe, rotation=self.rotation,
            candle_budget=self.candle_budget, now=observed_now,
            require_m5_regime=self.require_m5_regime, units=self.units, observer_config=self.config,
        )
        self.rotation = (self.rotation + self.candle_budget) % max(1, len(self.universe))
        if not refresh_runtime_lock(observer_lock_path(self.runtime_root), self.owner, ttl_seconds=LOCK_TTL_SECONDS, now=observed_now):
            raise RuntimeError("observer_lock_lost")
        write_cycle_evidence(self.runtime_root, cycle, owner=self.owner, config=self.config)
        return cycle

    def run_forever(
        self, *, stop_requested: Callable[[], bool], sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic, max_cycles: int | None = None,
    ) -> Iterable[dict[str, Any]]:
        """Run until an explicit safety stop; ``max_cycles`` exists only for deterministic tests."""
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("positive_test_cycle_bound_required")
        cadence = MonotonicCadence(monotonic=monotonic)
        completed = 0
        while not stop_requested():
            deadline = cadence.next_deadline()
            cycle = self.cycle()
            cycle["health"]["scheduled_monotonic"] = deadline.scheduled_at_monotonic
            cycle["health"]["observed_monotonic"] = deadline.observed_at_monotonic
            cycle["health"]["missed_deadline_count"] = 1 if deadline.missed_seconds else 0
            yield cycle
            completed += 1
            if max_cycles is not None and completed >= max_cycles:
                return
            sleep(max(0.0, deadline.scheduled_at_monotonic + OBSERVATION_SECONDS - monotonic()))

    def stop(self) -> bool:
        if self.owner is None:
            return False
        released = release_observer_lock(self.runtime_root, self.owner)
        if released:
            self.owner = None
        return released


def append_evidence(path: Path, record: Mapping[str, Any]) -> None:
    item = dict(record)
    _assert_safe_artifact(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(json.dumps(item, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def summarize_outcomes(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Account existing PAPER outcomes; it does not open or credit an outcome."""
    values = [dict(item) for item in records]
    for item in values:
        validate_paper_outcome(item)
    pnl = [float(item.get("net_pl_usd", 0.0)) for item in values]
    return {
        "wins": sum(value > 0 for value in pnl), "losses": sum(value < 0 for value in pnl),
        "flats": sum(value == 0 for value in pnl), "unclosed": sum(item.get("status") == "ACTIVE" for item in values),
        "net_pl_usd": round(sum(pnl), 8), "qualifying_trades_incremented": 0, **SAFETY,
    }


def validate_paper_outcome(record: Mapping[str, Any]) -> None:
    """Validate supplied PAPER outcome accounting without creating an outcome."""
    if record.get("record_type") != "PAPER_OUTCOME":
        raise ValueError("paper_outcome_record_required")
    if record.get("qualifying_credit") is True:
        raise ValueError("observer_may_not_award_qualifying_credit")
    if not str(record.get("candidate_id", "")).strip():
        raise ValueError("paper_outcome_candidate_id_required")
    if record.get("status") not in {"CLOSED", "ACTIVE"}:
        raise ValueError("paper_outcome_status_invalid")
    gross = _finite(record.get("gross_pl_usd", 0.0), "gross_pl_usd")
    net = _finite(record.get("net_pl_usd", 0.0), "net_pl_usd")
    spread = _finite(record.get("estimated_spread_cost_usd", 0.0), "estimated_spread_cost_usd")
    slippage = _finite(record.get("estimated_slippage_cost_usd", 0.0), "estimated_slippage_cost_usd")
    if round(gross - spread - slippage, 8) != round(net, 8):
        raise ValueError("paper_outcome_net_pl_mismatch")
    if _finite(record.get("mfe_price", 0.0), "mfe_price") < _finite(record.get("mae_price", 0.0), "mae_price"):
        raise ValueError("paper_outcome_mfe_mae_order_invalid")
    if _finite(record.get("holding_seconds", 0.0), "holding_seconds") < 0:
        raise ValueError("paper_outcome_holding_duration_invalid")
    _finite(record.get("r_multiple", 0.0), "r_multiple")


def observe_hypothetical_exit(
    session: Mapping[str, Any], quote: Mapping[str, Any], *, observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Observe an observer-owned hypothetical session; never closes a campaign session."""
    if session.get("observer_owned") is not True or session.get("qualifying_credit") is True:
        raise ValueError("observer_owned_zero_credit_session_required")
    direction = str(session.get("direction", "")).upper()
    if direction not in {"BUY", "SELL"}:
        raise ValueError("observer_session_direction_required")
    entry, stop, target = (_finite(session.get(key), key) for key in ("entry", "stop", "target"))
    units = int(_finite(session.get("units"), "units"))
    exit_price = _finite(quote.get("bid" if direction == "BUY" else "ask"), "exit_price")
    stop_hit = exit_price <= stop if direction == "BUY" else exit_price >= stop
    target_hit = exit_price >= target if direction == "BUY" else exit_price <= target
    if stop_hit and target_hit:
        raise ValueError("ambiguous_exit_boundary")
    prior_mfe = _finite(session.get("mfe_price", entry), "mfe_price")
    prior_mae = _finite(session.get("mae_price", entry), "mae_price")
    mfe = max(prior_mfe, exit_price) if direction == "BUY" else min(prior_mfe, exit_price)
    mae = min(prior_mae, exit_price) if direction == "BUY" else max(prior_mae, exit_price)
    gross = (exit_price - entry) * units if direction == "BUY" else (entry - exit_price) * units
    spread_cost = _finite(session.get("estimated_spread_cost_usd", 0.0), "estimated_spread_cost_usd")
    net = gross - spread_cost
    risk = abs(entry - stop) * units
    timestamp = observed_at or _parse_utc(str(quote["collection_timestamp_utc"]))
    opened_at = _parse_utc(str(session["opened_at_utc"]))
    reason = "TARGET" if target_hit else "STOP" if stop_hit else "HOLD"
    return {
        "schema": SCHEMA, "record_type": "PAPER_OUTCOME", "candidate_id": session["candidate_id"],
        "status": "CLOSED" if reason != "HOLD" else "ACTIVE", "observer_owned": True, "qualifying_credit": False,
        "direction": direction, "entry": entry, "exit_price": exit_price, "stop": stop, "target": target,
        "current_bid": quote.get("bid"), "current_ask": quote.get("ask"), "current_spread": quote.get("spread_price"),
        "distance_to_stop": abs(exit_price - stop), "distance_to_target": abs(target - exit_price),
        "gross_pl_usd": round(gross, 8), "estimated_spread_cost_usd": spread_cost,
        "estimated_slippage_cost_usd": 0.0, "net_pl_usd": round(net, 8), "mfe_price": mfe, "mae_price": mae,
        "holding_seconds": round(max(0.0, (timestamp - opened_at).total_seconds()), 6),
        "r_multiple": round(net / risk, 8) if risk else 0.0, "potential_stop_crossing": stop_hit,
        "potential_target_crossing": target_hit, "exit_reason": reason, **SAFETY,
    }


def _evidence_file(runtime_root: Path, *, now: datetime, max_bytes: int) -> Path:
    runtime_root.mkdir(parents=True, exist_ok=True)
    day = now.astimezone(timezone.utc).strftime("%Y%m%d")
    candidates = sorted(runtime_root.glob(f"observer-events-{day}-*.jsonl"))
    current = candidates[-1] if candidates else runtime_root / f"observer-events-{day}-0001.jsonl"
    if current.exists() and current.stat().st_size >= max_bytes:
        sequence = int(current.stem.rsplit("-", 1)[1]) + 1
        current = runtime_root / f"observer-events-{day}-{sequence:04d}.jsonl"
    return current


def append_rotating_evidence(
    runtime_root: Path, record: Mapping[str, Any], *, now: datetime,
    max_bytes: int = DEFAULT_EVIDENCE_MAX_BYTES, retention_files: int = DEFAULT_EVIDENCE_RETENTION_FILES,
) -> Path:
    """Append crash-safely and retain a bounded number of closed observer files."""
    if max_bytes < 1024 or retention_files < 2:
        raise ValueError("observer_evidence_bounds_invalid")
    path = _evidence_file(runtime_root, now=now, max_bytes=max_bytes)
    append_evidence(path, record)
    closed = sorted(item for item in runtime_root.glob("observer-events-*.jsonl") if item != path)
    while len(closed) > retention_files - 1:
        # Only closed observer-owned evidence files are eligible for bounded retention.
        closed.pop(0).unlink()
    return path


def observer_lock_path(runtime_root: Path) -> Path:
    return runtime_root / "observer.lock"


def acquire_observer_lock(runtime_root: Path, *, now: datetime | None = None) -> RuntimeLockOwnership | None:
    return acquire_runtime_lock(
        observer_lock_path(runtime_root), schema=RUNTIME_SCHEMA, campaign_identity=RUNTIME_IDENTITY,
        source_fingerprint_value=source_fingerprint(Path(__file__)), ttl_seconds=LOCK_TTL_SECONDS,
        now=now or _utc_now(),
    )


def release_observer_lock(runtime_root: Path, owner: RuntimeLockOwnership) -> bool:
    return release_runtime_lock(observer_lock_path(runtime_root), owner)


def observer_health(
    *, eligible: Sequence[str], quotes: Sequence[Mapping[str, Any]], deadline: Deadline,
    api_errors: int = 0, lock_owner: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fresh = [quote for quote in quotes if quote.get("data_status") == "FRESH"]
    return {
        "schema": SCHEMA, "record_type": "OBSERVER_HEALTH", "observer_version": VERSION,
        "eligible_pairs": len(eligible), "fresh_pairs": len(fresh), "degraded_pairs": len(eligible) - len(fresh),
        "actual_scans_per_second": round(len(quotes) / max(OBSERVATION_SECONDS, deadline.observed_at_monotonic - deadline.scheduled_at_monotonic + OBSERVATION_SECONDS), 6),
        "missed_deadline_seconds": round(deadline.missed_seconds, 6), "api_errors": int(api_errors),
        "coverage_status": (
            "HEALTHY_ONE_SECOND" if len(fresh) == len(eligible) and not api_errors and deadline.missed_seconds <= OBSERVATION_SECONDS
            else "DEGRADED_LATENCY" if deadline.missed_seconds > OBSERVATION_SECONDS
            else "DEGRADED_RATE_LIMIT"
        ),
        "lock_owner": dict(lock_owner or {}), "qualifying_closed_trades": 0, **SAFETY,
    }


def render_live_summary(health: Mapping[str, Any], decisions: Sequence[Mapping[str, Any]], *, active_session: Mapping[str, Any] | None = None) -> str:
    ranked = [item for item in decisions if item.get("paper_eligible")]
    top = ranked[0] if ranked else None
    lines = [
        f"OBSERVER {health.get('coverage_status')} | {health.get('fresh_pairs')}/{health.get('eligible_pairs')} fresh | scans/s {health.get('actual_scans_per_second')}",
        f"deadline_missed={health.get('missed_deadline_seconds')} api_errors={health.get('api_errors')}",
    ]
    if top:
        quote = top["quote"]
        lines.append(f"TOP {top['instrument']} {top['direction']} M2/M1 bid={quote['bid']} ask={quote['ask']} spread_pips={quote['spread_pips']} eligibility=PAPER_ELIGIBLE")
    else:
        lines.append("TOP NONE | exact rejection evidence recorded")
    if active_session:
        lines.append(
            "ACTIVE PAPER SESSION: ACTIVE "
            f"entry={active_session.get('entry_price')} latest={active_session.get('latest_price')} "
            f"stop={active_session.get('stop_price')} target={active_session.get('target_price')} "
            f"gross_pl={active_session.get('gross_pl')} net_pl={active_session.get('net_pl')} "
            f"mfe={active_session.get('mfe')} mae={active_session.get('mae')}"
        )
    else:
        lines.append("ACTIVE PAPER SESSION: NONE")
    lines.append(f"QUALIFYING CLOSED TRADES: {health.get('qualifying_closed_trades', 0)}")
    return "\n".join(lines) + "\n"
