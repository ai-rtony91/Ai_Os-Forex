"""Development-only Stage-1 screen for frozen CFTC asset-manager weekly-change candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from math import sqrt
from statistics import median, pstdev
from typing import Any, Iterable

from automation.forex_engine.forex_cftc_asset_manager_weekly_change_stage0_v1 import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_MECHANISM_FINGERPRINT,
    FOLD_ENDS,
    H1_CORPUS_ID,
    H1_CORPUS_SHA256,
    INFORMATION_CORPUS_SHA256,
    PRIOR_AFTER_COST_CANDIDATES,
    PRIOR_ATTEMPTS,
    STRATEGY_ID,
    candidate_definitions,
    fold_id,
    load_development_cftc,
    pair_signal_inventory,
    signal_inventory,
)


PACKET_ID = "PKT-FOREX-036"
WORKER_ID = "EAST_OCC_71"
STAGE0_ENGINE_SHA256 = "8dbe5165f198252160c81715d27bc71a3e72b0885c60427fb4f0fa7b08b34b47"
PREREGISTRATION_SHA256 = "8fc26b4ecdbf5af4a60cf33137baff48c59cb37a854c5c97cc29e701d78aa0d6"
STAGE0_COMPLETION_SHA256 = "882f14878c8f65d3e645335ce1a01fe311f1d1c82c0f5e5875fda33b8ff51fae"
H1_MANIFEST_SHA256 = "f784867978464aee59f4b3377eca013237378fd8c3a61c068f8c111ce6451d32"
BASE_SLIPPAGE_PIPS = 0.10
STRESS_SLIPPAGE_PIPS = 0.50
STOP_ATR = 1.5
PAIR_RISK_CAP = 0.0025 / 33.0
PORTFOLIO_RISK_CAP = 0.0025
CURRENCY_GROSS_RISK_CAP = 0.001
SEARCH_ADJUSTED_STANDARD_ERROR_MULTIPLE = 3.8

FROZEN_BASELINES = (
    "NO_TRADE_ZERO_EXPECTANCY",
    "MATCHED_DETERMINISTIC_RANDOM_DIRECTION_IDENTICAL_PAIR_TIMESTAMPS",
    "PRIOR_WEEK_H1_PRICE_ONLY_CONTINUATION_IDENTICAL_TIMESTAMPS",
    "PRIOR_WEEK_H1_PRICE_ONLY_REVERSAL_IDENTICAL_TIMESTAMPS",
    "RAW_UNSTANDARDIZED_ASSET_MANAGER_CHANGE_SIGN",
    "ASSET_MANAGER_NET_LEVEL_SIGN",
    "COST_FREE_GROSS",
    "BASE_AND_STRESS_COST",
)

REQUIRED_JOURNAL_FIELDS = {
    "strategy_id", "candidate_id", "instrument", "direction", "signal_timestamp",
    "entry_timestamp", "entry_price", "exit_timestamp", "exit_price", "stop_loss",
    "take_profit", "spread", "modeled_slippage", "executable_initial_risk_distance", "gross_result_r", "net_result_r",
    "result_r", "entry_reason", "exit_reason", "session", "volatility_regime",
    "trend_range_regime", "spread_regime", "economic_event_proximity", "filter_results",
}


def canonical_bytes(value: Any, *, compact: bool = False) -> bytes:
    options = {"sort_keys": True, "ensure_ascii": True, "allow_nan": False}
    text = json.dumps(value, separators=(",", ":"), **options) if compact else json.dumps(value, indent=2, **options)
    return (text + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_time(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    if "." in text:
        prefix, suffix = text.split(".", 1)
        if "+" in suffix:
            fraction, zone = suffix.split("+", 1)
            text = f"{prefix}.{fraction[:6]}+{zone}"
        elif "-" in suffix:
            fraction, zone = suffix.split("-", 1)
            text = f"{prefix}.{fraction[:6]}-{zone}"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("_JPY") else 0.0001


def stream_development_candles(path: Path, cutoff: datetime = DEVELOPMENT_END) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Stop at the first cutoff timestamp before parsing that row's price fields."""
    rows: list[dict[str, Any]] = []
    in_array = False
    in_object = False
    depth = 0
    buffer: list[str] = []
    skip_object = False
    sentinel: str | None = None
    time_pattern = re.compile(r'"time"\s*:\s*"([^"]+)"')
    warmup = DEVELOPMENT_START - timedelta(days=14)
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not in_array:
                if '"candles"' in line and "[" in line:
                    in_array = True
                continue
            stripped = line.strip()
            if not in_object:
                if stripped.startswith("{"):
                    in_object = True
                    skip_object = False
                    buffer = [line]
                    depth = line.count("{") - line.count("}")
                elif stripped.startswith("]"):
                    break
                else:
                    continue
            else:
                if not skip_object:
                    buffer.append(line)
                depth += line.count("{") - line.count("}")

            match = time_pattern.search(line)
            if match:
                candidate_time = parse_time(match.group(1))
                if candidate_time >= cutoff:
                    sentinel = match.group(1)
                    return rows, {
                        "first_excluded_timestamp": sentinel,
                        "excluded_row_price_fields_parsed": 0,
                        "stopped_before_validation_outcomes": True,
                    }
                if candidate_time < warmup:
                    skip_object = True
                    buffer = []

            if in_object and depth == 0:
                if skip_object:
                    in_object = False
                    skip_object = False
                    buffer = []
                    continue
                candle = json.loads("".join(buffer).rstrip(",\r\n "))
                timestamp = parse_time(str(candle["time"]))
                if timestamp >= warmup and candle.get("complete") is True:
                    rows.append({
                        "time": timestamp,
                        "bid": {key: float(candle["bid"][key]) for key in ("o", "h", "l", "c")},
                        "ask": {key: float(candle["ask"][key]) for key in ("o", "h", "l", "c")},
                        "mid": {key: float(candle["mid"][key]) for key in ("o", "h", "l", "c")},
                    })
                in_object = False
                buffer = []
    return rows, {
        "first_excluded_timestamp": sentinel,
        "excluded_row_price_fields_parsed": 0,
        "stopped_before_validation_outcomes": sentinel is not None,
    }


def true_range(candles: list[dict[str, Any]], index: int) -> float:
    current = candles[index]["mid"]
    prior_close = candles[index - 1]["mid"]["c"]
    return max(current["h"] - current["l"], abs(current["h"] - prior_close), abs(current["l"] - prior_close))


