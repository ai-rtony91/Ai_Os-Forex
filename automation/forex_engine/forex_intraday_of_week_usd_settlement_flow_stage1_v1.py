"""Bounded Stage-1 H1 screen for the frozen intraday-of-week USD-flow hypothesis."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from automation.forex_engine.forex_intraday_of_week_usd_settlement_flow_stage0_v1 import (
    EXPECTED_CANDIDATE_FINGERPRINTS,
    EXPECTED_MECHANISM_FINGERPRINT,
    H1_CORPUS_ID,
    H1_CORPUS_SHA256,
    H1_MANIFEST_SHA256,
    PAIRS,
    STRATEGY_ID,
    candidate_definitions,
    foreign_per_usd_order_sign,
    variant_foreign_direction,
)


PACKET_ID = "PKT-FOREX-034"
WORKER_ID = "EAST_OCC_69"
STAGE0_ENGINE_SHA256 = "834cf50b01073aebe3a0723a1f88bb5af4ed10d85dfad74e7f12593f3fa1fdd3"
PREREGISTRATION_SHA256 = "a794032d15bd81cc4f6f0a81fea35a232b991ab12ece71df4ad485d4b7e5acf6"
STAGE0_COMPLETION_SHA256 = "dad74e133440a260fe9ee70c0d15304be90cbde73acb9f6cf3d9f94b88fa65c3"
DEVELOPMENT_START = datetime(2015, 1, 1, tzinfo=timezone.utc)
SCORE_START = datetime(2019, 1, 1, tzinfo=timezone.utc)
DEVELOPMENT_END = datetime(2025, 1, 1, tzinfo=timezone.utc)
BASE_SLIPPAGE_PIPS = 0.10
STRESS_SLIPPAGE_PIPS = 0.50
PRIOR_ATTEMPTS = 1195
PRIOR_AFTER_COST_CANDIDATES = 143

FROZEN_BASELINES = (
    "NO_TRADE_ZERO_EXPECTANCY",
    "MATCHED_DETERMINISTIC_RANDOM_DIRECTION_IDENTICAL_PAIR_DATES",
    "ALWAYS_LONG_FOREIGN_SAME_WINDOW",
    "ALWAYS_SHORT_FOREIGN_SAME_WINDOW",
    "WEEKDAY_AGNOSTIC_SAME_WINDOW",
    "COST_FREE_GROSS",
    "BASE_AND_STRESS_COST",
)

REQUIRED_JOURNAL_FIELDS = {
    "strategy_id", "candidate_id", "pair", "direction", "signal_timestamp", "entry_timestamp",
    "entry_price", "exit_timestamp", "exit_price", "stop_loss", "take_profit", "spread",
    "modeled_slippage", "initial_equity_risk_fraction", "atr_stop_distance", "planned_time_exit_timestamp",
    "gross_result_r", "net_result_r", "result_r", "entry_reason",
    "exit_reason", "session", "volatility_regime", "trend_range_regime",
    "economic_event_proximity", "filter_results",
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


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("_JPY") else 0.0001


def stream_development_candles(path: Path, cutoff: datetime = DEVELOPMENT_END) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse candles before cutoff and stop at the boundary timestamp before price fields."""
    rows: list[dict[str, Any]] = []
    in_array = False
    in_object = False
    depth = 0
    buffer: list[str] = []
    sentinel: str | None = None
    time_pattern = re.compile(r'"time"\s*:\s*"([^"]+)"')
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
                    buffer = [line]
                    depth = line.count("{") - line.count("}")
                elif stripped.startswith("]"):
                    break
                else:
                    continue
            else:
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

            if in_object and depth == 0:
                payload = "".join(buffer).rstrip(",\r\n ")
                candle = json.loads(payload)
                timestamp = parse_time(str(candle["time"]))
                if timestamp >= DEVELOPMENT_START and candle.get("complete") is True:
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


def passes_fold_boundary_embargo(timestamp: datetime) -> bool:
    fold_start = datetime(timestamp.year, 1, 1, tzinfo=timezone.utc)
    return timestamp >= fold_start + timedelta(hours=21)


