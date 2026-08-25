"""DEVELOPMENT-only statistical marathon for the frozen PAPER30 candidate.

Unique historical trades, chronological windows, and resampled simulations are
kept as separate evidence classes.  This module performs no network, broker,
credential, order, money, strategy-selection, holdout, or PAPER30 write action.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from automation.forex_engine.forex_macd_confluence_runner_v1 import (  # noqa: E402
    _canonical_semantic_trade_hash,
    _simulate_symbol,
    _to_candles,
)
from automation.forex_engine.indicators import atr  # noqa: E402


PACKET_ID = "PKT-EAST-FOREX-PRO-HISTORICAL-EVIDENCE-MARATHON-022R2"
LOCK_ID = "LOCK_EAST_FOREX_HISTORICAL_EVIDENCE_RESEARCH_EAST_OCC_01"
WORKER_IDENTITY = "EAST_OCC_01"
LANE = "FOREX_HISTORICAL_EVIDENCE_RESEARCH"
REPOSITORY_IDENTITY = "ai-rtony91/Ai_Os-Forex"
STRATEGY_SHA256 = "13b96b3e227a2b5873ba5916a4987cf571868626339d1a89e2cd6e0e25bd1435"
EXPECTED_LEGACY_TRADE_HASH = "2f867464008f72d2767c885609e21ed24b3f769b8bb9f9535fae06721fa984ef"
EXPECTED_PAIR_COUNT = 68
SEED = 20260822
SAMPLE_SIZES = (30, 50, 75, 100, 150, 250)
PRIMARY_BOOTSTRAP_SIZES = (30, 50, 100, 250)
SUPPLEMENTAL_BOOTSTRAP_SIZES = (75, 150)
ORDINARY_BOOTSTRAP_RUNS = 50_000
BLOCK_BOOTSTRAP_RUNS = 20_000
BLOCK_SIZES = (5, 10, 20)
BLOCK_SAMPLE_SIZES = (30, 100)
PERMUTATION_RUNS = 50_000
CI_BOOTSTRAP_RUNS = 50_000
L5O_RUNS = 5_000
PAPER30_TARGET = 30
AUTHORIZED_MARATHON_EXECUTIONS = 1

REPLAY_CACHE_PATH = REPO_ROOT / ".aios/runtime/forex_multipair_m5_replay_mba_v1/replay_cache.json"
HISTORICAL_STRESS_PATH = REPO_ROOT / "Reports/forex_delivery/AIOS_FOREX_PAPER30_HISTORICAL_STRESS_V1_RESULTS.json"
PAPER30_RUNTIME_PATH = REPO_ROOT / "automation/forex_engine/forex_frozen_candidate_paper30_v1.py"
PAPER30_LEDGER_PATH = REPO_ROOT / ".aios/runtime/forex_frozen_candidate_paper30_v1/AIOS_FOREX_PAPER30_LEDGER.json"
PAPER30_STATE_PATH = REPO_ROOT / ".aios/runtime/forex_frozen_candidate_paper30_v1/AIOS_FOREX_PAPER30_STATE.json"
HOLDOUT_GUARD_PATH = REPO_ROOT / ".aios/runtime/forex_final_holdout_access_guard_v1.json"
RESULT_PATH = REPO_ROOT / "Reports/forex_delivery/AIOS_FOREX_PRO_HISTORICAL_EVIDENCE_MARATHON_V1_RESULTS.json"


def _timestamp(value: str) -> datetime:
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


def _skewness(values: Sequence[float]) -> float:
    if len(values) < 3:
        return 0.0
    mean = statistics.fmean(values)
    variance = statistics.fmean((value - mean) ** 2 for value in values)
    if variance == 0:
        return 0.0
    return statistics.fmean((value - mean) ** 3 for value in values) / variance ** 1.5


def _excess_kurtosis(values: Sequence[float]) -> float:
    if len(values) < 4:
        return 0.0
    mean = statistics.fmean(values)
    variance = statistics.fmean((value - mean) ** 2 for value in values)
    if variance == 0:
        return 0.0
    return statistics.fmean((value - mean) ** 4 for value in values) / variance ** 2 - 3.0


def sequence_metrics(values: Sequence[float]) -> dict[str, Any]:
    count = len(values)
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    loss_streak = 0
    max_loss_streak = 0
    for raw_value in values:
        value = float(raw_value)
        if value > 0:
            wins += 1
            gross_profit += value
            loss_streak = 0
        elif value < 0:
            losses += 1
            gross_loss -= value
            loss_streak += 1
            max_loss_streak = max(max_loss_streak, loss_streak)
        else:
            loss_streak = 0
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    profit_factor = gross_profit / gross_loss if gross_loss else (math.inf if gross_profit else 0.0)
    return {
        "closed": count,
        "wins": wins,
        "losses": losses,
        "flats": count - wins - losses,
        "win_rate": wins / count if count else 0.0,
        "expectancy_r": cumulative / count if count else 0.0,
        "profit_factor": profit_factor,
        "net_r": cumulative,
        "max_drawdown_r": drawdown,
        "max_loss_streak": max_loss_streak,
    }


def _paper_gate(metrics: Mapping[str, Any]) -> bool:
    return bool(
        int(metrics["closed"]) >= PAPER30_TARGET
        and float(metrics["net_r"]) > 0
        and float(metrics["expectancy_r"]) > 0
        and float(metrics["profit_factor"]) >= 1.10
    )


def _json_metrics(values: Sequence[float]) -> dict[str, Any]:
    metrics = sequence_metrics(values)
    wins = [float(value) for value in values if value > 0]
    losses = [float(value) for value in values if value < 0]
    pf = float(metrics["profit_factor"])
    return {
        **metrics,
        "average_win_r": statistics.fmean(wins) if wins else 0.0,
        "average_loss_r": statistics.fmean(losses) if losses else 0.0,
        "median_trade_r": statistics.median(values) if values else 0.0,
        "trade_r_stddev": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "profit_factor": pf if math.isfinite(pf) else None,
        "profit_factor_status": "FINITE" if math.isfinite(pf) else "POSITIVE_INFINITY",
    }


def _strict_json(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("STATISTICAL_INTEGRITY_FAILURE")
    if isinstance(value, Mapping):
        for child in value.values():
            _strict_json(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _strict_json(child)


def _forward_count() -> int:
    ledger = json.loads(PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    if ledger.get("schema") != "AIOS_FOREX_FROZEN_CANDIDATE_PAPER30_V1":
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")
    if ledger.get("strategy_config_sha256") != STRATEGY_SHA256:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")
    trades = ledger.get("trades")
    if not isinstance(trades, list):
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")
    return min(
        PAPER30_TARGET,
        sum(
            record.get("qualifying") is True
            and record.get("historical_backfill") is False
            and record.get("broker_order") is False
            and record.get("strategy_config_sha256") == STRATEGY_SHA256
            and record.get("direction") == "BUY"
            and bool(record.get("exit_timestamp_utc"))
            for record in trades
            if isinstance(record, Mapping)
        ),
    )


def _invariant_hashes() -> dict[str, str]:
    return {
        "PAPER30_RUNTIME_SHA256": _sha256_file(PAPER30_RUNTIME_PATH),
        "PAPER30_LEDGER_SHA256": _sha256_file(PAPER30_LEDGER_PATH),
        "PAPER30_STATE_SHA256": _sha256_file(PAPER30_STATE_PATH),
    }


def _development_candles(
    histories: Mapping[str, Mapping[str, Any]], development_end: str
) -> dict[str, list[Any]]:
    end = _timestamp(development_end)
    result = {
        instrument: [
            candle
            for candle in _to_candles(instrument, history)
            if _timestamp(candle.timestamp) <= end
        ]
        for instrument, history in sorted(histories.items())
    }
    if not result or any(
        _timestamp(candle.timestamp) > end for candles in result.values() for candle in candles
    ):
        raise ValueError("HISTORICAL_DATA_BOUNDARY_INVALID")
    return result


def _raw_closed_buy_trades(
    candles_by_pair: Mapping[str, Sequence[Any]], development_end: str
) -> list[dict[str, Any]]:
    end = _timestamp(development_end)
    trades: list[dict[str, Any]] = []
    for instrument, candles in sorted(candles_by_pair.items()):
        for trade in _simulate_symbol(candles, period=5, factor=2.0):
            if (
                trade["direction"] == "BUY"
                and trade["exit_reason"] != "END_OF_DATA"
                and _timestamp(str(trade["exit_timestamp_utc"])) <= end
            ):
                signal_index = int(trade["entry_index"]) - 1
                trades.append(
                    dict(
                        trade,
                        instrument=instrument,
                        signal_timestamp_utc=candles[signal_index].timestamp,
                    )
                )
    trades.sort(
        key=lambda item: (
            str(item["entry_timestamp_utc"]),
            str(item["instrument"]),
            str(item["exit_timestamp_utc"]),
        )
    )
    return trades


def _recover_partition_boundary(
    raw_trades: Sequence[Mapping[str, Any]], timestamps: Sequence[str], expected_hash: str
) -> tuple[str, list[dict[str, Any]]]:
    matches: list[tuple[str, list[dict[str, Any]]]] = []
    for timestamp in timestamps:
        boundary = _timestamp(timestamp)
        selected = [
            dict(trade)
            for trade in raw_trades
            if (_timestamp(str(trade["entry_timestamp_utc"])) <= boundary)
            == (_timestamp(str(trade["exit_timestamp_utc"])) <= boundary)
        ]
        if _canonical_semantic_trade_hash(selected) == expected_hash:
            matches.append((timestamp, selected))
    if len(matches) != 1:
        raise ValueError("HISTORICAL_DATA_BOUNDARY_INVALID")
    return matches[0]


def _partition_trades(
    raw_trades: Sequence[Mapping[str, Any]], train_end: str
) -> list[dict[str, Any]]:
    boundary = _timestamp(train_end)
    return [
        dict(trade)
        for trade in raw_trades
        if (_timestamp(str(trade["entry_timestamp_utc"])) <= boundary)
        == (_timestamp(str(trade["exit_timestamp_utc"])) <= boundary)
    ]


def semantic_trade_identity(trade: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        str(trade["instrument"]),
        str(trade["direction"]),
        str(trade["signal_timestamp_utc"]),
        str(trade["entry_timestamp_utc"]),
        float(trade["entry_price"]),
        float(trade["initial_stop"]),
        str(trade["exit_timestamp_utc"]),
        float(trade["exit_price"]),
    )


def deduplicate_trades(
    trades: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[dict[str, Any]] = []
    for trade in trades:
        identity = semantic_trade_identity(trade)
        if identity not in seen:
            seen.add(identity)
            unique.append(dict(trade))
    return unique, len(trades) - len(unique)


def semantic_trade_hash(trades: Sequence[Mapping[str, Any]]) -> str:
    records = [list(semantic_trade_identity(trade)) for trade in trades]
    payload = json.dumps(records, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def generate_historical_population() -> dict[str, Any]:
    prior = json.loads(HISTORICAL_STRESS_PATH.read_text(encoding="utf-8"))
    if prior.get("paper30_strategy_config_sha256") != STRATEGY_SHA256:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")
    if int(prior.get("holdout_v1_rows_used", -1)) != 0 or int(prior.get("holdout_v2_rows_used", -1)) != 0:
        raise ValueError("HISTORICAL_DATA_BOUNDARY_INVALID")
    if prior.get("historical_trade_hash") != EXPECTED_LEGACY_TRADE_HASH:
        raise ValueError("HISTORICAL_REPRODUCTION_FAILED")
    cache = json.loads(REPLAY_CACHE_PATH.read_text(encoding="utf-8"))
    if (
        cache.get("broker_write_performed") is not False
        or cache.get("practice_order_performed") is not False
        or cache.get("live_trade_performed") is not False
        or cache.get("money_movement_performed") is not False
    ):
        raise ValueError("HISTORICAL_DATA_BOUNDARY_INVALID")
    histories = cache.get("pair_histories")
    if not isinstance(histories, Mapping) or len(histories) != EXPECTED_PAIR_COUNT:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")
    development_end = str(prior["development_end_timestamp"])
    candles_by_pair = _development_candles(histories, development_end)
    timestamps = sorted(
        {candle.timestamp for candles in candles_by_pair.values() for candle in candles},
        key=_timestamp,
    )
    raw = _raw_closed_buy_trades(candles_by_pair, development_end)
    train_end, selected = _recover_partition_boundary(raw, timestamps, EXPECTED_LEGACY_TRADE_HASH)
    unique, duplicates = deduplicate_trades(selected)
    if _canonical_semantic_trade_hash(unique) != EXPECTED_LEGACY_TRADE_HASH:
        raise ValueError("HISTORICAL_REPRODUCTION_FAILED")
    return {
        "raw": raw,
        "trades": unique,
        "duplicates": duplicates,
        "candles_by_pair": candles_by_pair,
        "timestamps": timestamps,
        "train_end": train_end,
        "development_end": development_end,
        "instruments": sorted(histories),
    }


def rolling_analysis(values: Sequence[float], sample_size: int) -> dict[str, Any]:
    windows = [sequence_metrics(values[index : index + sample_size]) for index in range(len(values) - sample_size + 1)]
    if not windows:
        raise ValueError("STATISTICAL_INTEGRITY_FAILURE")
    net = [float(item["net_r"]) for item in windows]
    drawdown = [float(item["max_drawdown_r"]) for item in windows]
    pass_count = sum(_paper_gate(item) for item in windows)
    count = len(windows)
    return {
        "sample_size": sample_size,
        "window_count": count,
        "net_positive_probability": sum(value > 0 for value in net) / count,
        "expectancy_positive_probability": sum(float(item["expectancy_r"]) > 0 for item in windows) / count,
        "pf_ge_1_10_probability": sum(float(item["profit_factor"]) >= 1.10 for item in windows) / count,
        "all_gates_pass_count": pass_count,
        "all_gates_pass_probability": pass_count / count,
        "median_net_r": statistics.median(net),
        "net_r_p05": _quantile(net, 0.05),
        "net_r_p95": _quantile(net, 0.95),
        "worst_net_r": min(net),
        "best_net_r": max(net),
        "median_drawdown_r": statistics.median(drawdown),
        "drawdown_r_p95": _quantile(drawdown, 0.95),
    }


def _simulation_summary(
    net: Sequence[float], drawdowns: Sequence[float], streaks: Sequence[int], pf_ge: int, gate: int
) -> dict[str, Any]:
    count = len(net)
    return {
        "run_count": count,
        "net_positive_probability": sum(value > 0 for value in net) / count,
        "expectancy_positive_probability": sum(value > 0 for value in net) / count,
        "pf_ge_1_10_probability": pf_ge / count,
        "all_gate_pass_probability": gate / count,
        "net_r_p01": _quantile(net, 0.01),
        "net_r_p05": _quantile(net, 0.05),
        "net_r_p50": _quantile(net, 0.50),
        "net_r_p95": _quantile(net, 0.95),
        "net_r_p99": _quantile(net, 0.99),
        "drawdown_p50": _quantile(drawdowns, 0.50),
        "drawdown_p95": _quantile(drawdowns, 0.95),
        "drawdown_p99": _quantile(drawdowns, 0.99),
        "loss_streak_p50": _quantile(streaks, 0.50),
        "loss_streak_p95": _quantile(streaks, 0.95),
        "loss_streak_p99": _quantile(streaks, 0.99),
    }


def ordinary_bootstrap(
    values: Sequence[float], sample_size: int, runs: int = ORDINARY_BOOTSTRAP_RUNS, seed: int = SEED
) -> dict[str, Any]:
    generator = random.Random(seed)
    population = list(map(float, values))
    net: list[float] = []
    drawdowns: list[float] = []
    streaks: list[int] = []
    pf_ge = 0
    gate = 0
    for _ in range(runs):
        metrics = sequence_metrics(generator.choices(population, k=sample_size))
        net.append(float(metrics["net_r"]))
        drawdowns.append(float(metrics["max_drawdown_r"]))
        streaks.append(int(metrics["max_loss_streak"]))
        pf_ge += float(metrics["profit_factor"]) >= 1.10
        gate += _paper_gate(metrics)
    return {"sample_size": sample_size, "seed": seed, **_simulation_summary(net, drawdowns, streaks, pf_ge, gate)}


def moving_block_bootstrap(
    values: Sequence[float],
    sample_size: int,
    block_size: int,
    runs: int = BLOCK_BOOTSTRAP_RUNS,
    seed: int = SEED,
) -> dict[str, Any]:
    generator = random.Random(seed)
    population = list(map(float, values))
    max_start = len(population) - block_size
    blocks_needed = math.ceil(sample_size / block_size)
    net: list[float] = []
    drawdowns: list[float] = []
    streaks: list[int] = []
    pf_ge = 0
    gate = 0
    for _ in range(runs):
        sample: list[float] = []
        for _block in range(blocks_needed):
            start = generator.randrange(max_start + 1)
            sample.extend(population[start : start + block_size])
        metrics = sequence_metrics(sample[:sample_size])
        net.append(float(metrics["net_r"]))
        drawdowns.append(float(metrics["max_drawdown_r"]))
        streaks.append(int(metrics["max_loss_streak"]))
        pf_ge += float(metrics["profit_factor"]) >= 1.10
        gate += _paper_gate(metrics)
    return {
        "sample_size": sample_size,
        "block_size": block_size,
        "seed": seed,
        **_simulation_summary(net, drawdowns, streaks, pf_ge, gate),
    }


def permutation_sequence_risk(
    values: Sequence[float], runs: int = PERMUTATION_RUNS, seed: int = SEED
) -> dict[str, Any]:
    generator = random.Random(seed)
    sample = list(map(float, values))
    drawdowns: list[float] = []
    streaks: list[int] = []
    for _ in range(runs):
        generator.shuffle(sample)
        metrics = sequence_metrics(sample)
        drawdowns.append(float(metrics["max_drawdown_r"]))
        streaks.append(int(metrics["max_loss_streak"]))
    return {
        "run_count": runs,
        "seed": seed,
        "p50_drawdown": _quantile(drawdowns, 0.50),
        "p90_drawdown": _quantile(drawdowns, 0.90),
        "p95_drawdown": _quantile(drawdowns, 0.95),
        "p99_drawdown": _quantile(drawdowns, 0.99),
        "p50_loss_streak": _quantile(streaks, 0.50),
        "p95_loss_streak": _quantile(streaks, 0.95),
        "p99_loss_streak": _quantile(streaks, 0.99),
    }


def chronological_folds(
    trades: Sequence[Mapping[str, Any]], timestamps: Sequence[str], fold_count: int
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index in range(fold_count):
        start_index = len(timestamps) * index // fold_count
        end_index = len(timestamps) * (index + 1) // fold_count - 1
        start = timestamps[start_index]
        end = timestamps[end_index]
        fold = [
            float(trade["realized_r"])
            for trade in trades
            if _timestamp(start) <= _timestamp(str(trade["entry_timestamp_utc"])) <= _timestamp(end)
        ]
        records.append(
            {
                "fold": index + 1,
                "start_timestamp": start,
                "end_timestamp": end,
                **_json_metrics(fold),
            }
        )
    return records


def pair_analysis(
    trades: Sequence[Mapping[str, Any]], instruments: Sequence[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped = {instrument: [float(t["realized_r"]) for t in trades if t["instrument"] == instrument] for instrument in instruments}
    records = [{"instrument": instrument, **_json_metrics(values)} for instrument, values in grouped.items()]
    total = sum(sum(values) for values in grouped.values())
    ranked = sorted(grouped.items(), key=lambda item: sum(item[1]), reverse=True)
    share = lambda n: sum(sum(values) for _, values in ranked[:n]) / total if total else 0.0
    net_shares = [(sum(values) / total) if total else 0.0 for values in grouped.values()]
    summary = {
        "TOP_1_NET_R_SHARE": share(1),
        "TOP_3_NET_R_SHARE": share(3),
        "TOP_5_NET_R_SHARE": share(5),
        "TOP_10_NET_R_SHARE": share(10),
        "BOTTOM_5_NET_R": sum(sum(values) for _, values in ranked[-5:]),
        "PROFITABLE_PAIR_COUNT": sum(sum(values) > 0 for values in grouped.values()),
        "LOSING_PAIR_COUNT": sum(sum(values) < 0 for values in grouped.values()),
        "POSITIVE_EXPECTANCY_PAIR_COUNT": sum(statistics.fmean(values) > 0 for values in grouped.values() if values),
        "NEGATIVE_EXPECTANCY_PAIR_COUNT": sum(statistics.fmean(values) < 0 for values in grouped.values() if values),
        "HERFINDAHL_NET_R_CONCENTRATION": sum(value * value for value in net_shares),
        "PAIR_NET_R_RECONCILIATION": sum(sum(values) for values in grouped.values()),
        "TOP_5_EXCEEDS_100_PERCENT_OF_AGGREGATE_NET_R": share(5) > 1.0,
    }
    return records, summary


def leave_one_pair_out(
    trades: Sequence[Mapping[str, Any]], instruments: Sequence[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = []
    raw = []
    for instrument in instruments:
        values = [float(t["realized_r"]) for t in trades if t["instrument"] != instrument]
        metrics = sequence_metrics(values)
        raw.append(metrics)
        records.append({"excluded_instrument": instrument, **_json_metrics(values)})
    return records, {
        "LOPO_COUNT": len(records),
        "LOPO_NET_POSITIVE_COUNT": sum(float(item["net_r"]) > 0 for item in raw),
        "LOPO_EXPECTANCY_POSITIVE_COUNT": sum(float(item["expectancy_r"]) > 0 for item in raw),
        "LOPO_PF_GE_1_10_COUNT": sum(float(item["profit_factor"]) >= 1.10 for item in raw),
        "LOPO_WORST_EXPECTANCY": min(float(item["expectancy_r"]) for item in raw),
        "LOPO_WORST_PF": min(float(item["profit_factor"]) for item in raw),
        "LOPO_WORST_NET_R": min(float(item["net_r"]) for item in raw),
        "LOPO_BEST_EXPECTANCY": max(float(item["expectancy_r"]) for item in raw),
    }


def leave_five_pairs_out(
    trades: Sequence[Mapping[str, Any]], instruments: Sequence[str], runs: int = L5O_RUNS, seed: int = SEED
) -> dict[str, Any]:
    generator = random.Random(seed)
    exclusions: set[tuple[str, ...]] = set()
    while len(exclusions) < runs:
        exclusions.add(tuple(sorted(generator.sample(list(instruments), 5))))
    metrics = [
        sequence_metrics([float(t["realized_r"]) for t in trades if t["instrument"] not in excluded])
        for excluded in sorted(exclusions)
    ]
    return {
        "run_count": len(metrics),
        "seed": seed,
        "expectancy_positive_probability": sum(float(item["expectancy_r"]) > 0 for item in metrics) / len(metrics),
        "pf_ge_1_10_probability": sum(float(item["profit_factor"]) >= 1.10 for item in metrics) / len(metrics),
        "net_positive_probability": sum(float(item["net_r"]) > 0 for item in metrics) / len(metrics),
        "all_gate_pass_probability": sum(_paper_gate(item) for item in metrics) / len(metrics),
    }


def volatility_regimes(
    trades: Sequence[Mapping[str, Any]], candles_by_pair: Mapping[str, Sequence[Any]]
) -> list[dict[str, Any]]:
    atr_by_pair = {instrument: atr(candles, period=5) for instrument, candles in candles_by_pair.items()}
    ranked = []
    for trade in trades:
        instrument = str(trade["instrument"])
        entry_index = int(trade["entry_index"])
        value = atr_by_pair[instrument][entry_index - 1]
        if value is None:
            raise ValueError("HISTORICAL_REPRODUCTION_FAILED")
        ranked.append((float(value) / float(trade["entry_price"]), str(trade["trade_id"]), trade))
    ranked.sort(key=lambda item: (item[0], item[1]))
    groups: list[list[float]] = [[] for _ in range(4)]
    for index, (_value, _trade_id, trade) in enumerate(ranked):
        groups[min(3, index * 4 // len(ranked))].append(float(trade["realized_r"]))
    return [{"quartile": f"Q{index + 1}", **_json_metrics(group)} for index, group in enumerate(groups)]


def grouped_time_diagnostics(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    hours: dict[int, list[float]] = defaultdict(list)
    weekdays: dict[int, list[float]] = defaultdict(list)
    for trade in trades:
        when = _timestamp(str(trade["entry_timestamp_utc"]))
        hours[when.hour].append(float(trade["realized_r"]))
        weekdays[when.weekday()].append(float(trade["realized_r"]))
    hour_records = [{"utc_hour": hour, **_json_metrics(hours.get(hour, []))} for hour in range(24)]
    weekday_names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
    weekday_records = [{"weekday": name, **_json_metrics(weekdays.get(index, []))} for index, name in enumerate(weekday_names)]
    hour_expectancy = [float(item["expectancy_r"]) for item in hour_records if item["closed"]]
    return {
        "utc_hour": hour_records,
        "weekday": weekday_records,
        "HOUR_EDGE_DISPERSION": statistics.pstdev(hour_expectancy) if len(hour_expectancy) > 1 else 0.0,
        "HOUR_FILTER_CREATED": False,
        "WEEKDAY_FILTER_CREATED": False,
    }


def path_excursions(
    trades: Sequence[Mapping[str, Any]], candles_by_pair: Mapping[str, Sequence[Any]]
) -> dict[str, Any]:
    thresholds = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)
    mfe_values: list[float] = []
    mae_values: list[float] = []
    giveback: list[float] = []
    reached = {threshold: 0 for threshold in thresholds}
    then_loss = {1.0: 0, 2.0: 0, 3.0: 0}
    reached_5_before = 0
    reached_5_after = 0
    pair_trades: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for trade in trades:
        pair_trades[str(trade["instrument"])].append(trade)
    next_entry_by_id: dict[str, int] = {}
    for group in pair_trades.values():
        ordered = sorted(group, key=lambda item: int(item["entry_index"]))
        for index, trade in enumerate(ordered):
            next_entry_by_id[str(trade["trade_id"])] = (
                int(ordered[index + 1]["entry_index"]) if index + 1 < len(ordered) else -1
            )
    for trade in trades:
        candles = candles_by_pair[str(trade["instrument"])]
        entry_index = int(trade["entry_index"])
        exit_index = int(trade["exit_index"])
        if exit_index >= len(candles) or candles[exit_index].timestamp != trade["exit_timestamp_utc"]:
            raise ValueError("LOOKAHEAD_DETECTED")
        entry = float(trade["entry_price"])
        risk = float(trade["initial_risk_distance"])
        pre_exit = candles[entry_index:exit_index]
        favorable = [(float(candle.high) - entry) / risk for candle in pre_exit]
        adverse = [(entry - float(candle.low)) / risk for candle in pre_exit]
        mfe = max(0.0, max(favorable, default=0.0))
        mae = max(0.0, max(adverse, default=0.0))
        if trade["exit_reason"] == "PROTECTIVE_STOP":
            mae = max(mae, 1.0)
        mfe_values.append(mfe)
        mae_values.append(mae)
        realized = float(trade["realized_r"])
        giveback.append(max(0.0, mfe - max(0.0, realized)))
        for threshold in thresholds:
            reached[threshold] += mfe >= threshold
        for threshold in then_loss:
            then_loss[threshold] += mfe >= threshold and realized < 0
        reached_5_before += mfe >= 5.0
        next_entry = next_entry_by_id[str(trade["trade_id"])]
        post_end = next_entry if next_entry >= 0 else len(candles)
        post = candles[exit_index + 1 : post_end]
        post_reached = any((float(candle.high) - entry) / risk >= 5.0 for candle in post)
        reached_5_after += mfe < 5.0 and post_reached
    count = len(trades)
    result = {
        "MFE_CAUSAL": True,
        "INTRABAR_ORDER_ASSUMPTION": "CONSERVATIVE_EXCLUDE_PRIMARY_EXIT_BAR",
        "COUNTERFACTUAL_5R_HORIZON": "AFTER_PRIMARY_EXIT_UNTIL_NEXT_SAME_PAIR_ENTRY_OR_DEVELOPMENT_END",
        "MEAN_MFE_R": statistics.fmean(mfe_values),
        "MEDIAN_MFE_R": statistics.median(mfe_values),
        "P75_MFE_R": _quantile(mfe_values, 0.75),
        "P90_MFE_R": _quantile(mfe_values, 0.90),
        "P95_MFE_R": _quantile(mfe_values, 0.95),
        "MEAN_MAE_R": statistics.fmean(mae_values),
        "MEDIAN_MAE_R": statistics.median(mae_values),
        "MEAN_PROFIT_GIVEBACK_R": statistics.fmean(giveback),
        "MEDIAN_PROFIT_GIVEBACK_R": statistics.median(giveback),
        "MFE_GE_1R_THEN_LOSS_COUNT": then_loss[1.0],
        "MFE_GE_2R_THEN_LOSS_COUNT": then_loss[2.0],
        "MFE_GE_3R_THEN_LOSS_COUNT": then_loss[3.0],
        "MFE_GE_5R_THEN_EXIT_BELOW_1R_COUNT": sum(
            mfe >= 5.0 and float(trade["realized_r"]) < 1.0 for mfe, trade in zip(mfe_values, trades)
        ),
        "5R_REACH_RATE": reached[5.0] / count,
        "5R_REACHED_BEFORE_PRIMARY_EXIT_COUNT": reached_5_before,
        "5R_REACHED_AFTER_PRIMARY_EXIT_WOULD_HAVE_OCCURRED_COUNT": reached_5_after,
    }
    for threshold in thresholds:
        label = str(threshold).replace(".", "_")
        result[f"REACHED_{label}R_COUNT"] = reached[threshold]
        result[f"REACHED_{label}R_PERCENT"] = reached[threshold] / count * 100.0
    reach_rate = reached[5.0] / count
    result["5R_SHADOW_OBSERVATION_VALUE_CLASSIFICATION"] = (
        "HIGH" if reach_rate >= 0.20 else "MODERATE" if reach_rate >= 0.08 else "LOW" if count >= 100 else "INSUFFICIENT"
    )
    return result


def friction_analysis(values: Sequence[float]) -> dict[str, Any]:
    penalties = (0.00, 0.01, 0.02, 0.05, 0.10, 0.20, 0.30)
    records = []
    for penalty in penalties:
        adjusted = [float(value) - penalty for value in values]
        metrics = _json_metrics(adjusted)
        records.append(
            {
                "adverse_cost_r": penalty,
                **metrics,
                "rolling_30_all_gate_pass_probability": rolling_analysis(adjusted, 30)["all_gates_pass_probability"],
                "rolling_100_all_gate_pass_probability": rolling_analysis(adjusted, 100)["all_gates_pass_probability"],
            }
        )
    breakeven = statistics.fmean(values)
    return {
        "records": records,
        "BREAKEVEN_FRICTION_R": breakeven,
        "MAX_TOLERABLE_MEAN_COST_R": breakeven,
        "EXPECTANCY_ZERO_COST_R": breakeven,
        "NET_R_ZERO_COST_R": breakeven,
        "PF_APPROXIMATELY_ONE_COST_R": breakeven,
        "SYNTHETIC_STRESS_ONLY": True,
    }


def cluster_analysis(trades: Sequence[Mapping[str, Any]], size: int, best: bool) -> dict[str, Any]:
    candidates = []
    for index in range(len(trades) - size + 1):
        window = trades[index : index + size]
        values = [float(item["realized_r"]) for item in window]
        candidates.append((sum(values), index, window, values))
    _net, _index, window, values = (max(candidates) if best else min(candidates))
    return {
        "trade_count": size,
        "start_timestamp": window[0]["entry_timestamp_utc"],
        "end_timestamp": window[-1]["exit_timestamp_utc"],
        **_json_metrics(values),
    }


def time_to_30(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entries = [_timestamp(str(trade["entry_timestamp_utc"])) for trade in trades]
    rolling = [(entries[index + 29] - entries[index]).total_seconds() / 3600.0 for index in range(len(entries) - 29)]
    nonoverlapping = []
    for offset in range(30):
        for index in range(offset, len(entries) - 29, 30):
            nonoverlapping.append((entries[index + 29] - entries[index]).total_seconds() / 3600.0)
    combined = rolling + nonoverlapping
    return {
        "TIME_TO_30_SAMPLE_COUNT": len(combined),
        "TIME_TO_30_ROLLING_SAMPLE_COUNT": len(rolling),
        "TIME_TO_30_NONOVERLAPPING_SAMPLE_COUNT": len(nonoverlapping),
        "TIME_TO_30_HOURS_P10": _quantile(combined, 0.10),
        "TIME_TO_30_HOURS_P25": _quantile(combined, 0.25),
        "TIME_TO_30_HOURS_P50": _quantile(combined, 0.50),
        "TIME_TO_30_HOURS_P75": _quantile(combined, 0.75),
        "TIME_TO_30_HOURS_P90": _quantile(combined, 0.90),
        "TIME_TO_30_HOURS_P95": _quantile(combined, 0.95),
        "TRADING_DAYS_TO_30_P50": _quantile(combined, 0.50) / 24.0,
        "TRADING_DAYS_TO_30_P90": _quantile(combined, 0.90) / 24.0,
        "TRADING_DAY_DEFINITION": "24_MARKET_HOURS_NOT_CALENDAR_PROMISE",
    }


def confidence_intervals(
    values: Sequence[float], runs: int = CI_BOOTSTRAP_RUNS, seed: int = SEED
) -> dict[str, Any]:
    generator = random.Random(seed)
    population = list(map(float, values))
    size = len(population)
    expectancy: list[float] = []
    win_rate: list[float] = []
    net_30: list[float] = []
    pf: list[float] = []
    for _ in range(runs):
        metrics = sequence_metrics(generator.choices(population, k=size))
        expectation = float(metrics["expectancy_r"])
        expectancy.append(expectation)
        win_rate.append(float(metrics["win_rate"]))
        net_30.append(expectation * 30.0)
        factor = float(metrics["profit_factor"])
        if math.isfinite(factor):
            pf.append(factor)
    low = _quantile(expectancy, 0.025)
    high = _quantile(expectancy, 0.975)
    return {
        "run_count": runs,
        "seed": seed,
        "EXPECTANCY_CI95_LOW": low,
        "EXPECTANCY_CI95_HIGH": high,
        "WIN_RATE_CI95_LOW": _quantile(win_rate, 0.025),
        "WIN_RATE_CI95_HIGH": _quantile(win_rate, 0.975),
        "MEAN_TRADE_R_CI95_LOW": low,
        "MEAN_TRADE_R_CI95_HIGH": high,
        "NET_R_PER_30_CI95_LOW": _quantile(net_30, 0.025),
        "NET_R_PER_30_CI95_HIGH": _quantile(net_30, 0.975),
        "PROFIT_FACTOR_CI95_LOW": _quantile(pf, 0.025),
        "PROFIT_FACTOR_CI95_HIGH": _quantile(pf, 0.975),
        "PROFIT_FACTOR_REPRESENTABLE_RUN_COUNT": len(pf),
        "EXPECTANCY_HIGH_CONFIDENCE_POSITIVE": low > 0,
    }


def false_confidence_analysis(values: Sequence[float]) -> dict[str, Any]:
    comparable = 0
    passes = 0
    later_poor = 0
    for index in range(len(values) - 59):
        current = sequence_metrics(values[index : index + 30])
        following = sequence_metrics(values[index + 30 : index + 60])
        comparable += 1
        if _paper_gate(current):
            passes += 1
            if float(following["expectancy_r"]) <= 0 or float(following["profit_factor"]) < 1.0:
                later_poor += 1
    rate = later_poor / passes if passes else 0.0
    return {
        "COMPARABLE_CHRONOLOGICAL_30_PAIR_COUNT": comparable,
        "CURRENT_30_PASS_COUNT": passes,
        "PASS_THEN_NEXT_30_POOR_COUNT": later_poor,
        "PASS_THEN_NEXT_30_POOR_PROBABILITY": rate,
        "PAPER30_FALSE_CONFIDENCE_PROBABILITY": rate,
        "PAPER30_FALSE_CONFIDENCE_RISK": "LOW" if rate < 0.20 else "MODERATE" if rate < 0.40 else "HIGH",
        "POOR_LATER_DEFINITION": "NEXT_CONTIGUOUS_30_HAS_NONPOSITIVE_EXPECTANCY_OR_PF_BELOW_1_0",
    }


def early_late_decay(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(trades)
    comparisons = []
    for fraction in (0.25, 0.50):
        size = int(count * fraction)
        early = _json_metrics([float(item["realized_r"]) for item in trades[:size]])
        late = _json_metrics([float(item["realized_r"]) for item in trades[-size:]])
        early_pf = float(early["profit_factor"] or 0.0)
        late_pf = float(late["profit_factor"] or 0.0)
        comparisons.append(
            {
                "comparison": f"FIRST_{int(fraction * 100)}_VS_FINAL_{int(fraction * 100)}",
                "early": early,
                "late": late,
                "EXPECTANCY_DELTA": late["expectancy_r"] - early["expectancy_r"],
                "PF_DELTA": late_pf - early_pf,
                "NET_R_PER_TRADE_DELTA": late["expectancy_r"] - early["expectancy_r"],
                "WIN_RATE_DELTA": late["win_rate"] - early["win_rate"],
            }
        )
    signal = all(float(item["EXPECTANCY_DELTA"]) < -0.05 for item in comparisons)
    return {"comparisons": comparisons, "EDGE_DECAY_SIGNAL": signal, "MATERIAL_EXPECTANCY_DECAY_THRESHOLD_R": -0.05}


def _required_sample_sizes(
    bootstrap: Mapping[int, Mapping[str, Any]], metric: str
) -> dict[str, int | None]:
    return {
        str(threshold): next(
            (size for size in SAMPLE_SIZES if float(bootstrap[size][metric]) >= threshold), None
        )
        for threshold in (0.70, 0.80, 0.90)
    }


def _classify_edge(
    metrics: Mapping[str, Any], ci: Mapping[str, Any], folds: Mapping[int, Sequence[Mapping[str, Any]]],
    pair: Mapping[str, Any], ordinary: Mapping[int, Mapping[str, Any]], block: Sequence[Mapping[str, Any]],
    friction: Mapping[str, Any], serial_risk: bool,
) -> str:
    expectancy = float(metrics["expectancy_r"])
    pf = float(metrics["profit_factor"] or 0.0)
    positive_fold_ratio = sum(
        float(item["expectancy_r"]) > 0 for group in folds.values() for item in group
    ) / sum(len(group) for group in folds.values())
    block30 = statistics.fmean(
        float(item["all_gate_pass_probability"]) for item in block if item["sample_size"] == 30
    )
    if expectancy <= 0 and pf <= 1.0:
        return "HISTORICAL_EDGE_NEGATIVE"
    if expectancy <= 0 or float(ci["EXPECTANCY_CI95_HIGH"]) <= 0:
        return "HISTORICAL_EDGE_INCONCLUSIVE"
    broad = (
        bool(ci["EXPECTANCY_HIGH_CONFIDENCE_POSITIVE"])
        and positive_fold_ratio >= 0.75
        and float(pair["TOP_5_NET_R_SHARE"]) <= 0.80
        and float(ordinary[30]["all_gate_pass_probability"]) >= 0.70
        and block30 >= 0.65
        and float(friction["BREAKEVEN_FRICTION_R"]) >= 0.05
        and not serial_risk
    )
    return "HISTORICAL_EDGE_STRONG_AND_BROAD" if broad else "HISTORICAL_EDGE_POSITIVE_BUT_FRAGILE"


def build_report() -> dict[str, Any]:
    print("PHASE 1/6: verifying frozen state and reproducing DEVELOPMENT trades", flush=True)
    pre_hashes = _invariant_hashes()
    forward_pre = _forward_count()
    state = json.loads(PAPER30_STATE_PATH.read_text(encoding="utf-8"))
    if state.get("strategy_config_sha256") != STRATEGY_SHA256 or forward_pre != 0:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")
    guard = json.loads(HOLDOUT_GUARD_PATH.read_text(encoding="utf-8"))
    if guard.get("schema") != "AIOS_FOREX_FINAL_HOLDOUT_ACCESS_GUARD_V1":
        raise ValueError("HISTORICAL_DATA_BOUNDARY_INVALID")

    first = generate_historical_population()
    second_cache = json.loads(REPLAY_CACHE_PATH.read_text(encoding="utf-8"))
    second_candles = _development_candles(second_cache["pair_histories"], first["development_end"])
    second_raw = _raw_closed_buy_trades(second_candles, first["development_end"])
    second_selected = _partition_trades(second_raw, first["train_end"])
    second_trades, second_duplicates = deduplicate_trades(second_selected)
    trades = first["trades"]
    trade_hash_1 = semantic_trade_hash(trades)
    trade_hash_2 = semantic_trade_hash(second_trades)
    if (
        trade_hash_1 != trade_hash_2
        or len(trades) != len(second_trades)
        or first["duplicates"] != second_duplicates
        or _canonical_semantic_trade_hash(second_trades) != EXPECTED_LEGACY_TRADE_HASH
    ):
        raise ValueError("HISTORICAL_REPRODUCTION_FAILED")
    r_parity_failures = sum(
        abs(float(trade["price_r"]) - float(trade["quote_r"])) > 1e-9 for trade in trades
    )
    if r_parity_failures:
        raise ValueError("HISTORICAL_REPRODUCTION_FAILED")
    values = [float(trade["realized_r"]) for trade in trades]
    population_metrics = _json_metrics(values)
    population_metrics.update(
        {
            "SKEWNESS_R": _skewness(values),
            "KURTOSIS_R": _excess_kurtosis(values),
            "KURTOSIS_DEFINITION": "FISHER_EXCESS_POPULATION_MOMENT",
            "P05_TRADE_R": _quantile(values, 0.05),
            "P25_TRADE_R": _quantile(values, 0.25),
            "P50_TRADE_R": _quantile(values, 0.50),
            "P75_TRADE_R": _quantile(values, 0.75),
            "P95_TRADE_R": _quantile(values, 0.95),
        }
    )

    print("PHASE 2/6: rolling windows, folds, pair/regime/time diagnostics", flush=True)
    rolling = {size: rolling_analysis(values, size) for size in SAMPLE_SIZES}
    folds = {count: chronological_folds(trades, first["timestamps"], count) for count in (4, 8, 12)}
    fold_stability = {
        count: {
            "fold_count": len(records),
            "positive_expectancy_count": sum(float(item["expectancy_r"]) > 0 for item in records),
            "pf_ge_1_0_count": sum(float(item["profit_factor"] or 0.0) >= 1.0 for item in records),
            "pf_ge_1_10_count": sum(float(item["profit_factor"] or 0.0) >= 1.10 for item in records),
            "positive_net_r_count": sum(float(item["net_r"]) > 0 for item in records),
        }
        for count, records in folds.items()
    }
    temporal_score = statistics.fmean(
        summary["positive_expectancy_count"] / summary["fold_count"] for summary in fold_stability.values()
    )
    pair_records, pair_summary = pair_analysis(trades, first["instruments"])
    if not math.isclose(float(pair_summary["PAIR_NET_R_RECONCILIATION"]), float(population_metrics["net_r"]), abs_tol=1e-9):
        raise ValueError("STATISTICAL_INTEGRITY_FAILURE")
    lopo_records, lopo_summary = leave_one_pair_out(trades, first["instruments"])
    l5o = leave_five_pairs_out(trades, first["instruments"])
    regimes = volatility_regimes(trades, first["candles_by_pair"])
    regime_pass = sum(float(item["expectancy_r"]) > 0 and float(item["profit_factor"] or 0.0) >= 1.0 for item in regimes)
    time_groups = grouped_time_diagnostics(trades)
    decay = early_late_decay(trades)
    paths = path_excursions(trades, first["candles_by_pair"])
    friction = friction_analysis(values)
    worst = [cluster_analysis(trades, size, False) for size in (10, 20, 30, 50)]
    best = [cluster_analysis(trades, size, True) for size in (10, 20, 30, 50)]
    timing = time_to_30(trades)
    false_confidence = false_confidence_analysis(values)

    print("PHASE 3/6: 300,000 fixed-seed ordinary bootstrap samples", flush=True)
    ordinary = {size: ordinary_bootstrap(values, size) for size in SAMPLE_SIZES}

    print("PHASE 4/6: 120,000 moving-block samples and 50,000 permutations", flush=True)
    block = [moving_block_bootstrap(values, size, block_size) for block_size, size in itertools.product(BLOCK_SIZES, BLOCK_SAMPLE_SIZES)]
    permutation = permutation_sequence_risk(values)
    ordinary30 = ordinary[30]
    block30_probability = statistics.fmean(
        float(item["all_gate_pass_probability"]) for item in block if item["sample_size"] == 30
    )
    block100_probability = statistics.fmean(
        float(item["all_gate_pass_probability"]) for item in block if item["sample_size"] == 100
    )
    serial_difference = max(
        abs(float(item["all_gate_pass_probability"]) - float(ordinary[int(item["sample_size"])]["all_gate_pass_probability"]))
        for item in block
    )
    serial_risk = serial_difference >= 0.05

    print("PHASE 5/6: 50,000 full-population confidence bootstrap samples", flush=True)
    ci = confidence_intervals(values)
    required_net = _required_sample_sizes(ordinary, "net_positive_probability")
    required_pf = _required_sample_sizes(ordinary, "pf_ge_1_10_probability")
    false_rejection = 1.0 - float(ordinary30["all_gate_pass_probability"]) if population_metrics["expectancy_r"] > 0 else None
    edge = _classify_edge(population_metrics, ci, folds, pair_summary, ordinary, block, friction, serial_risk)

    post_hashes = _invariant_hashes()
    forward_post = _forward_count()
    unchanged = pre_hashes == post_hashes and forward_pre == forward_post == 0
    if not unchanged:
        raise ValueError("PAPER30_FORWARD_STATE_CHANGED")
    source_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    first_timestamp = str(trades[0]["entry_timestamp_utc"])
    last_timestamp = max((str(trade["exit_timestamp_utc"]) for trade in trades), key=_timestamp)
    simulation_total = (
        len(SAMPLE_SIZES) * ORDINARY_BOOTSTRAP_RUNS
        + len(BLOCK_SIZES) * len(BLOCK_SAMPLE_SIZES) * BLOCK_BOOTSTRAP_RUNS
        + PERMUTATION_RUNS
        + CI_BOOTSTRAP_RUNS
        + L5O_RUNS
    )

    report = {
        "PACKET_ID": PACKET_ID,
        "LOCK_ID": LOCK_ID,
        "WORKER_IDENTITY": WORKER_IDENTITY,
        "LANE": LANE,
        "REPOSITORY_IDENTITY": REPOSITORY_IDENTITY,
        "AUTHORIZED_MARATHON_EXECUTIONS": AUTHORIZED_MARATHON_EXECUTIONS,
        "ACTUAL_MARATHON_EXECUTIONS": 1,
        "SOURCE_HEAD": source_head,
        "CURRENT_BRANCH": "main",
        "PAPER30_STRATEGY_CONFIG_SHA256": STRATEGY_SHA256,
        "FROZEN_STRATEGY": {
            "TIMEFRAME": "M5",
            "DIRECTION_POLICY": "BUY_ONLY",
            "ATR_PERIOD": 5,
            "SUPERTREND_FACTOR": 2.0,
            "CONFIRMATION": "TRUE_2_CLOSE",
            "MACD_FILTER": "NONE",
            "PRIMARY_EXIT_POLICY": "EXIT_A_BASELINE",
            "PAIR_UNIVERSE_COUNT": 68,
            "SHADOW_5R_AUTHORITY": "OBSERVATION_ONLY",
        },
        "DEVELOPMENT_BOUNDARY": {
            "START_TIMESTAMP": first["timestamps"][0],
            "RECOVERED_TRAIN_END_TIMESTAMP": first["train_end"],
            "END_TIMESTAMP": first["development_end"],
            "RECOVERY_METHOD": "UNIQUE_BOUNDARY_MATCH_TO_PRIOR_AUTHORIZED_DEVELOPMENT_TRADE_HASH",
            "HOLDOUT_V1_ROWS_USED": 0,
            "HOLDOUT_V2_ROWS_USED": 0,
        },
        "RAW_CANDIDATE_COUNT": len(first["raw"]),
        "UNIQUE_HISTORICAL_TRADE_COUNT": len(trades),
        "MAXIMUM_UNIQUE_CAUSAL_HISTORICAL_TRADE_COUNT": len(trades),
        "DUPLICATE_HISTORICAL_TRADE_COUNT": first["duplicates"],
        "HISTORICAL_PAIR_COUNT": len(first["instruments"]),
        "FIRST_HISTORICAL_TRADE_TIMESTAMP": first_timestamp,
        "LAST_HISTORICAL_TRADE_TIMESTAMP": last_timestamp,
        "HISTORICAL_TIMESPAN_HOURS": (_timestamp(last_timestamp) - _timestamp(first_timestamp)).total_seconds() / 3600.0,
        "UNIQUE_HISTORICAL_TRADE_LIMIT_REACHED": len(trades) < 3000,
        "UNIQUE_HISTORICAL_TRADES": len(trades),
        "ROLLING_WINDOWS": sum(item["window_count"] for item in rolling.values()),
        "RESAMPLED_SIMULATIONS": simulation_total - L5O_RUNS,
        "SIMULATION_TOTAL_COUNT": simulation_total,
        "HISTORICAL_TRADE_HASH_RUN_1": trade_hash_1,
        "HISTORICAL_TRADE_HASH_RUN_2": trade_hash_2,
        "HISTORICAL_TRADE_HASH": trade_hash_1,
        "PRIOR_CANONICAL_TRADE_HASH": EXPECTED_LEGACY_TRADE_HASH,
        "HISTORICAL_REPRODUCIBLE": True,
        "R_PARITY_FAILURES": r_parity_failures,
        "FULL_POPULATION_METRICS": population_metrics,
        "CLOSED": population_metrics["closed"],
        "WINS": population_metrics["wins"],
        "LOSSES": population_metrics["losses"],
        "FLATS": population_metrics["flats"],
        "WIN_RATE": population_metrics["win_rate"],
        "AVERAGE_WIN_R": population_metrics["average_win_r"],
        "AVERAGE_LOSS_R": population_metrics["average_loss_r"],
        "EXPECTANCY_R": population_metrics["expectancy_r"],
        "PROFIT_FACTOR": population_metrics["profit_factor"],
        "NET_R": population_metrics["net_r"],
        "MAX_DRAWDOWN_R": population_metrics["max_drawdown_r"],
        "MAX_LOSS_STREAK": population_metrics["max_loss_streak"],
        "ROLLING_SAMPLE_SIZE_LADDER": [rolling[size] for size in SAMPLE_SIZES],
        "ROLLING_30_WINDOW_COUNT": rolling[30]["window_count"],
        "ROLLING_30_PASS_COUNT": rolling[30]["all_gates_pass_count"],
        "ROLLING_30_PASS_PERCENT": rolling[30]["all_gates_pass_probability"] * 100.0,
        "ROLLING_30_NET_POSITIVE_PERCENT": rolling[30]["net_positive_probability"] * 100.0,
        "ROLLING_30_EXPECTANCY_POSITIVE_PERCENT": rolling[30]["expectancy_positive_probability"] * 100.0,
        "ROLLING_30_PF_GE_1_10_PERCENT": rolling[30]["pf_ge_1_10_probability"] * 100.0,
        "ROLLING_30_ALL_GATE_PASS_PERCENT": rolling[30]["all_gates_pass_probability"] * 100.0,
        "ORDINARY_BOOTSTRAP": [ordinary[size] for size in SAMPLE_SIZES],
        "PRIMARY_ORDINARY_BOOTSTRAP_SAMPLE_SIZES": list(PRIMARY_BOOTSTRAP_SIZES),
        "SUPPLEMENTAL_SAMPLE_SIZE_LADDER_BOOTSTRAP_SIZES": list(SUPPLEMENTAL_BOOTSTRAP_SIZES),
        "ORDINARY_BOOTSTRAP_RUN_COUNT_PER_SAMPLE_SIZE": ORDINARY_BOOTSTRAP_RUNS,
        "MOVING_BLOCK_BOOTSTRAP": block,
        "BLOCK_BOOTSTRAP_RUN_COUNT_PER_CONFIGURATION": BLOCK_BOOTSTRAP_RUNS,
        "MONTE_CARLO_SEQUENCE_PERMUTATION": permutation,
        "CHRONOLOGICAL_FOLDS": {str(count): records for count, records in folds.items()},
        "CHRONOLOGICAL_FOLD_STABILITY": {str(count): summary for count, summary in fold_stability.items()},
        "TEMPORAL_EDGE_STABILITY_SCORE": temporal_score,
        "EARLY_VS_LATE_DECAY": decay,
        "EDGE_DECAY_SIGNAL": decay["EDGE_DECAY_SIGNAL"],
        "PAIR_CONTRIBUTION": pair_records,
        **pair_summary,
        "LEAVE_ONE_PAIR_OUT": lopo_records,
        **lopo_summary,
        "LEAVE_FIVE_PAIRS_OUT": l5o,
        "VOLATILITY_REGIMES": regimes,
        "REGIME_STABILITY_PASS_COUNT": regime_pass,
        "REGIME_FILTER_CREATED": False,
        "TIME_DIAGNOSTICS": time_groups,
        "PATH_EXCURSIONS": paths,
        "LATENCY_AND_COST_STRESS": friction,
        "WORST_CLUSTERS": worst,
        "BEST_CLUSTERS": best,
        "TIME_TO_30": timing,
        "CONFIDENCE_INTERVALS": ci,
        "EXPECTANCY_CI95_LOW": ci["EXPECTANCY_CI95_LOW"],
        "EXPECTANCY_CI95_HIGH": ci["EXPECTANCY_CI95_HIGH"],
        "EXPECTANCY_HIGH_CONFIDENCE_POSITIVE": ci["EXPECTANCY_HIGH_CONFIDENCE_POSITIVE"],
        "FALSE_CONFIDENCE_ANALYSIS": false_confidence,
        "PAPER30_FALSE_CONFIDENCE_PROBABILITY": false_confidence["PAPER30_FALSE_CONFIDENCE_PROBABILITY"],
        "PAPER30_FALSE_CONFIDENCE_RISK": false_confidence["PAPER30_FALSE_CONFIDENCE_RISK"],
        "PAPER30_FALSE_REJECTION_PROBABILITY": false_rejection,
        "REQUIRED_SAMPLE_SIZE_NET_POSITIVE": required_net,
        "REQUIRED_SAMPLE_SIZE_PF_GE_1_10": required_pf,
        "SAMPLE_SIZE_FOR_70_PERCENT_NET_POSITIVE": required_net["0.7"],
        "SAMPLE_SIZE_FOR_80_PERCENT_NET_POSITIVE": required_net["0.8"],
        "SAMPLE_SIZE_FOR_90_PERCENT_NET_POSITIVE": required_net["0.9"],
        "SAMPLE_SIZE_FOR_70_PERCENT_PF_GE_1_10": required_pf["0.7"],
        "SAMPLE_SIZE_FOR_80_PERCENT_PF_GE_1_10": required_pf["0.8"],
        "SAMPLE_SIZE_FOR_90_PERCENT_PF_GE_1_10": required_pf["0.9"],
        "SERIAL_DEPENDENCE_MAX_ALL_GATE_PROBABILITY_DELTA": serial_difference,
        "SERIAL_DEPENDENCE_RISK": serial_risk,
        "ESTIMATED_P30_NET_POSITIVE_PROBABILITY": ordinary30["net_positive_probability"],
        "ESTIMATED_P30_EXPECTANCY_POSITIVE_PROBABILITY": ordinary30["expectancy_positive_probability"],
        "ESTIMATED_P30_PF_GE_1_10_PROBABILITY": ordinary30["pf_ge_1_10_probability"],
        "ESTIMATED_P30_ALL_GATE_PASS_PROBABILITY": ordinary30["all_gate_pass_probability"],
        "ESTIMATED_P30_DRAWDOWN_P50": ordinary30["drawdown_p50"],
        "ESTIMATED_P30_DRAWDOWN_P95": ordinary30["drawdown_p95"],
        "ESTIMATED_P30_LOSS_STREAK_P50": ordinary30["loss_streak_p50"],
        "ESTIMATED_P30_LOSS_STREAK_P95": ordinary30["loss_streak_p95"],
        "P30_NET_POSITIVE_PROBABILITY": ordinary30["net_positive_probability"],
        "P30_EXPECTANCY_POSITIVE_PROBABILITY": ordinary30["expectancy_positive_probability"],
        "P30_PF_GE_1_10_PROBABILITY": ordinary30["pf_ge_1_10_probability"],
        "P30_ALL_GATE_PASS_PROBABILITY": ordinary30["all_gate_pass_probability"],
        "P50_ALL_GATE_PASS_PROBABILITY": ordinary[50]["all_gate_pass_probability"],
        "P100_ALL_GATE_PASS_PROBABILITY": ordinary[100]["all_gate_pass_probability"],
        "P250_ALL_GATE_PASS_PROBABILITY": ordinary[250]["all_gate_pass_probability"],
        "BOOTSTRAP_30_ALL_GATE_PASS_PROBABILITY": ordinary30["all_gate_pass_probability"],
        "BOOTSTRAP_100_ALL_GATE_PASS_PROBABILITY": ordinary[100]["all_gate_pass_probability"],
        "BLOCK_BOOTSTRAP_30_ALL_GATE_PASS_PROBABILITY": block30_probability,
        "BLOCK_BOOTSTRAP_100_ALL_GATE_PASS_PROBABILITY": block100_probability,
        "REACHED_1R_PERCENT": paths["REACHED_1_0R_PERCENT"],
        "REACHED_2R_PERCENT": paths["REACHED_2_0R_PERCENT"],
        "REACHED_3R_PERCENT": paths["REACHED_3_0R_PERCENT"],
        "REACHED_4R_PERCENT": paths["REACHED_4_0R_PERCENT"],
        "REACHED_5R_PERCENT": paths["REACHED_5_0R_PERCENT"],
        "MEAN_MFE_R": paths["MEAN_MFE_R"],
        "MEAN_PROFIT_GIVEBACK_R": paths["MEAN_PROFIT_GIVEBACK_R"],
        "5R_SHADOW_OBSERVATION_VALUE_CLASSIFICATION": paths["5R_SHADOW_OBSERVATION_VALUE_CLASSIFICATION"],
        "BREAKEVEN_FRICTION_R": friction["BREAKEVEN_FRICTION_R"],
        "MAX_TOLERABLE_MEAN_COST_R": friction["MAX_TOLERABLE_MEAN_COST_R"],
        "TIME_TO_30_HOURS_P50": timing["TIME_TO_30_HOURS_P50"],
        "TIME_TO_30_HOURS_P90": timing["TIME_TO_30_HOURS_P90"],
        "HISTORICAL_EDGE_CLASSIFICATION": edge,
        "PAPER30_INVARIANT_PRE_SHA256": pre_hashes,
        "PAPER30_INVARIANT_POST_SHA256": post_hashes,
        "FORWARD_PAPER30_COUNT_PRE": forward_pre,
        "FORWARD_PAPER30_COUNT_POST": forward_post,
        "HISTORICAL_BACKFILL_TRADE_COUNT": 0,
        "QUALIFYING_FORWARD_TRADES_CREDITED": 0,
        "PAPER30_FORWARD_STATE_UNCHANGED": unchanged,
        "SIMULATION_SEEDS": {
            "ORDINARY_BOOTSTRAP": SEED,
            "BLOCK_BOOTSTRAP": SEED,
            "MONTE_CARLO_PERMUTATION": SEED,
            "L5O": SEED,
            "CONFIDENCE_INTERVAL_BOOTSTRAP": SEED,
        },
        "NETWORK_CALLS": False,
        "BROKER_CALLS": False,
        "BROKER_WRITES": False,
        "PRACTICE_ORDERS": False,
        "LIVE_ORDERS": False,
        "MONEY_MOVEMENT": False,
        "CREDENTIALS_ACCESSED": False,
        "ACCOUNT_IDENTIFIERS_ACCESSED": False,
        "LIVE_EXECUTION_ENABLED": False,
        "STATUS": edge,
    }
    _strict_json(report)
    json.dumps(report, sort_keys=True, allow_nan=False)
    print("PHASE 6/6: integrity and PAPER30 immutability verified", flush=True)
    return report


def run() -> dict[str, Any]:
    report = build_report()
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({"status": result["STATUS"], "result_path": str(RESULT_PATH)}, allow_nan=False))