def fold_boundaries(fold: int) -> tuple[datetime, datetime]:
    start = DEVELOPMENT_START if fold == 1 else FOLD_ENDS[fold - 2]
    return start, FOLD_ENDS[fold - 1]


def build_signal_events(histories: dict[str, list[dict[str, Any]]], pairs: tuple[str, ...]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    inventories = {currency: signal_inventory(history) for currency, history in histories.items()}
    for pair in pairs:
        base, quote = pair.split("_")
        for signal in pair_signal_inventory(pair, inventories):
            zscore = signal["pair_zscore"]
            if zscore == 0:
                continue
            raw_change = signal["pair_weekly_change"]
            net_level = signal["pair_normalized_net"]
            events.append({
                "currency": f"{base}-{quote}",
                "base_currency": base,
                "quote_currency": quote,
                "pair": pair,
                "positive_pair_sign": 1,
                "decision": signal["decision"],
                "source_available": signal["source_available"],
                "source_observation": signal["source_observation"],
                "zscore": zscore,
                "zsign": 1 if zscore > 0 else -1,
                "raw_change": raw_change,
                "raw_change_sign": 1 if raw_change > 0 else (-1 if raw_change < 0 else 0),
                "net_level": net_level,
                "net_level_sign": 1 if net_level > 0 else (-1 if net_level < 0 else 0),
                "fold": fold_id(signal["decision"]),
            })
    return sorted(events, key=lambda item: (item["decision"], item["pair"]))


def enrich_events_with_price(events: list[dict[str, Any]], candles_by_pair: dict[str, list[dict[str, Any]]], holding: int) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    indices = {pair: {row["time"]: index for index, row in enumerate(rows)} for pair, rows in candles_by_pair.items()}
    ranges = {pair: [0.0] + [true_range(rows, index) for index in range(1, len(rows))] for pair, rows in candles_by_pair.items()}
    for signal in events:
        pair = signal["pair"]
        candles = candles_by_pair[pair]
        entry_index = indices[pair].get(signal["decision"])
        if entry_index is None or entry_index < 121:
            continue
        exit_index = entry_index + holding
        if exit_index >= len(candles):
            continue
        if candles[exit_index]["time"] != signal["decision"] + timedelta(hours=holding):
            continue
        if any(candles[pos + 1]["time"] - candles[pos]["time"] != timedelta(hours=1) for pos in range(entry_index, exit_index)):
            continue
        fold_start, fold_end = fold_boundaries(signal["fold"])
        if signal["decision"] < fold_start + timedelta(hours=12) or candles[exit_index]["time"] >= fold_end:
            continue
        atr = sum(ranges[pair][entry_index - 20:entry_index]) / 20.0
        if atr <= 0:
            continue
        prior_atrs = [sum(ranges[pair][pos - 20:pos]) / 20.0 for pos in range(entry_index - 100, entry_index) if pos >= 20]
        entry_spread = candles[entry_index]["ask"]["o"] - candles[entry_index]["bid"]["o"]
        prior_spreads = [candles[pos]["ask"]["o"] - candles[pos]["bid"]["o"] for pos in range(entry_index - 100, entry_index)]
        path_length = sum(ranges[pair][entry_index - 20:entry_index])
        displacement = abs(candles[entry_index - 1]["mid"]["c"] - candles[entry_index - 21]["mid"]["c"])
        prior_week_return = candles[entry_index - 1]["mid"]["c"] - candles[entry_index - 121]["mid"]["c"]
        item = dict(signal)
        item.update({
            "holding": holding,
            "entry_index": entry_index,
            "exit_index": exit_index,
            "atr": atr,
            "volatility_regime": "ABOVE_PRIOR_100H_ATR_MEDIAN" if atr > median(prior_atrs) else "AT_OR_BELOW_PRIOR_100H_ATR_MEDIAN",
            "trend_range_regime": "TREND" if path_length > 0 and displacement / path_length >= 0.35 else "RANGE",
            "spread_regime": "ABOVE_PRIOR_100H_SPREAD_MEDIAN" if entry_spread > median(prior_spreads) else "AT_OR_BELOW_PRIOR_100H_SPREAD_MEDIAN",
            "prior_week_pair_sign": 1 if prior_week_return > 0 else (-1 if prior_week_return < 0 else 0),
            "event_id": sha256_bytes(f"{signal['pair']}|{iso_z(signal['decision'])}|H{holding}".encode()),
        })
        enriched.append(item)
    return enriched


def candidate_event_order_sign(variant: str, event: dict[str, Any]) -> int | None:
    positive = event["positive_pair_sign"]
    if variant == "ORIGINAL_LONG_CONTINUATION":
        return positive if event["zsign"] > 0 else None
    if variant == "EXACT_REVERSED_SHORT":
        return -positive if event["zsign"] > 0 else None
    if variant == "ORIGINAL_SHORT_CONTINUATION":
        return -positive if event["zsign"] < 0 else None
    if variant == "EXACT_REVERSED_LONG":
        return positive if event["zsign"] < 0 else None
    if variant == "SYMMETRIC_BIDIRECTIONAL":
        return positive * event["zsign"]
    raise ValueError(f"UNKNOWN_VARIANT:{variant}")


def executable_initial_risk_distance(candles: list[dict[str, Any]], event: dict[str, Any], order_sign: int) -> float:
    """Distance from the executable base-cost entry to the modeled base-cost stop fill."""
    midpoint_entry = candles[event["entry_index"]]["mid"]["o"]
    stop = midpoint_entry - order_sign * STOP_ATR * event["atr"]
    slip = pip_size(event["pair"]) * BASE_SLIPPAGE_PIPS
    entry_side = "ask" if order_sign == 1 else "bid"
    entry = candles[event["entry_index"]][entry_side]["o"] + order_sign * slip
    modeled_stop_fill = stop - order_sign * slip
    distance = abs(entry - modeled_stop_fill)
    if distance <= 0:
        raise RuntimeError("NON_POSITIVE_EXECUTABLE_INITIAL_RISK_DISTANCE")
    return distance


def simulate_trade(
    candles: list[dict[str, Any]],
    event: dict[str, Any],
    order_sign: int,
    slippage_pips: float | None,
    risk_distance: float | None = None,
) -> dict[str, Any]:
    if order_sign not in (-1, 1):
        raise ValueError("ORDER_SIGN_MUST_BE_PLUS_OR_MINUS_ONE")
    entry_index = event["entry_index"]
    exit_index = event["exit_index"]
    stop_distance = STOP_ATR * event["atr"]
    midpoint_entry = candles[entry_index]["mid"]["o"]
    stop = midpoint_entry - order_sign * stop_distance
    if slippage_pips is None:
        entry = midpoint_entry
        slippage = 0.0
    else:
        slippage = pip_size(event["pair"]) * slippage_pips
        entry_side = "ask" if order_sign == 1 else "bid"
        entry = candles[entry_index][entry_side]["o"] + order_sign * slippage
    exit_price: float | None = None
    exit_timestamp = candles[exit_index]["time"]
    exit_reason = f"TIME_EXIT_H{event['holding']}"
    for row in candles[entry_index:exit_index]:
        check_side = "mid" if slippage_pips is None else ("bid" if order_sign == 1 else "ask")
        if order_sign == 1 and row[check_side]["l"] <= stop:
            exit_price = min(stop, row[check_side]["o"]) - slippage
            exit_timestamp = row["time"]
            exit_reason = "ATR_STOP"
            break
        if order_sign == -1 and row[check_side]["h"] >= stop:
            exit_price = max(stop, row[check_side]["o"]) + slippage
            exit_timestamp = row["time"]
            exit_reason = "ATR_STOP"
            break
    if exit_price is None:
        exit_side = "mid" if slippage_pips is None else ("bid" if order_sign == 1 else "ask")
        exit_price = candles[exit_index][exit_side]["o"] - order_sign * slippage
    return {
        "entry_price": entry,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "exit_timestamp": exit_timestamp,
        "result_r": order_sign * (exit_price - entry) / (risk_distance or stop_distance),
        "stop_loss": stop,
        "stop_distance": stop_distance,
    }


def profit_factor(values: Iterable[float]) -> float | None:
    material = list(values)
    wins = sum(value for value in material if value > 0)
    losses = -sum(value for value in material if value < 0)
    return wins / losses if losses > 0 else None


def expectancy(values: Iterable[float]) -> float:
    material = list(values)
    return sum(material) / len(material) if material else 0.0


def baseline_comparison_pass(candidate_expectancy: float, baselines: dict[str, float]) -> bool:
    """A negative or zero candidate can never pass, even if every comparator is worse."""
    return candidate_expectancy > 0.0 and candidate_expectancy > max([0.0, *baselines.values()])


def deterministic_random_sign(event_id: str) -> int:
    return 1 if int(event_id[-1], 16) % 2 == 0 else -1


def assign_event_risk_weights(events: list[dict[str, Any]]) -> None:
    by_entry: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_entry[event["decision"]].append(event)
    for timestamp_events in by_entry.values():
        initial = min(PAIR_RISK_CAP, PORTFOLIO_RISK_CAP / len(timestamp_events))
        currency_totals: dict[str, float] = defaultdict(float)
        for event in timestamp_events:
            currency_totals[event["base_currency"]] += initial / 2.0
            currency_totals[event["quote_currency"]] += initial / 2.0
        scale = min(1.0, CURRENCY_GROSS_RISK_CAP / max(currency_totals.values()))
        for event in timestamp_events:
            event["frozen_initial_equity_risk_fraction"] = initial * scale


def assign_frozen_risk_weights(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        row["initial_equity_risk_fraction"] = row.pop("frozen_initial_equity_risk_fraction")
    totals: dict[str, float] = defaultdict(float)
    currency_totals_by_entry: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        if row["initial_equity_risk_fraction"] > PAIR_RISK_CAP + 1e-15:
            raise RuntimeError("PAIR_RISK_CAP_EXCEEDED")
        totals[row["entry_timestamp"]] += row["initial_equity_risk_fraction"]
        currency_totals_by_entry[(row["entry_timestamp"], row["base_currency"])] += row["initial_equity_risk_fraction"] / 2.0
        currency_totals_by_entry[(row["entry_timestamp"], row["quote_currency"])] += row["initial_equity_risk_fraction"] / 2.0
    if any(value > PORTFOLIO_RISK_CAP + 1e-15 for value in totals.values()):
        raise RuntimeError("PORTFOLIO_RISK_CAP_EXCEEDED")
    if any(value > CURRENCY_GROSS_RISK_CAP + 1e-15 for value in currency_totals_by_entry.values()):
        raise RuntimeError("CURRENCY_GROSS_RISK_CAP_EXCEEDED")


def maximum_drawdown_pct(rows: list[dict[str, Any]]) -> float:
    by_entry: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_entry[row["entry_timestamp"]].append(row)
    equity = 1.0
    peak = 1.0
    maximum = 0.0
    for timestamp in sorted(by_entry):
        period_return = sum(row["initial_equity_risk_fraction"] * row["net_result_r"] for row in by_entry[timestamp])
        equity *= max(0.0, 1.0 + period_return)
        peak = max(peak, equity)
        maximum = max(maximum, (peak - equity) / peak * 100.0)
    return maximum


def concentration_share(rows: list[dict[str, Any]], key: str) -> float:
    profits: dict[str, float] = defaultdict(float)
    for row in rows:
        profits[str(row[key])] += row["net_result_r"]
    positive = {name: value for name, value in profits.items() if value > 0}
    total = sum(positive.values())
    return max(positive.values()) / total if total > 0 else 1.0


def pearson_correlation(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = sqrt(sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right))
    return numerator / denominator if denominator > 0 else 0.0


def candidate_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = sorted({row["instrument"] for row in rows})
    currencies = sorted({currency for row in rows for currency in (row["base_currency"], row["quote_currency"])})
    pair_expectancy = {pair: expectancy(row["net_result_r"] for row in rows if row["instrument"] == pair) for pair in pairs}
    currency_values = {currency: [row["net_result_r"] / 2.0 for row in rows if currency in (row["base_currency"], row["quote_currency"])] for currency in currencies}
    currency_expectancy = {currency: expectancy(values) for currency, values in currency_values.items()}
    currency_profit = {currency: sum(values) for currency, values in currency_values.items()}
    positive_currency_profit = {currency: value for currency, value in currency_profit.items() if value > 0}
    total_positive_currency_profit = sum(positive_currency_profit.values())
    fold_metrics = {str(fold): {"after_cost_expectancy_r": expectancy(row["net_result_r"] for row in rows if row["fold"] == fold), "trade_count": sum(row["fold"] == fold for row in rows)} for fold in range(1, 7)}
    regime_metrics = {}
    for field in ("session", "volatility_regime", "trend_range_regime", "spread_regime"):
        regime_metrics[field] = {name: {"after_cost_expectancy_r": expectancy(row["net_result_r"] for row in rows if row[field] == name), "trade_count": sum(row[field] == name for row in rows)} for name in sorted({row[field] for row in rows})}
    gross = expectancy(row["gross_result_r"] for row in rows)
    net = expectancy(row["net_result_r"] for row in rows)
    stress = expectancy(row["stress_result_r"] for row in rows)
    mean_cost = gross - net
    standard_error = pstdev([row["net_result_r"] for row in rows]) / sqrt(len(rows)) if len(rows) > 1 else float("inf")
    return {
        "predictive_correlation": pearson_correlation([row["signal_zscore"] for row in rows], [row["forward_mid_return_r"] for row in rows]),
        "gross_expectancy_r": gross,
        "after_cost_expectancy_r": net,
        "stress_expectancy_r": stress,
        "profit_factor": profit_factor(row["net_result_r"] for row in rows),
        "win_rate": sum(row["net_result_r"] > 0 for row in rows) / len(rows) if rows else 0.0,
        "average_win_r": expectancy(row["net_result_r"] for row in rows if row["net_result_r"] > 0),
        "average_loss_r": expectancy(row["net_result_r"] for row in rows if row["net_result_r"] < 0),
        "maximum_drawdown_pct": maximum_drawdown_pct(rows),
        "trade_count": len(rows),
        "loss_count": sum(row["net_result_r"] < 0 for row in rows),
        "long_count": sum(row["direction"] == "LONG" for row in rows),
        "short_count": sum(row["direction"] == "SHORT" for row in rows),
        "positive_fold_count": sum(item["after_cost_expectancy_r"] > 0 for item in fold_metrics.values()),
        "positive_pair_count": sum(value > 0 for value in pair_expectancy.values()),
        "positive_currency_count": sum(value > 0 for value in currency_expectancy.values()),
        "largest_pair_positive_profit_share": concentration_share(rows, "instrument"),
        "largest_currency_positive_profit_share": max(positive_currency_profit.values()) / total_positive_currency_profit if total_positive_currency_profit > 0 else 1.0,
        "search_adjusted_standard_error_r": standard_error,
        "search_adjusted_required_expectancy_r": SEARCH_ADJUSTED_STANDARD_ERROR_MULTIPLE * standard_error,
        "search_adjusted_multiple_testing_pass": net > SEARCH_ADJUSTED_STANDARD_ERROR_MULTIPLE * standard_error,
        "break_even_base_cost_multiple": gross / mean_cost if gross > 0 and mean_cost > 0 else 0.0,
        "turnover_trades_per_week": len(rows) / 38.0,
        "pair_expectancy_r": pair_expectancy,
        "currency_expectancy_r": currency_expectancy,
        "fold_metrics": fold_metrics,
        "regime_metrics": regime_metrics,
    }


def baseline_order_sign(name: str, event: dict[str, Any]) -> int:
    if name == "MATCHED_DETERMINISTIC_RANDOM_DIRECTION_IDENTICAL_PAIR_TIMESTAMPS":
        return deterministic_random_sign(event["event_id"])
    if name == "PRIOR_WEEK_H1_PRICE_ONLY_CONTINUATION_IDENTICAL_TIMESTAMPS":
        return event["prior_week_pair_sign"] or deterministic_random_sign(event["event_id"])
    if name == "PRIOR_WEEK_H1_PRICE_ONLY_REVERSAL_IDENTICAL_TIMESTAMPS":
        return -(event["prior_week_pair_sign"] or deterministic_random_sign(event["event_id"]))
    if name == "RAW_UNSTANDARDIZED_ASSET_MANAGER_CHANGE_SIGN":
        return event["positive_pair_sign"] * (event["raw_change_sign"] or deterministic_random_sign(event["event_id"]))
    if name == "ASSET_MANAGER_NET_LEVEL_SIGN":
        return event["positive_pair_sign"] * (event["net_level_sign"] or deterministic_random_sign(event["event_id"]))
    raise ValueError(f"UNKNOWN_BASELINE:{name}")


def score_baselines(events: list[dict[str, Any]], candles_by_pair: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {"NO_TRADE_ZERO_EXPECTANCY": {"after_cost_expectancy_r": 0.0, "profit_factor": None, "trade_count": 0}}
    for name in FROZEN_BASELINES[1:6]:
        values = []
        for event in events:
            order_sign = baseline_order_sign(name, event)
            candles = candles_by_pair[event["pair"]]
            risk_distance = executable_initial_risk_distance(candles, event, order_sign)
            values.append(simulate_trade(candles, event, order_sign, BASE_SLIPPAGE_PIPS, risk_distance)["result_r"])
        output[name] = {"after_cost_expectancy_r": expectancy(values), "profit_factor": profit_factor(values), "trade_count": len(values)}
    return output


def classify_failures(metrics: dict[str, Any], baseline_pass: bool, bidirectional: bool) -> list[str]:
    failures: list[str] = []
    if metrics["gross_expectancy_r"] <= 0:
        failures.append("NO_GROSS_EDGE")
    if metrics["gross_expectancy_r"] > 0 and metrics["after_cost_expectancy_r"] <= 0:
        failures.append("COST_DESTROYED_EDGE")
    if metrics["after_cost_expectancy_r"] > 0 and metrics["stress_expectancy_r"] <= 0:
        failures.append("COST_DESTROYED_EDGE")
    pf = metrics["profit_factor"]
    if pf is not None and pf < 1.05:
        failures.append("BASELINE_FAILURE")
    if metrics["maximum_drawdown_pct"] > 15.0:
        failures.append("EXCESSIVE_DRAWDOWN")
    if metrics["trade_count"] < 100:
        failures.append("INSUFFICIENT_TRADES")
    if metrics["positive_fold_count"] < 4:
        failures.append("WALK_FORWARD_FAILURE")
    if metrics["positive_pair_count"] < 10 or metrics["positive_currency_count"] < 7:
        failures.append("INSUFFICIENT_BREADTH")
    if metrics["largest_pair_positive_profit_share"] > 0.25:
        failures.append("PAIR_CONCENTRATION")
    if metrics["largest_currency_positive_profit_share"] > 0.35:
        failures.append("CURRENCY_CONCENTRATION")
    if not baseline_pass:
        failures.append("BASELINE_FAILURE")
    if bidirectional and (metrics["long_count"] == 0 or metrics["short_count"] == 0):
        failures.append("DIRECTION_CONCENTRATION")
    if not metrics["search_adjusted_multiple_testing_pass"]:
        failures.append("MULTIPLE_TESTING_FAILURE")
    return list(dict.fromkeys(failures))


def primary_failure(failures: list[str]) -> str:
    priority = ["NO_GROSS_EDGE", "COST_DESTROYED_EDGE", "BASELINE_FAILURE", "MULTIPLE_TESTING_FAILURE", "WALK_FORWARD_FAILURE", "INSUFFICIENT_BREADTH", "PAIR_CONCENTRATION", "CURRENCY_CONCENTRATION", "EXCESSIVE_DRAWDOWN", "DIRECTION_CONCENTRATION"]
    return next((item for item in priority if item in failures), failures[0] if failures else "NONE")


def reverse_identity_check(original: str, reverse: str, rows_by_candidate: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    left = {row["event_id"]: row for row in rows_by_candidate[original]}
    right = {row["event_id"]: row for row in rows_by_candidate[reverse]}
    same_ids = set(left) == set(right)
    keys = ("instrument", "base_currency", "quote_currency", "source_observation", "signal_zscore", "signal_timestamp", "entry_timestamp", "planned_time_exit_timestamp", "maximum_holding_h1", "fold", "atr_stop_distance", "initial_equity_risk_fraction", "spread", "modeled_slippage", "stress_modeled_slippage_pips_per_side")
    identity = {f"same_{key}": same_ids and all(left[event_id][key] == right[event_id][key] for event_id in left) for key in keys}
    opposite = same_ids and all(left[event_id]["order_sign"] == -right[event_id]["order_sign"] for event_id in left)
    return {"original": original, "reverse": reverse, "event_ids_identical": same_ids, **identity, "order_sides_arithmetic_opposites": opposite, "event_count": len(left), "status": "PASS" if same_ids and opposite and all(identity.values()) else "FAIL"}


def symmetric_union_check(holding: int, long_rows: list[dict[str, Any]], short_rows: list[dict[str, Any]], symmetric_rows: list[dict[str, Any]]) -> dict[str, Any]:
    originals = {row["event_id"]: row for row in long_rows + short_rows}
    symmetric = {row["event_id"]: row for row in symmetric_rows}
    same_ids = set(originals) == set(symmetric) and len(originals) == len(long_rows) + len(short_rows)
    identity_keys = ("base_currency", "quote_currency", "source_observation", "signal_zscore", "signal_timestamp", "entry_timestamp", "planned_time_exit_timestamp", "maximum_holding_h1", "fold", "atr_stop_distance", "order_sign", "entry_price", "exit_timestamp", "exit_price", "exit_reason", "stop_loss", "executable_initial_risk_distance", "initial_equity_risk_fraction", "spread", "modeled_slippage", "stress_modeled_slippage_pips_per_side", "gross_result_r", "net_result_r", "stress_result_r")
    identity = {f"same_{key}": same_ids and all(originals[event_id][key] == symmetric[event_id][key] for event_id in originals) for key in identity_keys}
    return {"holding_h1": holding, "event_ids_equal_disjoint_original_union": same_ids, **identity, "order_sides_equal_originals": identity["same_order_sign"], "event_count": len(symmetric), "status": "PASS" if same_ids and all(identity.values()) else "FAIL"}


def run(repo_root: Path, output: Path) -> dict[str, Any]:
    stage0_engine = repo_root / "automation/forex_engine/forex_cftc_asset_manager_weekly_change_stage0_v1.py"
    prereg_path = repo_root / ".aios/staging/PKT_FOREX_035/expansion58/run1/AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_PREREGISTRATION.json"
    completion_path = repo_root / ".aios/staging/PKT_FOREX_035/PKT_FOREX_035_EXPANSION58_COMPLETION.json"
    manifest_path = repo_root / ".aios/runtime/forex_multi_regime_corpus_v3/manifests/manifest.json"
    expected = ((stage0_engine, STAGE0_ENGINE_SHA256), (prereg_path, PREREGISTRATION_SHA256), (completion_path, STAGE0_COMPLETION_SHA256), (manifest_path, H1_MANIFEST_SHA256))
    for path, digest in expected:
        if sha256_file(path) != digest:
            raise RuntimeError(f"FROZEN_INPUT_SHA256_MISMATCH:{path.as_posix()}")
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    candidates = candidate_definitions()
    if prereg["strategy_mechanism_fingerprint"] != EXPECTED_MECHANISM_FINGERPRINT or prereg["parameter_grid"]["candidate_count"] != 10:
        raise RuntimeError("FROZEN_PREREGISTRATION_DRIFT")
    if tuple(prereg["baselines"]) != FROZEN_BASELINES or completion["result"] != "ADMIT_STAGE1_LOW_COST_ONLY":
        raise RuntimeError("STAGE0_ADMISSION_OR_BASELINE_DRIFT")
    pairs = tuple(prereg["pair_universe"])
    if len(pairs) != 33 or len(set(pairs)) != 33:
        raise RuntimeError("FROZEN_33_PAIR_SCOPE_DRIFT")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["corpus_id"] != H1_CORPUS_ID or manifest["aggregate_hash"] != H1_CORPUS_SHA256:
        raise RuntimeError("H1_CORPUS_IDENTITY_MISMATCH")
    artifact_map = {item["instrument"]: item for item in manifest["sanitized_artifacts"]}
    if not set(pairs) <= set(artifact_map):
        raise RuntimeError("FROZEN_PAIR_SCOPE_MISSING")

    histories, cftc_audit = load_development_cftc(repo_root)
    signals = build_signal_events(histories, pairs)
    if len(signals) != 1254 or sum(item["zsign"] > 0 for item in signals) != 645 or sum(item["zsign"] < 0 for item in signals) != 609:
        raise RuntimeError("FROZEN_SIGNAL_INVENTORY_DRIFT")

    candles_by_pair: dict[str, list[dict[str, Any]]] = {}
    h1_source_audit: dict[str, Any] = {}
    for pair in pairs:
        artifact = artifact_map[pair]
        source_path = repo_root / artifact["path"]
        if sha256_file(source_path) != artifact["sha256"]:
            raise RuntimeError(f"H1_SOURCE_HASH_MISMATCH:{pair}")
        candles, boundary = stream_development_candles(source_path)
        if not boundary["stopped_before_validation_outcomes"] or boundary["excluded_row_price_fields_parsed"] != 0:
            raise RuntimeError(f"VALIDATION_BOUNDARY_FAILURE:{pair}")
        candles_by_pair[pair] = candles
        h1_source_audit[pair] = {"development_and_warmup_rows_parsed": len(candles), "source_sha256": artifact["sha256"], **boundary}

    events_by_holding = {holding: enrich_events_with_price(signals, candles_by_pair, holding) for holding in (6, 12)}
    if any(len(values) != 1254 for values in events_by_holding.values()):
        raise RuntimeError("COMPLETE_DEVELOPMENT_EVENT_CAPACITY_FAILED")
    for values in events_by_holding.values():
        assign_event_risk_weights(values)
    capacity = {
        "schema": "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_CAPACITY.v2",
        "packet_id": PACKET_ID,
        "signal_count": len(signals),
        "event_counts_by_holding": {str(key): len(value) for key, value in events_by_holding.items()},
        "fold_counts": {str(fold): sum(item["fold"] == fold for item in signals) for fold in range(1, 7)},
        "pair_counts": {pair: sum(item["pair"] == pair for item in signals) for pair in pairs},
        "outcome_function_calls_before_capacity_verdict": 0,
        "status": "PASS",
    }

    journal_rows: list[dict[str, Any]] = []
    candidate_results: list[dict[str, Any]] = []
    baseline_audit: dict[str, Any] = {}
    rows_by_candidate: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        candidate_events = []
        for event in events_by_holding[candidate["maximum_holding_h1"]]:
            order_sign = candidate_event_order_sign(candidate["variant"], event)
            if order_sign is not None:
                candidate_events.append((event, order_sign))
        rows: list[dict[str, Any]] = []
        for event, order_sign in candidate_events:
            candles = candles_by_pair[event["pair"]]
            risk_distance = executable_initial_risk_distance(candles, event, order_sign)
            gross = simulate_trade(candles, event, order_sign, None, risk_distance)
            net = simulate_trade(candles, event, order_sign, BASE_SLIPPAGE_PIPS, risk_distance)
            stress = simulate_trade(candles, event, order_sign, STRESS_SLIPPAGE_PIPS, risk_distance)
            entry_candle = candles[event["entry_index"]]
            rows.append({
                "strategy_id": STRATEGY_ID,
                "candidate_id": candidate["candidate_id"],
                "candidate_fingerprint": candidate["candidate_fingerprint"],
                "event_id": event["event_id"],
                "instrument": event["pair"],
                "pair": event["pair"],
                "foreign_currency": event["currency"],
                "base_currency": event["base_currency"],
                "quote_currency": event["quote_currency"],
                "direction": "LONG" if order_sign == 1 else "SHORT",
                "order_sign": order_sign,
                "fold": event["fold"],
                "source_observation": iso_z(event["source_observation"]),
                "signal_zscore": event["zscore"],
                "signal_timestamp": iso_z(event["source_available"]),
                "decision_timestamp": iso_z(event["decision"]),
                "entry_timestamp": iso_z(event["decision"]),
                "entry_price": net["entry_price"],
                "exit_timestamp": iso_z(net["exit_timestamp"]),
                "exit_price": net["exit_price"],
                "stop_loss": net["stop_loss"],
                "atr_stop_distance": net["stop_distance"],
                "executable_initial_risk_distance": risk_distance,
                "take_profit": None,
                "spread": entry_candle["ask"]["o"] - entry_candle["bid"]["o"],
                "spread_pips": (entry_candle["ask"]["o"] - entry_candle["bid"]["o"]) / pip_size(event["pair"]),
                "modeled_slippage": BASE_SLIPPAGE_PIPS,
                "modeled_slippage_pips_per_side": BASE_SLIPPAGE_PIPS,
                "stress_modeled_slippage_pips_per_side": STRESS_SLIPPAGE_PIPS,
                "maximum_holding_h1": event["holding"],
                "planned_time_exit_timestamp": iso_z(candles[event["exit_index"]]["time"]),
                "gross_result_r": gross["result_r"],
                "forward_mid_return_r": gross["result_r"] * order_sign,
                "net_result_r": net["result_r"],
                "result_r": net["result_r"],
                "stress_result_r": stress["result_r"],
                "entry_reason": candidate["variant"],
                "exit_reason": net["exit_reason"],
                "session": "MONDAY_07_UTC",
                "volatility_regime": event["volatility_regime"],
                "trend_range_regime": event["trend_range_regime"],
                "spread_regime": event["spread_regime"],
                "economic_event_proximity": "NOT_APPLICABLE_NO_CERTIFIED_POINT_IN_TIME_EVENT_SERIES",
                "filter_results": {"cftc_available_before_entry": event["source_available"] < event["decision"], "completed_h1_only": True, "prior_only_atr20": True, "fold_purge_embargo": True, "validation_sealed": True},
                "frozen_initial_equity_risk_fraction": event["frozen_initial_equity_risk_fraction"],
            })
        assign_frozen_risk_weights(rows)
        rows_by_candidate[candidate["candidate_id"]] = rows
        journal_rows.extend(rows)
        baselines = score_baselines([item for item, _ in candidate_events], candles_by_pair)
        metrics = candidate_metrics(rows)
        baselines["COST_FREE_GROSS"] = {"gross_expectancy_r": metrics["gross_expectancy_r"], "trade_count": metrics["trade_count"], "comparison_role": "DIAGNOSTIC"}
        baselines["BASE_AND_STRESS_COST"] = {"base_after_cost_expectancy_r": metrics["after_cost_expectancy_r"], "stress_after_cost_expectancy_r": metrics["stress_expectancy_r"], "trade_count": metrics["trade_count"], "comparison_role": "DIAGNOSTIC"}
        comparable = {name: baselines[name]["after_cost_expectancy_r"] for name in FROZEN_BASELINES[:6]}
        baseline_pass = baseline_comparison_pass(metrics["after_cost_expectancy_r"], comparable)
        failures = classify_failures(metrics, baseline_pass, candidate["variant"] == "SYMMETRIC_BIDIRECTIONAL")
        candidate_results.append({**candidate, **metrics, "baseline_comparison_pass": baseline_pass, "failure_causes": failures, "primary_failure_cause": primary_failure(failures), "status": "PASS_STAGE1" if not failures else "REJECT_STAGE1"})
        baseline_audit[candidate["candidate_id"]] = {"candidate_after_cost_expectancy_r": metrics["after_cost_expectancy_r"], "required_strict_floor_r": max([0.0, *comparable.values()]), "baselines": baselines, "pass": baseline_pass}

    reverse_pairs = []
    for holding in (6, 12):
        reverse_pairs.extend([
            (f"CFTC-AM-WC-ORIGINAL_LONG_CONTINUATION-H{holding}", f"CFTC-AM-WC-EXACT_REVERSED_SHORT-H{holding}"),
            (f"CFTC-AM-WC-ORIGINAL_SHORT_CONTINUATION-H{holding}", f"CFTC-AM-WC-EXACT_REVERSED_LONG-H{holding}"),
        ])
    reverse_checks = [reverse_identity_check(left, right, rows_by_candidate) for left, right in reverse_pairs]
    if not all(item["status"] == "PASS" for item in reverse_checks):
        raise RuntimeError("EXACT_REVERSE_AUDIT_FAILED")
    symmetric_union_checks = []
    for holding in (6, 12):
        long_id = f"CFTC-AM-WC-ORIGINAL_LONG_CONTINUATION-H{holding}"
        short_id = f"CFTC-AM-WC-ORIGINAL_SHORT_CONTINUATION-H{holding}"
        symmetric_id = f"CFTC-AM-WC-SYMMETRIC_BIDIRECTIONAL-H{holding}"
        symmetric_union_checks.append(symmetric_union_check(holding, rows_by_candidate[long_id], rows_by_candidate[short_id], rows_by_candidate[symmetric_id]))
    if not all(item["status"] == "PASS" for item in symmetric_union_checks):
        raise RuntimeError("SYMMETRIC_UNION_AUDIT_FAILED")
    if any(not REQUIRED_JOURNAL_FIELDS <= set(row) for row in journal_rows):
        raise RuntimeError("TRADE_JOURNAL_REQUIRED_FIELD_MISSING")

    survivors = [item["candidate_id"] for item in candidate_results if item["status"] == "PASS_STAGE1"]
    attempts_after = PRIOR_ATTEMPTS + len(candidate_results)
    candidates_after = PRIOR_AFTER_COST_CANDIDATES + len(candidate_results)
    family_failures = sorted({failure for item in candidate_results for failure in item["failure_causes"]})
    family_primary = primary_failure(family_failures) if family_failures else "NONE"
    candidate_fingerprints = [item["candidate_fingerprint"] for item in candidates]
    rejection_fingerprint = sha256_bytes(canonical_bytes({"mechanism_fingerprint": EXPECTED_MECHANISM_FINGERPRINT, "candidate_fingerprints": candidate_fingerprints, "family_primary_failure": family_primary, "family_failure_causes": family_failures}, compact=True))
    results = {
        "schema": "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_RESULTS.v2",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_mechanism_fingerprint": EXPECTED_MECHANISM_FINGERPRINT,
        "candidate_results": candidate_results,
        "stage1_survivors": survivors,
        "candidate_count_scored": len(candidate_results),
        "pair_universe_count": len(pairs),
        "pair_universe": list(pairs),
        "actual_computational_attempt_lower_bound_before": PRIOR_ATTEMPTS,
        "actual_computational_attempt_lower_bound_after": attempts_after,
        "governed_after_cost_candidates_before": PRIOR_AFTER_COST_CANDIDATES,
        "governed_after_cost_candidates_after": candidates_after,
        "trade_journal_rows": len(journal_rows),
        "loss_count": sum(row["net_result_r"] < 0 for row in journal_rows),
        "validation_rows_opened": 0,
        "final_holdout_rows_opened": 0,
        "multiple_testing_result": {"method": "CONSERVATIVE_GLOBAL_3_8_STANDARD_ERROR_SCREEN", "global_governed_candidate_count_after": candidates_after, "passing_candidates": [item["candidate_id"] for item in candidate_results if item["search_adjusted_multiple_testing_pass"]], "status": "PASS_SOME" if any(item["search_adjusted_multiple_testing_pass"] for item in candidate_results) else "FAIL_ALL"},
        "research_throughput": {"mechanisms_screened": 1, "candidates_scored": len(candidate_results), "candidates_rejected": len(candidate_results) - len(survivors), "survivors": len(survivors), "pair_week_signals": len(signals)},
        "status": "STAGE1_SURVIVOR_REQUIRES_STAGE2" if survivors else "VALID_STAGE1_FAILURE",
    }
    acceptance = {
        "schema": "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_ACCEPTANCE.v1",
        "packet_id": PACKET_ID,
        "strict_gates": prereg["stage1_rejection_gates"],
        "survivors": survivors,
        "promotion_authorized": False,
        "status": "PASS_TO_STAGE2_REQUIRES_NEW_PACKET_AUTHORITY" if survivors else "NO_STAGE1_SURVIVOR",
    }
    baseline_doc = {
        "schema": "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_BASELINE_AUDIT.v1",
        "packet_id": PACKET_ID,
        "comparison_rule": "candidate_after_cost_expectancy_strictly_greater_than_zero_and_every_required_after_cost_baseline",
        "frozen_baseline_ids": list(FROZEN_BASELINES),
        "candidate_audits": baseline_audit,
        "negative_or_zero_candidate_can_pass": False,
        "status": "PASS",
    }
    reverse_doc = {"schema": "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_REVERSE_AUDIT.v1", "packet_id": PACKET_ID, "checks": reverse_checks, "symmetric_union_checks": symmetric_union_checks, "status": "PASS"}
    postmortem = {
        "schema": "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_POSTMORTEM.v1",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "economic_mechanism": prereg["economic_mechanism"],
        "exact_rules": {key: prereg[key] for key in ("signal_calculation", "entry_rules", "exit_rules", "direction_rules", "position_sizing", "risk_limits", "cost_model", "parameter_grid")},
        "dataset": prereg["dataset"],
        "pair_universe": prereg["pair_universe"],
        "timeframes": prereg["timeframes"],
        "candidate_results": candidate_results,
        "baseline_audit": baseline_audit,
        "walk_forward": "PASS_ONLY_IF_AT_LEAST_FOUR_OF_SIX_FOLDS_POSITIVE",
        "parameter_sensitivity": "NOT_APPLICABLE_STAGE1_BOUNDED_DIRECTION_AND_HOLDING_CANDIDATES_NO_POST_HOC_TUNING",
        "concentration": "PAIR_CURRENCY_FOLD_VOLATILITY_TREND_RANGE_AND_SPREAD_REGIME_METRICS_PRESERVED_PER_CANDIDATE",
        "leakage": "PASS_CFTC_PUBLICATION_LAG_AND_PRIOR_26_ENFORCED_H1_STREAM_STOPPED_BEFORE_FIRST_VALIDATION_PRICE_FIELDS",
        "multiple_testing": {"method": "CONSERVATIVE_GLOBAL_3_8_STANDARD_ERROR_SCREEN", "global_attempt_lower_bound_after": attempts_after, "governed_after_cost_candidates_after": candidates_after, "passing_candidates": [item["candidate_id"] for item in candidate_results if item["search_adjusted_multiple_testing_pass"]], "result": "PASS_FOR_AT_LEAST_ONE_CANDIDATE_BUT_ALL_GATES_STILL_REQUIRED" if any(item["search_adjusted_multiple_testing_pass"] for item in candidate_results) else "FAIL_ALL_CANDIDATES"},
        "primary_failure_cause": family_primary,
        "secondary_failure_causes": [item for item in family_failures if item != family_primary],
        "candidate_fingerprints": candidate_fingerprints,
        "strategy_fingerprint": EXPECTED_MECHANISM_FINGERPRINT,
        "rejection_fingerprint": rejection_fingerprint,
        "prohibited_repetitions": ["renamed asset-manager weekly-change z-score", "post-hoc direction or holding-period selection", "pair-specific positioning thresholds", "removing executable costs", "dropping losing trades"],
        "salvageable_evidence": "Only preregistered gross, cost, fold, breadth, inverse, and baseline diagnostics may guide a materially distinct mechanism; this family cannot be rescued by grid expansion.",
        "next_distinct_hypothesis": "ROUND_NUMBER_COMPLETED_CROSS_CONTINUATION_VERSUS_APPROACH_REJECTION_STAGE0_DUPLICATE_AND_DATA_ELIGIBILITY_GATE",
        "status": "POSTMORTEM_COMPLETE" if not survivors else "NOT_APPLICABLE_STAGE1_SURVIVOR",
    }
    checkpoint = {
        "schema": "RESUMABLE_EDGE_RESEARCH.v1",
        "packet_id": PACKET_ID,
        "result": results["status"],
        "rejection_fingerprint": rejection_fingerprint if not survivors else None,
        "next_action": postmortem["next_distinct_hypothesis"] if not survivors else "REQUEST_EXACT_STAGE2_PROTECTED_WRITE_AUTHORITY",
        "verified_edge": False,
        "validation_rows_opened": 0,
        "final_holdout_rows_opened": 0,
        "commit": "NOT_PERFORMED",
        "push": "NOT_PERFORMED",
    }

    output.mkdir(parents=True, exist_ok=True)
    artifact_payloads = {
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_ACCEPTANCE.json": canonical_bytes(acceptance),
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_BASELINE_AUDIT.json": canonical_bytes(baseline_doc),
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_CAPACITY.json": canonical_bytes(capacity),
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_CHECKPOINT.json": canonical_bytes(checkpoint),
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_POSTMORTEM.json": canonical_bytes(postmortem),
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_RESULTS.json": canonical_bytes(results),
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_REVERSE_AUDIT.json": canonical_bytes(reverse_doc),
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_TRADE_JOURNAL.jsonl": b"".join(canonical_bytes(row, compact=True) for row in journal_rows),
    }
    files: dict[str, dict[str, Any]] = {}
    for name, payload in sorted(artifact_payloads.items()):
        (output / name).write_bytes(payload)
        files[name] = {"bytes": len(payload), "sha256": sha256_bytes(payload)}
    source_hashes = {
        "packet": sha256_file(repo_root / "automation/orchestration/work_packets/active/PKT-FOREX-036.md"),
        "engine": sha256_file(Path(__file__)),
        "runner": sha256_file(repo_root / "scripts/forex_delivery/run_forex_cftc_asset_manager_weekly_change_stage1_v1.py"),
        "tests": sha256_file(repo_root / "tests/forex_engine/test_forex_cftc_asset_manager_weekly_change_stage1_v1.py"),
        "stage0_engine": STAGE0_ENGINE_SHA256,
        "stage0_preregistration": PREREGISTRATION_SHA256,
        "stage0_completion": STAGE0_COMPLETION_SHA256,
        "h1_manifest": H1_MANIFEST_SHA256,
    }
    manifest_doc = {
        "schema": "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_MANIFEST.v1",
        "packet_id": PACKET_ID,
        "information_corpus_sha256": INFORMATION_CORPUS_SHA256,
        "h1_corpus_id": H1_CORPUS_ID,
        "h1_corpus_sha256": H1_CORPUS_SHA256,
        "development_boundary": iso_z(DEVELOPMENT_END),
        "cftc_source_audit": cftc_audit,
        "h1_source_audit": h1_source_audit,
        "source_hashes": source_hashes,
        "artifact_files": files,
        "safety": {"validation_rows_opened": 0, "final_holdout_rows_opened": 0, "broker_access": False, "credentials_accessed": False, "orders": False},
        "status": "PASS",
    }
    manifest_payload = canonical_bytes(manifest_doc)
    manifest_name = "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_MANIFEST.json"
    (output / manifest_name).write_bytes(manifest_payload)
    files[manifest_name] = {"bytes": len(manifest_payload), "sha256": sha256_bytes(manifest_payload)}
    receipt = {
        "schema": "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "worker_id": WORKER_ID,
        "files": files,
        "aggregate_sha256": sha256_bytes(b"".join(name.encode("utf-8") + b"\0" + bytes.fromhex(details["sha256"]) for name, details in sorted(files.items()))),
        "result": results["status"],
        "candidate_count_scored": len(candidate_results),
        "trade_journal_rows": len(journal_rows),
        "loss_count": results["loss_count"],
        "stage1_survivors": survivors,
        "actual_computational_attempt_lower_bound_after": attempts_after,
        "governed_after_cost_candidates_after": candidates_after,
        "validation_rows_opened": 0,
        "final_holdout_rows_opened": 0,
        "status": "PASS",
    }
    receipt_payload = canonical_bytes(receipt)
    (output / "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_RECEIPT.json").write_bytes(receipt_payload)
    return {"receipt_sha256": sha256_bytes(receipt_payload), **receipt}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.repo_root.resolve(), args.output.resolve())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
