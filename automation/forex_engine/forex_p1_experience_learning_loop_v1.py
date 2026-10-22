"""Governed PAPER/shadow experience ledger and transparent learning summaries.

Analysis-only: it never edits production configuration, calls a broker, opens
positions, or credits shadow outcomes to canonical PAPER evidence.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA = "AIOS_FOREX_P1_EXPERIENCE_EVENT.v1"
LEDGER_FILENAME = "AIOS_FOREX_P1_EXPERIENCE_LEDGER.jsonl"
CSV_FILENAME = "AIOS_FOREX_P1_EXPERIENCE_LEDGER.csv"
SAFETY = {"paper_only": True, "shadow_not_executed": True, "production_mutation_allowed": False,
          "broker_write_performed": False, "practice_order_performed": False,
          "live_trade_performed": False, "money_movement_performed": False}
_SECRET_PARTS = ("token", "credential", "account", "password", "secret", "payload", "order", "transaction")


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def config_hash(config: Mapping[str, Any]) -> str:
    return hashlib.sha256(stable_json(dict(config)).encode()).hexdigest()


def dataset_hash(identity: Mapping[str, Any] | str) -> str:
    value = identity if isinstance(identity, str) else stable_json(dict(identity))
    return hashlib.sha256(value.encode()).hexdigest()


def _sanitize(value: Any, key: str = "") -> Any:
    if any(part in key.lower() for part in _SECRET_PARTS):
        return None
    if isinstance(value, Mapping):
        return {str(k): _sanitize(v, str(k)) for k, v in value.items()
                if not any(part in str(k).lower() for part in _SECRET_PARTS)}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def classify_experience(*, production_decision: str, outcome_r: float | None) -> str:
    if outcome_r is None:
        return "UNRESOLVED"
    if outcome_r == 0:
        return "BREAKEVEN"
    accepted = production_decision in {"ACCEPTED", "PAPER_ELIGIBLE", "PAPER_SESSION_OPEN"}
    return ("TRUE_POSITIVE" if outcome_r > 0 else "FALSE_POSITIVE") if accepted else ("FALSE_NEGATIVE" if outcome_r > 0 else "TRUE_NEGATIVE")


def build_experience_event(*, experience_id: str, event_type: str, strategy_name: str,
                           strategy_config: Mapping[str, Any], git_commit: str,
                           dataset_identity: Mapping[str, Any] | str, decision_utc: str,
                           production_decision: str, shadow_classification: str,
                           outcome_r: float | None = None, instrument: str = "EUR_USD",
                           timeframe: str = "M5", features: Mapping[str, Any] | None = None,
                           outcome: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if shadow_classification not in {"ACTUAL_PAPER", "SHADOW_COUNTERFACTUAL"}:
        raise ValueError("experience_source_invalid")
    return _sanitize({
        "schema": SCHEMA, "experience_id": str(experience_id), "event_type": event_type,
        "strategy_name": strategy_name, "strategy_config": dict(strategy_config),
        "strategy_config_hash": config_hash(strategy_config), "git_commit": git_commit,
        "dataset_hash": dataset_hash(dataset_identity), "instrument": instrument,
        "timeframe": timeframe, "decision_utc": decision_utc,
        "production_decision": production_decision, "shadow_classification": shadow_classification,
        "outcome_classification": classify_experience(production_decision=production_decision, outcome_r=outcome_r),
        "features": dict(features or {}), "outcome": dict(outcome or {}), "outcome_r": outcome_r,
        "safety": dict(SAFETY),
    })


def experience_from_shadow_candidate(candidate: Mapping[str, Any], *, strategy_config: Mapping[str, Any], git_commit: str,
                                     dataset_identity: Mapping[str, Any] | str, decision_utc: str) -> dict[str, Any]:
    """Adapt the existing shadow audit output without changing its accounting."""
    counterfactual = candidate.get("counterfactual") if isinstance(candidate.get("counterfactual"), Mapping) else {}
    return build_experience_event(
        experience_id=str(candidate.get("shadow_candidate_id", "shadow-unknown")), event_type="SHADOW_OUTCOME",
        strategy_name=str(candidate.get("strategy_name", "supertrend_pullback_v1")), strategy_config=strategy_config,
        git_commit=git_commit, dataset_identity=dataset_identity, decision_utc=decision_utc,
        production_decision="REJECTED", shadow_classification="SHADOW_COUNTERFACTUAL",
        outcome_r=counterfactual.get("hypothetical_r"), features={"first_failed_gate": candidate.get("first_failed_gate"), **dict(candidate.get("features") or {})},
        outcome=dict(counterfactual),
    )


def append_experience_event(path: Path, event: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(_sanitize(dict(event)), sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(line); stream.flush(); os.fsync(stream.fileno())


def read_experience_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or value.get("schema") != SCHEMA:
            raise ValueError(f"experience_ledger_line_invalid_{number}")
        records.append(value)
    return records


def export_csv(records: Iterable[Mapping[str, Any]], path: Path) -> None:
    rows = [{key: record.get(key) for key in ("experience_id", "decision_utc", "shadow_classification", "production_decision", "outcome_classification", "outcome_r", "strategy_config_hash", "dataset_hash")} for record in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["experience_id"])
        writer.writeheader(); writer.writerows(rows)


def filter_value_scorecard(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("shadow_classification") == "SHADOW_COUNTERFACTUAL":
            groups[str(record.get("features", {}).get("first_failed_gate") or "unattributed")].append(record)
    result = {}
    for gate, items in sorted(groups.items()):
        resolved = [item for item in items if item.get("outcome_r") is not None]
        wins = [item for item in resolved if float(item["outcome_r"]) > 0]
        losses = [item for item in resolved if float(item["outcome_r"]) < 0]
        result[gate] = {"total_rejections": len(items), "resolved": len(resolved), "would_win": len(wins), "would_lose": len(losses),
                        "ambiguous_or_unresolved": len(items) - len(resolved), "false_negative_rate": round(len(wins) / len(resolved), 8) if resolved else None,
                        "shadow_expectancy_r": round(sum(float(item["outcome_r"]) for item in resolved) / len(resolved), 8) if resolved else None,
                        "saved_loss_r": round(-sum(float(item["outcome_r"]) for item in losses), 8), "regret_r": round(sum(float(item["outcome_r"]) for item in wins), 8)}
    return result


def near_threshold_bucket(distance_percent: float | None) -> str:
    if distance_percent is None:
        return "NOT_EVALUATED"
    value = abs(float(distance_percent))
    return "0_5_PERCENT" if value <= 5 else "5_10_PERCENT" if value <= 10 else "10_20_PERCENT" if value <= 20 else "OVER_20_PERCENT"


def walk_forward_scorecard(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(records, key=lambda item: str(item.get("decision_utc", "")))
    first, second = int(len(ordered) * .6), int(len(ordered) * .8)
    result = {}
    for name, segment in (("TRAIN", ordered[:first]), ("VALIDATION", ordered[first:second]), ("TEST", ordered[second:])):
        values = [float(item["outcome_r"]) for item in segment if item.get("outcome_r") is not None]
        result[name] = {"count": len(segment), "resolved": len(values), "expectancy_r": round(sum(values) / len(values), 8) if values else None}
    return {"split": "chronological_60_20_20", "segments": result, "selection_uses_test": False}


def similarity_bucket(features: Mapping[str, Any]) -> str:
    return "|".join(str(features.get(key, "UNKNOWN")) for key in ("volatility_regime", "session_bucket", "supertrend_age_bucket", "spread_risk_bucket"))


def postmortem_learning_summary(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Keep actual PAPER and counterfactual metrics explicitly separate."""
    actual = [dict(r) for r in records if r.get("shadow_classification") == "ACTUAL_PAPER"]
    shadow = [dict(r) for r in records if r.get("shadow_classification") == "SHADOW_COUNTERFACTUAL"]
    return {"ACTUAL_PAPER": {"count": len(actual), "events": actual}, "COUNTERFACTUAL": {"count": len(shadow), "events": shadow}, "mixed_accounting": False}


