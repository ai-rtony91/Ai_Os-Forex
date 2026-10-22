"""Read-only P1 production-control versus shadow-opportunity audit.

Production decisions remain the control.  This module replays those exact rules
against sanitized completed M5 candles, then evaluates rejected long candidates
only after each control decision is fixed.  Nothing in this module can open a
PAPER position, modify campaign evidence, or feed Supertrend into production.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from automation.forex_engine.forex_p1_eurusd_market_history_signal_v1 import (
    FRESHNESS_SECONDS,
    GRANULARITY,
    INSTRUMENT,
    MINIMUM_CANDLES,
    MINIMUM_REWARD_TO_RISK,
    M5_CANDLE_DURATION,
    build_signal_state,
    calculate_regime,
    calculate_volatility,
    derive_stop_target,
    evaluate_buy_signal,
    resolve_canonical_signal_rules,
    validate_market_history,
)
from automation.forex_engine.forex_p1_supertrend_shadow_v1 import (
    ATR_LENGTH,
    MULTIPLIER,
    STRATEGY_NAME,
    evaluate_supertrend_shadow,
)
from automation.forex_engine.regime import (
    HIGH_VOLATILITY,
    HIGH_VOLATILITY_RANGE_PCT,
    LOW_VOLATILITY,
    LOW_VOLATILITY_RANGE_PCT,
    NORMAL_VOLATILITY,
    RANGING,
    TRENDING_DOWN,
    TRENDING_UP,
)

VERSION = "forex_p1_shadow_opportunity_audit_v1"
IDENTITY_MARKER = "AIOS-FOREX-P1-PRO-MONEY-FOLLOWING-SUPERTREND-AUDIT-V3"
PACKET_ID = "PKT-EAST-FOREX-P1-PRO-MONEY-FOLLOWING-AUDIT-V3"
DEFAULT_PAPER_UNITS = 100
FORWARD_HORIZONS = (1, 3, 6, 12, 24)

SAFETY = {
    "paper_only": True,
    "shadow_not_executed": True,
    "production_feedback_allowed": False,
    "position_open_allowed": False,
    "qualifying_trade_credit_allowed": False,
    "production_pnl_mutation_allowed": False,
    "broker_call_performed": False,
    "broker_write_performed": False,
    "practice_order_performed": False,
    "live_trade_performed": False,
    "money_movement_performed": False,
    "credentials_persisted": False,
}


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("explicit_utc_timestamp_required")
    raw = value[:-1]
    if "." in raw:
        head, fraction = raw.split(".", 1)
        raw = head + "." + (fraction + "000000")[:6]
    try:
        return datetime.fromisoformat(raw + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("invalid_utc_timestamp") from exc


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _mean(values: Sequence[float]) -> float | None:
    return round(statistics.fmean(values), 8) if values else None


def _gate(
    gate_id: str,
    name: str,
    *,
    actual: Any,
    required: Any,
    passed: bool | None,
    distance: float | None,
    rule: str,
    fail_status: str,
    reason: str,
    source_function: str,
    source_file: str = "automation/forex_engine/forex_p1_eurusd_market_history_signal_v1.py",
    inputs: Sequence[str] = (),
) -> dict[str, Any]:
    relative = None
    if passed is False and distance is not None and isinstance(required, (int, float)):
        denominator = abs(float(required))
        relative = round(abs(min(0.0, float(distance))) / denominator * 100, 8) if denominator else None
    return {
        "gate_id": gate_id,
        "gate_name": name,
        "source_file": source_file,
        "source_function": source_function,
        "inputs": list(inputs),
        "actual_value": actual,
        "required_value": required,
        "rule": rule,
        "pass_condition": rule,
        "fail_condition": f"NOT ({rule})",
        "gate_status": "NOT_EVALUATED" if passed is None else ("PASS" if passed else "FAIL"),
        "distance_to_pass": round(distance, 10) if distance is not None else None,
        "distance_to_pass_pct": relative,
        "fail_status": fail_status,
        "rejection_reason": reason,
        "downstream_effect": "continue" if passed else ("not_evaluated" if passed is None else fail_status),
    }


def production_decision_graph() -> list[dict[str, Any]]:
    """Machine-readable graph of the actual P1 runtime decision path."""
    return [
        {
            "gate_id": "G01_MARKET_DATA_CONTRACT",
            "gate_name": "Sanitized completed M5 market history",
            "source_file": "automation/forex_engine/forex_p1_eurusd_market_history_signal_v1.py",
            "source_function": "validate_market_history",
            "input_fields": ["schema", "provenance", "candles", "last_observed_at_utc"],
            "threshold_or_rule": f"completed, sorted, unique, genuine Practice history; freshness <= {FRESHNESS_SECONDS}s",
            "pass_condition": "contract valid and latest completed candle fresh",
            "fail_condition": "invalid, future, incomplete, conflicting, or stale history",
            "fail_status": "INVALID_MARKET_DATA or STALE_MARKET_DATA",
            "downstream_effect": "campaign halts before signal evaluation",
        },
        {
            "gate_id": "G02_MINIMUM_COMPLETED_CANDLES",
            "gate_name": "Minimum completed-candle history",
            "source_file": "automation/forex_engine/forex_p1_eurusd_market_history_signal_v1.py",
            "source_function": "evaluate_buy_signal",
            "input_fields": ["candles"],
            "threshold_or_rule": f"candle_count >= {MINIMUM_CANDLES}",
            "pass_condition": f"at least {MINIMUM_CANDLES} completed candles",
            "fail_condition": f"fewer than {MINIMUM_CANDLES} completed candles",
            "fail_status": "REQUIRE_MORE_HISTORY",
            "downstream_effect": "no production candidate",
        },
        {
            "gate_id": "G03_MINIMUM_VOLATILITY",
            "gate_name": "Minimum normal-volatility boundary",
            "source_file": "automation/forex_engine/regime.py",
            "source_function": "assess_regime",
            "input_fields": ["high", "low", "close"],
            "threshold_or_rule": f"average_range / average_close >= {LOW_VOLATILITY_RANGE_PCT}",
            "pass_condition": "range percent is not LOW_VOLATILITY",
            "fail_condition": "range percent is below the lower boundary",
            "fail_status": "RISK_REJECTED",
            "downstream_effect": "no production candidate",
        },
        {
            "gate_id": "G04_MAXIMUM_VOLATILITY",
            "gate_name": "Maximum normal-volatility boundary",
            "source_file": "automation/forex_engine/regime.py",
            "source_function": "assess_regime",
            "input_fields": ["high", "low", "close"],
            "threshold_or_rule": f"average_range / average_close <= {HIGH_VOLATILITY_RANGE_PCT}",
            "pass_condition": "range percent is not HIGH_VOLATILITY",
            "fail_condition": "range percent is above the upper boundary",
            "fail_status": "RISK_REJECTED",
            "downstream_effect": "no production candidate",
        },
        {
            "gate_id": "G05_BUY_TREND_ALIGNMENT",
            "gate_name": "Three-candle long trend alignment",
            "source_file": "automation/forex_engine/regime.py",
            "source_function": "assess_regime",
            "input_fields": ["first_close", "last_close", "average_range"],
            "threshold_or_rule": "last_close - first_close >= average_range * 0.5",
            "pass_condition": "TRENDING_UP",
            "fail_condition": "RANGING or TRENDING_DOWN",
            "fail_status": "REGIME_REJECTED or NO_SIGNAL",
            "downstream_effect": "no production candidate",
        },
        {
            "gate_id": "G06_POSITIVE_STOP_DISTANCE",
            "gate_name": "Canonical long stop geometry",
            "source_file": "automation/forex_engine/forex_p1_eurusd_market_history_signal_v1.py",
            "source_function": "derive_stop_target",
            "input_fields": ["last_close", "minimum_recent_low"],
            "threshold_or_rule": "entry_reference - stop_price > 0",
            "pass_condition": "positive finite risk distance",
            "fail_condition": "zero, negative, or non-finite risk distance",
            "fail_status": "INVALID_MARKET_DATA",
            "downstream_effect": "campaign halts before a PAPER candidate",
        },
        {
            "gate_id": "G07_MINIMUM_REWARD_TO_RISK",
            "gate_name": "Canonical target geometry",
            "source_file": "automation/forex_engine/forex_p1_eurusd_market_history_signal_v1.py",
            "source_function": "derive_stop_target",
            "input_fields": ["entry_reference", "stop_price", "target_price"],
            "threshold_or_rule": f"reward_to_risk == {MINIMUM_REWARD_TO_RISK}",
            "pass_condition": "target equals entry plus canonical 2R distance",
            "fail_condition": "reward/risk differs from the canonical rule",
            "fail_status": "INVALID_MARKET_DATA",
            "downstream_effect": "no PAPER candidate",
        },
        {
            "gate_id": "G08_SANITIZED_PRICING_GEOMETRY",
            "gate_name": "Practice pricing versus stop/target",
            "source_file": "automation/forex_engine/forex_p1_practice_paper_campaign_runtime_v1.py",
            "source_function": "_candidate_from_signal",
            "input_fields": ["ask", "stop_price", "target_price"],
            "threshold_or_rule": "stop_price < current ask < target_price",
            "pass_condition": "sanitized current ask is inside canonical geometry",
            "fail_condition": "ask is outside stop/target geometry",
            "fail_status": "NO PAPER CANDIDATE",
            "downstream_effect": "WAIT_FOR_NEXT_CYCLE",
        },
        {
            "gate_id": "G09_ONE_ACTIVE_PAPER_POSITION",
            "gate_name": "One-active-position restriction",
            "source_file": "automation/forex_engine/forex_p1_practice_paper_campaign_runtime_v1.py",
            "source_function": "completed_paper_records",
            "input_fields": ["active_session"],
            "threshold_or_rule": "maximum active PAPER positions == 1",
            "pass_condition": "no active session before opening",
            "fail_condition": "active PAPER session already exists",
            "fail_status": "MANAGE EXISTING PAPER POSITION",
            "downstream_effect": "new candidate is not opened",
        },
        {
            "gate_id": "G10_CAMPAIGN_SAFETY_HALTS",
            "gate_name": "Owner, kill-switch, and risk halts",
            "source_file": "automation/forex_engine/forex_p1_practice_paper_campaign_runtime_v1.py",
            "source_function": "completed_paper_records",
            "input_fields": ["owner_cancelled", "kill_switch_active", "risk_halt_active"],
            "threshold_or_rule": "all halt flags false",
            "pass_condition": "campaign safety flags permit the next read-only cycle",
            "fail_condition": "any explicit campaign halt flag is active",
            "fail_status": "CAMPAIGN HALT",
            "downstream_effect": "campaign stops fail closed",
        },
    ]


def _prefix(history: Mapping[str, Any], end: int) -> dict[str, Any]:
    result = copy.deepcopy(dict(history))
    result["candles"] = copy.deepcopy(list(history["candles"][:end]))
    result["requested_count"] = len(result["candles"])
    result["returned_count"] = len(result["candles"])
    result["first_observed_at_utc"] = result["candles"][0]["observed_at_utc"]
    result["last_observed_at_utc"] = result["candles"][-1]["observed_at_utc"]
    return result


def validate_audit_history(history: Mapping[str, Any]) -> dict[str, Any]:
    """Validate recorded evidence at its own completion boundary, not with future data."""
    if not isinstance(history, Mapping) or not isinstance(history.get("candles"), list) or not history["candles"]:
        raise ValueError("market_history_required")
    completion = _utc(str(history["candles"][-1]["observed_at_utc"])) + M5_CANDLE_DURATION
    return validate_market_history(history, now=completion, allow_fixture=history.get("provenance") == "TEST_FIXTURE")


def decision_lineage(history: Mapping[str, Any], *, cycle: int) -> dict[str, Any]:
    """Expose the exact ordered production gate values without changing the decision."""
    candles = history["candles"]
    gates: list[dict[str, Any]] = []
    count = len(candles)
    gates.append(_gate(
        "G02_MINIMUM_COMPLETED_CANDLES", "Minimum completed-candle history",
        actual=count, required=MINIMUM_CANDLES, passed=count >= MINIMUM_CANDLES,
        distance=float(count - MINIMUM_CANDLES), rule=f"candle_count >= {MINIMUM_CANDLES}",
        fail_status="REQUIRE_MORE_HISTORY", reason="minimum_3_completed_candles_required",
        source_function="evaluate_buy_signal", inputs=("candles",),
    ))

    regime = {"trend": "UNKNOWN", "volatility": "UNKNOWN", "lookback": count, "reason": "Insufficient candles."}
    volatility = {"state": "UNKNOWN", "average_range": None, "average_close": None, "range_pct": None}
    if count >= MINIMUM_CANDLES:
        regime = calculate_regime(history)
        volatility = calculate_volatility(history)
        range_pct = float(volatility["range_pct"])
        gates.append(_gate(
            "G03_MINIMUM_VOLATILITY", "Minimum normal-volatility boundary",
            actual=range_pct, required=LOW_VOLATILITY_RANGE_PCT,
            passed=range_pct >= LOW_VOLATILITY_RANGE_PCT,
            distance=range_pct - LOW_VOLATILITY_RANGE_PCT,
            rule=f"range_pct >= {LOW_VOLATILITY_RANGE_PCT}", fail_status="RISK_REJECTED",
            reason="low_volatility_blocked", source_function="assess_regime",
            source_file="automation/forex_engine/regime.py", inputs=("high", "low", "close"),
        ))
        gates.append(_gate(
            "G04_MAXIMUM_VOLATILITY", "Maximum normal-volatility boundary",
            actual=range_pct, required=HIGH_VOLATILITY_RANGE_PCT,
            passed=range_pct <= HIGH_VOLATILITY_RANGE_PCT,
            distance=HIGH_VOLATILITY_RANGE_PCT - range_pct,
            rule=f"range_pct <= {HIGH_VOLATILITY_RANGE_PCT}", fail_status="RISK_REJECTED",
            reason="high_volatility_blocked", source_function="assess_regime",
            source_file="automation/forex_engine/regime.py", inputs=("high", "low", "close"),
        ))
        metadata = regime_metadata(history)
        trend_pass = regime["trend"] == TRENDING_UP
        trend_fail_status = "NO_SIGNAL" if regime["trend"] == TRENDING_DOWN else "REGIME_REJECTED"
        trend_reason = "buy_rule_not_satisfied" if regime["trend"] == TRENDING_DOWN else "ranging_regime_blocked"
        gates.append(_gate(
            "G05_BUY_TREND_ALIGNMENT", "Three-candle long trend alignment",
            actual=metadata["close_change"], required=metadata["trend_threshold"],
            passed=trend_pass, distance=metadata["close_change"] - metadata["trend_threshold"],
            rule="close_change >= average_range * 0.5", fail_status=trend_fail_status,
            reason=trend_reason, source_function="assess_regime",
            source_file="automation/forex_engine/regime.py",
            inputs=("first_close", "last_close", "average_range"),
        ))

    generated = _stamp(_utc(str(candles[-1]["observed_at_utc"])) + M5_CANDLE_DURATION)
    decision = evaluate_buy_signal(history)
    signal: dict[str, Any] | None = None
    upstream_error: str | None = None
    try:
        signal = build_signal_state(history, generated_at_utc=generated)
    except ValueError as exc:
        upstream_error = str(exc)

    if decision["status"] == "BUY":
        recent = candles[-3:]
        entry = float(recent[-1]["close"])
        stop = min(float(item["low"]) for item in recent)
        risk = entry - stop
        gates.append(_gate(
            "G06_POSITIVE_STOP_DISTANCE", "Canonical long stop geometry",
            actual=risk, required=0.0, passed=math.isfinite(risk) and risk > 0,
            distance=risk, rule="entry_reference - stop_price > 0",
            fail_status="INVALID_MARKET_DATA", reason="invalid_stop_distance",
            source_function="derive_stop_target", inputs=("entry_reference", "minimum_recent_low"),
        ))
        if risk > 0:
            gates.append(_gate(
                "G07_MINIMUM_REWARD_TO_RISK", "Canonical target geometry",
                actual=MINIMUM_REWARD_TO_RISK, required=MINIMUM_REWARD_TO_RISK, passed=True,
                distance=0.0, rule=f"reward_to_risk == {MINIMUM_REWARD_TO_RISK}",
                fail_status="INVALID_MARKET_DATA", reason="invalid_reward_to_risk",
                source_function="derive_stop_target", inputs=("entry_reference", "stop_price", "target_price"),
            ))

    failed = [item for item in gates if item["gate_status"] == "FAIL"]
    first = failed[0] if failed else None
    production_status = signal["status"] if signal else ("INVALID_MARKET_DATA" if upstream_error else decision["status"])
    return {
        "decision_lineage_id": "p1-lineage-" + hashlib.sha256(
            f"{cycle}|{history['last_observed_at_utc']}|{production_status}".encode()
        ).hexdigest()[:24],
        "cycle": cycle,
        "utc": history["last_observed_at_utc"],
        "pair": INSTRUMENT,
        "timeframe": GRANULARITY,
        "market_data_valid": True,
        "production_signal": production_status,
        "production_decision": "PAPER_CANDIDATE_REQUIRES_PRICING" if production_status == "BUY" else "NO_PAPER_ENTRY",
        "first_failed_gate": first["gate_id"] if first else None,
        "all_failed_gates": [item["gate_id"] for item in failed],
        "rejection_reason": first["rejection_reason"] if first else None,
        "actual_value": first["actual_value"] if first else None,
        "required_value": first["required_value"] if first else None,
        "distance_to_pass": first["distance_to_pass"] if first else None,
        "distance_to_pass_pct": first["distance_to_pass_pct"] if first else None,
        "gates": gates,
        "blockers": decision.get("blockers", []),
        "regime": regime,
        "volatility": volatility,
        "signal_state": signal,
        "upstream_error": upstream_error,
        "historical_pricing_gate": "NOT_EVALUATED_HISTORICAL_ASK_UNAVAILABLE",
    }


def regime_metadata(history: Mapping[str, Any]) -> dict[str, float]:
    recent = history["candles"][-3:]
    ranges = [float(item["high"]) - float(item["low"]) for item in recent]
    closes = [float(item["close"]) for item in recent]
    average_range = sum(ranges) / len(ranges)
    average_close = sum(closes) / len(closes)
    return {
        "average_range": average_range,
        "average_close": average_close,
        "range_pct": average_range / average_close,
        "close_change": closes[-1] - closes[0],
        "trend_threshold": average_range * 0.5,
    }


def _geometry(history: Mapping[str, Any]) -> dict[str, float] | None:
    try:
        return derive_stop_target(history)
    except ValueError:
        return None


def _score(lineage: Mapping[str, Any], supertrend_state: Mapping[str, Any], geometry: Mapping[str, Any] | None) -> int:
    trend = lineage["regime"]["trend"]
    volatility = lineage["regime"]["volatility"]
    trend_points = 40 if trend == TRENDING_UP else (20 if trend == RANGING else 0)
    volatility_points = 30 if volatility == NORMAL_VOLATILITY else (15 if volatility == LOW_VOLATILITY else 0)
    supertrend_points = 20 if supertrend_state["supertrend_direction"] == "BULLISH" else 0
    geometry_points = 10 if geometry else 0
    return trend_points + volatility_points + supertrend_points + geometry_points


def _candidate(
    lineage: Mapping[str, Any],
    supertrend_state: Mapping[str, Any],
    geometry: Mapping[str, Any],
    *,
    source_group: str,
) -> dict[str, Any]:
    identity = {
        "utc": lineage["utc"], "status": lineage["production_signal"],
        "entry": geometry["entry_reference"], "stop": geometry["stop_price"],
        "target": geometry["target_price"], "source": source_group,
    }
    prefix = "production-control" if source_group == "PRODUCTION_ACCEPTED" else "shadow-reject"
    return {
        "shadow_candidate_id": prefix + "-" + hashlib.sha256(stable_json(identity).encode()).hexdigest()[:24],
        "cycle": lineage["cycle"],
        "pair": INSTRUMENT,
        "timeframe": GRANULARITY,
        "observed_utc": lineage["utc"],
        "direction": "BUY",
        "source_group": source_group,
        "strategy_name": STRATEGY_NAME,
        "production_signal": lineage["production_signal"],
        "production_decision": lineage["production_decision"],
        "production_status": lineage["production_signal"],
        "first_failed_gate": lineage["first_failed_gate"],
        "all_failed_gates": list(lineage["all_failed_gates"]),
        "rejection_reason": lineage["rejection_reason"],
        "actual_value": lineage["actual_value"],
        "required_value": lineage["required_value"],
        "distance_to_pass": lineage["distance_to_pass"],
        "distance_to_pass_pct": lineage["distance_to_pass_pct"],
        "supertrend_direction": supertrend_state["supertrend_direction"],
        "supertrend_flip": supertrend_state["supertrend_flip_this_cycle"],
        "shadow_opportunity_score": _score(lineage, supertrend_state, geometry),
        "hypothetical_entry": geometry["entry_reference"],
        "hypothetical_stop": geometry["stop_price"],
        "hypothetical_target": geometry["target_price"],
        "risk_r": 1.0,
        "paper_units": DEFAULT_PAPER_UNITS,
        "entry_basis": "canonical_signal_entry_reference; historical ask unavailable",
        "executed": False,
        "production_credit": 0,
        "production_pnl_effect": 0,
        **SAFETY,
    }


def classify_shadow_candidate(
    history: Mapping[str, Any],
    lineage: Mapping[str, Any],
    supertrend_state: Mapping[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    if lineage["production_signal"] == "BUY":
        return "NO_CANDIDATE", None
    if len(history["candles"]) < MINIMUM_CANDLES:
        return "INSUFFICIENT_INFORMATION", None
    premise = (
        lineage["regime"]["trend"] == TRENDING_UP
        or supertrend_state["supertrend_direction"] == "BULLISH"
    )
    if not premise:
        return "NO_CANDIDATE", None
    geometry = _geometry(history)
    if geometry is None:
        return "INSUFFICIENT_INFORMATION", None
    return "REJECTED_CANDIDATE", _candidate(
        lineage, supertrend_state, geometry, source_group="PRODUCTION_REJECTED_SHADOW"
    )


def _forward_path(
    candidate: Mapping[str, Any], future_candles: Sequence[Mapping[str, Any]], horizons: Sequence[int]
) -> dict[str, Any]:
    entry = float(candidate["hypothetical_entry"])
    output: dict[str, Any] = {}
    for horizon in horizons:
        if len(future_candles) < horizon:
            output[str(horizon)] = {"available": False, "directional_return": None, "mfe": None, "mae": None}
            continue
        window = future_candles[:horizon]
        output[str(horizon)] = {
            "available": True,
            "directional_return": round(float(window[-1]["close"]) - entry, 10),
            "mfe": round(max(float(item["high"]) for item in window) - entry, 10),
            "mae": round(entry - min(float(item["low"]) for item in window), 10),
        }
    return output


def resolve_counterfactual(
    candidate: Mapping[str, Any],
    future_candles: Sequence[Mapping[str, Any]],
    *,
    horizons: Sequence[int] = FORWARD_HORIZONS,
) -> dict[str, Any]:
    """Resolve stop/target ordering conservatively using future candles only."""
    required = ("hypothetical_entry", "hypothetical_stop", "hypothetical_target", "observed_utc")
    if any(candidate.get(key) is None for key in required):
        return {
            "result": "UNRESOLVED", "win_loss": None, "hypothetical_r": None,
            "hypothetical_pnl": None, "resolution_reason": "missing_canonical_rule_data",
            "forward_path": {},
        }
    try:
        entry = float(candidate["hypothetical_entry"])
        stop = float(candidate["hypothetical_stop"])
        target = float(candidate["hypothetical_target"])
        observed = _utc(str(candidate["observed_utc"]))
    except (TypeError, ValueError):
        return {
            "result": "UNRESOLVED", "win_loss": None, "hypothetical_r": None,
            "hypothetical_pnl": None, "resolution_reason": "invalid_canonical_rule_data",
            "forward_path": {},
        }
    risk = entry - stop
    if not (math.isfinite(risk) and risk > 0 and stop < entry < target):
        return {
            "result": "UNRESOLVED", "win_loss": None, "hypothetical_r": None,
            "hypothetical_pnl": None, "resolution_reason": "invalid_canonical_rule_geometry",
            "forward_path": _forward_path(candidate, future_candles, horizons),
        }

    maximum_high = entry
    minimum_low = entry
    time_to_mfe = None
    time_to_mae = None
    resolution: tuple[str, Mapping[str, Any], int] | None = None
    for number, candle in enumerate(future_candles, start=1):
        stamp = str(candle["observed_at_utc"])
        high, low = float(candle["high"]), float(candle["low"])
        if high > maximum_high:
            maximum_high, time_to_mfe = high, stamp
        if low < minimum_low:
            minimum_low, time_to_mae = low, stamp
        target_hit, stop_hit = high >= target, low <= stop
        if target_hit and stop_hit:
            resolution = ("AMBIGUOUS", candle, number)
            break
        if target_hit:
            resolution = ("WIN", candle, number)
            break
        if stop_hit:
            resolution = ("LOSS", candle, number)
            break

    mfe = maximum_high - entry
    mae = entry - minimum_low
    base = {
        "mfe_r": round(mfe / risk, 8),
        "mae_r": round(mae / risk, 8),
        "mfe_price": round(maximum_high, 10),
        "mae_price": round(minimum_low, 10),
        "time_to_mfe": time_to_mfe,
        "time_to_mae": time_to_mae,
        "target_touched": bool(resolution and resolution[0] in {"WIN", "AMBIGUOUS"}),
        "stop_touched": bool(resolution and resolution[0] in {"LOSS", "AMBIGUOUS"}),
        "forward_path": _forward_path(candidate, future_candles, horizons),
    }
    if resolution is None:
        return {
            **base, "result": "UNRESOLVED", "win_loss": None,
            "target_before_stop": None, "stop_before_target": None,
            "hypothetical_exit_reason": "forward_observations_exhausted",
            "hypothetical_r": None, "hypothetical_pnl": None,
            "resolution_time": None, "resolution_candles": None, "resolution_seconds": None,
        }
    result, candle, number = resolution
    stamp = str(candle["observed_at_utc"])
    seconds = (_utc(stamp) - observed).total_seconds()
    if result == "AMBIGUOUS":
        return {
            **base, "result": "AMBIGUOUS", "win_loss": None,
            "target_before_stop": False, "stop_before_target": False,
            "hypothetical_exit_reason": "target_and_stop_inside_same_candle_order_unknown",
            "hypothetical_r": None, "hypothetical_pnl": None,
            "resolution_time": stamp, "resolution_candles": number,
            "resolution_seconds": seconds,
        }
    won = result == "WIN"
    r_value = (target - entry) / risk if won else -1.0
    pnl = (target - entry) * int(candidate.get("paper_units", DEFAULT_PAPER_UNITS)) if won else -risk * int(candidate.get("paper_units", DEFAULT_PAPER_UNITS))
    return {
        **base, "result": result, "win_loss": result,
        "target_before_stop": won, "stop_before_target": not won,
        "hypothetical_exit_reason": "canonical_target" if won else "canonical_stop",
        "hypothetical_r": round(r_value, 8), "hypothetical_pnl": round(pnl, 8),
        "resolution_time": stamp, "resolution_candles": number,
        "resolution_seconds": seconds,
    }


def analyze_cycle(
    history: Mapping[str, Any],
    future_candles: Sequence[Mapping[str, Any]],
    *,
    cycle: int,
    atr_length: int = ATR_LENGTH,
    multiplier: float = MULTIPLIER,
) -> dict[str, Any]:
    validated = validate_audit_history(history)
    lineage = decision_lineage(validated, cycle=cycle)
    supertrend_state = evaluate_supertrend_shadow(validated, atr_length=atr_length, multiplier=multiplier)
    status, shadow = classify_shadow_candidate(validated, lineage, supertrend_state)
    production = None
    if lineage["production_signal"] == "BUY":
        geometry = _geometry(validated)
        if geometry:
            production = _candidate(lineage, supertrend_state, geometry, source_group="PRODUCTION_ACCEPTED")
            production["counterfactual"] = resolve_counterfactual(production, future_candles)
    if shadow:
        shadow["counterfactual"] = resolve_counterfactual(shadow, future_candles)

    direction = supertrend_state["supertrend_direction"]
    if direction == "INSUFFICIENT_DATA":
        disagreement = "SUPERTREND_INSUFFICIENT_DATA"
    else:
        suffix = "ACCEPTED" if lineage["production_signal"] == "BUY" else (
            "NONE" if lineage["production_signal"] in {"NO_SIGNAL", "REQUIRE_MORE_HISTORY"} else "REJECTED"
        )
        disagreement = f"SUPERTREND_{direction}_PRODUCTION_{suffix}"
    return {
        "cycle": cycle,
        "utc": lineage["utc"],
        "lineage": lineage,
        "supertrend": supertrend_state,
        "supertrend_disagreement": disagreement,
        "candidate_classification": status,
        "production_candidate": production,
        "shadow_candidate": shadow,
    }


def _wilson(wins: int, total: int) -> list[float] | None:
    if total <= 0:
        return None
    z = 1.959963984540054
    p = wins / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [round(max(0.0, center - spread), 8), round(min(1.0, center + spread), 8)]


def trade_metrics(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    resolved = [item for item in candidates if item.get("counterfactual", {}).get("result") in {"WIN", "LOSS"}]
    ambiguous = [item for item in candidates if item.get("counterfactual", {}).get("result") == "AMBIGUOUS"]
    unresolved = [item for item in candidates if item.get("counterfactual", {}).get("result") == "UNRESOLVED"]
    r_values = [float(item["counterfactual"]["hypothetical_r"]) for item in resolved]
    pnl_values = [float(item["counterfactual"]["hypothetical_pnl"]) for item in resolved]
    wins = sum(value > 0 for value in r_values)
    losses = sum(value < 0 for value in r_values)
    gross_profit = sum(value for value in r_values if value > 0)
    gross_loss = abs(sum(value for value in r_values if value < 0))
    profit_factor: float | str | None = None
    if gross_loss:
        profit_factor = round(gross_profit / gross_loss, 8)
    elif gross_profit:
        profit_factor = "INFINITE"
    equity = peak = max_drawdown = 0.0
    for value in r_values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    standard_error = None
    expectancy_ci = None
    if len(r_values) >= 2:
        standard_error = statistics.stdev(r_values) / math.sqrt(len(r_values))
        mean = statistics.fmean(r_values)
        expectancy_ci = [round(mean - 1.96 * standard_error, 8), round(mean + 1.96 * standard_error, 8)]
    mfe_values = [float(item["counterfactual"]["mfe_r"]) for item in candidates if item.get("counterfactual", {}).get("mfe_r") is not None]
    mae_values = [float(item["counterfactual"]["mae_r"]) for item in candidates if item.get("counterfactual", {}).get("mae_r") is not None]
    expectancy = _mean(r_values)
    return {
        "sample_size": len(candidates),
        "resolved": len(resolved),
        "unresolved": len(unresolved),
        "ambiguous": len(ambiguous),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(resolved), 8) if resolved else None,
        "win_rate_pct": round(wins / len(resolved) * 100, 8) if resolved else None,
        "win_rate_confidence_interval_95": _wilson(wins, len(resolved)),
        "expectancy_r": expectancy,
        "expectancy_uncertainty": {
            "standard_error_r": round(standard_error, 8) if standard_error is not None else None,
            "confidence_interval_95_r": expectancy_ci,
        },
        "profit_factor": profit_factor,
        "max_drawdown_r": round(max_drawdown, 8),
        "mean_mfe_r": _mean(mfe_values),
        "mean_mae_r": _mean(mae_values),
        "hypothetical_pnl": round(sum(pnl_values), 8),
        "risk_adjusted_performance": (
            round(float(expectancy) / max_drawdown, 8) if expectancy is not None and max_drawdown else None
        ),
    }


def portfolio_replay(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Chronological one-active-position replay with no outcome-based selection."""
    ordered = sorted(
        candidates,
        key=lambda item: (
            _utc(str(item["observed_utc"])),
            0 if item.get("source_group") == "PRODUCTION_ACCEPTED" else 1,
            str(item.get("shadow_candidate_id", "")),
        ),
    )
    selected: list[Mapping[str, Any]] = []
    skipped: list[str] = []
    active_until: datetime | None = None
    for candidate in ordered:
        observed = _utc(str(candidate["observed_utc"]))
        if active_until is not None and observed < active_until:
            skipped.append(str(candidate["shadow_candidate_id"]))
            continue
        selected.append(candidate)
        resolution_time = candidate.get("counterfactual", {}).get("resolution_time")
        active_until = _utc(str(resolution_time)) if resolution_time else datetime.max.replace(tzinfo=timezone.utc)
    resolved = [item for item in selected if item.get("counterfactual", {}).get("hypothetical_r") is not None]
    return {
        "one_active_position_respected": True,
        "risk_budget": "one canonical 1R candidate at a time",
        "input_candidates": len(candidates),
        "selected_candidates": len(selected),
        "skipped_overlapping_candidates": len(skipped),
        "selected_candidate_ids": [str(item["shadow_candidate_id"]) for item in selected],
        "skipped_candidate_ids": skipped,
        "resolved_selected": len(resolved),
        "total_r": round(sum(float(item["counterfactual"]["hypothetical_r"]) for item in resolved), 8),
        "hypothetical_pnl": round(sum(float(item["counterfactual"]["hypothetical_pnl"]) for item in resolved), 8),
    }


