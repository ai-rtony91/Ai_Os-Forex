"""Zero-credit R:R calibration for the normalized multi-pair Supertrend lane."""

from __future__ import annotations

import json
import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from automation.forex_engine.forex_p1_multipair_normalization_v1 import MIN_RR
from automation.forex_engine.strategies import classify_r_multiple, realized_r_multiple

VERSION = "forex_rr_calibration_v1"
SCHEMA = "AIOS_FOREX_RR_CALIBRATION_V1"
REPORT_ROOT = Path("Reports/forex_delivery")
TARGETS = (2.0, 2.5, 3.0, 4.0)
DEFAULT_REPLAY_CACHE = Path(".aios/runtime/forex_multipair_m5_replay_mba_v1/replay_cache.json")


@dataclass(frozen=True)
class CalibrationSplit:
    calibration: list[dict[str, Any]]
    validation: list[dict[str, Any]]


def _stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _finite(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_{name}") from exc
    if not math.isfinite(number):
        raise ValueError(f"invalid_{name}")
    return number


def _utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _load_replay_cache(replay_cache_path: Path = DEFAULT_REPLAY_CACHE) -> dict[str, Any]:
    payload = json.loads(replay_cache_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("pair_histories"), dict):
        raise ValueError("invalid_replay_cache")
    return payload


def _simulate_targeted_exit_from_history(
    *,
    candles: Sequence[Mapping[str, Any]],
    entry_index: int,
    direction: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
) -> dict[str, Any] | None:
    for index in range(entry_index + 1, len(candles)):
        candle = candles[index]
        high = _finite(candle.get("high"), "high")
        low = _finite(candle.get("low"), "low")
        if direction == "BUY":
            if low <= stop_price:
                return {"exit_index": index, "exit_price": stop_price, "exit_reason": "paper_stop"}
            if high >= target_price:
                return {"exit_index": index, "exit_price": target_price, "exit_reason": "paper_target"}
        else:
            if high >= stop_price:
                return {"exit_index": index, "exit_price": stop_price, "exit_reason": "paper_stop"}
            if low <= target_price:
                return {"exit_index": index, "exit_price": target_price, "exit_reason": "paper_target"}
    return None


def _outcome_for_target(
    trade: Mapping[str, Any],
    *,
    target_rr: float,
    replay_cache: Mapping[str, Any],
) -> dict[str, Any]:
    instrument = str(trade["instrument"])
    history = replay_cache["pair_histories"][instrument]
    candles = history["candles"]
    entry_time = str(trade["entry_timestamp_utc"])
    entry_index = next(
        index for index, candle in enumerate(candles)
        if str(candle.get("observed_at_utc", candle.get("timestamp"))) == entry_time
    )
    display_precision = int(trade.get("display_precision", 5))
    entry = _finite(trade.get("actual_paper_entry", trade.get("entry_price")), "entry_price")
    stop = _finite(trade["stop_price"], "stop_price")
    risk_distance = entry - stop
    if risk_distance <= 0:
        raise ValueError("invalid_actual_entry_geometry")
    target = round(entry + (risk_distance * target_rr), display_precision)
    if not stop < entry < target:
        raise ValueError("invalid_actual_entry_geometry")
    exit_record = _simulate_targeted_exit_from_history(
        candles=candles,
        entry_index=entry_index,
        direction=str(trade.get("direction", "BUY")).upper(),
        entry_price=entry,
        stop_price=stop,
        target_price=target,
    )
    if exit_record is None:
        censored = {
            "terminal_state": "CENSORED_OPEN_AT_END_OF_HISTORY",
            "censored": True,
            "target_price": target,
            "nominal_target_rr": round(target_rr, 8),
            "effective_reward_risk": round((target - entry) / risk_distance, 8),
            "risk_amount_quote": round(risk_distance * float(trade.get("units", 100)), 8),
            "TARGET_GEOMETRY_HASH": None,
            "EXIT_OUTCOME_HASH": None,
            "REALIZED_R": None,
        }
        return censored
    realized_pl_quote = (
        (exit_record["exit_price"] - entry) * float(trade.get("units", 100))
        if str(trade.get("direction", "BUY")).upper() == "BUY"
        else (entry - exit_record["exit_price"]) * float(trade.get("units", 100))
    )
    risk_amount_quote = risk_distance * float(trade.get("units", 100))
    realized_r = realized_r_multiple(realized_pl_quote, risk_amount_quote)
    geometry = {
        "entry": round(entry, display_precision),
        "stop": round(stop, display_precision),
        "target": round(target, display_precision),
        "target_rr": round(target_rr, 8),
    }
    exit_summary = {
        "exit_index": exit_record["exit_index"],
        "exit_price": round(exit_record["exit_price"], display_precision),
        "exit_reason": exit_record["exit_reason"],
    }
    realized_r_value = round(realized_r, 8) if realized_r is not None else None
    outcome = {
        "terminal_state": "CLOSED_TRADE",
        **exit_summary,
        "realized_pl_quote_currency": round(realized_pl_quote, 8),
        "risk_amount_quote": round(risk_amount_quote, 8),
        "realized_r": realized_r_value,
        "effective_reward_risk": round((target - entry) / risk_distance, 8),
        "geometry": geometry,
        "TARGET_GEOMETRY_HASH": hashlib.sha256(_stable_json({
            "domain": "TARGET_GEOMETRY",
            "target_rr": round(target_rr, 8),
            "geometry": geometry,
            "entry_index": exit_record["exit_index"],
        }).encode("utf-8")).hexdigest(),
        "EXIT_OUTCOME_HASH": hashlib.sha256(_stable_json({
            "domain": "EXIT_OUTCOMES",
            "target_rr": round(target_rr, 8),
            "exit_index": exit_summary["exit_index"],
            "exit_reason": exit_summary["exit_reason"],
            "exit_price": exit_summary["exit_price"],
            "realized_r": realized_r_value,
        }).encode("utf-8")).hexdigest(),
        "REALIZED_R": realized_r_value,
    }
    return outcome


def calibrate_actual_entry_geometry(
    *,
    signal_reference_entry: float,
    actual_paper_entry: float,
    stop_price: float,
    units: float,
    target_rr: float,
    display_precision: int,
) -> dict[str, Any]:
    if display_precision < 0:
        raise ValueError("invalid_display_precision")
    entry = round(_finite(actual_paper_entry, "actual_paper_entry"), display_precision)
    stop = round(_finite(stop_price, "stop_price"), display_precision)
    planned_rr = _finite(target_rr, "target_rr")
    if planned_rr <= 0:
        raise ValueError("invalid_target_rr")
    if not stop < entry:
        raise ValueError("invalid_actual_entry_geometry")
    risk_distance = entry - stop
    if risk_distance <= 0:
        raise ValueError("invalid_actual_entry_geometry")
    target = round(entry + (risk_distance * planned_rr), display_precision)
    if not target > entry:
        raise ValueError("invalid_actual_entry_geometry")
    effective_rr = (target - entry) / risk_distance
    if effective_rr + 1e-12 < MIN_RR:
        raise ValueError("rr_below_minimum_after_rounding")
    return {
        "signal_reference_entry": round(_finite(signal_reference_entry, "signal_reference_entry"), display_precision),
        "actual_paper_entry": entry,
        "stop_price": stop,
        "target_price": target,
        "risk_distance": round(risk_distance, display_precision + 4),
        "risk_amount": round(risk_distance * _finite(units, "units"), 8),
        "nominal_reward_risk": round(planned_rr, 8),
        "effective_reward_risk": round(effective_rr, 8),
        "spread_to_risk": round(max(0.0, entry - _finite(signal_reference_entry, "signal_reference_entry")) / risk_distance, 8),
    }


def _realized_r_from_pl_and_risk(realized_pl_quote: float, risk_amount_quote: float) -> float:
    if risk_amount_quote <= 0:
        raise ValueError("invalid_risk_amount_quote")
    return round(realized_pl_quote / risk_amount_quote, 8)


def _candidate_state_bucket(item: Mapping[str, Any]) -> str:
    terminal_state = str(item.get("terminal_state") or "").strip()
    if terminal_state:
        return terminal_state
    if item.get("realized_r") is None:
        return "UNKNOWN_TERMINAL_STATE"
    return "CLOSED_TRADE"


def trade_result_classification(realized_r: float | None) -> str:
    if realized_r is None:
        return "INVALID_R"
    if realized_r < 0:
        return "LOSS_R"
    if realized_r == 0:
        return "FLAT_R"
    if realized_r < 1:
        return "POSITIVE_LT_1R"
    if realized_r < 2:
        return "R_1_TO_LT_2"
    if realized_r < 2.5:
        return "R_2_TO_LT_2_5"
    if realized_r < 3:
        return "R_2_5_TO_LT_3"
    if realized_r < 4:
        return "R_3_TO_LT_4"
    return "R_4_PLUS"


def split_calibration_validation(records: Sequence[Mapping[str, Any]], *, calibration_fraction: float = 0.7) -> CalibrationSplit:
    ordered = sorted((dict(item) for item in records), key=lambda item: item["entry_timestamp_utc"])
    if not ordered:
        return CalibrationSplit([], [])
    split_index = max(1, min(len(ordered) - 1, int(len(ordered) * calibration_fraction)))
    return CalibrationSplit(ordered[:split_index], ordered[split_index:])


def _trade_stats(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    realized = [float(item["realized_r"]) for item in trades]
    if not realized:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "flats": 0,
            "win_rate": 0.0,
            "average_realized_r": 0.0,
            "expectancy_r": 0.0,
            "net_r": 0.0,
            "gross_winning_r": 0.0,
            "gross_losing_r": 0.0,
            "profit_factor": None,
            "maximum_drawdown_r": 0.0,
            "maximum_consecutive_losses": 0,
            "target_hit_rate": 0.0,
            "stop_hit_rate": 0.0,
            "average_holding_duration_seconds": None,
            "median_holding_duration_seconds": None,
            "average_mfe_r": None,
            "average_mae_r": None,
            "reach_rates": {},
            "by_instrument": {},
        }
    wins = [value for value in realized if value > 0]
    losses = [value for value in realized if value < 0]
    equity = peak = drawdown = 0.0
    streak = max_streak = 0
    for value in realized:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        streak = streak + 1 if value < 0 else 0
        max_streak = max(max_streak, streak)
    durations = [float(item["holding_duration_seconds"]) for item in trades if item.get("holding_duration_seconds") is not None]
    mfe = [float(item["mfe_r"]) for item in trades if item.get("mfe_r") is not None]
    mae = [float(item["mae_r"]) for item in trades if item.get("mae_r") is not None]
    reach_rates = {}
    for threshold in (1.0, 2.0, 2.5, 3.0, 4.0):
        key = f"pct_reached_{threshold:g}r"
        reach_rates[key] = round(sum(1 for item in trades if float(item.get("max_favorable_r", 0.0)) >= threshold) / len(trades), 8)
    by_instrument: dict[str, list[float]] = {}
    for item in trades:
        instrument = str(item.get("instrument", "UNKNOWN"))
        by_instrument.setdefault(instrument, []).append(float(item["realized_r"]))
    return {
        "total_trades": len(realized),
        "wins": len(wins),
        "losses": len(losses),
        "flats": sum(1 for value in realized if value == 0),
        "win_rate": round(len(wins) / len(realized), 8),
        "average_realized_r": round(sum(realized) / len(realized), 8),
        "expectancy_r": round(sum(realized) / len(realized), 8),
        "net_r": round(sum(realized), 8),
        "gross_winning_r": round(sum(wins), 8),
        "gross_losing_r": round(abs(sum(losses)), 8),
        "profit_factor": round(sum(wins) / abs(sum(losses)), 8) if losses else (999.0 if wins else None),
        "maximum_drawdown_r": round(drawdown, 8),
        "maximum_consecutive_losses": max_streak,
        "target_hit_rate": round(sum(1 for item in trades if item.get("exit_reason") == "paper_target") / len(trades), 8),
        "stop_hit_rate": round(sum(1 for item in trades if item.get("exit_reason") == "paper_stop") / len(trades), 8),
        "average_holding_duration_seconds": round(sum(durations) / len(durations), 8) if durations else None,
        "median_holding_duration_seconds": round(median(durations), 8) if durations else None,
        "average_mfe_r": round(sum(mfe) / len(mfe), 8) if mfe else None,
        "average_mae_r": round(sum(mae) / len(mae), 8) if mae else None,
        "reach_rates": reach_rates,
        "by_instrument": {
            instrument: {
                "trade_count": len(values),
                "win_rate": round(sum(v > 0 for v in values) / len(values), 8),
                "expectancy_r": round(sum(values) / len(values), 8),
            }
            for instrument, values in by_instrument.items()
        },
    }


def trade_series_from_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    for item in records:
        trade = dict(item)
        realized_r = trade.get("realized_r")
        if realized_r is None and {"realized_pl_quote_currency", "risk_amount_quote"}.issubset(trade):
            realized_r = _realized_r_from_pl_and_risk(
                _finite(trade.get("realized_pl_quote_currency"), "realized_pl_quote_currency"),
                _finite(trade.get("risk_amount_quote"), "risk_amount_quote"),
            )
        trade["realized_r"] = realized_r
        trade["result_class"] = trade_result_classification(realized_r)
        series.append(trade)
    return series


def _geometry_signature(record: Mapping[str, Any], target_rr: float) -> tuple[Any, ...]:
    precision = int(record.get("display_precision", 5))
    entry = _finite(record.get("actual_paper_entry", record.get("entry_price")), "entry")
    stop = _finite(record.get("stop_price"), "stop")
    risk_distance = entry - stop
    if risk_distance <= 0:
        raise ValueError("invalid_actual_entry_geometry")
    target = round(entry + (risk_distance * target_rr), precision)
    if not stop < entry < target:
        raise ValueError("invalid_actual_entry_geometry")
    effective = (target - entry) / risk_distance
    return (
        round(entry, precision),
        round(stop, precision),
        round(target, precision),
        round(target_rr, 8),
        round(effective, 8),
    )


def evaluate_rr_configuration(
    records: Sequence[Mapping[str, Any]],
    *,
    target_rr: float,
    calibration_fraction: float = 0.7,
    replay_cache_path: Path | None = None,
) -> dict[str, Any]:
    split = split_calibration_validation(records, calibration_fraction=calibration_fraction)
    replay_cache = _load_replay_cache(replay_cache_path) if replay_cache_path is not None else None
    if replay_cache is None:
        calibration = trade_series_from_records(split.calibration)
        validation = trade_series_from_records(split.validation)
        for item in calibration + validation:
            item["nominal_target_rr"] = target_rr
            item["effective_target_rr"] = target_rr
            if item.get("stop_price") is not None and item.get("actual_paper_entry") is not None:
                item["geometry_signature"] = _geometry_signature(item, target_rr)
            item["result_class"] = trade_result_classification(item.get("realized_r"))
    else:
        calibration = []
        for item in split.calibration:
            outcome = _outcome_for_target(item, target_rr=target_rr, replay_cache=replay_cache)
            if not outcome.get("censored"):
                trade = dict(item) | outcome
                trade["nominal_target_rr"] = target_rr
                trade["effective_target_rr"] = outcome["effective_reward_risk"]
                trade["result_class"] = trade_result_classification(trade.get("realized_r"))
                trade["geometry_signature"] = _geometry_signature(trade, target_rr)
                calibration.append(trade)
        validation = []
        for item in split.validation:
            outcome = _outcome_for_target(item, target_rr=target_rr, replay_cache=replay_cache)
            if not outcome.get("censored"):
                trade = dict(item) | outcome
                trade["nominal_target_rr"] = target_rr
                trade["effective_target_rr"] = outcome["effective_reward_risk"]
                trade["result_class"] = trade_result_classification(trade.get("realized_r"))
                trade["geometry_signature"] = _geometry_signature(trade, target_rr)
                validation.append(trade)
    calibration_candidates = len(split.calibration)
    validation_candidates = len(split.validation)
    calibration_start = split.calibration[0]["entry_timestamp_utc"] if split.calibration else None
    calibration_end = split.calibration[-1]["entry_timestamp_utc"] if split.calibration else None
    validation_start = split.validation[0]["entry_timestamp_utc"] if split.validation else None
    validation_end = split.validation[-1]["entry_timestamp_utc"] if split.validation else None
    calibration_stats = _trade_stats(calibration)
    validation_stats = _trade_stats(validation)
    sufficient = len(validation) >= 30 and len(calibration) >= 30 and validation_stats["total_trades"] >= 30
    evidence_integrity = bool(calibration) and bool(validation)
    normalization_integrity = all(
        item.get("geometry_signature") is None or len(item["geometry_signature"]) == 5
        for item in calibration + validation
    )
    rr_accounting_integrity = True
    for item in calibration + validation:
        realized_r = item.get("realized_r")
        if realized_r is None:
            continue
        if {"realized_pl_quote_currency", "risk_amount_quote"}.issubset(item):
            recomputed = _realized_r_from_pl_and_risk(
                _finite(item["realized_pl_quote_currency"], "realized_pl_quote_currency"),
                _finite(item["risk_amount_quote"], "risk_amount_quote"),
            )
            if recomputed is None or abs(recomputed - float(realized_r)) > 1e-9:
                rr_accounting_integrity = False
                break
    candidate_state_count_conservation = True
    state_counts = {
        "invalid_geometry_count": 0,
        "closed_trade_count": 0,
        "censored_trade_count": 0,
        "other_terminal_state_count": 0,
    }
    for item in split.calibration + split.validation:
        bucket = _candidate_state_bucket(item)
        if bucket == "INVALID_ENTRY_GEOMETRY":
            state_counts["invalid_geometry_count"] += 1
        elif bucket == "CLOSED_TRADE":
            state_counts["closed_trade_count"] += 1
        elif bucket == "CENSORED_OPEN_AT_END_OF_HISTORY":
            state_counts["censored_trade_count"] += 1
        else:
            state_counts["other_terminal_state_count"] += 1
    candidate_total = len(split.calibration) + len(split.validation)
    candidate_state_count_conservation = candidate_total == sum(state_counts.values())
    geometry_hash_payload = {
        "domain": "TARGET_GEOMETRY",
        "target_rr": target_rr,
        "calibration_geometry": [item.get("geometry_signature") for item in calibration],
        "validation_geometry": [item.get("geometry_signature") for item in validation],
    }
    exit_hash_payload = {
        "domain": "EXIT_OUTCOMES",
        "target_rr": target_rr,
        "exit_records": [
            {
                "exit_index": item.get("exit_index"),
                "exit_reason": item.get("exit_reason"),
                "exit_price": item.get("exit_price"),
                "terminal_state": _candidate_state_bucket(item),
            }
            for item in calibration + validation
        ],
    }
    realized_r_series_payload = {
        "domain": "REALIZED_R_SERIES",
        "target_rr": target_rr,
        "realized_r": [item.get("realized_r") for item in calibration + validation if item.get("realized_r") is not None],
    }
    promotion_status = (
        "RESEARCH_WINNER"
        if sufficient
        and evidence_integrity
        and normalization_integrity
        and rr_accounting_integrity
        and candidate_state_count_conservation
        and validation_stats["expectancy_r"] > 0
        and (validation_stats["profit_factor"] or 0) >= 1.10
        and validation_stats["maximum_drawdown_r"] <= 10.0
        else ("INSUFFICIENT_SAMPLE" if not sufficient else "OWNER_REVIEW_REQUIRED")
    )
    if not sufficient:
        sample_label = "INSUFFICIENT_SAMPLE"
    else:
        sample_label = "SAMPLE_SUFFICIENT"
    return {
        "target_rr": target_rr,
        "calibration_trades": len(calibration),
        "validation_trades": len(validation),
        "calibration_candidates": calibration_candidates,
        "validation_candidates": validation_candidates,
        "total_candidates_pre_split": candidate_total,
        "calibration_split_start_timestamp": calibration_start,
        "calibration_split_end_timestamp": calibration_end,
        "validation_split_start_timestamp": validation_start,
        "validation_split_end_timestamp": validation_end,
        "calibration_censored_trades": len(split.calibration) - len(calibration),
        "validation_censored_trades": len(split.validation) - len(validation),
        "calibration": calibration_stats,
        "validation": validation_stats,
        "sample_label": sample_label,
        "promotion_status": promotion_status,
        "sample_count_sufficient": len(validation) >= 30,
        "accounting_integrity": rr_accounting_integrity,
        "normalization_integrity": normalization_integrity,
        "evidence_integrity": evidence_integrity,
        "candidate_state_count_conservation": candidate_state_count_conservation,
        "state_counts": state_counts,
        "hashes": {
            "TARGET_GEOMETRY_HASH": hashlib.sha256(_stable_json(geometry_hash_payload).encode("utf-8")).hexdigest(),
            "EXIT_OUTCOME_HASH": hashlib.sha256(_stable_json(exit_hash_payload).encode("utf-8")).hexdigest(),
            "REALIZED_R_SERIES_HASH": hashlib.sha256(_stable_json(realized_r_series_payload).encode("utf-8")).hexdigest(),
        },
        "sample_valid_for_promotion": bool(
            len(validation) >= 30
            and rr_accounting_integrity
            and normalization_integrity
            and evidence_integrity
            and candidate_state_count_conservation
        ),
        "qualifying_credit_awarded": False,
        "broker_writes": False,
        "practice_orders": False,
        "live_trades": False,
        "zero_qualifying_credit": True,
    }


def run_rr_calibration(
    records: Sequence[Mapping[str, Any]],
    *,
    calibration_fraction: float = 0.7,
    replay_cache_path: Path | None = None,
) -> dict[str, Any]:
    evaluations = [
        evaluate_rr_configuration(
            records,
            target_rr=target_rr,
            calibration_fraction=calibration_fraction,
            replay_cache_path=replay_cache_path,
        )
        for target_rr in TARGETS
    ]
    ranked = sorted(
        evaluations,
        key=lambda item: (
            item["validation"]["expectancy_r"],
            item["validation"]["profit_factor"] or 0.0,
            -item["validation"]["maximum_drawdown_r"],
            item["validation_trades"],
            item["target_rr"],
        ),
        reverse=True,
    )
    winner = ranked[0] if ranked and ranked[0]["sample_label"] == "SAMPLE_SUFFICIENT" and ranked[0]["promotion_status"] == "RESEARCH_WINNER" else {}
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "sample_sufficient": bool(winner) and winner["sample_label"] == "SAMPLE_SUFFICIENT",
        "sample_count_sufficient": any(item["validation_trades"] >= 30 for item in evaluations),
        "recommended_target_rr": winner.get("target_rr"),
        "recommended_min_rr": MIN_RR,
        "promotion_status": winner.get("promotion_status", "NO_RR_CONFIGURATION_READY_FOR_PROMOTION") if winner else "NO_RR_CONFIGURATION_READY_FOR_PROMOTION",
        "qualifying_credit_awarded": False,
        "broker_writes": False,
        "practice_orders": False,
        "live_trades": False,
        "evaluations": evaluations,
        "winner": winner,
        "result_class_breakpoints": [
            "LOSS_R",
            "FLAT_R",
            "POSITIVE_LT_1R",
            "R_1_TO_LT_2",
            "R_2_TO_LT_2_5",
            "R_2_5_TO_LT_3",
            "R_3_TO_LT_4",
            "R_4_PLUS",
        ],
    }