ENTRY_EXPERIMENTS = {
    "minimum_atr": [0.00025, 0.00030, 0.00035, 0.00040, 0.00045, 0.00050],
    "minimum_body_ratio": [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60],
    "maximum_band_extension_atr": [1.5, 2.0, 2.5, 3.0],
    "minimum_reward_risk": [1.0, 1.25, 1.5, 1.75, 2.0],
    "supertrend_atr_period": [3, 5, 7, 10],
    "supertrend_multiplier": [1.5, 2.0, 2.5, 3.0],
}
EXIT_EXPERIMENTS = {
    "target_r": [1.5, 2.0, 2.5, 3.0],
    "break_even_r": [None, 0.5, 1.0],
    "exit_policy": ["CONTROL", "SUPERTREND_FLIP", "ATR_TRAIL", "SUPERTREND_BAND_TRAIL", "TIME_6", "TIME_12", "TIME_24"],
}


def event_from_cycle_record(record: Mapping[str, Any], *, git_commit: str, dataset_identity: Mapping[str, Any] | str) -> dict[str, Any]:
    """Convert one provenance record into one stable, deduplicatable experience."""
    cycle = str(record.get("cycle_number", "0"))
    action = str(record.get("cycle_action") or record.get("action") or "UNKNOWN")
    signal = str(record.get("signal_status") or "NO_SIGNAL")
    accepted = action in {"PAPER_SESSION_OPEN", "PAPER_SESSION_HELD", "PAPER_SESSION_CLOSE", "QUALIFYING_TRADE_RECORDED"}
    decision = "ACCEPTED" if accepted else ("WAIT" if action == "WAIT_FOR_DATA" else "REJECTED")
    outcome_r = record.get("realized_r", record.get("outcome_r"))
    if outcome_r is not None:
        outcome_r = float(outcome_r)
    identity = {"campaign": record.get("campaign_identity"), "cycle": cycle, "action": action, "event": record.get("paper_session_event")}
    experience_id = "cycle-" + hashlib.sha256(stable_json(identity).encode()).hexdigest()[:24]
    features = {key: record.get(key) for key in (
        "atr_actual", "minimum_atr", "candle_body_ratio", "minimum_candle_body_ratio", "supertrend_direction",
        "supertrend_value", "bars_in_current_direction", "flip_this_cycle", "recent_flip_count", "band",
        "band_extension", "extension_atr_ratio", "entry_reference", "bid", "ask", "spread", "stop",
        "target", "reward_risk_actual", "history_age_seconds", "snapshot_age_seconds", "active_position_status",
        "first_failed_gate", "all_failed_gates", "atr_distance_to_pass", "atr_distance_percent",
        "body_distance_to_pass", "price_distance_to_band", "spread_stop_distance_ratio", "buy_only_boundary")}
    features.update({key: record.get(key) for key in (
        "atr_percentile", "atr_slope", "atr_acceleration", "volatility_regime", "upper_wick_ratio", "lower_wick_ratio",
        "close_location", "h1_bullish", "h1_supertrend_direction", "h1_atr_period", "h1_supertrend_multiplier",
        "rsi", "rsi_period", "rsi_status", "pullback_depth", "pullback_depth_atr", "session_bucket", "utc_hour",
        "day_of_week", "spread_rolling_mean_24h", "spread_quality_status", "hypothetical_slippage",
        "risk_percent", "risk_budget", "daily_drawdown_percent", "news_blackout_status", "clock_integrity",
        "bar_identity", "candidate_idempotency_key")})
    return build_experience_event(
        experience_id=experience_id, event_type=action, strategy_name=str(record.get("strategy_name") or "supertrend_pullback_v1"),
        strategy_config=record.get("strategy_config") if isinstance(record.get("strategy_config"), Mapping) else {},
        git_commit=git_commit, dataset_identity=dataset_identity, decision_utc=str(record.get("cycle_completed_utc") or record.get("cycle_started_utc")),
        production_decision=decision, shadow_classification="ACTUAL_PAPER", outcome_r=outcome_r,
        features={"signal_status": signal, **features}, outcome={key: record.get(key) for key in (
            "entry_price", "exit_price", "exit_reason", "holding_duration_seconds", "realized_paper_pl", "mfe_price", "mfe_r", "mae_price", "mae_r", "time_to_mfe", "time_to_mae")})


