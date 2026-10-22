"""PAPER/shadow-only Forex risk and market-integrity hardening primitives.

These functions calculate and validate research evidence.  They do not place,
modify, or cancel broker orders and cannot mutate production strategy state.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence


SCHEMA = "AIOS_FOREX_P1_RISK_MARKET_HARDENING.v1"
NEWS_SCHEMA = "AIOS_FOREX_HIGH_IMPACT_EVENT.v1"


@dataclass(frozen=True)
class HardeningConfig:
    """Governed values; production calibration is never changed by this module."""

    max_risk_percent: float = 1.0
    minimum_reward_risk: float = 1.5
    shadow_reward_risk: float = 2.0
    spread_multiple: float = 1.5
    daily_drawdown_percent: float = 3.0
    h1_atr_period: int = 10
    h1_supertrend_multiplier: float = 3.0
    rsi_period: int = 14
    rsi_long_ceiling: float = 70.0
    news_blackout_before_minutes: int = 30
    news_blackout_after_minutes: int = 30


def completed_candle_gate(*, is_complete: bool, candle_open_utc: str, now_utc: str) -> dict[str, Any]:
    """Require completed bars and expose the open/close boundary explicitly."""
    opened = _parse_utc(candle_open_utc)
    now = _parse_utc(now_utc)
    close = opened + timedelta(minutes=5)
    passed = bool(is_complete and close <= now)
    return {"passed": passed, "is_bar_closed": bool(is_complete),
            "candle_open_utc": candle_open_utc, "candle_close_utc": _stamp(close),
            "evaluated_at_utc": now_utc, "reason": "PASS" if passed else "INCOMPLETE_OR_FUTURE_BAR"}


def immutable_bar_identity(*, instrument: str, timeframe: str, candle_open_utc: str) -> str:
    value = f"{instrument}|{timeframe}|{candle_open_utc}"
    return "bar-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def debounce_candidate(*, candidate_id: str, seen_candidate_ids: Sequence[str]) -> dict[str, Any]:
    duplicate = candidate_id in set(seen_candidate_ids)
    return {"candidate_id": candidate_id, "duplicate": duplicate, "passed": not duplicate,
            "reason": "DUPLICATE_COMPLETED_BAR" if duplicate else "DISTINCT_COMPLETED_BAR"}


def h1_supertrend_shadow_filter(*, m5_direction: str, h1_bullish: bool | None, config: HardeningConfig = HardeningConfig()) -> dict[str, Any]:
    passed = None if h1_bullish is None else m5_direction == "BUY" and bool(h1_bullish)
    return {"enabled": True, "shadow_only": True, "h1_atr_period": config.h1_atr_period,
            "h1_supertrend_multiplier": config.h1_supertrend_multiplier, "m5_direction": m5_direction,
            "h1_bullish": h1_bullish, "passed": passed,
            "status": "NOT_EVALUATED" if passed is None else ("PASS" if passed else "FAIL")}


def rsi_shadow_filter(rsi: float | None, *, direction: str = "BUY", config: HardeningConfig = HardeningConfig()) -> dict[str, Any]:
    passed = None if rsi is None else (float(rsi) <= config.rsi_long_ceiling if direction == "BUY" else True)
    return {"enabled": True, "shadow_only": True, "period": config.rsi_period, "rsi": rsi,
            "long_ceiling": config.rsi_long_ceiling, "passed": passed,
            "status": "NOT_EVALUATED" if passed is None else ("PASS" if passed else "FAIL")}


def pair_state_key(instrument: str, timeframe: str) -> str:
    return f"{instrument.upper()}|{timeframe.upper()}"


class PairStateStore:
    """Explicitly key state by pair/timeframe to prevent cross-pair leakage."""

    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}

    def get(self, instrument: str, timeframe: str) -> dict[str, Any]:
        return dict(self._states.get(pair_state_key(instrument, timeframe), {}))

    def set(self, instrument: str, timeframe: str, state: Mapping[str, Any]) -> None:
        self._states[pair_state_key(instrument, timeframe)] = dict(state)


def paper_position_size(*, account_equity: float, entry: float, stop: float, config: HardeningConfig = HardeningConfig()) -> dict[str, Any]:
    if account_equity <= 0 or entry <= stop:
        raise ValueError("invalid_paper_risk_inputs")
    equity_decimal = Decimal(str(account_equity)); entry_decimal = Decimal(str(entry)); stop_decimal = Decimal(str(stop))
    risk_budget_decimal = equity_decimal * Decimal(str(config.max_risk_percent)) / Decimal("100")
    stop_distance_decimal = entry_decimal - stop_decimal
    units = int(risk_budget_decimal / stop_distance_decimal)
    return {"shadow_only": True, "paper_only": True, "account_equity": account_equity,
            "risk_percent": config.max_risk_percent, "risk_budget": round(float(risk_budget_decimal), 8),
            "stop_distance": round(float(stop_distance_decimal), 8), "units": max(0, units),
            "broker_write_performed": False, "live_trade_performed": False}


def reward_risk_guard(actual: float | None, *, config: HardeningConfig = HardeningConfig()) -> dict[str, Any]:
    production_passed = actual is not None and float(actual) >= config.minimum_reward_risk
    shadow_strict_passed = actual is not None and float(actual) >= config.shadow_reward_risk
    return {"actual": actual, "production_minimum": config.minimum_reward_risk,
            "shadow_strict_minimum": config.shadow_reward_risk, "production_passed": production_passed,
            "shadow_strict_passed": shadow_strict_passed, "production_mutation_allowed": False}


def spread_quality_guard(*, spread: float, rolling_spreads: Sequence[float], config: HardeningConfig = HardeningConfig()) -> dict[str, Any]:
    if spread < 0 or any(value < 0 for value in rolling_spreads):
        raise ValueError("invalid_spread")
    mean = sum(rolling_spreads) / len(rolling_spreads) if rolling_spreads else None
    threshold = mean * config.spread_multiple if mean is not None else None
    passed = None if threshold is None else spread <= threshold
    return {"spread": spread, "rolling_mean_24h": mean, "threshold_multiple": config.spread_multiple,
            "threshold": threshold, "passed": passed, "status": "NOT_EVALUATED" if passed is None else ("PASS" if passed else "FAIL"), "shadow_only": True}


def slippage_model(*, signal_price: float, quote_price: float, spread: float) -> dict[str, Any]:
    slippage = float(quote_price) - float(signal_price)
    return {"signal_price": signal_price, "quote_price": quote_price, "spread": spread,
            "hypothetical_slippage": round(slippage, 10),
            "hypothetical_total_burden": round(abs(slippage) + spread, 10), "shadow_only": True,
            "order_submitted": False}


def high_impact_event(*, event_id: str, name: str, event_utc: str, impact: str = "HIGH") -> dict[str, Any]:
    if impact != "HIGH":
        raise ValueError("high_impact_event_required")
    return {"schema": NEWS_SCHEMA, "event_id": event_id, "name": name, "event_utc": event_utc,
            "impact": impact, "provider_neutral": True, "provider_integration": "PENDING",
            "execution_authority": False}


def news_blackout(*, evaluation_utc: str, event: Mapping[str, Any], config: HardeningConfig = HardeningConfig()) -> dict[str, Any]:
    evaluation = _parse_utc(evaluation_utc); event_time = _parse_utc(str(event["event_utc"]))
    before = event_time - timedelta(minutes=config.news_blackout_before_minutes)
    after = event_time + timedelta(minutes=config.news_blackout_after_minutes)
    blocked = before <= evaluation <= after
    return {"blocked": blocked, "shadow_only": True, "before_minutes": config.news_blackout_before_minutes,
            "after_minutes": config.news_blackout_after_minutes, "provider_integration": event.get("provider_integration", "PENDING")}


def daily_drawdown_model(*, starting_equity: float, current_equity: float, config: HardeningConfig = HardeningConfig()) -> dict[str, Any]:
    if starting_equity <= 0:
        raise ValueError("invalid_starting_equity")
    drawdown = max(0.0, (starting_equity - current_equity) / starting_equity * 100.0)
    return {"starting_equity": starting_equity, "current_equity": current_equity,
            "drawdown_percent": round(drawdown, 8), "threshold_percent": config.daily_drawdown_percent,
            "paper_shadow_halt": drawdown >= config.daily_drawdown_percent, "live_authority": False}


def idempotency_identity(*, instrument: str, timeframe: str, bar_identity: str, strategy_name: str, entry: float, stop: float, target: float) -> str:
    payload = json.dumps({"instrument": instrument, "timeframe": timeframe, "bar_identity": bar_identity,
                          "strategy_name": strategy_name, "entry": entry, "stop": stop, "target": target}, sort_keys=True, separators=(",", ":"))
    return "intent-" + hashlib.sha256(payload.encode()).hexdigest()


def reconcile_paper_state(*, local_position: Mapping[str, Any] | None, broker_snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    local = dict(local_position or {}); broker = dict(broker_snapshot or {})
    fields = ("instrument", "direction", "units", "entry_price")
    mismatches = [field for field in fields if local.get(field) != broker.get(field)]
    return {"reconciliation_required": True, "match": not mismatches, "mismatches": mismatches,
            "broker_snapshot_read_only": True, "mutation_allowed": False}


def clock_latency_integrity(*, broker_timestamp_utc: str, candle_close_utc: str, pricing_timestamp_utc: str, evaluated_at_utc: str, max_age_seconds: int = 300) -> dict[str, Any]:
    broker = _parse_utc(broker_timestamp_utc); close = _parse_utc(candle_close_utc); pricing = _parse_utc(pricing_timestamp_utc); evaluated = _parse_utc(evaluated_at_utc)
    ages = {"broker_to_evaluation_seconds": (evaluated - broker).total_seconds(), "candle_close_to_evaluation_seconds": (evaluated - close).total_seconds(), "pricing_to_evaluation_seconds": (evaluated - pricing).total_seconds()}
    passed = all(0 <= value <= max_age_seconds for value in ages.values())
    return {"passed": passed, "max_age_seconds": max_age_seconds, "ages_seconds": ages, "clock_integrity": "PASS" if passed else "FAIL"}


def weekly_performance_drift(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    resolved = [record for record in records if record.get("outcome_r") is not None]
    wins = [record for record in resolved if float(record["outcome_r"]) > 0]
    values = [float(record["outcome_r"]) for record in resolved]
    return {"schema": SCHEMA, "sample": len(records), "resolved": len(resolved), "trade_count": len(wins) + sum(value < 0 for value in values),
            "win_rate": round(len(wins) / len(resolved), 8) if resolved else None,
            "expectancy_r": round(sum(values) / len(values), 8) if values else None,
            "mfe_r": [record.get("mfe_r") for record in records if record.get("mfe_r") is not None],
            "mae_r": [record.get("mae_r") for record in records if record.get("mae_r") is not None],
            "false_positive_count": sum(record.get("outcome_classification") == "FALSE_POSITIVE" for record in records),
            "false_negative_count": sum(record.get("outcome_classification") == "FALSE_NEGATIVE" for record in records),
            "filter_value_drift": "ANALYSIS_ONLY", "production_mutation_allowed": False}


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