def _gate_performance(cycles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rejected = [item for item in cycles if item["lineage"]["production_signal"] != "BUY"]
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    sources: dict[str, dict[str, Any]] = {}
    for cycle in rejected:
        gate_id = cycle["lineage"]["first_failed_gate"] or "UPSTREAM_OR_UNMAPPED"
        counts[gate_id] += 1
        for gate in cycle["lineage"]["gates"]:
            if gate["gate_id"] == gate_id:
                sources[gate_id] = gate
                break
        if cycle["shadow_candidate"]:
            groups[gate_id].append(cycle["shadow_candidate"])
    output: dict[str, Any] = {}
    for gate_id in sorted(counts):
        metrics = trade_metrics(groups[gate_id])
        output[gate_id] = {
            "gate_id": gate_id,
            "gate_name": sources.get(gate_id, {}).get("gate_name"),
            "source_file": sources.get(gate_id, {}).get("source_file"),
            "source_function": sources.get(gate_id, {}).get("source_function"),
            "total_rejections": counts[gate_id],
            "resolved_rejections": metrics["resolved"],
            "shadow_wins": metrics["wins"],
            "shadow_losses": metrics["losses"],
            "shadow_expectancy_r": metrics["expectancy_r"],
            "shadow_profit_factor": metrics["profit_factor"],
            "shadow_max_drawdown_r": metrics["max_drawdown_r"],
            "mean_mfe_r": metrics["mean_mfe_r"],
            "mean_mae_r": metrics["mean_mae_r"],
            "false_rejection_candidates": metrics["wins"],
            "false_rejection_rate": round(metrics["wins"] / metrics["resolved"], 8) if metrics["resolved"] else None,
            "candidate_level_regret_r": round(sum(
                max(0.0, float(item["counterfactual"]["hypothetical_r"]))
                for item in groups[gate_id]
                if item.get("counterfactual", {}).get("hypothetical_r") is not None
            ), 8),
            "sample_size": metrics["sample_size"],
            "win_rate_confidence_interval_95": metrics["win_rate_confidence_interval_95"],
            "expectancy_uncertainty": metrics["expectancy_uncertainty"],
        }
    return output


def _near_threshold(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    buckets = {
        "0-5% below threshold": [], "5-10% below threshold": [],
        "10-20% below threshold": [], ">20% below threshold": [],
    }
    for candidate in candidates:
        distance = candidate.get("distance_to_pass_pct")
        if distance is None:
            continue
        value = float(distance)
        bucket = "0-5% below threshold" if value <= 5 else (
            "5-10% below threshold" if value <= 10 else (
                "10-20% below threshold" if value <= 20 else ">20% below threshold"
            )
        )
        buckets[bucket].append(candidate)
    result = {}
    for name, items in buckets.items():
        metrics = trade_metrics(items)
        result[name] = {
            "count": len(items), "resolved": metrics["resolved"], "win_rate": metrics["win_rate"],
            "expectancy_r": metrics["expectancy_r"], "profit_factor": metrics["profit_factor"],
            "max_drawdown_r": metrics["max_drawdown_r"], "mean_mfe_r": metrics["mean_mfe_r"],
            "mean_mae_r": metrics["mean_mae_r"],
            "profitable_rejections": metrics["wins"],
        }
    return result


def confidence_classification(sample_size: int) -> tuple[str, str]:
    if sample_size < 10:
        return "VERY_LOW", "resolved sample < 10"
    if sample_size < 30:
        return "LOW", "resolved sample 10-29"
    if sample_size < 100:
        return "MODERATE", "resolved sample 30-99"
    return "HIGH", "resolved sample >= 100"


def _actual_campaign_metrics(state: Mapping[str, Any] | None) -> dict[str, Any]:
    state = state or {}
    results = state.get("trade_results", []) if isinstance(state.get("trade_results", []), list) else []
    values = []
    for item in results:
        if isinstance(item, Mapping):
            raw = item.get("realized_paper_pl", item.get("realized_pl"))
            if isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(float(raw)):
                values.append(float(raw))
    return {
        "campaign_status": state.get("campaign_status", "NO_STATE"),
        "accepted_qualifying_trades": int(state.get("accepted_qualifying_trades", 0) or 0),
        "completed_trades": len(values),
        "wins": sum(value > 0 for value in values),
        "losses": sum(value < 0 for value in values),
        "paper_pnl": round(sum(values), 8),
        "expectancy": state.get("expectancy", 0.0),
        "profit_factor": state.get("profit_factor"),
        "maximum_drawdown": state.get("maximum_drawdown", 0.0),
        "active_position": state.get("active_position"),
        "source_label": "PRE_AUDIT_PRODUCTION_BASELINE_V2",
    }


def _summarize_cycles(
    cycles: Sequence[Mapping[str, Any]], campaign_state: Mapping[str, Any] | None
) -> dict[str, Any]:
    production_candidates = [item["production_candidate"] for item in cycles if item["production_candidate"]]
    shadow_candidates = [item["shadow_candidate"] for item in cycles if item["shadow_candidate"]]
    production_metrics = trade_metrics(production_candidates)
    shadow_metrics = trade_metrics(shadow_candidates)
    supertrend_aligned = [item for item in shadow_candidates if item["supertrend_direction"] == "BULLISH"]
    supertrend_metrics = trade_metrics(supertrend_aligned)
    gate_performance = _gate_performance(cycles)
    near_threshold = _near_threshold(shadow_candidates)
    most_common = max(gate_performance, key=lambda key: gate_performance[key]["total_rejections"], default=None)
    most_expensive = max(gate_performance, key=lambda key: gate_performance[key]["candidate_level_regret_r"], default=None)

    control_replay = portfolio_replay(production_candidates)
    alternative_replay = portfolio_replay([*production_candidates, *shadow_candidates])
    candidate_regret_r = round(sum(
        max(0.0, float(item["counterfactual"]["hypothetical_r"]))
        for item in shadow_candidates
        if item.get("counterfactual", {}).get("hypothetical_r") is not None
    ), 8)
    portfolio_regret_r = round(max(0.0, alternative_replay["total_r"] - control_replay["total_r"]), 8)
    profitable_production = production_metrics["wins"]
    profitable_shadow = shadow_metrics["wins"]
    opportunity_denominator = profitable_production + profitable_shadow
    opportunity_capture = round(profitable_production / opportunity_denominator, 8) if opportunity_denominator else None
    confidence, confidence_rule = confidence_classification(shadow_metrics["resolved"])

    # A negative rejected-candidate sample is useful preliminary evidence, but it
    # cannot establish filter quality without a moderate sample and a resolved
    # production-control comparison group.
    if shadow_metrics["resolved"] < 30 or production_metrics["resolved"] < 10:
        over_filtering = money_following = "INSUFFICIENT_EVIDENCE"
    elif (
        shadow_metrics["expectancy_r"] is not None
        and production_metrics["expectancy_r"] is not None
        and shadow_metrics["expectancy_r"] > production_metrics["expectancy_r"] + 0.25
    ):
        over_filtering = "LIKELY_OVER_FILTERING"
        money_following = "MONEY_FOLLOWING_DEFICIENCY"
    elif shadow_metrics["expectancy_r"] is not None and shadow_metrics["expectancy_r"] <= 0:
        over_filtering = money_following = "FILTERS_APPEAR_EFFECTIVE"
    else:
        over_filtering = money_following = "SOME_FILTERS_REQUIRE_REVIEW"

    root_causes = Counter(
        item["lineage"]["first_failed_gate"] or "NO_FAILED_GATE"
        for item in cycles if item["lineage"]["production_signal"] != "BUY"
    )
    disagreements = Counter(item["supertrend_disagreement"] for item in cycles)
    current = cycles[-1] if cycles else None
    scorecard = {
        "production_control": production_metrics,
        "production_rejected_shadow": shadow_metrics,
        "supertrend_aligned_shadow": supertrend_metrics,
        "opportunity_capture_rate": opportunity_capture,
        "candidate_level_regret_r": candidate_regret_r,
        "portfolio_feasible_regret_r": portfolio_regret_r,
        "false_rejection_rate": round(shadow_metrics["wins"] / shadow_metrics["resolved"], 8) if shadow_metrics["resolved"] else None,
        "most_common_rejection_gate": most_common,
        "most_expensive_rejection_gate": most_expensive,
        "over_filtering_status": over_filtering,
        "money_following_status": money_following,
        "sample_confidence": confidence,
    }
    return {
        "no_signal_root_causes": dict(sorted(root_causes.items())),
        "supertrend_disagreement_counts": dict(sorted(disagreements.items())),
        "production_control_candidates": len(production_candidates),
        "production_control_rejected_cycles": sum(item["lineage"]["production_signal"] != "BUY" for item in cycles),
        "shadow_candidates": len(shadow_candidates),
        "shadow_metrics": shadow_metrics,
        "production_control_metrics": production_metrics,
        "supertrend_aligned_candidates": len(supertrend_aligned),
        "supertrend_aligned_metrics": supertrend_metrics,
        "supertrend_aligned_accepted": sum(
            bool(item["production_candidate"] and item["supertrend"]["supertrend_direction"] == "BULLISH") for item in cycles
        ),
        "supertrend_aligned_rejected": len(supertrend_aligned),
        "supertrend_flip_candidates": sum(bool(item["shadow_candidate"] and item["supertrend"]["supertrend_flip_this_cycle"]) for item in cycles),
        "supertrend_flip_profitable_rejections": sum(
            bool(item["shadow_candidate"] and item["supertrend"]["supertrend_flip_this_cycle"] and item["shadow_candidate"]["counterfactual"]["result"] == "WIN")
            for item in cycles
        ),
        "gate_performance": gate_performance,
        "near_threshold_performance": near_threshold,
        "production_actual_campaign_evidence": _actual_campaign_metrics(campaign_state),
        "opportunity_capture_rate": opportunity_capture,
        "profitable_shadow_opportunities": profitable_shadow,
        "production_profitable_control_candidates": profitable_production,
        "missed_profitable_opportunities": profitable_shadow,
        "candidate_level_regret_r": candidate_regret_r,
        "portfolio_feasible_regret_r": portfolio_regret_r,
        "production_portfolio_replay": control_replay,
        "portfolio_feasible_alternative_replay": alternative_replay,
        "most_common_rejection_gate": most_common,
        "most_expensive_rejection_gate": most_expensive,
        "near_threshold_profitable_rejections": near_threshold["0-5% below threshold"]["profitable_rejections"],
        "over_filtering_status": over_filtering,
        "money_following_status": money_following,
        "sample_confidence": confidence,
        "sample_confidence_rule": confidence_rule,
        "current_observation": current,
        "scorecard": scorecard,
    }


def build_audit_state(
    history: Mapping[str, Any],
    *,
    campaign_state: Mapping[str, Any] | None = None,
    atr_length: int = ATR_LENGTH,
    multiplier: float = MULTIPLIER,
) -> dict[str, Any]:
    """Build a deterministic audit state from one genuine sanitized history."""
    validated_full = validate_audit_history(history)
    candles = validated_full["candles"]
    cycles = []
    for end in range(MINIMUM_CANDLES, len(candles) + 1):
        prefix = validate_audit_history(_prefix(validated_full, end))
        cycles.append(analyze_cycle(
            prefix, copy.deepcopy(candles[end:]), cycle=end,
            atr_length=atr_length, multiplier=multiplier,
        ))

    summary = _summarize_cycles(cycles, campaign_state)
    source_hash = hashlib.sha256(stable_json(validated_full).encode()).hexdigest()
    return {
        "version": VERSION,
        "identity_marker": IDENTITY_MARKER,
        "packet_id": PACKET_ID,
        "generated_from_latest_candle_utc": validated_full["last_observed_at_utc"],
        "source_history_sha256": source_hash,
        "source_provenance": validated_full["provenance"],
        "instrument": INSTRUMENT,
        "timeframe": GRANULARITY,
        "strategy_name": STRATEGY_NAME,
        "mode": "PAPER_ONLY",
        "paper_only": True,
        "configuration": {
            "production_rules": resolve_canonical_signal_rules(),
            "freshness_seconds": FRESHNESS_SECONDS,
            "low_volatility_range_pct": LOW_VOLATILITY_RANGE_PCT,
            "high_volatility_range_pct": HIGH_VOLATILITY_RANGE_PCT,
            "supertrend_atr_length": atr_length,
            "supertrend_multiplier": multiplier,
            "supertrend_strategy_name": STRATEGY_NAME,
            "forward_horizons_m5": list(FORWARD_HORIZONS),
            "confidence_rule": "VERY_LOW <10; LOW 10-29; MODERATE 30-99; HIGH >=100 resolved shadow candidates",
        },
        "decision_graph": production_decision_graph(),
        "cycles_analyzed": len(cycles),
        "cycle_records": cycles,
        "source_history_windows": [source_hash],
        **summary,
        "production_decision_changed": False,
        "production_threshold_changed": False,
        "production_supertrend_enabled": False,
        "shadow_isolation": "PASS",
        "supertrend_isolation": "PASS",
        **SAFETY,
    }


def merge_audit_states(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    *,
    campaign_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge rolling 50-candle windows without double-counting the same M5 UTC."""
    if not isinstance(previous, Mapping) or previous.get("version") != VERSION:
        return copy.deepcopy(dict(current))
    selected: dict[str, dict[str, Any]] = {}

    def quality(record: Mapping[str, Any]) -> tuple[int, int, int]:
        candidate = record.get("shadow_candidate") or record.get("production_candidate") or {}
        counterfactual = candidate.get("counterfactual", {}) if isinstance(candidate, Mapping) else {}
        result = counterfactual.get("result")
        resolved = 2 if result in {"WIN", "LOSS", "AMBIGUOUS"} else (1 if result == "UNRESOLVED" else 0)
        available = sum(
            bool(item.get("available")) for item in counterfactual.get("forward_path", {}).values()
            if isinstance(item, Mapping)
        ) if isinstance(counterfactual.get("forward_path", {}), Mapping) else 0
        context = int(record.get("supertrend", {}).get("candle_count", 0) or 0)
        return resolved, available, context

    for state in (previous, current):
        for raw in state.get("cycle_records", []):
            if not isinstance(raw, Mapping) or not isinstance(raw.get("utc"), str):
                continue
            record = copy.deepcopy(dict(raw))
            existing = selected.get(record["utc"])
            if existing is None or quality(record) >= quality(existing):
                selected[record["utc"]] = record
    cycles = sorted(selected.values(), key=lambda item: _utc(str(item["utc"])))
    for sequence, record in enumerate(cycles, start=1):
        record["audit_sequence"] = sequence
    previous_latest = str(previous.get("generated_from_latest_candle_utc", ""))
    current_latest = str(current.get("generated_from_latest_candle_utc", ""))
    base_state = previous if previous_latest > current_latest else current
    result = copy.deepcopy(dict(base_state))
    result["cycle_records"] = cycles
    result["cycles_analyzed"] = len(cycles)
    result["generated_from_latest_candle_utc"] = cycles[-1]["utc"] if cycles else current.get("generated_from_latest_candle_utc")
    windows = [
        *list(previous.get("source_history_windows", [previous.get("source_history_sha256")])),
        *list(current.get("source_history_windows", [current.get("source_history_sha256")])),
    ]
    result["source_history_windows"] = sorted({str(value) for value in windows if value})
    result["source_history_window_count"] = len(result["source_history_windows"])
    result.update(_summarize_cycles(cycles, campaign_state))
    return result


def shadow_audit_safety_state() -> dict[str, Any]:
    return {"version": VERSION, "identity_marker": IDENTITY_MARKER, **SAFETY}