def append_cycle_experience(telemetry_root: Path, record: Mapping[str, Any], *, git_commit: str, dataset_identity: Mapping[str, Any] | str) -> bool:
    """Append exactly once by stable experience_id; JSONL remains authoritative."""
    path = telemetry_root / LEDGER_FILENAME
    event = event_from_cycle_record(record, git_commit=git_commit, dataset_identity=dataset_identity)
    existing = {item.get("experience_id") for item in read_experience_ledger(path)}
    if event["experience_id"] in existing:
        return False
    append_experience_event(path, event)
    return True


def excursion_metrics(entry: float, stop: float, candles: Iterable[Mapping[str, Any]], *, entry_utc: str | None = None) -> dict[str, Any]:
    """Calculate deterministic MFE/MAE from completed-candle highs/lows."""
    risk = entry - stop
    if not risk > 0:
        return {"mfe_price": None, "mfe_r": None, "mae_price": None, "mae_r": None, "time_to_mfe": None, "time_to_mae": None}
    max_high, min_low, mfe_time, mae_time = entry, entry, None, None
    for candle in candles:
        if float(candle["high"]) > max_high:
            max_high, mfe_time = float(candle["high"]), candle.get("observed_at_utc")
        if float(candle["low"]) < min_low:
            min_low, mae_time = float(candle["low"]), candle.get("observed_at_utc")
    return {"mfe_price": round(max_high, 10), "mfe_r": round((max_high - entry) / risk, 8), "mae_price": round(min_low, 10),
            "mae_r": round((entry - min_low) / risk, 8), "time_to_mfe": mfe_time, "time_to_mae": mae_time}


