"""Packet 012 bounded feature-edge research over frozen Corpus V2.

This module is research-only: it reads frozen bid/ask candles, writes packet-owned
evidence, and contains no broker or order capability.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import random
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from automation.forex_engine.forex_edge_research_v1 import aggregate, atr, load_pair, metrics, split_contract, stable, ts

CORPUS = Path(".aios/runtime/forex_m5_immutable_corpus_v2")
ROOT = Path(".aios/runtime/forex_feature_edge_research_v2")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_FEATURE_EDGE_RESEARCH_V2_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_FEATURE_EDGE_RESEARCH_V2_REPORT.md")
PACKET = "PKT-EAST-FOREX-EDGE-TO-OANDA-CREDENTIAL-012"
CORPUS_HASH = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
EXECUTOR_HASH = "6dd60fb853a088636f2367a0f58e2a0c305f68ac72f83bd20e9ae6114f2aeba5"
RISK = 0.0025


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    generation: str
    event_family: str
    score_rule: str
    stop_atr: float
    target_r: float
    threshold: float
    top_n: int = 0


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_json(path: Path, value) -> None:
    def json_safe(item):
        if isinstance(item, float) and not math.isfinite(item):
            return "INF" if item > 0 else "-INF"
        if isinstance(item, dict):
            return {key: json_safe(child) for key, child in item.items()}
        if isinstance(item, list):
            return [json_safe(child) for child in item]
        if isinstance(item, tuple):
            return [json_safe(child) for child in item]
        return item

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(json_safe(value), handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_state(**updates):
    current = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    current.update(updates)
    current["updated_utc"] = datetime.now(timezone.utc).isoformat()
    atomic_json(STATE, current)
    atomic_json(ROOT / "campaign_state.json", current)
    return current


def registry() -> list[Candidate]:
    candidates = []
    definitions = [
        ("A", "FAILED_BREAKOUT", "FACTOR_DIVERGENCE"),
        ("A", "FAILED_BREAKOUT", "VOLATILITY_TRANSITION"),
        ("A", "FAILED_BREAKOUT_TRUE2", "TRUE_2_CLOSE"),
        ("A", "TREND_PULLBACK", "FACTOR_ALIGNMENT"),
        ("A", "CROSS_CURRENCY_DIVERGENCE", "RESIDUAL_REVERSION"),
        ("A", "STRENGTH_ALIGNMENT", "FACTOR_CONTINUATION"),
    ]
    for generation, family, rule in definitions:
        for stop, target in ((1.0, 2.0), (1.5, 3.0)):
            candidates.append(Candidate(f"{generation}-{len(candidates)+1:02d}", generation, family, rule, stop, target, 0.0))
    for family in ("FAILED_BREAKOUT", "STRENGTH_ALIGNMENT"):
        for top_n in (1, 3, 5):
            candidates.append(Candidate(f"B-{len(candidates)-11:02d}", "B", family, "CROSS_SECTIONAL_RANK", 1.5, 3.0, 0.0, top_n))
    for strength in (0.01, 0.1, 1.0):
        for threshold in (0.55, 0.60):
            candidates.append(Candidate(f"C-{len(candidates)-17:02d}", "C", "ALL", f"LOGISTIC_L2_{strength}", 1.5, 3.0, threshold))
    for threshold in (0.55, 0.60):
        candidates.append(Candidate(f"C-{len(candidates)-17:02d}", "C", "ALL", "MONOTONIC_LINEAR", 1.0, 2.0, threshold))
    return candidates


def protocol(manifest):
    split = split_contract(manifest)
    candidates = registry()
    body = {
        "schema": "AIOS_FOREX_FEATURE_EDGE_PROTOCOL_V2",
        "corpus_hash": manifest["aggregate_corpus_fingerprint"],
        "executor_hash": EXECUTOR_HASH,
        "eligible_pairs": manifest["eligible_pairs"],
        "partitions": {key: [value[0].isoformat(), value[1].isoformat()] for key, value in split.items()},
        "development_folds": 6,
        "embargo_m5_bars": 288,
        "features": ["factor_spread_1h", "factor_residual_4h", "event_magnitude_atr", "trend_persistence", "spread_risk_ratio", "atr_percentile", "volatility_change", "h1_slope", "h4_slope", "hour_utc", "weekday"],
        "events": ["FAILED_BREAKOUT", "BREAKOUT_RESET", "VOLATILITY_TRANSITION", "TREND_PULLBACK", "CROSS_CURRENCY_DIVERGENCE", "STRENGTH_ALIGNMENT"],
        "targets": ["2R_BEFORE_STOP", "3R_BEFORE_STOP", "4R_BEFORE_STOP", "MFE_R", "MAE_R"],
        "candidate_cap": 30,
        "candidates": [asdict(item) for item in candidates],
        "null_campaigns": 500,
        "bootstrap_resamples": 1000,
        "validation_policy": "OPEN_ONLY_FOR_DEVELOPMENT_PASSERS",
        "holdout_policy": "SEALED_UNTIL_SHORTLIST_HASH",
    }
    body["protocol_hash"] = sha_bytes(stable(body).encode())
    return body, split, candidates


def six_folds(window):
    span = window[1] - window[0]
    return [(window[0] + span * i / 6, window[0] + span * (i + 1) / 6) for i in range(6)]


def completed_aggregate(rows, minutes):
    return aggregate(rows, minutes)


def currency_factor(pair_returns):
    values = defaultdict(list)
    for pair, value in pair_returns.items():
        base, quote = pair.split("_")
        values[base].append(value / 2)
        values[quote].append(-value / 2)
    raw = {currency: sum(items) / len(items) for currency, items in values.items()}
    center = sum(raw.values()) / len(raw) if raw else 0.0
    return {currency: value - center for currency, value in raw.items()}


def build_factor_table(manifest):
    returns = defaultdict(dict)
    for pair in manifest["eligible_pairs"]:
        hourly = completed_aggregate(load_pair(manifest, pair), 60)
        for index in range(24, len(hourly)):
            close = float(hourly[index]["mid"]["c"])
            previous = float(hourly[index - 1]["mid"]["c"])
            returns[hourly[index]["timestamp"]][pair] = math.log(close / previous)
    factors = {stamp: currency_factor(items) for stamp, items in returns.items()}
    atomic_json(ROOT / "currency_factor_table.json", factors)
    return factors


def _future_r(rows, index, side, stop_atr, target_r, current_atr, max_bars=288):
    if index + 1 >= len(rows) or not current_atr:
        return None
    entry_row = rows[index + 1]
    entry = float(entry_row["ask"]["o"] if side == "LONG" else entry_row["bid"]["o"])
    risk = current_atr * stop_atr
    stop = entry - risk if side == "LONG" else entry + risk
    target = entry + target_r * risk if side == "LONG" else entry - target_r * risk
    mfe = 0.0
    mae = 0.0
    for row in rows[index + 1 : min(len(rows), index + max_bars + 2)]:
        if side == "LONG":
            mfe = max(mfe, (float(row["bid"]["h"]) - entry) / risk)
            mae = min(mae, (float(row["bid"]["l"]) - entry) / risk)
            stop_hit = float(row["bid"]["l"]) <= stop
            target_hit = float(row["bid"]["h"]) >= target
        else:
            mfe = max(mfe, (entry - float(row["ask"]["l"])) / risk)
            mae = min(mae, (entry - float(row["ask"]["h"])) / risk)
            stop_hit = float(row["ask"]["h"]) >= stop
            target_hit = float(row["ask"]["l"]) <= target
        if stop_hit:
            return -1.0, mfe, mae
        if target_hit:
            return target_r, mfe, mae
    return 0.0, mfe, mae


def event_rows(pair, rows, factors):
    output = []
    active = set()
    h1 = completed_aggregate(rows, 60)
    factor_by_m5 = {item["timestamp"]: factors.get(item["timestamp"], {}) for item in h1}
    latest_factor = {}
    h1_index = 0
    for index in range(60, len(rows) - 290):
        while h1_index < len(h1) and h1[h1_index]["timestamp"] <= rows[index]["timestamp"]:
            latest_factor = factor_by_m5.get(h1[h1_index]["timestamp"], {})
            h1_index += 1
        current_atr = atr(rows, index)
        if not current_atr:
            continue
        close = float(rows[index]["mid"]["c"])
        previous = float(rows[index - 1]["mid"]["c"])
        prior = rows[index - 20 : index]
        older = rows[index - 21 : index - 1]
        high = max(float(item["mid"]["h"]) for item in prior)
        low = min(float(item["mid"]["l"]) for item in prior)
        old_high = max(float(item["mid"]["h"]) for item in older)
        old_low = min(float(item["mid"]["l"]) for item in older)
        history = [atr(rows, j) for j in range(index - 40, index)]
        history = [value for value in history if value]
        atr_rank = sum(value <= current_atr for value in history) / len(history)
        vol_change = current_atr / (sum(history) / len(history)) - 1
        trend = (close - float(rows[index - 48]["mid"]["c"])) / current_atr
        base, quote = pair.split("_")
        factor_spread = latest_factor.get(base, 0.0) - latest_factor.get(quote, 0.0)
        pair_return = math.log(close / float(rows[index - 12]["mid"]["c"]))
        residual = pair_return - factor_spread
        spread = float(rows[index]["ask"]["c"]) - float(rows[index]["bid"]["c"])
        definitions = []
        if previous > old_high and close <= high:
            definitions.append(("FAILED_BREAKOUT", "SHORT", (previous - high) / current_atr))
        if previous < old_low and close >= low:
            definitions.append(("FAILED_BREAKOUT", "LONG", (low - previous) / current_atr))
        if close > high:
            definitions.append(("BREAKOUT_RESET", "LONG", (close - high) / current_atr))
        elif close < low:
            definitions.append(("BREAKOUT_RESET", "SHORT", (low - close) / current_atr))
        if atr_rank < 1 / 3 and abs(close - previous) > current_atr:
            definitions.append(("VOLATILITY_TRANSITION", "LONG" if close > previous else "SHORT", abs(close - previous) / current_atr))
        ma = sum(float(item["mid"]["c"]) for item in rows[index - 50 : index]) / 50
        if trend > 0 and previous <= ma < close:
            definitions.append(("TREND_PULLBACK", "LONG", abs(close - ma) / current_atr))
        elif trend < 0 and previous >= ma > close:
            definitions.append(("TREND_PULLBACK", "SHORT", abs(close - ma) / current_atr))
        if abs(residual) > current_atr / close:
            definitions.append(("CROSS_CURRENCY_DIVERGENCE", "SHORT" if residual > 0 else "LONG", abs(residual) * close / current_atr))
        if abs(factor_spread) > 0.0001:
            definitions.append(("STRENGTH_ALIGNMENT", "LONG" if factor_spread > 0 else "SHORT", abs(factor_spread) * close / current_atr))
        present = set()
        for family, side, magnitude in definitions:
            key = (family, side)
            present.add(key)
            if key in active:
                continue
            active.add(key)
            event_id = f"{pair}:{family}:{side}:{rows[index]['timestamp']}"
            record = {
                "event_id": event_id,
                "pair": pair,
                "timestamp": rows[index]["timestamp"],
                "family": family,
                "side": side,
                "factor_spread_1h": factor_spread,
                "factor_residual_4h": residual,
                "event_magnitude_atr": magnitude,
                "trend_persistence": trend,
                "spread_risk_ratio": spread / current_atr,
                "atr_percentile": atr_rank,
                "volatility_change": vol_change,
                "hour_utc": ts(rows[index]["timestamp"]).hour,
                "weekday": ts(rows[index]["timestamp"]).weekday(),
            }
            for stop, target in ((1.0, 2.0), (1.5, 3.0), (1.5, 4.0)):
                result = _future_r(rows, index, side, stop, target, current_atr)
                if result:
                    record[f"r_{stop}_{target}"] = result[0]
                    record[f"mfe_{stop}"] = result[1]
                    record[f"mae_{stop}"] = result[2]
            output.append(record)
        active.intersection_update(present)
    return output


def build_events(manifest, factors):
    event_root = ROOT / "events"
    event_root.mkdir(parents=True, exist_ok=True)
    counts = defaultdict(int)
    hashes = {}
    total = 0
    for pair in manifest["eligible_pairs"]:
        target = event_root / f"{pair}.jsonl.gz"
        if target.exists():
            rows = [json.loads(line) for line in gzip.open(target, "rt", encoding="utf-8")]
        else:
            rows = event_rows(pair, load_pair(manifest, pair), factors)
            with gzip.open(target, "wt", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(stable(row) + "\n")
        hashes[pair] = sha_bytes(target.read_bytes())
        total += len(rows)
        for row in rows:
            counts[row["family"]] += 1
        write_state(current_phase="EVENT_TABLE_BUILD", current_action=pair, event_count=total, first_incomplete_action="next eligible pair", stop_gate_result="FAIL")
    manifest_payload = {"total_events": total, "family_counts": dict(counts), "pair_hashes": hashes}
    manifest_payload["hash"] = sha_bytes(stable(manifest_payload).encode())
    atomic_json(ROOT / "event_manifest.json", manifest_payload)
    return manifest_payload


def load_events(manifest):
    events = []
    for pair in manifest["eligible_pairs"]:
        with gzip.open(ROOT / "events" / f"{pair}.jsonl.gz", "rt", encoding="utf-8") as handle:
            events.extend(json.loads(line) for line in handle)
    return events


def candidate_accepts(candidate, event):
    if candidate.generation == "A":
        family = candidate.event_family.replace("_TRUE2", "")
        if event["family"] != family:
            return False
        if candidate.score_rule == "FACTOR_DIVERGENCE":
            return abs(event["factor_residual_4h"]) > 0.00015
        if candidate.score_rule == "VOLATILITY_TRANSITION":
            return event["volatility_change"] > 0
        if candidate.score_rule == "TRUE_2_CLOSE":
            return abs(event["trend_persistence"]) > 0.25
        if candidate.score_rule == "FACTOR_ALIGNMENT":
            return event["factor_spread_1h"] * (1 if event["side"] == "LONG" else -1) > 0
        if candidate.score_rule == "RESIDUAL_REVERSION":
            return abs(event["factor_residual_4h"]) > 0.0002
        return event["factor_spread_1h"] * (1 if event["side"] == "LONG" else -1) > 0.00005
    return candidate.generation == "B"


def select_r(candidate, event):
    return event.get(f"r_{candidate.stop_atr}_{candidate.target_r}")


def chronological_rank(events, top_n):
    grouped = defaultdict(list)
    for event in events:
        grouped[event["timestamp"]].append(event)
    selected = []
    for items in grouped.values():
        ranked = sorted(items, key=lambda x: (abs(x["factor_spread_1h"]) + x["event_magnitude_atr"] - x["spread_risk_ratio"]), reverse=True)
        selected.extend(ranked[:top_n])
    return selected


def development_gate(result, folds):
    return result["trades"] >= 50 and result["expectancy_r"] > 0 and result["profit_factor"] >= 1.15 and result["net_r"] > 0 and result["max_drawdown_pct"] <= 10 and sum(item["trades"] >= 8 and item["expectancy_r"] > 0 for item in folds) >= 4


def feature_vector(event):
    side_sign = 1.0 if event["side"] == "LONG" else -1.0
    return [
        max(-5.0, min(5.0, event["factor_spread_1h"] * 10000 * side_sign)),
        max(-5.0, min(5.0, event["factor_residual_4h"] * 10000 * side_sign)),
        max(-5.0, min(5.0, event["event_magnitude_atr"])),
        max(-5.0, min(5.0, event["trend_persistence"] * side_sign)),
        max(0.0, min(5.0, event["spread_risk_ratio"])),
        event["atr_percentile"] - 0.5,
        max(-5.0, min(5.0, event["volatility_change"])),
    ]


def _probability(weights, features):
    score = max(-30.0, min(30.0, weights[0] + sum(weight * value for weight, value in zip(weights[1:], features))))
    return 1.0 / (1.0 + math.exp(-score))


def fit_logistic(events, candidate, epochs=2):
    strength = float(candidate.score_rule.rsplit("_", 1)[-1]) if candidate.score_rule.startswith("LOGISTIC") else 0.1
    weights = [0.0] * 8
    learning_rate = 0.01
    for _ in range(epochs):
        for event in events:
            outcome = select_r(candidate, event)
            if outcome is None:
                continue
            features = feature_vector(event)
            error = (1.0 if outcome > 0 else 0.0) - _probability(weights, features)
            weights[0] += learning_rate * error
            for index, value in enumerate(features, 1):
                weights[index] += learning_rate * (error * value - strength * weights[index])
    return weights


def score_model_events(events, candidate, weights):
    selected = []
    for event in events:
        features = feature_vector(event)
        if candidate.score_rule == "MONOTONIC_LINEAR":
            score = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, sum(features[:4]) - features[4]))))
        else:
            score = _probability(weights, features)
        if score >= candidate.threshold:
            selected.append(event)
    return selected


def evaluate(events, candidate, window, side, model_training_events=None):
    window_events = [event for event in events if window[0] <= ts(event["timestamp"]) < window[1] and event["side"] == side]
    if candidate.generation == "C":
        training = [event for event in (model_training_events or []) if event["side"] == side]
        weights = fit_logistic(training, candidate) if candidate.score_rule.startswith("LOGISTIC") else [0.0] * 8
        chosen = score_model_events(window_events, candidate, weights)
    else:
        chosen = [event for event in window_events if candidate_accepts(candidate, event)]
    if candidate.generation == "B":
        chosen = chronological_rank([event for event in chosen if event["family"] == candidate.event_family], candidate.top_n)
    trades = [{"r": select_r(candidate, event), "pair": event["pair"], "event_id": event["event_id"], "signal_time": event["timestamp"]} for event in chosen if select_r(candidate, event) is not None]
    return trades


def evaluate_development(events, candidate, development_window, side):
    if candidate.generation != "C":
        trades = evaluate(events, candidate, development_window, side)
        folds = [metrics([trade for trade in trades if fold[0] <= ts(trade["signal_time"]) < fold[1]]) for fold in six_folds(development_window)]
        return trades, folds
    folds = six_folds(development_window)
    trades = []
    fold_metrics = []
    for index, fold in enumerate(folds):
        if index == 0:
            fold_trades = []
        else:
            training = [event for event in events if development_window[0] <= ts(event["timestamp"]) < fold[0]]
            fold_trades = evaluate(events, candidate, fold, side, training)
        trades.extend(fold_trades)
        fold_metrics.append(metrics(fold_trades))
    return trades, fold_metrics


def null_campaign(results, repetitions=500):
    rng = random.Random(12012)
    best = []
    # Preserve 50-trade dependence blocks while avoiding a full trade-table
    # traversal for every registry-wide repetition.
    block_sums = {
        key: ([sum(item["r"] for item in trades[index : index + 50]) for index in range(0, len(trades), 50)], len(trades))
        for key, trades in results.items()
    }
    for _ in range(repetitions):
        values = []
        for blocks, trade_count in block_sums.values():
            shifted_sum = sum(value * (1 if rng.random() > 0.5 else -1) for value in blocks)
            values.append(shifted_sum / trade_count if trade_count else 0.0)
        best.append(max(values, default=0.0))
    best.sort()
    return {"repetitions": repetitions, "best_expectancy_95pct": best[int(0.95 * (len(best) - 1))]}


def bootstrap(trades, repetitions=1000):
    if not trades:
        return {"repetitions": repetitions, "probability_positive": 0.0}
    rng = random.Random(12013)
    blocks = [trades[i : i + 50] for i in range(0, len(trades), 50)]
    outcomes = []
    for _ in range(repetitions):
        sample = [item["r"] for _ in blocks for item in rng.choice(blocks)]
        outcomes.append(sum(sample) / len(sample))
    outcomes.sort()
    return {"repetitions": repetitions, "probability_positive": sum(value > 0 for value in outcomes) / repetitions, "interval_90": [outcomes[50], outcomes[949]], "interval_95": [outcomes[25], outcomes[974]]}


def execute():
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    if manifest["aggregate_corpus_fingerprint"] != CORPUS_HASH:
        raise RuntimeError("Corpus V2 fingerprint mismatch")
    frozen = json.loads((CORPUS / "FROZEN.json").read_text(encoding="utf-8"))
    if frozen["status"] != "FROZEN_VALID":
        raise RuntimeError("Corpus V2 is not frozen")
    frozen_protocol, split, candidates = protocol(manifest)
    atomic_json(ROOT / "feature_protocol.json", frozen_protocol)
    atomic_json(ROOT / "candidate_registry.json", {"candidates": [asdict(item) for item in candidates], "hash": sha_bytes(stable([asdict(item) for item in candidates]).encode())})
    write_state(schema="AIOS_FOREX_FEATURE_EDGE_RESEARCH_V2", packet_id=PACKET, lock_id="AIOS-LOCK-a2eb257a6de346ccb5791025b45396df", revision="CONTINUATION_REINFORCED_R1", current_phase="CAUSAL_AGGREGATION", current_action="currency factors", next_action_queue=["EVENT_TABLE_BUILD", "FEATURE_TABLE_BUILD", "TARGET_TABLE_BUILD"], first_incomplete_action="currency factor table", authorized_internal_work_remaining=True, safe_independent_work_remaining=True, external_dependency_present=False, stop_gate_result="FAIL", resume_command="python -B -m automation.forex_engine.forex_feature_edge_research_v2 --execute")
    factor_path = ROOT / "currency_factor_table.json"
    factors = json.loads(factor_path.read_text(encoding="utf-8")) if factor_path.exists() else build_factor_table(manifest)
    event_manifest = build_events(manifest, factors)
    events = load_events(manifest)
    event_ids = [event["event_id"] for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise RuntimeError("Duplicate EVENT_ID detected")
    folds = six_folds(split["development"])
    development = {}
    dev_trades = {}
    passers = []
    for candidate in candidates:
        development[candidate.candidate_id] = {}
        for side in ("LONG", "SHORT"):
            trades, fold_metrics = evaluate_development(events, candidate, split["development"], side)
            dev_trades[f"{candidate.candidate_id}:{side}"] = trades
            result = metrics(trades)
            passed = development_gate(result, fold_metrics)
            development[candidate.candidate_id][side] = {"metrics": result, "folds": fold_metrics, "pass": passed}
            if passed:
                passers.append((candidate, side))
        write_state(current_phase=f"GENERATION_{candidate.generation}_DEVELOPMENT", current_action=candidate.candidate_id, first_incomplete_action="next candidate", next_action_queue=["REGISTRY_WIDE_NULL", "BLOCK_BOOTSTRAP", "VALIDATION"], development_completed=len(development), stop_gate_result="FAIL")
    null = null_campaign(dev_trades)
    validated_passers = []
    bootstrap_results = {}
    for candidate, side in passers:
        key = f"{candidate.candidate_id}:{side}"
        result = development[candidate.candidate_id][side]["metrics"]
        boot = bootstrap(dev_trades[key])
        bootstrap_results[key] = boot
        if result["expectancy_r"] > null["best_expectancy_95pct"] and boot["probability_positive"] >= 0.95:
            validated_passers.append((candidate, side))
    validation = {}
    shortlist = []
    development_events = [event for event in events if split["development"][0] <= ts(event["timestamp"]) < split["development"][1]]
    for candidate, side in validated_passers:
        trades = evaluate(events, candidate, split["validation"], side, development_events)
        result = metrics(trades)
        passed = result["trades"] >= 50 and result["expectancy_r"] > 0 and result["profit_factor"] >= 1.10 and result["net_r"] > 0 and result["max_drawdown_pct"] <= 10
        validation[f"{candidate.candidate_id}:{side}"] = {"metrics": result, "pass": passed}
        if passed:
            shortlist.append((candidate, side))
    shortlist = shortlist[:5]
    shortlist_payload = [{"candidate": asdict(candidate), "side": side} for candidate, side in shortlist]
    shortlist_hash = sha_bytes(stable(shortlist_payload).encode())
    atomic_json(ROOT / "shortlist_freeze.json", {"hash": shortlist_hash, "candidates": shortlist_payload, "frozen_utc": datetime.now(timezone.utc).isoformat()})
    holdout = {}
    finalists = []
    training_events = [event for event in events if split["development"][0] <= ts(event["timestamp"]) < split["validation"][1]]
    for candidate, side in shortlist:
        trades = evaluate(events, candidate, split["sealed_holdout"], side, training_events)
        result = metrics(trades)
        boot = bootstrap(trades)
        passed = result["trades"] >= 50 and result["expectancy_r"] > 0 and result["profit_factor"] >= 1.10 and result["net_r"] > 0 and result["max_drawdown_pct"] <= 10 and boot["probability_positive"] >= 0.95
        holdout[f"{candidate.candidate_id}:{side}"] = {"metrics": result, "bootstrap": boot, "pass": passed}
        if passed:
            finalists.append((candidate, side))
    status = "FORWARD_HOLDOUT_ACCUMULATING" if finalists else "RESEARCH_EXHAUSTED_FEATURE_EDGE_NOT_FOUND"
    dominant = None if finalists else "NO_INCREMENTAL_FEATURE_EDGE"
    final_state = write_state(current_phase="FORWARD_INITIALIZATION" if finalists else "TERMINAL_REPORT", current_action="finalist freeze" if finalists else "research exhaustion classification", first_incomplete_action="forward initialization" if finalists else "NONE", next_action_queue=["FORWARD_INITIALIZATION"] if finalists else [], authorized_internal_work_remaining=bool(finalists), safe_independent_work_remaining=bool(finalists), external_dependency_present=False, stop_gate_result="FAIL" if finalists else "PASS", objective_terminal_basis=None if finalists else "All frozen candidates processed with direction isolation; no candidate survived Development/statistical/Validation/Holdout gates.", exact_resume_trigger="immediate" if finalists else "new governed methodology or data authorization", event_manifest=event_manifest, protocol_hash=frozen_protocol["protocol_hash"], candidate_count=len(candidates), development=development, development_passers=[f"{item.candidate_id}:{side}" for item, side in passers], registry_null=null, bootstrap=bootstrap_results, validation=validation, shortlist_hash=shortlist_hash, sealed_holdout=holdout, finalists=[{"candidate": asdict(item), "side": side} for item, side in finalists], dominant_failure=dominant, status=status, safety={"broker_write": False, "practice_order": False, "live": False, "money_movement": False})
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(f"# AIOS Forex Feature Edge Research V2\n\n- Status: `{status}`\n- Protocol: `{frozen_protocol['protocol_hash']}`\n- Corpus: `{CORPUS_HASH}`\n- Events: {event_manifest['total_events']}\n- Candidates: {len(candidates)}\n- Development passers: {len(passers)}\n- Validation passers: {len(shortlist)}\n- Finalists: {len(finalists)}\n- OANDA LIVE contacted: false\n- Broker write: false\n", encoding="utf-8")
    return final_state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required")
    state = execute()
    print(stable({"status": state["status"], "candidate_count": state["candidate_count"], "finalists": len(state["finalists"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
