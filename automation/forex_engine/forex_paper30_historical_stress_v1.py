"""Deterministic DEVELOPMENT-only robustness audit for the frozen PAPER30 strategy.

This module is research-only.  It never calls a broker, never changes the frozen
strategy, and never credits historical trades to the forward PAPER30 campaign.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_macd_confluence_runner_v1 import (  # noqa: E402
    _canonical_semantic_trade_hash,
    _simulate_symbol,
    _to_candles,
)
from automation.forex_engine.indicators import atr  # noqa: E402


PACKET_ID = "PKT-EAST-FOREX-PAPER30-WEEKEND-STRESS-016A"
ORIGINAL_AUDIT_PACKET_ID = "PKT-EAST-FOREX-PAPER30-WEEKEND-STRESS-016"
LOCK_ID = "LOCK_EAST_FOREX_PAPER30_RESEARCH_EAST_OCC_01"
WORKER_IDENTITY = "EAST_OCC_01"
LANE = "FOREX_PAPER30_RESEARCH"
REPOSITORY_IDENTITY = "ai-rtony91/Ai_Os-Forex"
REPOSITORY_ID = 1227385337
PAPER30_STRATEGY_CONFIG_SHA256 = (
    "13b96b3e227a2b5873ba5916a4987cf571868626339d1a89e2cd6e0e25bd1435"
)
EXPECTED_DEVELOPMENT_ENTRY_HASH = (
    "2f867464008f72d2767c885609e21ed24b3f769b8bb9f9535fae06721fa984ef"
)
EXPECTED_PAIR_COUNT = 68
CHRONOLOGICAL_FOLD_COUNT = 8
BOOTSTRAP_SEED = 20260822
BOOTSTRAP_SIMULATIONS = 10_000
PAPER30_LEDGER_SCHEMA = "AIOS_FOREX_FROZEN_CANDIDATE_PAPER30_V1"
PAPER30_LEDGER_TRADE_COLLECTION_FIELD = "trades"
PAPER30_TARGET = 30
SUPPORTED_LEDGER_SHAPES = (
    "OBJECT_ENVELOPE_SCHEMA_AIOS_FOREX_FROZEN_CANDIDATE_PAPER30_V1_WITH_TRADES_LIST",
)

REPLAY_CACHE_PATH = ROOT / ".aios/runtime/forex_multipair_m5_replay_mba_v1/replay_cache.json"
DEVELOPMENT_REPORT_PATH = (
    ROOT / "Reports/forex_delivery/AIOS_FOREX_DEVELOPMENT_TARGET_AND_FINAL_HOLDOUT_V1_RESULTS.json"
)
RECOVERY_REPORT_PATH = (
    ROOT / "Reports/forex_delivery/AIOS_FOREX_HOLDOUT_CONTAMINATION_RECOVERY_V1_RESULTS.json"
)
PAPER30_RUNTIME_PATH = ROOT / "automation/forex_engine/forex_frozen_candidate_paper30_v1.py"
PAPER30_LAUNCHER_PATH = ROOT / "scripts/forex_delivery/run_forex_frozen_candidate_paper30_v1.py"
PAPER30_STATE_PATH = (
    ROOT / ".aios/runtime/forex_frozen_candidate_paper30_v1/AIOS_FOREX_PAPER30_STATE.json"
)
PAPER30_LEDGER_PATH = (
    ROOT / ".aios/runtime/forex_frozen_candidate_paper30_v1/AIOS_FOREX_PAPER30_LEDGER.json"
)
PAPER30_ACTIVE_PATH = (
    ROOT / ".aios/runtime/forex_frozen_candidate_paper30_v1/AIOS_FOREX_PAPER30_ACTIVE.json"
)
RESULT_PATH = ROOT / "Reports/forex_delivery/AIOS_FOREX_PAPER30_HISTORICAL_STRESS_V1_RESULTS.json"


def _timestamp_key(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _profit_factor(values: Sequence[float]) -> float:
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = abs(sum(value for value in values if value < 0))
    if gross_loss:
        return gross_profit / gross_loss
    return math.inf if gross_profit > 0 else 0.0


def trade_metrics(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = [float(trade["realized_r"]) for trade in trades]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    loss_streak = 0
    max_loss_streak = 0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
        loss_streak = loss_streak + 1 if value < 0 else 0
        max_loss_streak = max(max_loss_streak, loss_streak)
    return {
        "closed": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "flats": sum(value == 0 for value in values),
        "win_rate": len(wins) / len(values) if values else 0.0,
        "average_win_r": statistics.fmean(wins) if wins else 0.0,
        "average_loss_r": statistics.fmean(losses) if losses else 0.0,
        "expectancy_r": statistics.fmean(values) if values else 0.0,
        "profit_factor": _profit_factor(values),
        "net_r": sum(values),
        "max_drawdown_r": max_drawdown,
        "max_loss_streak": max_loss_streak,
        "median_trade_r": statistics.median(values) if values else 0.0,
        "standard_deviation_r": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "positive_trade_percent": (len(wins) / len(values) * 100.0) if values else 0.0,
    }


def report_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(metrics)
    value = float(result["profit_factor"])
    if math.isnan(value) or value == -math.inf:
        raise ValueError("NONFINITE_METRIC_INVALID")
    if value == math.inf:
        result["profit_factor"] = None
        result["profit_factor_status"] = "POSITIVE_INFINITY"
        result["profit_factor_reason"] = "POSITIVE_GROSS_PROFIT_WITH_ZERO_GROSS_LOSS"
    else:
        result["profit_factor_status"] = "FINITE"
        result["profit_factor_reason"] = None
    return result


def _assert_json_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NONFINITE_METRIC_INVALID")
    if isinstance(value, Mapping):
        for child in value.values():
            _assert_json_finite(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _assert_json_finite(child)


def filter_development_candles(
    histories: Mapping[str, Mapping[str, Any]], development_end_timestamp: str
) -> dict[str, list[Any]]:
    end = _timestamp_key(development_end_timestamp)
    return {
        instrument: [
            candle for candle in _to_candles(instrument, history)
            if _timestamp_key(candle.timestamp) <= end
        ]
        for instrument, history in sorted(histories.items())
    }


def reproduce_trades(
    candles_by_pair: Mapping[str, Sequence[Any]],
    train_end_timestamp: str,
    development_end_timestamp: str,
) -> list[dict[str, Any]]:
    train_end = _timestamp_key(train_end_timestamp)
    development_end = _timestamp_key(development_end_timestamp)
    trades: list[dict[str, Any]] = []
    for instrument, candles in sorted(candles_by_pair.items()):
        if any(_timestamp_key(candle.timestamp) > development_end for candle in candles):
            raise ValueError("HISTORICAL_DATA_BOUNDARY_INVALID")
        for trade in _simulate_symbol(candles, period=5, factor=2.0):
            entry = _timestamp_key(str(trade["entry_timestamp_utc"]))
            exit_time = _timestamp_key(str(trade["exit_timestamp_utc"]))
            same_partition = (entry <= train_end) == (exit_time <= train_end)
            # A position still open at the DEVELOPMENT boundary is not a closed
            # historical trade and is excluded without consulting holdout data.
            if (
                trade["direction"] == "BUY"
                and trade["exit_reason"] != "END_OF_DATA"
                and same_partition
                and exit_time <= development_end
            ):
                trades.append(dict(trade, instrument=instrument))
    trades.sort(
        key=lambda item: (
            str(item["entry_timestamp_utc"]),
            str(item["instrument"]),
            str(item["exit_timestamp_utc"]),
        )
    )
    return trades


def chronological_folds(
    trades: Sequence[Mapping[str, Any]], timestamps: Sequence[str], count: int = 8
) -> list[dict[str, Any]]:
    if count != CHRONOLOGICAL_FOLD_COUNT or len(timestamps) < count:
        raise ValueError("HISTORICAL_DATA_BOUNDARY_INVALID")
    folds: list[dict[str, Any]] = []
    for index in range(count):
        start_index = len(timestamps) * index // count
        end_index = len(timestamps) * (index + 1) // count - 1
        start = timestamps[start_index]
        end = timestamps[end_index]
        fold_trades = [
            trade for trade in trades
            if _timestamp_key(start)
            <= _timestamp_key(str(trade["entry_timestamp_utc"]))
            <= _timestamp_key(end)
        ]
        folds.append(
            {
                "fold_id": f"DEV_FOLD_{index + 1}",
                "start_timestamp": start,
                "end_timestamp": end,
                "unique_timestamp_count": end_index - start_index + 1,
                **report_metrics(trade_metrics(fold_trades)),
            }
        )
    return folds


def pair_contribution(
    trades: Sequence[Mapping[str, Any]], instruments: Sequence[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = []
    raw_by_pair: dict[str, dict[str, Any]] = {}
    for instrument in sorted(instruments):
        raw = trade_metrics([trade for trade in trades if trade["instrument"] == instrument])
        raw_by_pair[instrument] = raw
        records.append({"instrument": instrument, **report_metrics(raw)})
    total_net = sum(float(item["net_r"]) for item in raw_by_pair.values())
    ranked = sorted(raw_by_pair.items(), key=lambda item: float(item[1]["net_r"]), reverse=True)

    def share(pair_count: int) -> float:
        return (
            sum(float(metrics["net_r"]) for _, metrics in ranked[:pair_count]) / total_net
            if total_net else 0.0
        )

    summary = {
        "profitable_pair_count": sum(float(item["net_r"]) > 0 for item in raw_by_pair.values()),
        "losing_pair_count": sum(float(item["net_r"]) < 0 for item in raw_by_pair.values()),
        "positive_expectancy_pair_count": sum(
            float(item["expectancy_r"]) > 0 for item in raw_by_pair.values()
        ),
        "top_1_pair_net_r_share": share(1),
        "top_5_pair_net_r_share": share(5),
        "top_10_pair_net_r_share": share(10),
        "bottom_5_pair_net_r": sum(float(metrics["net_r"]) for _, metrics in ranked[-5:]),
        "pair_net_r_reconciliation": total_net,
    }
    return records, summary


def leave_one_pair_out(
    trades: Sequence[Mapping[str, Any]], instruments: Sequence[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    for instrument in sorted(instruments):
        metrics = trade_metrics([trade for trade in trades if trade["instrument"] != instrument])
        raw.append(metrics)
        records.append({"excluded_instrument": instrument, **report_metrics(metrics)})
    summary = {
        "leave_one_pair_out_runs": len(records),
        "lopo_positive_expectancy_count": sum(float(item["expectancy_r"]) > 0 for item in raw),
        "lopo_pf_ge_1_10_count": sum(float(item["profit_factor"]) >= 1.10 for item in raw),
        "lopo_positive_net_r_count": sum(float(item["net_r"]) > 0 for item in raw),
        "lopo_worst_expectancy_r": min(float(item["expectancy_r"]) for item in raw),
        "lopo_worst_profit_factor": min(float(item["profit_factor"]) for item in raw),
        "lopo_worst_net_r": min(float(item["net_r"]) for item in raw),
    }
    return records, summary


def rolling_30_trade_stress(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    windows = [trade_metrics(trades[index:index + 30]) for index in range(max(0, len(trades) - 29))]
    if not windows:
        raise ValueError("HISTORICAL_REPRODUCTION_FAILED")
    net = [float(item["net_r"]) for item in windows]
    drawdown = [float(item["max_drawdown_r"]) for item in windows]
    return {
        "rolling_30_trade_window_count": len(windows),
        "95th_percentile_rolling_30_trade_drawdown_r": _quantile(drawdown, 0.95),
        "worst_30_trade_net_r": min(net),
        "best_30_trade_net_r": max(net),
        "median_30_trade_net_r": statistics.median(net),
        "percent_of_30_trade_windows_positive_net_r": sum(value > 0 for value in net) / len(net) * 100.0,
        "percent_of_30_trade_windows_expectancy_positive": (
            sum(float(item["expectancy_r"]) > 0 for item in windows) / len(windows) * 100.0
        ),
        "percent_of_30_trade_windows_pf_ge_1_10": (
            sum(float(item["profit_factor"]) >= 1.10 for item in windows) / len(windows) * 100.0
        ),
    }


def trade_frequency(
    trades: Sequence[Mapping[str, Any]], timestamps: Sequence[str]
) -> dict[str, Any]:
    ordinal = {timestamp: index for index, timestamp in enumerate(timestamps)}
    entry_ordinals = [ordinal[str(trade["entry_timestamp_utc"])] for trade in trades]
    daily_counts = [
        sum(start <= item < min(start + 288, len(timestamps)) for item in entry_ordinals)
        for start in range(0, len(timestamps), 288)
    ]
    five_day_counts = [
        sum(start <= item < min(start + 1440, len(timestamps)) for item in entry_ordinals)
        for start in range(0, len(timestamps), 1440)
    ]
    hours_to_30 = [
        (entry_ordinals[index + 29] - entry_ordinals[index]) * 5.0 / 60.0
        for index in range(len(entry_ordinals) - 29)
    ]
    return {
        "trades_per_24h_market_time_mean": statistics.fmean(daily_counts),
        "trades_per_24h_market_time_median": statistics.median(daily_counts),
        "trades_per_5_trading_days_mean": statistics.fmean(five_day_counts),
        "median_hours_to_30_trades": statistics.median(hours_to_30),
        "p25_hours_to_30_trades": _quantile(hours_to_30, 0.25),
        "p75_hours_to_30_trades": _quantile(hours_to_30, 0.75),
        "p90_hours_to_30_trades": _quantile(hours_to_30, 0.90),
        "timing_basis": "GLOBAL_COMPLETED_M5_MARKET_TIMESTAMPS_HISTORICAL_ONLY",
    }


def forward_path_metrics(
    trades: Sequence[Mapping[str, Any]], candles_by_pair: Mapping[str, Sequence[Any]]
) -> dict[str, Any]:
    thresholds = (1.0, 1.5, 2.0, 3.0, 4.0, 5.0)
    records: list[dict[str, Any]] = []
    for trade in trades:
        candles = candles_by_pair[str(trade["instrument"])]
        entry_index = int(trade["entry_index"])
        exit_index = int(trade["exit_index"])
        if exit_index >= len(candles) or candles[exit_index].timestamp != trade["exit_timestamp_utc"]:
            raise ValueError("LOOKAHEAD_DETECTED")
        entry = float(trade["entry_price"])
        risk = float(trade["initial_risk_distance"])
        favorable = [
            (float(candle.high) - entry) / risk
            for candle in candles[entry_index:exit_index + 1]
        ]
        mfe = max(0.0, max(favorable, default=0.0))
        bars_to = {
            threshold: next((index for index, value in enumerate(favorable) if value >= threshold), None)
            for threshold in thresholds
        }
        realized = float(trade["realized_r"])
        records.append(
            {
                "trade_id": trade["trade_id"],
                "realized_r": realized,
                "mfe_r": mfe,
                "profit_giveback_r": max(0.0, mfe - max(0.0, realized)),
                "bars_to": bars_to,
            }
        )
    result: dict[str, Any] = {"path_trade_count": len(records), "lookahead_detected": False}
    names = {1.0: "1", 1.5: "1_5", 2.0: "2", 3.0: "3", 4.0: "4", 5.0: "5"}
    for threshold in thresholds:
        count = sum(record["bars_to"][threshold] is not None for record in records)
        result[f"reached_{names[threshold]}r_count"] = count
        result[f"reached_{names[threshold]}r_percent"] = count / len(records) * 100.0
    result.update(
        {
            "winners_reached_5r_count": sum(
                item["realized_r"] > 0 and item["bars_to"][5.0] is not None for item in records
            ),
            "losers_that_first_reached_1r_count": sum(
                item["realized_r"] < 0 and item["bars_to"][1.0] is not None for item in records
            ),
            "losers_that_first_reached_2r_count": sum(
                item["realized_r"] < 0 and item["bars_to"][2.0] is not None for item in records
            ),
            "mean_max_favorable_excursion_r": statistics.fmean(item["mfe_r"] for item in records),
            "median_max_favorable_excursion_r": statistics.median(item["mfe_r"] for item in records),
            "mean_profit_giveback_r": statistics.fmean(item["profit_giveback_r"] for item in records),
            "shadow_5r_authority": "OBSERVATION_ONLY",
        }
    )
    return result


def volatility_regimes(
    trades: Sequence[Mapping[str, Any]], candles_by_pair: Mapping[str, Sequence[Any]]
) -> list[dict[str, Any]]:
    atr_by_pair = {instrument: atr(candles, period=5) for instrument, candles in candles_by_pair.items()}
    ranked: list[tuple[float, str, Mapping[str, Any]]] = []
    for trade in trades:
        instrument = str(trade["instrument"])
        signal_index = int(trade["entry_index"]) - 1
        atr_value = atr_by_pair[instrument][signal_index]
        if atr_value is None:
            raise ValueError("HISTORICAL_REPRODUCTION_FAILED")
        normalized = float(atr_value) / float(trade["entry_price"])
        ranked.append((normalized, str(trade["trade_id"]), trade))
    ranked.sort(key=lambda item: (item[0], item[1]))
    groups: list[list[Mapping[str, Any]]] = [[] for _ in range(4)]
    for index, (_, _, trade) in enumerate(ranked):
        groups[min(3, index * 4 // len(ranked))].append(trade)
    return [
        {"regime": f"VOL_Q{index + 1}", **report_metrics(trade_metrics(group))}
        for index, group in enumerate(groups)
    ]


def bootstrap_30(
    realized: Sequence[float], seed: int = BOOTSTRAP_SEED, simulations: int = BOOTSTRAP_SIMULATIONS
) -> dict[str, Any]:
    if not realized or simulations < 10_000:
        raise ValueError("HISTORICAL_REPRODUCTION_FAILED")
    generator = random.Random(seed)
    net_values: list[float] = []
    drawdowns: list[float] = []
    positive_expectancy = 0
    pf_ge = 0
    for _ in range(simulations):
        sample = [float(realized[generator.randrange(len(realized))]) for _ in range(30)]
        sample_trades = [{"realized_r": value} for value in sample]
        metrics = trade_metrics(sample_trades)
        net_values.append(float(metrics["net_r"]))
        drawdowns.append(float(metrics["max_drawdown_r"]))
        positive_expectancy += float(metrics["expectancy_r"]) > 0
        pf_ge += float(metrics["profit_factor"]) >= 1.10
    return {
        "bootstrap_seed": seed,
        "bootstrap_simulation_count": simulations,
        "p30_net_r_positive": sum(value > 0 for value in net_values) / simulations,
        "p30_expectancy_positive": positive_expectancy / simulations,
        "p30_pf_ge_1_10": pf_ge / simulations,
        "p30_max_drawdown_r_median": statistics.median(drawdowns),
        "p30_max_drawdown_r_p95": _quantile(drawdowns, 0.95),
        "p30_net_r_p05": _quantile(net_values, 0.05),
        "p30_net_r_median": statistics.median(net_values),
        "p30_net_r_p95": _quantile(net_values, 0.95),
    }


def classify_historical_stress(
    global_metrics: Mapping[str, Any],
    fold_summary: Mapping[str, Any],
    pair_summary: Mapping[str, Any],
    rolling: Mapping[str, Any],
    bootstrap: Mapping[str, Any],
) -> tuple[str, list[str]]:
    severe = []
    if float(global_metrics["expectancy_r"]) <= 0:
        severe.append("NONPOSITIVE_GLOBAL_EXPECTANCY")
    if int(fold_summary["positive_expectancy_fold_count"]) <= 3:
        severe.append("HALF_OR_FEWER_FOLDS_POSITIVE_EXPECTANCY")
    if float(rolling["percent_of_30_trade_windows_positive_net_r"]) < 35.0:
        severe.append("FEWER_THAN_35_PERCENT_OF_ROLLING_30_WINDOWS_POSITIVE")
    if float(bootstrap["p30_net_r_positive"]) < 0.35:
        severe.append("BOOTSTRAP_30_POSITIVE_NET_PROBABILITY_BELOW_35_PERCENT")
    if float(pair_summary["top_5_pair_net_r_share"]) > 0.80:
        severe.append("TOP_5_PAIR_CONCENTRATION_ABOVE_80_PERCENT")
    if severe:
        return "HISTORICAL_STRESS_SHOWS_MATERIAL_FRAGILITY", severe
    supporting = (
        int(fold_summary["positive_expectancy_fold_count"]) >= 6
        and int(fold_summary["pf_above_1_10_fold_count"]) >= 5
        and float(rolling["percent_of_30_trade_windows_positive_net_r"]) >= 60.0
        and float(bootstrap["p30_pf_ge_1_10"]) >= 0.50
        and float(pair_summary["top_5_pair_net_r_share"]) <= 0.60
    )
    if supporting:
        return "HISTORICAL_STRESS_SUPPORTS_FORWARD_PAPER30", ["ALL_SUPPORTING_DIAGNOSTIC_THRESHOLDS_MET"]
    return "HISTORICAL_STRESS_INCONCLUSIVE", ["MIXED_NONSEVERE_ROBUSTNESS_EVIDENCE"]


def _fold_summary(folds: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expectancy = [float(item["expectancy_r"]) for item in folds]
    net = [float(item["net_r"]) for item in folds]
    pf = [math.inf if item["profit_factor"] is None else float(item["profit_factor"]) for item in folds]
    return {
        "positive_expectancy_fold_count": sum(value > 0 for value in expectancy),
        "pf_above_1_fold_count": sum(value > 1.0 for value in pf),
        "pf_above_1_10_fold_count": sum(value > 1.10 for value in pf),
        "positive_net_r_fold_count": sum(value > 0 for value in net),
        "worst_fold_expectancy_r": min(expectancy),
        "worst_fold_net_r": min(net),
        "best_fold_expectancy_r": max(expectancy),
        "fold_expectancy_median": statistics.median(expectancy),
        "fold_expectancy_stddev": statistics.pstdev(expectancy),
    }


def _ledger_trade_collection(ledger: Any) -> list[Mapping[str, Any]]:
    if not isinstance(ledger, Mapping):
        raise ValueError("PAPER30_LEDGER_SCHEMA_UNSUPPORTED")
    if ledger.get("schema") != PAPER30_LEDGER_SCHEMA:
        raise ValueError("PAPER30_LEDGER_SCHEMA_UNSUPPORTED")
    if ledger.get("strategy_config_sha256") != PAPER30_STRATEGY_CONFIG_SHA256:
        raise ValueError("PAPER30_LEDGER_SCHEMA_UNSUPPORTED")
    trades = ledger.get(PAPER30_LEDGER_TRADE_COLLECTION_FIELD)
    if not isinstance(trades, list) or any(not isinstance(record, Mapping) for record in trades):
        raise ValueError("PAPER30_LEDGER_SCHEMA_UNSUPPORTED")
    return trades


def _qualifying_closed_forward_trade(record: Mapping[str, Any]) -> bool:
    if record.get("qualifying") is not True:
        return False
    if record.get("historical_backfill") is not False or record.get("broker_order") is not False:
        return False
    if record.get("strategy_config_sha256") != PAPER30_STRATEGY_CONFIG_SHA256:
        return False
    if record.get("direction") != "BUY":
        return False
    if not isinstance(record.get("exit_timestamp_utc"), str) or not record["exit_timestamp_utc"]:
        return False
    if not isinstance(record.get("exit_reason"), str) or not record["exit_reason"]:
        return False
    realized_r = record.get("realized_r")
    if isinstance(realized_r, bool) or not isinstance(realized_r, (int, float)):
        return False
    return math.isfinite(float(realized_r))


def _ledger_metadata(ledger: Any) -> dict[str, Any]:
    trades = _ledger_trade_collection(ledger)
    return {
        "ledger_root_type": "object",
        "ledger_schema": PAPER30_LEDGER_SCHEMA,
        "ledger_trade_collection_field": PAPER30_LEDGER_TRADE_COLLECTION_FIELD,
        "ledger_trade_collection_type": "list",
        "ledger_current_record_count": len(trades),
        "supported_ledger_shapes": list(SUPPORTED_LEDGER_SHAPES),
    }


def _current_forward_count(ledger_path: Path) -> int:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    trades = _ledger_trade_collection(ledger)
    qualifying = sum(_qualifying_closed_forward_trade(record) for record in trades)
    return min(qualifying, PAPER30_TARGET)


def build_report() -> dict[str, Any]:
    invariant_paths = {
        "paper30_runtime": PAPER30_RUNTIME_PATH,
        "paper30_launcher": PAPER30_LAUNCHER_PATH,
        "paper30_state": PAPER30_STATE_PATH,
        "paper30_ledger": PAPER30_LEDGER_PATH,
        "paper30_active": PAPER30_ACTIVE_PATH,
    }
    pre_hashes = {name: _sha256_file(path) for name, path in invariant_paths.items()}
    ledger_payload = json.loads(PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    ledger_metadata = _ledger_metadata(ledger_payload)
    forward_count_pre = _current_forward_count(PAPER30_LEDGER_PATH)
    paper30_state = json.loads(PAPER30_STATE_PATH.read_text(encoding="utf-8"))
    if paper30_state.get("strategy_config_sha256") != PAPER30_STRATEGY_CONFIG_SHA256:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")
    if forward_count_pre != 0:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")

    development = json.loads(DEVELOPMENT_REPORT_PATH.read_text(encoding="utf-8"))
    recovery = json.loads(RECOVERY_REPORT_PATH.read_text(encoding="utf-8"))
    expected_config = {
        "timeframe": "M5",
        "direction": "BUY_ONLY",
        "atr_period": 5,
        "supertrend_factor": 2.0,
        "confirmation": "TRUE_2_CLOSE",
        "macd_filter": "NONE",
        "exit_policy": "EXIT_A_BASELINE",
        "entry_timing": "NEXT_CANDLE_OPEN",
        "initial_r_frozen": True,
    }
    if development.get("strategy_config") != expected_config:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")
    development_end = str(development["original_validation_end_timestamp"])
    holdout_start = str(recovery["final_holdout_v1_start_timestamp"])
    if not _timestamp_key(development_end) < _timestamp_key(holdout_start):
        raise ValueError("HISTORICAL_DATA_BOUNDARY_INVALID")
    if int(recovery.get("post_v1_raw_candle_count", 0)) != 0:
        raise ValueError("HISTORICAL_DATA_BOUNDARY_INVALID")

    cache = json.loads(REPLAY_CACHE_PATH.read_text(encoding="utf-8"))
    histories = cache["pair_histories"]
    if len(histories) != EXPECTED_PAIR_COUNT:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")
    candles_by_pair = filter_development_candles(histories, development_end)
    timestamps = sorted(
        {candle.timestamp for candles in candles_by_pair.values() for candle in candles},
        key=_timestamp_key,
    )
    if not timestamps or _timestamp_key(timestamps[-1]) > _timestamp_key(development_end):
        raise ValueError("HISTORICAL_DATA_BOUNDARY_INVALID")

    first = reproduce_trades(
        candles_by_pair,
        str(development["original_train_end_timestamp"]),
        development_end,
    )
    second = reproduce_trades(
        candles_by_pair,
        str(development["original_train_end_timestamp"]),
        development_end,
    )
    first_hash = _canonical_semantic_trade_hash(first)
    second_hash = _canonical_semantic_trade_hash(second)
    if first_hash != second_hash or first_hash != EXPECTED_DEVELOPMENT_ENTRY_HASH:
        raise ValueError("HISTORICAL_REPRODUCTION_FAILED")
    if first_hash != development.get("development_entry_hash"):
        raise ValueError("HISTORICAL_REPRODUCTION_FAILED")
    r_parity_failures = sum(
        abs(float(trade["price_r"]) - float(trade["quote_r"])) > 1e-9 for trade in first
    )
    if r_parity_failures or any(trade["direction"] != "BUY" for trade in first):
        raise ValueError("HISTORICAL_REPRODUCTION_FAILED")

    global_raw = trade_metrics(first)
    global_report = report_metrics(global_raw)
    folds = chronological_folds(first, timestamps)
    fold_summary = _fold_summary(folds)
    pair_records, pair_summary = pair_contribution(first, sorted(histories))
    if not math.isclose(float(pair_summary["pair_net_r_reconciliation"]), float(global_raw["net_r"]), abs_tol=1e-9):
        raise ValueError("HISTORICAL_REPRODUCTION_FAILED")
    lopo_records, lopo_summary = leave_one_pair_out(first, sorted(histories))
    rolling = rolling_30_trade_stress(first)
    frequency = trade_frequency(first, timestamps)
    paths = forward_path_metrics(first, candles_by_pair)
    regimes = volatility_regimes(first, candles_by_pair)
    bootstrap = bootstrap_30([float(trade["realized_r"]) for trade in first])
    classification, reasons = classify_historical_stress(
        global_raw, fold_summary, pair_summary, rolling, bootstrap
    )

    post_hashes = {name: _sha256_file(path) for name, path in invariant_paths.items()}
    forward_count_post = _current_forward_count(PAPER30_LEDGER_PATH)
    forward_unchanged = pre_hashes == post_hashes and forward_count_pre == forward_count_post
    if not forward_unchanged:
        raise ValueError("PAPER30_FORWARD_STATE_CHANGED")
    source_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()

    result = {
        "packet_id": PACKET_ID,
        "original_audit_packet_id": ORIGINAL_AUDIT_PACKET_ID,
        "lock_id": LOCK_ID,
        "worker_identity": WORKER_IDENTITY,
        "lane": LANE,
        "repository_identity": REPOSITORY_IDENTITY,
        "repository_id": REPOSITORY_ID,
        "source_head": source_head,
        "current_branch": "main",
        "paper30_strategy_config_sha256": PAPER30_STRATEGY_CONFIG_SHA256,
        **ledger_metadata,
        "frozen_strategy": expected_config,
        "development_start_timestamp": timestamps[0],
        "development_end_timestamp": development_end,
        "development_unique_timestamp_count": len(timestamps),
        "development_pair_count": len(histories),
        "holdout_v1_start_timestamp_metadata_only": holdout_start,
        "holdout_v1_rows_used": 0,
        "holdout_v2_rows_used": 0,
        "historical_trade_count": len(first),
        "buy_count": len(first),
        "sell_count": 0,
        "r_parity_failures": r_parity_failures,
        "historical_trade_hash": first_hash,
        "historical_reproducible": True,
        "global_metrics": global_report,
        "expectancy_r": global_report["expectancy_r"],
        "profit_factor": global_report["profit_factor"],
        "profit_factor_status": global_report["profit_factor_status"],
        "profit_factor_reason": global_report["profit_factor_reason"],
        "net_r": global_report["net_r"],
        "max_drawdown_r": global_report["max_drawdown_r"],
        "max_loss_streak": global_report["max_loss_streak"],
        "chronological_fold_count": len(folds),
        "chronological_folds": folds,
        **fold_summary,
        "pair_contribution": pair_records,
        **pair_summary,
        "pair_concentration_material": float(pair_summary["top_5_pair_net_r_share"]) > 0.60,
        "leave_one_pair_out": lopo_records,
        **lopo_summary,
        **rolling,
        **frequency,
        **paths,
        "volatility_regimes": regimes,
        "regime_filter_created": False,
        **bootstrap,
        "historical_stress_classification": classification,
        "historical_stress_classification_reasons": reasons,
        "forward_paper30_required": True,
        "paper30_forward_evidence_count_unchanged": True,
        "qualifying_forward_trades_credited": 0,
        "current_forward_qualifying_count_pre": forward_count_pre,
        "current_forward_qualifying_count_post": forward_count_post,
        "paper30_forward_state_unchanged": forward_unchanged,
        "paper30_invariant_pre_sha256": pre_hashes,
        "paper30_invariant_post_sha256": post_hashes,
        "network_calls": False,
        "broker_calls": False,
        "broker_writes": False,
        "practice_orders": False,
        "live_orders": False,
        "money_movement": False,
        "credentials_accessed": False,
        "historical_backfill_trade_count": 0,
        "json_nonfinite_float_count": 0,
        "status": classification,
    }
    _assert_json_finite(result)
    json.dumps(result, sort_keys=True, allow_nan=False)
    return result


def run() -> dict[str, Any]:
    result = build_report()
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    RESULT_PATH.write_text(payload, encoding="utf-8")
    return result


if __name__ == "__main__":
    report = run()
    print(json.dumps({"status": report["status"], "result_path": str(RESULT_PATH)}, allow_nan=False))