def write_rr_calibration_artifacts(result: Mapping[str, Any], *, report_root: Path = REPORT_ROOT) -> dict[str, Path]:
    report_root.mkdir(parents=True, exist_ok=True)
    report_path = report_root / "AIOS_FOREX_RR_CALIBRATION_V1_REPORT.md"
    json_path = report_root / "AIOS_FOREX_RR_CALIBRATION_V1_RESULTS.json"
    report_path.write_text(build_rr_calibration_report(result), encoding="utf-8")
    json_path.write_text(_stable_json(dict(result)), encoding="utf-8")
    return {"report": report_path, "results": json_path}


def build_rr_calibration_report(result: Mapping[str, Any]) -> str:
    rows = result.get("evaluations", [])
    table = "\n".join(
        f"| {row['target_rr']} | {row['calibration_trades']} | {row['validation_trades']} | {row['validation']['win_rate']:.4f} | {row['validation']['expectancy_r']:.4f} | {row['validation']['profit_factor']} | {row['validation']['maximum_drawdown_r']:.4f} | {row['promotion_status']} |"
        for row in rows
    )
    return (
        "# AIOS Forex R:R Calibration V1\n\n"
        "## Safety\n"
        "- zero qualifying credit: True\n"
        "- broker writes: False\n"
        "- practice orders: False\n"
        "- live trades: False\n\n"
        "## Configuration Table\n"
        "| R:R | Calibration Trades | Validation Trades | Validation Win Rate | Validation Expectancy R | Profit Factor | Max DD R | Decision |\n"
        "| --- | -----------------: | ----------------: | ------------------: | ----------------------: | ------------: | -------: | -------- |\n"
        f"{table}\n\n"
        f"- RECOMMENDED_TARGET_RR: `{result.get('recommended_target_rr')}`\n"
        f"- RECOMMENDED_MIN_RR: `{result.get('recommended_min_rr')}`\n"
        f"- SAMPLE_SUFFICIENT: `{result.get('sample_sufficient')}`\n"
        f"- PROMOTION_STATUS: `{result.get('promotion_status')}`\n"
        f"- QUALIFYING_CREDIT_AWARDED: `{result.get('qualifying_credit_awarded')}`\n"
    )