def simulate_exit_policy(entry: float, stop: float, candles: Iterable[Mapping[str, Any]], *, target_r: float = 2.0,
                         policy: str = "CONTROL", max_bars: int | None = None) -> dict[str, Any]:
    """Simulate exits only on completed candles; same-candle stop/target is AMBIGUOUS."""
    values = list(candles)[:max_bars] if max_bars is not None else list(candles)
    risk = entry - stop
    if not risk > 0:
        return {"result": "UNRESOLVED", "reason": "invalid_risk"}
    target = entry + risk * target_r
    excursion = excursion_metrics(entry, stop, values)
    for index, candle in enumerate(values, start=1):
        high, low = float(candle["high"]), float(candle["low"])
        if policy.startswith("TIME_") and index >= int(policy.split("_")[1]):
            exit_price = float(candle["close"])
            return {**excursion, "result": "TIME_EXIT", "exit_price": exit_price, "exit_reason": policy, "holding_bars": index, "outcome_r": round((exit_price - entry) / risk, 8)}
        if high >= target and low <= stop:
            return {**excursion, "result": "AMBIGUOUS", "exit_price": None, "exit_reason": "same_candle_stop_target_order_unknown", "holding_bars": index, "outcome_r": None}
        if high >= target:
            return {**excursion, "result": "WIN", "exit_price": target, "exit_reason": "target", "holding_bars": index, "outcome_r": round(target_r, 8)}
        if low <= stop:
            return {**excursion, "result": "LOSS", "exit_price": stop, "exit_reason": "stop", "holding_bars": index, "outcome_r": -1.0}
    return {**excursion, "result": "UNRESOLVED", "exit_price": None, "exit_reason": "future_data_exhausted", "holding_bars": None, "outcome_r": None}


def run_entry_experiment_specs() -> dict[str, Any]:
    return {"control": {"minimum_atr": 0.0004, "minimum_body_ratio": 0.45, "maximum_band_extension_atr": 2.5, "minimum_reward_risk": 1.5, "supertrend_atr_period": 3, "supertrend_multiplier": 2.0}, "alternatives": ENTRY_EXPERIMENTS, "production_mutation_allowed": False}


def run_exit_experiment_specs() -> dict[str, Any]:
    return {"control": {"target_r": 2.0, "stop_policy": "CONTROL"}, "alternatives": EXIT_EXPERIMENTS, "production_mutation_allowed": False}