def build_pair_events(pair: str, candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_time = {row["time"]: index for index, row in enumerate(candles)}
    ranges = [0.0] + [true_range(candles, index) for index in range(1, len(candles))]
    events: list[dict[str, Any]] = []
    for index, row in enumerate(candles):
        timestamp = row["time"]
        if timestamp < SCORE_START or timestamp >= DEVELOPMENT_END or timestamp.hour != 0 or timestamp.weekday() >= 5:
            continue
        if not passes_fold_boundary_embargo(timestamp):
            continue
        exit_time = timestamp.replace(hour=20)
        exit_index = by_time.get(exit_time)
        if exit_index is None or exit_index <= index or index < 121:
            continue
        if any(candles[position + 1]["time"].timestamp() - candles[position]["time"].timestamp() != 3600 for position in range(index, exit_index)):
            continue
        atr_window = ranges[index - 20:index]
        atr = sum(atr_window) / 20.0
        if atr <= 0:
            continue
        prior_atrs = [sum(ranges[position - 20:position]) / 20.0 for position in range(index - 100, index) if position >= 20]
        volatility_regime = "ABOVE_PRIOR_100H_ATR_MEDIAN" if atr > median(prior_atrs) else "AT_OR_BELOW_PRIOR_100H_ATR_MEDIAN"
        path_length = sum(ranges[index - 20:index])
        displacement = abs(candles[index - 1]["mid"]["c"] - candles[index - 21]["mid"]["c"])
        trend_range_regime = "TREND" if path_length > 0 and displacement / path_length >= 0.35 else "RANGE"
        prior_return = candles[index - 1]["mid"]["c"] - candles[index - 21]["mid"]["c"]
        if prior_return == 0:
            prior_direction = 1 if int(sha256_bytes(f"{pair}|{timestamp.isoformat()}".encode())[-1], 16) % 2 == 0 else -1
        else:
            prior_direction = 1 if prior_return > 0 else -1
        events.append({
            "atr": atr,
            "date": timestamp.date().isoformat(),
            "entry_index": index,
            "entry_timestamp": timestamp,
            "event_id": sha256_bytes(f"{pair}|{timestamp.isoformat()}|00_TO_20".encode()),
            "exit_index": exit_index,
            "fold": timestamp.year - 2018,
            "pair": pair,
            "prior_momentum_foreign_direction": prior_direction * (1 if pair.endswith("_USD") else -1),
            "trend_range_regime": trend_range_regime,
            "volatility_regime": volatility_regime,
            "weekday": timestamp.weekday(),
        })
    return events


def build_capacity(candles_by_pair: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events = [event for pair in PAIRS for event in build_pair_events(pair, candles_by_pair[pair])]
    per_pair = {pair: sum(event["pair"] == pair for event in events) for pair in PAIRS}
    per_fold_pairs = {
        str(fold): len({event["pair"] for event in events if event["fold"] == fold})
        for fold in range(1, 7)
    }
    candidate_counts = {
        item["candidate_id"]: sum(event["weekday"] in item["weekdays"] for event in events)
        for item in candidate_definitions()
    }
    gates = {
        "minimum_complete_pair_days_per_candidate": min(candidate_counts.values()) >= 100,
        "minimum_complete_days_per_pair": min(per_pair.values()) >= 100,
        "minimum_pairs": sum(count > 0 for count in per_pair.values()) >= 10,
        "minimum_pairs_per_each_of_six_folds": min(per_fold_pairs.values()) >= 8,
        "exact_pair_scope": set(candles_by_pair) == set(PAIRS),
    }
    return events, {
        "schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_CAPACITY.v1",
        "packet_id": PACKET_ID,
        "candidate_event_counts": candidate_counts,
        "pair_event_counts": per_pair,
        "fold_pair_counts": per_fold_pairs,
        "gates": gates,
        "capacity_pass": all(gates.values()),
        "outcome_function_calls_before_capacity_verdict": 0,
        "status": "PASS" if all(gates.values()) else "BLOCK_INSUFFICIENT_CAPACITY",
    }


def simulate_trade(candles: list[dict[str, Any]], event: dict[str, Any], order_sign: int, slippage_pips: float | None) -> dict[str, Any]:
    if order_sign not in (-1, 1):
        raise ValueError("ORDER_SIGN_MUST_BE_PLUS_OR_MINUS_ONE")
    entry_index = event["entry_index"]
    exit_index = event["exit_index"]
    atr = event["atr"]
    midpoint_entry = candles[entry_index]["mid"]["o"]
    stop = midpoint_entry - order_sign * atr
    if slippage_pips is None:
        entry = midpoint_entry
        side = "mid"
        slippage = 0.0
    else:
        side = "ask" if order_sign == 1 else "bid"
        slippage = pip_size(event["pair"]) * slippage_pips
        entry = candles[entry_index][side]["o"] + order_sign * slippage

    exit_price: float | None = None
    exit_timestamp = candles[exit_index]["time"]
    exit_reason = "TIME_EXIT_20_00_UTC"
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
        "result_r": order_sign * (exit_price - entry) / atr,
        "stop_loss": stop,
    }


def profit_factor(values: Iterable[float]) -> float | None:
    material = list(values)
    wins = sum(value for value in material if value > 0)
    losses = -sum(value for value in material if value < 0)
    return wins / losses if losses > 0 else None


def expectancy(values: Iterable[float]) -> float:
    material = list(values)
    return sum(material) / len(material) if material else 0.0


def maximum_drawdown_pct(rows: list[dict[str, Any]]) -> float:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[row["date"]].append(row)
    equity = 1.0
    peak = 1.0
    maximum = 0.0
    for date in sorted(by_date):
        daily_return = sum(row["initial_equity_risk_fraction"] * row["net_result_r"] for row in by_date[date])
        equity *= max(0.0, 1.0 + daily_return)
        peak = max(peak, equity)
        maximum = max(maximum, (peak - equity) / peak * 100.0)
    return maximum


def assign_frozen_risk_weights(rows: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["date"]] += 1
    for row in rows:
        row["initial_equity_risk_fraction"] = min(0.00025, 0.0025 / counts[row["date"]])
    daily_totals: dict[str, float] = defaultdict(float)
    for row in rows:
        if row["initial_equity_risk_fraction"] > 0.00025 + 1e-15:
            raise RuntimeError("PAIR_RISK_CAP_EXCEEDED")
        daily_totals[row["date"]] += row["initial_equity_risk_fraction"]
    if any(total > 0.0025 + 1e-15 for total in daily_totals.values()):
        raise RuntimeError("PORTFOLIO_RISK_CAP_EXCEEDED")


def baseline_comparison_pass(candidate_expectancy: float, baselines: dict[str, float]) -> bool:
    return candidate_expectancy > max([0.0, *baselines.values()])


def random_foreign_direction(event_id: str) -> int:
    return 1 if int(event_id[-1], 16) % 2 == 0 else -1


def score_baselines(events: list[dict[str, Any]], candles_by_pair: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    modes = {
        "MATCHED_DETERMINISTIC_RANDOM_DIRECTION_IDENTICAL_PAIR_DATES": lambda event: random_foreign_direction(event["event_id"]),
        "ALWAYS_LONG_FOREIGN_SAME_WINDOW": lambda _event: 1,
        "ALWAYS_SHORT_FOREIGN_SAME_WINDOW": lambda _event: -1,
        "WEEKDAY_AGNOSTIC_SAME_WINDOW": lambda event: event["prior_momentum_foreign_direction"],
    }
    output: dict[str, dict[str, Any]] = {}
    for name, direction_fn in modes.items():
        values = []
        for event in events:
            foreign_direction = direction_fn(event)
            order_sign = foreign_per_usd_order_sign(event["pair"], foreign_direction)
            values.append(simulate_trade(candles_by_pair[event["pair"]], event, order_sign, BASE_SLIPPAGE_PIPS)["result_r"])
        output[name] = {"after_cost_expectancy_r": expectancy(values), "profit_factor": profit_factor(values), "trade_count": len(values)}
    output["NO_TRADE_ZERO_EXPECTANCY"] = {"after_cost_expectancy_r": 0.0, "profit_factor": None, "trade_count": 0}
    return output


def candidate_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pair_expectancy = {pair: expectancy(row["net_result_r"] for row in rows if row["pair"] == pair) for pair in sorted({row["pair"] for row in rows})}
    currency_expectancy = {
        pair.replace("USD_", "").replace("_USD", ""): value
        for pair, value in pair_expectancy.items()
    }
    fold_metrics = {
        str(fold): {
            "after_cost_expectancy_r": expectancy(row["net_result_r"] for row in rows if row["fold"] == fold),
            "trade_count": sum(row["fold"] == fold for row in rows),
        }
        for fold in range(1, 7)
    }
    regime_metrics = {
        regime: {
            "after_cost_expectancy_r": expectancy(row["net_result_r"] for row in rows if row["trend_range_regime"] == regime),
            "trade_count": sum(row["trend_range_regime"] == regime for row in rows),
        }
        for regime in ("TREND", "RANGE")
    }
    gross = expectancy(row["gross_result_r"] for row in rows)
    net = expectancy(row["net_result_r"] for row in rows)
    stress = expectancy(row["stress_result_r"] for row in rows)
    mean_cost = gross - net
    daily_risk: dict[str, float] = defaultdict(float)
    for row in rows:
        daily_risk[row["date"]] += row["initial_equity_risk_fraction"]
    return {
        "gross_expectancy_r": gross,
        "after_cost_expectancy_r": net,
        "stress_expectancy_r": stress,
        "profit_factor": profit_factor(row["net_result_r"] for row in rows),
        "maximum_drawdown_pct": maximum_drawdown_pct(rows),
        "trade_count": len(rows),
        "loss_count": sum(row["net_result_r"] < 0 for row in rows),
        "long_count": sum(row["direction"] == "LONG" for row in rows),
        "short_count": sum(row["direction"] == "SHORT" for row in rows),
        "positive_fold_count": sum(item["after_cost_expectancy_r"] > 0 for item in fold_metrics.values()),
        "positive_pair_count": sum(value > 0 for value in pair_expectancy.values()),
        "positive_currency_count": sum(value > 0 for value in currency_expectancy.values()),
        "break_even_base_cost_multiple": gross / mean_cost if gross > 0 and mean_cost > 0 else 0.0,
        "maximum_pair_initial_risk_fraction": max((row["initial_equity_risk_fraction"] for row in rows), default=0.0),
        "maximum_daily_initial_risk_fraction": max(daily_risk.values(), default=0.0),
        "sparse_days_below_full_portfolio_risk": sum(total < 0.0025 - 1e-15 for total in daily_risk.values()),
        "fold_metrics": fold_metrics,
        "pair_expectancy_r": pair_expectancy,
        "currency_expectancy_r": currency_expectancy,
        "regime_metrics": regime_metrics,
    }


def classify_failures(metrics: dict[str, Any], baseline_pass: bool, bidirectional: bool) -> list[str]:
    failures = []
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
    if metrics["positive_pair_count"] < 10 or metrics["positive_currency_count"] < 6:
        failures.append("INSUFFICIENT_BREADTH")
    if not baseline_pass:
        failures.append("BASELINE_FAILURE")
    if bidirectional and (metrics["long_count"] < 100 or metrics["short_count"] < 100):
        failures.append("DIRECTION_CONCENTRATION")
    return list(dict.fromkeys(failures))


def primary_failure(failures: list[str]) -> str:
    priority = ["NO_GROSS_EDGE", "COST_DESTROYED_EDGE", "BASELINE_FAILURE", "WALK_FORWARD_FAILURE", "EXCESSIVE_DRAWDOWN", "INSUFFICIENT_BREADTH", "DIRECTION_CONCENTRATION"]
    return next((item for item in priority if item in failures), failures[0] if failures else "NONE")


def reverse_identity_check(original: str, reverse: str, rows_by_candidate: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    left = {row["event_id"]: row for row in rows_by_candidate[original]}
    right = {row["event_id"]: row for row in rows_by_candidate[reverse]}
    same_ids = set(left) == set(right)
    keys = ("pair", "date", "signal_timestamp", "entry_timestamp", "planned_time_exit_timestamp", "atr_stop_distance", "spread", "modeled_slippage")
    identity = {f"same_{key}": same_ids and all(left[event_id][key] == right[event_id][key] for event_id in left) for key in keys}
    directions_opposite = same_ids and all(left[event_id]["direction"] != right[event_id]["direction"] for event_id in left)
    return {
        "original": original,
        "reverse": reverse,
        "event_ids_identical": same_ids,
        **identity,
        "directions_opposite": directions_opposite,
        "event_count": len(left),
        "status": "PASS" if same_ids and directions_opposite and all(identity.values()) else "FAIL",
    }


def run(repo_root: Path, output: Path) -> dict[str, Any]:
    stage0_engine = repo_root / "automation/forex_engine/forex_intraday_of_week_usd_settlement_flow_stage0_v1.py"
    prereg_path = repo_root / ".aios/staging/PKT_FOREX_033/run1/AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_PREREGISTRATION.json"
    completion_path = repo_root / ".aios/staging/PKT_FOREX_033/PKT_FOREX_033_COMPLETION.json"
    manifest_path = repo_root / ".aios/runtime/forex_multi_regime_corpus_v3/manifests/manifest.json"
    if sha256_file(stage0_engine) != STAGE0_ENGINE_SHA256:
        raise RuntimeError("STAGE0_ENGINE_SHA256_MISMATCH")
    if sha256_file(prereg_path) != PREREGISTRATION_SHA256:
        raise RuntimeError("PREREGISTRATION_SHA256_MISMATCH")
    if sha256_file(completion_path) != STAGE0_COMPLETION_SHA256:
        raise RuntimeError("STAGE0_COMPLETION_SHA256_MISMATCH")
    if sha256_file(manifest_path) != H1_MANIFEST_SHA256:
        raise RuntimeError("H1_MANIFEST_SHA256_MISMATCH")
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    if prereg["strategy_mechanism_fingerprint"] != EXPECTED_MECHANISM_FINGERPRINT or prereg["direction_rules"]["variants"] != candidate_definitions():
        raise RuntimeError("FROZEN_PREREGISTRATION_DRIFT")
    if tuple(prereg["baselines"]) != FROZEN_BASELINES:
        raise RuntimeError("FROZEN_BASELINE_CONTRACT_DRIFT")
    if completion["result"] != "VALID_STAGE0_ADMISSION_PREREGISTRATION_FROZEN":
        raise RuntimeError("STAGE0_NOT_ADMITTED")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["corpus_id"] != H1_CORPUS_ID or manifest["aggregate_hash"] != H1_CORPUS_SHA256:
        raise RuntimeError("H1_CORPUS_IDENTITY_MISMATCH")
    artifacts = {item["instrument"]: item for item in manifest["sanitized_artifacts"]}
    if not set(PAIRS) <= set(artifacts):
        raise RuntimeError("FROZEN_PAIR_SCOPE_MISSING")

    candles_by_pair: dict[str, list[dict[str, Any]]] = {}
    source_audit: dict[str, Any] = {}
    for pair in PAIRS:
        item = artifacts[pair]
        source_path = repo_root / item["path"]
        if sha256_file(source_path) != item["sha256"]:
            raise RuntimeError(f"SOURCE_HASH_MISMATCH:{pair}")
        candles, boundary = stream_development_candles(source_path)
        if not boundary["stopped_before_validation_outcomes"] or boundary["excluded_row_price_fields_parsed"] != 0:
            raise RuntimeError(f"VALIDATION_BOUNDARY_FAILURE:{pair}")
        candles_by_pair[pair] = candles
        source_audit[pair] = {"development_rows_parsed": len(candles), "source_sha256": item["sha256"], **boundary}

    events, capacity = build_capacity(candles_by_pair)
    if not capacity["capacity_pass"]:
        raise RuntimeError("CAPACITY_GATE_FAILED_BEFORE_OUTCOME_SCORING")

    journal_rows: list[dict[str, Any]] = []
    candidate_results: list[dict[str, Any]] = []
    baseline_audit: dict[str, Any] = {}
    rows_by_candidate: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidate_definitions():
        candidate_events = [event for event in events if event["weekday"] in candidate["weekdays"]]
        rows: list[dict[str, Any]] = []
        for event in candidate_events:
            foreign_direction = variant_foreign_direction(candidate["variant"], event["weekday"])
            order_sign = foreign_per_usd_order_sign(event["pair"], foreign_direction)
            candles = candles_by_pair[event["pair"]]
            gross = simulate_trade(candles, event, order_sign, None)
            net = simulate_trade(candles, event, order_sign, BASE_SLIPPAGE_PIPS)
            stress = simulate_trade(candles, event, order_sign, STRESS_SLIPPAGE_PIPS)
            entry_candle = candles[event["entry_index"]]
            row = {
                "strategy_id": STRATEGY_ID,
                "candidate_id": candidate["candidate_id"],
                "candidate_fingerprint": candidate["candidate_fingerprint"],
                "event_id": event["event_id"],
                "pair": event["pair"],
                "foreign_currency": event["pair"].replace("USD_", "").replace("_USD", ""),
                "direction": "LONG" if order_sign == 1 else "SHORT",
                "foreign_per_usd_direction": "LONG" if foreign_direction == 1 else "SHORT",
                "date": event["date"],
                "weekday": event["weekday"],
                "fold": event["fold"],
                "signal_timestamp": event["entry_timestamp"].isoformat().replace("+00:00", "Z"),
                "entry_timestamp": event["entry_timestamp"].isoformat().replace("+00:00", "Z"),
                "entry_price": net["entry_price"],
                "exit_timestamp": net["exit_timestamp"].isoformat().replace("+00:00", "Z"),
                "exit_price": net["exit_price"],
                "stop_loss": net["stop_loss"],
                "atr_stop_distance": event["atr"],
                "take_profit": None,
                "spread": entry_candle["ask"]["o"] - entry_candle["bid"]["o"],
                "modeled_slippage": BASE_SLIPPAGE_PIPS,
                "modeled_slippage_pips_per_side": BASE_SLIPPAGE_PIPS,
                "planned_time_exit_timestamp": candles[event["exit_index"]]["time"].isoformat().replace("+00:00", "Z"),
                "gross_result_r": gross["result_r"],
                "net_result_r": net["result_r"],
                "result_r": net["result_r"],
                "stress_result_r": stress["result_r"],
                "entry_reason": candidate["variant"],
                "exit_reason": net["exit_reason"],
                "session": "UTC_00_TO_20",
                "volatility_regime": event["volatility_regime"],
                "trend_range_regime": event["trend_range_regime"],
                "economic_event_proximity": "NOT_AVAILABLE_NOT_USED",
                "filter_results": {"weekday_rule": True, "complete_intraday_window": True, "prior_only_atr20": True, "fold_boundary_embargo_21h": True, "rollover_avoided": True},
            }
            rows.append(row)
        assign_frozen_risk_weights(rows)
        journal_rows.extend(rows)
        rows_by_candidate[candidate["candidate_id"]] = rows
        baselines = score_baselines(candidate_events, candles_by_pair)
        metrics = candidate_metrics(rows)
        baselines["COST_FREE_GROSS"] = {
            "gross_expectancy_r": metrics["gross_expectancy_r"],
            "trade_count": metrics["trade_count"],
            "comparison_role": "DIAGNOSTIC_GROSS_VERSUS_NET_NOT_AFTER_COST_COMPETITOR",
        }
        baselines["BASE_AND_STRESS_COST"] = {
            "base_after_cost_expectancy_r": metrics["after_cost_expectancy_r"],
            "stress_after_cost_expectancy_r": metrics["stress_expectancy_r"],
            "trade_count": metrics["trade_count"],
            "comparison_role": "COST_RESISTANCE_DIAGNOSTIC_NOT_SEPARATE_DIRECTION_BASELINE",
        }
        competitor_names = FROZEN_BASELINES[:5]
        comparable = {name: baselines[name]["after_cost_expectancy_r"] for name in competitor_names}
        baseline_pass = baseline_comparison_pass(metrics["after_cost_expectancy_r"], comparable)
        failures = classify_failures(metrics, baseline_pass, candidate["variant"] == "SYMMETRIC_ORIGINAL")
        result = {
            **candidate,
            **metrics,
            "baseline_comparison_pass": baseline_pass,
            "failure_causes": failures,
            "primary_failure_cause": primary_failure(failures),
            "status": "PASS_STAGE1" if not failures else "REJECT_STAGE1",
        }
        candidate_results.append(result)
        baseline_audit[candidate["candidate_id"]] = {"candidate_after_cost_expectancy_r": metrics["after_cost_expectancy_r"], "required_strict_floor_r": max([0.0, *comparable.values()]), "baselines": baselines, "pass": baseline_pass}

    reverse_pairs = [
        ("IDOW-WED_FRI_ORIGINAL_LONG", "IDOW-WED_FRI_EXACT_REVERSED_SHORT"),
        ("IDOW-MON_TUE_ORIGINAL_SHORT", "IDOW-MON_TUE_EXACT_REVERSED_LONG"),
    ]
    reverse_checks = []
    for original, reverse in reverse_pairs:
        reverse_checks.append(reverse_identity_check(original, reverse, rows_by_candidate))
    if not all(item["status"] == "PASS" for item in reverse_checks):
        raise RuntimeError("EXACT_REVERSE_AUDIT_FAILED")
    if any(not REQUIRED_JOURNAL_FIELDS <= set(row) for row in journal_rows):
        raise RuntimeError("TRADE_JOURNAL_REQUIRED_FIELD_MISSING")

    survivors = [item["candidate_id"] for item in candidate_results if item["status"] == "PASS_STAGE1"]
    attempts_after = PRIOR_ATTEMPTS + len(candidate_results)
    candidates_after = PRIOR_AFTER_COST_CANDIDATES + len(candidate_results)
    family_failures = sorted({failure for item in candidate_results for failure in item["failure_causes"]})
    family_primary = primary_failure(family_failures) if family_failures else "NONE"
    rejection_fingerprint = sha256_bytes(canonical_bytes({
        "mechanism_fingerprint": EXPECTED_MECHANISM_FINGERPRINT,
        "candidate_fingerprints": EXPECTED_CANDIDATE_FINGERPRINTS,
        "family_primary_failure": family_primary,
        "family_failure_causes": family_failures,
    }, compact=True))
    results = {
        "schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_RESULTS.v1",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_mechanism_fingerprint": EXPECTED_MECHANISM_FINGERPRINT,
        "candidate_results": candidate_results,
        "stage1_survivors": survivors,
        "candidate_count_scored": len(candidate_results),
        "actual_computational_attempt_lower_bound_before": PRIOR_ATTEMPTS,
        "actual_computational_attempt_lower_bound_after": attempts_after,
        "governed_after_cost_candidates_before": PRIOR_AFTER_COST_CANDIDATES,
        "governed_after_cost_candidates_after": candidates_after,
        "trade_journal_rows": len(journal_rows),
        "loss_count": sum(row["net_result_r"] < 0 for row in journal_rows),
        "validation_rows_opened": 0,
        "final_holdout_rows_opened": 0,
        "status": "STAGE1_SURVIVOR_REQUIRES_STAGE2" if survivors else "VALID_STAGE1_FAILURE",
    }
    acceptance = {
        "schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_ACCEPTANCE.v1",
        "packet_id": PACKET_ID,
        "strict_gates": {"after_cost_expectancy": ">0", "profit_factor": ">=1.05", "maximum_drawdown_pct": "<=15", "positive_folds": ">=4_of_6", "positive_pairs": ">=10", "positive_currencies": ">=6", "cost_stress_expectancy": ">0", "baseline": "strictly_above_zero_and_every_required_baseline"},
        "survivors": survivors,
        "promotion_authorized": False,
        "status": "PASS_TO_STAGE2" if survivors else "NO_STAGE1_SURVIVOR",
    }
    baseline_doc = {
        "schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_BASELINE_AUDIT.v1",
        "packet_id": PACKET_ID,
        "comparison_rule": "candidate_after_cost_expectancy_strictly_greater_than_max_zero_and_required_baseline_expectancies",
        "frozen_baseline_ids": list(FROZEN_BASELINES),
        "semantic_mapping": {
            "WEEKDAY_AGNOSTIC_SAME_WINDOW": "prior 20 completed H1 foreign-per-USD momentum direction on the identical candidate pair-dates; frozen in code before the first outcome run",
            "COST_FREE_GROSS": "candidate gross expectancy diagnostic",
            "BASE_AND_STRESS_COST": "candidate base and stressed executable-cost diagnostic",
        },
        "candidate_audits": baseline_audit,
        "negative_or_zero_candidate_can_pass": False,
        "status": "PASS",
    }
    reverse_doc = {"schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_REVERSE_AUDIT.v1", "packet_id": PACKET_ID, "checks": reverse_checks, "status": "PASS"}
    postmortem = {
        "schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_POSTMORTEM.v1",
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
        "parameter_sensitivity": "NOT_APPLICABLE_ZERO_FITTED_PARAMETERS_FIVE_DIRECTION_VARIANTS_ARE_DISTINCT_CANDIDATES",
        "concentration": "PAIR_CURRENCY_FOLD_AND_TREND_RANGE_REGIME_METRICS_PRESERVED_PER_CANDIDATE",
        "leakage": "PASS_STREAM_STOPPED_AT_FIRST_2025_TIMESTAMP_BEFORE_PRICE_FIELDS",
        "multiple_testing": {"global_attempt_lower_bound_after": attempts_after, "governed_after_cost_candidates_after": candidates_after, "result": "DEFERRED_TO_STAGE2_FOR_ANY_SURVIVOR" if survivors else "FAIL_NO_SURVIVOR_CAN_PASS_SEARCH_ADJUSTMENT"},
        "primary_failure_cause": family_primary,
        "secondary_failure_causes": [item for item in family_failures if item != family_primary],
        "candidate_fingerprints": EXPECTED_CANDIDATE_FINGERPRINTS,
        "strategy_fingerprint": EXPECTED_MECHANISM_FINGERPRINT,
        "rejection_fingerprint": rejection_fingerprint,
        "prohibited_repetitions": ["same fixed weekday directions under renamed labels", "post-hoc best weekday or hour", "pair-specific weekday tuning", "cost removal", "deleting losing trades"],
        "salvageable_evidence": "Only a positive gross result that survives exact inverse, fold, breadth, and cost diagnostics may motivate a materially distinct settlement-flow mechanism; no cosmetic calendar rescue is allowed.",
        "next_distinct_hypothesis": "SELECT_FROM_REMAINING_UNSCORED_NON_CALENDAR_CLUSTER_AFTER_LEDGER_REVIEW",
        "status": "POSTMORTEM_COMPLETE" if not survivors else "NOT_APPLICABLE_STAGE1_SURVIVOR",
    }
    checkpoint = {
        "schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_CHECKPOINT.v1",
        "packet_id": PACKET_ID,
        "result": results["status"],
        "rejection_fingerprint": rejection_fingerprint if not survivors else None,
        "next_action": postmortem["next_distinct_hypothesis"] if not survivors else "FREEZE_SURVIVOR_AND_GENERATE_STAGE2_PACKET",
        "verified_edge": False,
        "validation_rows_opened": 0,
        "final_holdout_rows_opened": 0,
        "commit": "NOT_PERFORMED",
        "push": "NOT_PERFORMED",
    }

    output.mkdir(parents=True, exist_ok=True)
    artifacts_to_write = {
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_ACCEPTANCE.json": canonical_bytes(acceptance),
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_BASELINE_AUDIT.json": canonical_bytes(baseline_doc),
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_CAPACITY.json": canonical_bytes(capacity),
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_CHECKPOINT.json": canonical_bytes(checkpoint),
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_POSTMORTEM.json": canonical_bytes(postmortem),
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_RESULTS.json": canonical_bytes(results),
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_REVERSE_AUDIT.json": canonical_bytes(reverse_doc),
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_TRADE_JOURNAL.jsonl": b"".join(canonical_bytes(row, compact=True) for row in journal_rows),
    }
    files: dict[str, dict[str, Any]] = {}
    for name, payload in sorted(artifacts_to_write.items()):
        (output / name).write_bytes(payload)
        files[name] = {"bytes": len(payload), "sha256": sha256_bytes(payload)}
    source_hashes = {
        "packet": sha256_file(repo_root / "automation/orchestration/work_packets/active/PKT-FOREX-034.md"),
        "engine": sha256_file(Path(__file__)),
        "runner": sha256_file(repo_root / "scripts/forex_delivery/run_forex_intraday_of_week_usd_settlement_flow_stage1_v1.py"),
        "tests": sha256_file(repo_root / "tests/forex_engine/test_forex_intraday_of_week_usd_settlement_flow_stage1_v1.py"),
        "stage0_engine": STAGE0_ENGINE_SHA256,
        "stage0_preregistration": PREREGISTRATION_SHA256,
        "h1_manifest": H1_MANIFEST_SHA256,
    }
    manifest_doc = {
        "schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_MANIFEST.v1",
        "packet_id": PACKET_ID,
        "corpus_id": H1_CORPUS_ID,
        "corpus_sha256": H1_CORPUS_SHA256,
        "development_boundary": DEVELOPMENT_END.isoformat().replace("+00:00", "Z"),
        "source_audit": source_audit,
        "source_hashes": source_hashes,
        "artifact_files": files,
        "safety": {"validation_rows_opened": 0, "final_holdout_rows_opened": 0, "broker_access": False, "credentials_accessed": False, "orders": False},
        "status": "PASS",
    }
    manifest_payload = canonical_bytes(manifest_doc)
    manifest_name = "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_MANIFEST.json"
    (output / manifest_name).write_bytes(manifest_payload)
    files[manifest_name] = {"bytes": len(manifest_payload), "sha256": sha256_bytes(manifest_payload)}
    receipt = {
        "schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_RECEIPT.v1",
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
    (output / "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_RECEIPT.json").write_bytes(receipt_payload)
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
