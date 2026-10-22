"""Canonical, offline EUR_USD M5 market-history to paper-only signal contract."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from automation.forex_engine.models import Candle
from automation.forex_engine.regime import (
    HIGH_VOLATILITY, LOW_VOLATILITY, NORMAL_VOLATILITY, RANGING,
    TRENDING_DOWN, TRENDING_UP, assess_regime,
)
from automation.forex_engine.signal_rules import SPRINT_4_STRATEGY_NAME

HISTORY_SCHEMA = "AIOS_P1_EURUSD_MARKET_HISTORY.v1"
SIGNAL_SCHEMA = "AIOS_P1_EURUSD_SIGNAL_DECISION.v1"
INSTRUMENT = "EUR_USD"
ENGINE_SYMBOL = "EURUSD"
GRANULARITY = "M5"
M5_CANDLE_DURATION = timedelta(minutes=5)
MINIMUM_CANDLES = 3
FRESHNESS_SECONDS = 300
MINIMUM_REWARD_TO_RISK = 2.0
GENUINE_PROVENANCE = "GENUINE_OBSERVED_MARKET_DATA"
HISTORY_KEYS = frozenset({"schema", "evidence_type", "provenance", "broker_label", "environment", "instrument", "granularity", "requested_count", "returned_count", "first_observed_at_utc", "last_observed_at_utc", "candles", "source_status", "stale_status", "read_only", "complete", "broker_write_performed", "credentials_persisted", "account_identifier_included", "raw_payload_included", "order_submission_allowed", "demo_execution_allowed", "live_execution_allowed", "money_movement_allowed"})
CANDLE_REQUIRED = frozenset({"observed_at_utc", "open", "high", "low", "close", "complete"})
SIGNAL_KEYS = frozenset({"schema", "signal_id", "strategy_id", "instrument", "direction", "status", "generated_at_utc", "history_first_utc", "history_last_utc", "candle_count", "granularity", "entry_reference", "stop_price", "target_price", "stop_distance", "target_distance", "reward_to_risk", "volatility", "regime", "rationale", "blockers", "provenance", "paper_only", "owner_supervision_required", "broker_call_performed", "credentials_loaded", "account_access_performed", "order_submission_allowed", "demo_execution_allowed", "live_execution_allowed", "money_movement_allowed"})


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("explicit_utc_timestamp_required")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("invalid_utc_timestamp") from exc
    return parsed.astimezone(timezone.utc)


def _positive(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"invalid_{field}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_{field}") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"invalid_{field}")
    return result


def resolve_canonical_signal_rules() -> dict[str, Any]:
    """Expose, rather than duplicate, the repository Sprint 4 rule constants."""
    return {"strategy_id": SPRINT_4_STRATEGY_NAME, "minimum_candles": MINIMUM_CANDLES,
            "lookback": 3, "granularity": GRANULARITY, "minimum_reward_to_risk": MINIMUM_REWARD_TO_RISK,
            "allowed_direction": "BUY", "allowed_volatility": NORMAL_VOLATILITY,
            "source_modules": ["automation.forex_engine.regime", "automation.forex_engine.signal_rules"]}


def validate_market_history(history: Mapping[str, Any], *, now: datetime | None = None,
                            allow_fixture: bool = False) -> dict[str, Any]:
    if not isinstance(history, Mapping):
        raise ValueError("market_history_required")
    if set(history) != HISTORY_KEYS:
        raise ValueError("history_fields_not_allowlisted")
    expected = {"schema": HISTORY_SCHEMA, "evidence_type": "SANITIZED_CANDLE_HISTORY",
                "broker_label": "OANDA", "environment": "PRACTICE", "instrument": INSTRUMENT,
                "granularity": GRANULARITY, "source_status": "VALID", "stale_status": "VALID",
                "read_only": True, "complete": True, "broker_write_performed": False,
                "credentials_persisted": False, "account_identifier_included": False,
                "raw_payload_included": False, "order_submission_allowed": False,
                "demo_execution_allowed": False, "live_execution_allowed": False,
                "money_movement_allowed": False}
    if any(history.get(key) != value for key, value in expected.items()):
        raise ValueError("invalid_or_unsafe_history_contract")
    provenance = history.get("provenance")
    if provenance != GENUINE_PROVENANCE and not (allow_fixture and provenance == "TEST_FIXTURE"):
        raise ValueError("genuine_observed_provenance_required")
    candles = history.get("candles")
    if not isinstance(candles, list) or not candles:
        raise ValueError("market_history_required")
    requested, returned = history.get("requested_count"), history.get("returned_count")
    if isinstance(requested, bool) or not isinstance(requested, int) or requested <= 0:
        raise ValueError("invalid_requested_count")
    if returned != len(candles) or requested < returned:
        raise ValueError("history_count_mismatch")
    timestamps = []
    normalized_candles = []
    for item in candles:
        if not isinstance(item, Mapping) or not CANDLE_REQUIRED <= set(item) or not set(item) <= CANDLE_REQUIRED | {"volume"}:
            raise ValueError("candle_fields_not_allowlisted")
        if item.get("complete") is not True:
            raise ValueError("incomplete_candle")
        timestamp = _utc(item.get("observed_at_utc")); timestamps.append(timestamp)
        values = {name: _positive(item.get(name), name) for name in ("open", "high", "low", "close")}
        if not values["low"] <= min(values["open"], values["close"]) or not values["high"] >= max(values["open"], values["close"]):
            raise ValueError("invalid_ohlc")
        normalized = dict(item); normalized.update(values)
        if "volume" in item:
            volume = item["volume"]
            if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not math.isfinite(float(volume)) or volume < 0:
                raise ValueError("invalid_volume")
        normalized_candles.append(normalized)
    if len(set(timestamps)) != len(timestamps): raise ValueError("duplicate_candle_timestamp")
    if timestamps != sorted(timestamps): raise ValueError("unsorted_candle_timestamps")
    if history.get("first_observed_at_utc") != candles[0]["observed_at_utc"] or history.get("last_observed_at_utc") != candles[-1]["observed_at_utc"]:
        raise ValueError("history_time_boundary_mismatch")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    latest_timestamp = timestamps[-1]
    latest_completion = latest_timestamp + M5_CANDLE_DURATION
    if latest_timestamp > current or (current - latest_completion).total_seconds() > FRESHNESS_SECONDS:
        raise ValueError("stale_history")
    result = dict(history); result["candles"] = normalized_candles
    return result


def _engine_candles(history: Mapping[str, Any]) -> list[Candle]:
    return [Candle(symbol=ENGINE_SYMBOL, timeframe="5m", timestamp=item["observed_at_utc"],
                   open=item["open"], high=item["high"], low=item["low"], close=item["close"],
                   volume=item.get("volume", 0), source="sanitized_market_history") for item in history["candles"]]


def calculate_regime(history: Mapping[str, Any]) -> dict[str, Any]:
    assessment = assess_regime(_engine_candles(history))
    return {"trend": assessment.trend_state, "volatility": assessment.volatility_state,
            "lookback": assessment.lookback, "reason": assessment.reason}


def calculate_volatility(history: Mapping[str, Any]) -> dict[str, Any]:
    selected = history["candles"][-3:]
    average_range = sum(item["high"] - item["low"] for item in selected) / 3
    average_close = sum(item["close"] for item in selected) / 3
    return {"state": calculate_regime(history)["volatility"], "average_range": average_range,
            "average_close": average_close, "range_pct": average_range / average_close}


def evaluate_buy_signal(history: Mapping[str, Any]) -> dict[str, Any]:
    if len(history["candles"]) < MINIMUM_CANDLES:
        return {"status": "REQUIRE_MORE_HISTORY", "direction": None, "blockers": ["minimum_3_completed_candles_required"]}
    regime = calculate_regime(history)
    if regime["volatility"] in (LOW_VOLATILITY, HIGH_VOLATILITY):
        return {"status": "RISK_REJECTED", "direction": None, "blockers": [f"{regime['volatility'].lower()}_blocked"]}
    if regime["trend"] == RANGING:
        return {"status": "REGIME_REJECTED", "direction": None, "blockers": ["ranging_regime_blocked"]}
    if regime["trend"] == TRENDING_DOWN:
        return {"status": "NO_SIGNAL", "direction": None, "blockers": ["buy_rule_not_satisfied"]}
    if regime["trend"] != TRENDING_UP:
        return {"status": "REGIME_REJECTED", "direction": None, "blockers": ["unknown_regime_blocked"]}
    return {"status": "BUY", "direction": "BUY", "blockers": []}


def derive_stop_target(history: Mapping[str, Any]) -> dict[str, float]:
    recent = history["candles"][-3:]; entry = recent[-1]["close"]; stop = min(item["low"] for item in recent)
    risk = entry - stop
    if not math.isfinite(risk) or risk <= 0: raise ValueError("invalid_stop_distance")
    target = entry + MINIMUM_REWARD_TO_RISK * risk
    return {"entry_reference": round(entry, 5), "stop_price": round(stop, 5), "target_price": round(target, 5),
            "stop_distance": round(risk, 5), "target_distance": round(target-entry, 5), "reward_to_risk": MINIMUM_REWARD_TO_RISK}


def build_signal_state(history: Mapping[str, Any], *, generated_at_utc: str) -> dict[str, Any]:
    generated = _utc(generated_at_utc); decision = evaluate_buy_signal(history)
    prices = derive_stop_target(history) if decision["status"] == "BUY" else {key: None for key in ("entry_reference", "stop_price", "target_price", "stop_distance", "target_distance", "reward_to_risk")}
    regime, volatility = calculate_regime(history) if len(history["candles"]) >= 3 else {"trend": "UNKNOWN", "volatility": "UNKNOWN", "lookback": len(history["candles"]), "reason": "Insufficient candles."}, None
    if volatility is None: volatility = calculate_volatility(history) if len(history["candles"]) >= 3 else {"state": "UNKNOWN", "average_range": None, "average_close": None, "range_pct": None}
    identity = {"history": history, "generated_at_utc": generated_at_utc, "strategy_id": SPRINT_4_STRATEGY_NAME}
    result = {"schema": SIGNAL_SCHEMA, "signal_id": "sig-" + hashlib.sha256(stable_json(identity).encode()).hexdigest()[:24],
              "strategy_id": SPRINT_4_STRATEGY_NAME, "instrument": INSTRUMENT, "direction": decision["direction"], "status": decision["status"],
              "generated_at_utc": generated.isoformat().replace("+00:00", "Z"), "history_first_utc": history["first_observed_at_utc"], "history_last_utc": history["last_observed_at_utc"],
              "candle_count": len(history["candles"]), "granularity": GRANULARITY, **prices, "volatility": volatility, "regime": regime,
              "rationale": regime["reason"], "blockers": decision["blockers"], "provenance": history["provenance"], "paper_only": True,
              "owner_supervision_required": True, "broker_call_performed": False, "credentials_loaded": False, "account_access_performed": False,
              "order_submission_allowed": False, "demo_execution_allowed": False, "live_execution_allowed": False, "money_movement_allowed": False}
    return validate_signal_decision(result)


def validate_signal_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    if set(decision) != SIGNAL_KEYS: raise ValueError("signal_fields_not_allowlisted")
    if decision.get("status") not in {"BUY", "NO_SIGNAL", "REQUIRE_MORE_HISTORY", "REGIME_REJECTED", "RISK_REJECTED"}: raise ValueError("invalid_signal_status")
    for key in ("broker_call_performed", "credentials_loaded", "account_access_performed", "order_submission_allowed", "demo_execution_allowed", "live_execution_allowed", "money_movement_allowed"):
        if decision.get(key) is not False: raise ValueError("execution_permission_forbidden")
    if decision.get("paper_only") is not True or decision.get("owner_supervision_required") is not True: raise ValueError("paper_supervision_required")
    if decision["status"] == "BUY":
        entry, stop, target = (_positive(decision[key], key) for key in ("entry_reference", "stop_price", "target_price"))
        if not stop < entry < target: raise ValueError("invalid_buy_price_order")
        if not math.isclose(float(decision["reward_to_risk"]), MINIMUM_REWARD_TO_RISK, abs_tol=1e-9): raise ValueError("invalid_reward_to_risk")
    elif decision.get("direction") is not None: raise ValueError("non_buy_direction_forbidden")
    return dict(decision)


def render_owner_report(state: Mapping[str, Any]) -> str:
    return "# AIOS P1 EUR_USD Market-History Signal V1\n\n" + "\n".join(f"- {key}: {str(value).lower() if isinstance(value, bool) else value}" for key, value in state.items()) + "\n"