def build_regime_scorecard(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        features = record.get("features", {})
        groups[str(features.get("volatility_regime", "UNKNOWN"))].append(record)
    return {regime: {"count": len(items), "resolved": sum(item.get("outcome_r") is not None for item in items),
                     "expectancy_r": (round(sum(float(item["outcome_r"]) for item in items if item.get("outcome_r") is not None) / sum(item.get("outcome_r") is not None for item in items), 8)
                                      if any(item.get("outcome_r") is not None for item in items) else None)} for regime, items in sorted(groups.items())}


def build_learning_reports(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(records)
    return {"filter_value_scorecard": filter_value_scorecard(values), "near_threshold_analysis": {
        "atr": near_threshold_bucket(None), "body_ratio": near_threshold_bucket(None), "band_extension": near_threshold_bucket(None), "reward_risk": near_threshold_bucket(None)},
        "entry_experiment_scorecard": run_entry_experiment_specs(), "exit_experiment_scorecard": run_exit_experiment_specs(),
        "market_regime_scorecard": build_regime_scorecard(values), "walk_forward_scorecard": walk_forward_scorecard(values),
        "production_vs_shadow": postmortem_learning_summary(values), "safety": dict(SAFETY),
        "recommendations": ["No production mutation is authorized; collect sufficient resolved PAPER/shadow evidence before ranking."],
    }


def paper_campaign_readiness(*, qualifying_count: int, telemetry_writable: bool, ledger_writable: bool, monitor_available: bool,
                             postmortem_available: bool, safety: Mapping[str, Any] | None = None) -> dict[str, Any]:
    gates = {"qualifying_count_initialized": qualifying_count >= 0, "telemetry_writable": telemetry_writable, "experience_ledger_writable": ledger_writable,
             "monitor_available": monitor_available, "postmortem_available": postmortem_available, "paper_only": True,
             "broker_write": False, "practice_order": False, "live": False, "money_movement": False,
             "production_auto_mutation": False, "current_strategy_unchanged": True}
    if safety:
        gates.update({key: value is False for key, value in safety.items() if key in {"broker_write_performed", "practice_order_performed", "live_trade_performed", "money_movement_performed", "production_mutation_allowed"}})
    return {"status": "AIOS_FOREX_30_TO_50_PAPER_CAMPAIGN_READY" if all(gates.values()) else "BLOCKED", "minimum_target": 30, "extended_target": 50,
            "qualifying_count": qualifying_count, "gates": gates, "no_profitability_claim": True}


def is_completed_bar(bar: Mapping[str, Any], *, now_utc: str | None = None) -> bool:
    """Require an explicit completed-bar contract; never infer from a partial bar."""
    if "is_bar_closed" in bar:
        return bool(bar["is_bar_closed"])
    return bool(bar.get("completed", False))


def distinct_bar_decision(bar_identity: str, last_bar_identity: str | None) -> bool:
    """Return true only once for an immutable completed-bar identity."""
    return bool(bar_identity) and bar_identity != last_bar_identity


def rsi_confirmation(rsi: float | None, *, direction: str = "BUY", period: int = 14) -> dict[str, Any]:
    if rsi is None:
        return {"enabled": True, "period": period, "passed": None, "status": "NOT_EVALUATED", "rsi": None}
    passed = float(rsi) <= 70 if direction == "BUY" else float(rsi) >= 30
    return {"enabled": True, "period": period, "passed": passed, "status": "PASS" if passed else "FAIL", "rsi": float(rsi), "shadow_only": True}


def mtf_confirmation(*, m5_direction: str, h1_direction: str | None, enabled: bool = True) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "status": "DISABLED", "passed": True, "shadow_only": True}
    if h1_direction is None:
        return {"enabled": True, "status": "NOT_EVALUATED", "passed": None, "m5_direction": m5_direction, "h1_direction": None, "shadow_only": True}
    passed = m5_direction == "BUY" and h1_direction == "BUY"
    return {"enabled": True, "status": "PASS" if passed else "FAIL", "passed": passed, "m5_direction": m5_direction, "h1_direction": h1_direction, "shadow_only": True}


def post_exit_horizon_returns(exit_price: float, candles: Iterable[Mapping[str, Any]], horizons: Iterable[int] = (1, 3, 6, 12, 24)) -> dict[str, float | None]:
    values = list(candles)
    result: dict[str, float | None] = {}
    for horizon in horizons:
        index = int(horizon) - 1
        result[f"{int(horizon)}_bar_return"] = (round(float(values[index]["close"]) - exit_price, 10) if 0 <= index < len(values) else None)
    return result


def trade_quality_metrics(*, realized_r: float | None, mfe_r: float | None, mae_r: float | None, stop_distance: float | None) -> dict[str, float | None]:
    def ratio(numerator: float | None, denominator: float | None) -> float | None:
        return round(float(numerator) / float(denominator), 8) if numerator is not None and denominator not in (None, 0) else None
    return {"entry_efficiency_mfe_to_mae": ratio(mfe_r, mae_r), "exit_efficiency_realized_to_mfe": ratio(realized_r, mfe_r),
            "stop_efficiency_mae_to_stop_distance": ratio(mae_r, stop_distance), "profit_capture": ratio(realized_r, mfe_r)}


def run_entry_experiments(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Evaluate only supplied labeled records; controls and alternatives never mutate production."""
    values = list(records)
    results: dict[str, Any] = {"production_mutation_allowed": False, "control": {}, "alternatives": {}}
    for name, options in ENTRY_EXPERIMENTS.items():
        results["alternatives"][name] = [{"value": value, "sample": len(values), "resolved": sum(r.get("outcome_r") is not None for r in values),
                                          "expectancy_r": (round(sum(float(r["outcome_r"]) for r in values if r.get("outcome_r") is not None) /
                                                           sum(r.get("outcome_r") is not None for r in values), 8)
                                                           if any(r.get("outcome_r") is not None for r in values) else None),
                                          "shadow_only": True} for value in options]
    return results


def run_exit_experiments(records: Iterable[Mapping[str, Any]], candles_by_experience: Mapping[str, Iterable[Mapping[str, Any]]] | None = None) -> dict[str, Any]:
    """Run deterministic exit alternatives against explicitly supplied future candles."""
    values = list(records)
    future = candles_by_experience or {}
    results: dict[str, Any] = {"production_mutation_allowed": False, "alternatives": {}}
    for policy in EXIT_EXPERIMENTS["exit_policy"]:
        outcomes = []
        for record in values:
            candles = future.get(str(record.get("experience_id")), [])
            if record.get("entry_price") is None or record.get("stop") is None:
                continue
            outcome = simulate_exit_policy(float(record["entry_price"]), float(record["stop"]), candles, target_r=2.0, policy=policy)
            outcomes.append(outcome)
        resolved = [item["outcome_r"] for item in outcomes if item.get("outcome_r") is not None]
        results["alternatives"][policy] = {"sample": len(outcomes), "resolved": len(resolved),
                                            "expectancy_r": round(sum(resolved) / len(resolved), 8) if resolved else None,
                                            "shadow_only": True}
    return results


def write_learning_reports(records: Iterable[Mapping[str, Any]], output_root: Path, *, readiness: Mapping[str, Any] | None = None) -> dict[str, Path]:
    """Write derived reports beside runtime evidence; the JSONL ledger remains canonical."""
    values = list(records)
    output_root.mkdir(parents=True, exist_ok=True)
    ledger = output_root / LEDGER_FILENAME
    if not ledger.exists():
        for value in values:
            append_experience_event(ledger, value)
    export_csv(values, output_root / CSV_FILENAME)
    reports = build_learning_reports(values)
    reports["entry_experiment_scorecard"] = run_entry_experiments(values)
    reports["exit_experiment_scorecard"] = run_exit_experiments(values)
    reports["similar_experience_scorecard"] = {similarity_bucket(item.get("features", {})): 0 for item in values}
    reports["readiness"] = dict(readiness or {})
    paths: dict[str, Path] = {"ledger": ledger, "csv": output_root / CSV_FILENAME}
    json_reports = {"AIOS_FOREX_FILTER_VALUE_SCORECARD.json": reports["filter_value_scorecard"],
                    "AIOS_FOREX_NEAR_THRESHOLD_ANALYSIS.json": reports["near_threshold_analysis"],
                    "AIOS_FOREX_ENTRY_EXPERIMENT_SCORECARD.json": reports["entry_experiment_scorecard"],
                    "AIOS_FOREX_EXIT_EXPERIMENT_SCORECARD.json": reports["exit_experiment_scorecard"],
                    "AIOS_FOREX_MARKET_REGIME_SCORECARD.json": reports["market_regime_scorecard"],
                    "AIOS_FOREX_SIMILAR_EXPERIENCE_SCORECARD.json": reports["similar_experience_scorecard"],
                    "AIOS_FOREX_WALK_FORWARD_SCORECARD.json": reports["walk_forward_scorecard"]}
    for filename, value in json_reports.items():
        path = output_root / filename
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths[filename] = path
    markdown = {
        "AIOS_FOREX_FILTER_VALUE_SCORECARD.md": "# Filter value scorecard\n\nShadow-only; no production mutation.\n",
        "AIOS_FOREX_PRODUCTION_VS_SHADOW_REPORT.md": "# Production versus shadow\n\nActual PAPER and counterfactual accounting remain separate.\n",
        "AIOS_FOREX_POSTMORTEM_LEARNING_REPORT.md": "# Post-Mortem learning\n\nDerived from the experience ledger; no profitability claim.\n",
        "AIOS_FOREX_LEARNING_RECOMMENDATIONS.md": "# Learning recommendations\n\nCollect sufficient resolved out-of-sample evidence before changing production.\n",
        "AIOS_FOREX_PAPER_CAMPAIGN_READINESS_REPORT.md": "# PAPER campaign readiness\n\n" + json.dumps(dict(readiness or {}), sort_keys=True) + "\n",
    }
    for filename, content in markdown.items():
        path = output_root / filename; path.write_text(content, encoding="utf-8"); paths[filename] = path
    return paths
