"""Frozen Stage-1 screen for directed USD-anchor to non-USD-cross lead-lag.

Pass one uses completed signal data and entry timestamps only to enforce the
preregistered capacity gate.  Forward outcomes are calculated only after every
fixed candidate has enough synchronized opportunities.  Validation and final
holdout partitions are never opened.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import itertools
import json
import math
import random
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable

from automation.forex_engine.forex_abnormal_price_update_response_stage1_v1 import (
    RISK_FRACTION,
    audit_journal_bytes,
    break_even_cost,
    development_artifacts,
    journal_bytes,
    metrics,
    pip_size,
    read_pair_bars,
    true_range,
    verify_manifest,
)
from automation.forex_engine.forex_directed_anchor_cross_lead_lag_stage0_v1 import (
    ANCHORS,
    CORPUS_ID,
    CORPUS_SHA256,
    EXPECTED_CANDIDATE_FINGERPRINTS,
    MECHANISM_FINGERPRINT,
    STRATEGY_ID,
    TARGETS,
    candidate_definitions,
    directed_links,
    order_sign,
    target_exposure_sign,
)


PACKET_ID = "PKT-FOREX-032"
PREREGISTRATION_SHA256 = "743b28805713e73328f198fecdbd0d907d988c4e1b5c145d89b3b518261bba97"
PRIOR_ATTEMPTS = 1187
CANDIDATE_COUNT = 8
CUMULATIVE_ATTEMPTS = 1195
RANDOM_SEED = 32032
SCORE_START = datetime(2024, 4, 1, tzinfo=timezone.utc)
DEV_END = datetime(2025, 4, 1, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
FOLD_BOUNDARIES = (
    datetime(2024, 4, 1, tzinfo=timezone.utc),
    datetime(2024, 6, 1, tzinfo=timezone.utc),
    datetime(2024, 8, 1, tzinfo=timezone.utc),
    datetime(2024, 10, 1, tzinfo=timezone.utc),
    datetime(2024, 12, 1, tzinfo=timezone.utc),
    datetime(2025, 2, 1, tzinfo=timezone.utc),
    datetime(2025, 4, 1, tzinfo=timezone.utc),
)
ROTATED_CURRENCY = {
    "AUD": "CAD", "CAD": "CHF", "CHF": "EUR", "EUR": "GBP",
    "GBP": "JPY", "JPY": "NZD", "NZD": "AUD",
}
DEPENDENCY_HASHES = {
    "automation/forex_engine/forex_abnormal_price_update_response_stage1_v1.py": "c1aa687f18bec0e9d0cc148b411ab54c29e4c43d7f094d78862a54242c26d4f1",
    "automation/forex_engine/forex_directed_anchor_cross_lead_lag_stage0_v1.py": "b91104d2e18933c83dda0fa86b19aa2684cc1e7232502e6b6e84751e167e23d9",
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fold_index(moment: datetime) -> int:
    for index, (left, right) in enumerate(zip(FOLD_BOUNDARIES, FOLD_BOUNDARIES[1:])):
        if left <= moment < right:
            return index
    return -1


def in_embargo(moment: datetime) -> bool:
    distance = timedelta(minutes=115)
    return any(abs(moment - boundary) < distance for boundary in FOLD_BOUNDARIES)


def session_label(moment: datetime) -> str:
    if 7 <= moment.hour < 12:
        return "LONDON"
    if 12 <= moment.hour < 16:
        return "LONDON_NEW_YORK_OVERLAP"
    if 16 <= moment.hour < 21:
        return "NEW_YORK"
    return "ASIA_HANDOFF_OTHER"


def rollover_intersection(entry: datetime, maximum_holding_bars: int = 3) -> bool:
    for offset in range(maximum_holding_bars + 1):
        moment = entry + timedelta(minutes=5 * offset)
        minute = moment.hour * 60 + moment.minute
        if 21 * 60 + 55 <= minute <= 22 * 60 + 10:
            return True
    return False


def consecutive_path(bars: list[dict[str, Any]], index: int, maximum_holding_bars: int = 3) -> bool:
    if index + maximum_holding_bars >= len(bars):
        return False
    moments = [parse_timestamp(bars[item]["timestamp"]) for item in range(index, index + maximum_holding_bars + 1)]
    return all(right - left == timedelta(minutes=5) for left, right in zip(moments, moments[1:]))


def verify_preregistration(path: Path) -> dict[str, Any]:
    if sha256_file(path) != PREREGISTRATION_SHA256:
        raise RuntimeError("PREREGISTRATION_SHA256_MISMATCH")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("strategy_id") != STRATEGY_ID or data.get("strategy_mechanism_fingerprint") != MECHANISM_FINGERPRINT:
        raise RuntimeError("PREREGISTRATION_IDENTITY_MISMATCH")
    observed = {item["candidate_id"]: item["candidate_fingerprint"] for item in data.get("candidates", [])}
    if observed != EXPECTED_CANDIDATE_FINGERPRINTS:
        raise RuntimeError("PREREGISTRATION_CANDIDATE_MISMATCH")
    return data


def verify_dependencies(repo_root: Path) -> None:
    for relative, expected in DEPENDENCY_HASHES.items():
        if sha256_file(repo_root / relative) != expected:
            raise RuntimeError(f"DEPENDENCY_SHA256_MISMATCH:{relative}")


def consecutive_previous(previous_start: datetime | None, current_start: datetime) -> bool:
    return previous_start is not None and current_start - previous_start == timedelta(minutes=5)


def anchor_shocks(
    bars: list[dict[str, Any]], anchor: str,
) -> list[dict[str, Any]]:
    ranges: deque[float] = deque(maxlen=20)
    previous_close: float | None = None
    previous_start: datetime | None = None
    shocks = []
    details = ANCHORS[anchor]
    for index, bar in enumerate(bars):
        start = parse_timestamp(bar["timestamp"])
        signal = start + timedelta(minutes=5)
        close = float(bar["mid"]["c"])
        if (
            len(ranges) == 20 and previous_close is not None and SCORE_START <= signal < DEV_END
            and consecutive_previous(previous_start, start) and not in_embargo(signal)
        ):
            atr = math.fsum(ranges) / len(ranges)
            raw_log_return = math.log(close / previous_close)
            ratio = abs(close - previous_close) / atr if atr > 0 else 0.0
            if ratio >= 1.0 and raw_log_return != 0:
                raw_sign = 1 if raw_log_return > 0 else -1
                shocks.append({
                    "shock_id": sha256_bytes(canonical_bytes({
                        "anchor": anchor, "bar_start": bar["timestamp"], "shock_ratio": round(ratio, 12),
                    })),
                    "anchor": anchor,
                    "anchor_currency": details["currency"],
                    "bar_start": bar["timestamp"],
                    "signal_timestamp": timestamp_text(signal),
                    "fold": fold_index(signal),
                    "raw_anchor_return": raw_log_return,
                    "raw_anchor_sign": raw_sign,
                    "normalized_anchor_sign": raw_sign * int(details["sign_multiplier"]),
                    "shock_ratio": ratio,
                    "anchor_atr": atr,
                })
        ranges.append(true_range(bar, previous_close))
        previous_close = close
        previous_start = start
    return shocks


def rolling_atr_including_current(bars: list[dict[str, Any]]) -> list[float | None]:
    ranges: deque[float] = deque(maxlen=20)
    values: list[float | None] = []
    previous_close: float | None = None
    for bar in bars:
        ranges.append(true_range(bar, previous_close))
        values.append(math.fsum(ranges) / 20 if len(ranges) == 20 else None)
        previous_close = float(bar["mid"]["c"])
    return values


def build_opportunities_for_target(
    target: str, bars: list[dict[str, Any]], original_shocks: list[dict[str, Any]],
    wrong_shocks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexes = {bar["timestamp"]: index for index, bar in enumerate(bars)}
    atrs = rolling_atr_including_current(bars)

    def build(shocks: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        rows = []
        for shock in shocks:
            index = indexes.get(shock["bar_start"])
            if index is None or not consecutive_path(bars, index, 3):
                continue
            atr = atrs[index]
            entry_time = parse_timestamp(bars[index + 1]["timestamp"])
            if atr is None or atr <= 0 or rollover_intersection(entry_time, 3):
                continue
            signal_close = float(bars[index]["mid"]["c"])
            previous_close = float(bars[index - 1]["mid"]["c"])
            target_return = math.log(signal_close / previous_close)
            if target_return == 0:
                target_momentum_sign = 0
            else:
                target_momentum_sign = 1 if target_return > 0 else -1
            spread = float(bars[index + 1]["ask"]["o"]) - float(bars[index + 1]["bid"]["o"])
            signal_close_spread_pips = (
                float(bars[index]["ask"]["c"]) - float(bars[index]["bid"]["c"])
            ) / pip_size(target)
            currency = shock["anchor_currency"] if kind == "ORIGINAL" else ROTATED_CURRENCY[shock["anchor_currency"]]
            rows.append({
                **shock,
                "opportunity_id": sha256_bytes(canonical_bytes({
                    "kind": kind, "shock_id": shock["shock_id"], "target": target,
                })),
                "kind": kind,
                "transmitted_currency": currency,
                "target": target,
                "target_atr": atr,
                "entry_spread_to_atr": spread / atr,
                "signal_close_spread_pips": signal_close_spread_pips,
                "target_momentum_sign": target_momentum_sign,
                "entry_timestamp": bars[index + 1]["timestamp"],
            })
        return rows

    return build(original_shocks, "ORIGINAL"), build(wrong_shocks, "WRONG_CURRENCY")


def select_opportunities(opportunities: list[dict[str, Any]], threshold: float, hold: int) -> list[dict[str, Any]]:
    filtered = [row for row in opportunities if row["shock_ratio"] >= threshold]
    accepted: list[dict[str, Any]] = []
    active: list[tuple[str, set[str]]] = []
    for signal_timestamp, grouped in itertools.groupby(
        sorted(filtered, key=lambda row: (row["signal_timestamp"], row["target"], -row["shock_ratio"], row["anchor"])),
        key=lambda row: row["signal_timestamp"],
    ):
        group = list(grouped)
        deduplicated = []
        for _, target_rows in itertools.groupby(group, key=lambda row: row["target"]):
            deduplicated.append(min(target_rows, key=lambda row: (-row["shock_ratio"], row["anchor"])))
        active = [item for item in active if item[0] > signal_timestamp]
        for row in sorted(deduplicated, key=lambda item: (-item["shock_ratio"], item["entry_spread_to_atr"], item["target"], item["anchor"])):
            currencies = set(row["target"].split("_"))
            if len(active) >= 5 or any(currencies & used for _, used in active):
                continue
            exit_timestamp = timestamp_text(parse_timestamp(row["entry_timestamp"]) + timedelta(minutes=5 * hold))
            active.append((exit_timestamp, currencies))
            accepted.append(row)
    return accepted


def capacity_audit(selected: list[dict[str, Any]]) -> dict[str, Any]:
    fold_counts = {str(index): sum(row["fold"] == index for row in selected) for index in range(6)}
    target_currencies = {currency for row in selected for currency in row["target"].split("_")}
    checks = {
        "minimum_selected_opportunities": len(selected) >= 400,
        "minimum_positive_anchor_opportunities": sum(row["normalized_anchor_sign"] > 0 for row in selected) >= 100,
        "minimum_negative_anchor_opportunities": sum(row["normalized_anchor_sign"] < 0 for row in selected) >= 100,
        "minimum_targets": len({row["target"] for row in selected}) >= 20,
        "minimum_currencies": len(target_currencies) >= 10,
        "minimum_each_fold": all(count >= 30 for count in fold_counts.values()),
    }
    return {
        "selected_opportunities": len(selected),
        "positive_anchor_opportunities": sum(row["normalized_anchor_sign"] > 0 for row in selected),
        "negative_anchor_opportunities": sum(row["normalized_anchor_sign"] < 0 for row in selected),
        "target_count": len({row["target"] for row in selected}),
        "currency_count": len(target_currencies),
        "fold_counts": fold_counts,
        "checks": checks,
        "pass": all(checks.values()),
    }


def deterministic_random_sign(candidate_fingerprint: str, opportunity: dict[str, Any]) -> int:
    key = "|".join((candidate_fingerprint, opportunity["anchor"], opportunity["target"], opportunity["signal_timestamp"]))
    return 1 if hashlib.sha256(key.encode("ascii")).digest()[0] & 0x80 else -1


def aggregate_currency_strength(
    repo_root: Path, manifest: dict[str, Any], required: set[tuple[str, str]], verification: dict[str, Any],
) -> dict[tuple[str, str], float]:
    timestamps = {timestamp for _, timestamp in required}
    sums: dict[tuple[str, str], float] = defaultdict(float)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    corpus_root = repo_root / ".aios/runtime/forex_m5_immutable_corpus_v2"
    for pair in sorted(manifest["eligible_pairs"]):
        bars = read_pair_bars(corpus_root, manifest, pair, verification)
        previous_close: float | None = None
        base, quote = pair.split("_")
        for bar in bars:
            close = float(bar["mid"]["c"])
            if previous_close is not None and bar["timestamp"] in timestamps:
                raw = math.log(close / previous_close)
                for currency, value in ((base, raw), (quote, -raw)):
                    key = (currency, bar["timestamp"])
                    if key in required:
                        sums[key] += value
                        counts[key] += 1
            previous_close = close
    return {key: sums[key] / counts[key] for key in required if counts[key] > 0}


def scenario_outcome(
    pair: str, bars: list[dict[str, Any]], signal_index: int, hold: int,
    direction: str, atr: float, scenario: str,
) -> dict[str, Any]:
    entry_bar = bars[signal_index + 1]
    slippage_pips = {"gross": 0.0, "base": 0.1, "stress": 0.5}[scenario]
    slippage = pip_size(pair) * slippage_pips
    if direction == "LONG":
        entry = float(entry_bar["mid" if scenario == "gross" else "ask"]["o"]) + slippage
        stop = entry - atr
    else:
        entry = float(entry_bar["mid" if scenario == "gross" else "bid"]["o"]) - slippage
        stop = entry + atr
    exit_price = entry
    exit_reason = "TIME"
    exit_bar = entry_bar
    for offset in range(1, hold + 1):
        bar = bars[signal_index + offset]
        side = "mid" if scenario == "gross" else ("bid" if direction == "LONG" else "ask")
        if direction == "LONG" and float(bar[side]["l"]) <= stop:
            exit_price = min(stop, float(bar[side]["o"])) - slippage
            exit_reason = "STOP"
            exit_bar = bar
            break
        if direction == "SHORT" and float(bar[side]["h"]) >= stop:
            exit_price = max(stop, float(bar[side]["o"])) + slippage
            exit_reason = "STOP"
            exit_bar = bar
            break
        if offset == hold:
            exit_price = float(bar[side]["c"]) + (-slippage if direction == "LONG" else slippage)
            exit_bar = bar
    result_price = exit_price - entry if direction == "LONG" else entry - exit_price
    return {
        "entry_price": entry,
        "exit_timestamp": timestamp_text(parse_timestamp(exit_bar["timestamp"]) + timedelta(minutes=5)),
        "exit_price": exit_price,
        "stop_loss": stop,
        "exit_reason": exit_reason,
        "result_r": result_price / atr,
        "result_pips": result_price / pip_size(pair),
        "entry_open_spread_pips": (float(entry_bar["ask"]["o"]) - float(entry_bar["bid"]["o"])) / pip_size(pair),
        "exit_bar_close_spread_pips": (float(exit_bar["ask"]["c"]) - float(exit_bar["bid"]["c"])) / pip_size(pair),
    }


def outcome_lookup(
    repo_root: Path, manifest: dict[str, Any], needs: dict[str, set[tuple[str, str, int, float]]],
    verification: dict[str, Any], *, capacity_verdict: bool,
) -> dict[tuple[str, str, str, int, float], dict[str, dict[str, Any]]]:
    if capacity_verdict is not True:
        raise RuntimeError("FORWARD_RETURN_BLOCKED_UNTIL_CAPACITY_PASS")
    corpus_root = repo_root / ".aios/runtime/forex_m5_immutable_corpus_v2"
    output = {}
    for pair in sorted(needs):
        bars = read_pair_bars(corpus_root, manifest, pair, verification)
        indexes = {bar["timestamp"]: index for index, bar in enumerate(bars)}
        for bar_start, direction, hold, atr in sorted(needs[pair]):
            index = indexes[bar_start]
            output[(pair, bar_start, direction, hold, atr)] = {
                scenario: scenario_outcome(pair, bars, index, hold, direction, atr, scenario)
                for scenario in ("gross", "base", "stress")
            }
    return output


def make_row(
    opportunity: dict[str, Any], direction: str, hold: int, candidate_id: str,
    candidate_fingerprint: str, outcomes: dict[tuple[str, str, str, int, float], dict[str, dict[str, Any]]],
    strategy_id: str = STRATEGY_ID,
) -> dict[str, Any]:
    key = (opportunity["target"], opportunity["bar_start"], direction, hold, opportunity["target_atr"])
    gross, base, stress = (outcomes[key][name] for name in ("gross", "base", "stress"))
    return {
        "strategy_id": strategy_id,
        "candidate_id": candidate_id,
        "candidate_fingerprint": candidate_fingerprint,
        "event_id": opportunity["opportunity_id"],
        "anchor": opportunity["anchor"],
        "anchor_currency": opportunity["anchor_currency"],
        "transmitted_currency": opportunity["transmitted_currency"],
        "instrument": opportunity["target"],
        "direction": direction,
        "signal_timestamp": opportunity["signal_timestamp"],
        "entry_timestamp": opportunity["entry_timestamp"],
        "entry_price": base["entry_price"],
        "exit_timestamp": base["exit_timestamp"],
        "exit_price": base["exit_price"],
        "stop_loss": base["stop_loss"],
        "take_profit": None,
        "signal_close_spread_pips": opportunity["signal_close_spread_pips"],
        "entry_open_spread_pips": base["entry_open_spread_pips"],
        "exit_bar_close_spread_pips": base["exit_bar_close_spread_pips"],
        "modeled_slippage_pips_per_side": 0.1,
        "gross_result_pips": gross["result_pips"],
        "net_result_pips": base["result_pips"],
        "gross_result_r": gross["result_r"],
        "net_result_r": base["result_r"],
        "stress_result_r": stress["result_r"],
        "result_r": base["result_r"],
        "entry_reason": "COMPLETED_USD_MAJOR_ANCHOR_SHOCK_TO_DIFFERENT_NON_USD_CROSS",
        "exit_reason": base["exit_reason"],
        "session": session_label(parse_timestamp(opportunity["signal_timestamp"])),
        "volatility_regime": "HIGH" if opportunity["shock_ratio"] >= 1.5 else "ELEVATED",
        "trend_or_range_regime": "NOT_APPLICABLE_STAGE1_ANCHOR_SHOCK_SCREEN",
        "economic_event_proximity": "NOT_APPLICABLE_NO_CERTIFIED_POINT_IN_TIME_EVENT_FEED",
        "fold": opportunity["fold"],
        "filter_results": {
            "completed_anchor_candle": True,
            "exact_target_timestamp": True,
            "next_synchronized_bar_entry": True,
            "purge_embargo_clear": True,
            "rollover_clear": True,
            "anchor_shock_ratio": opportunity["shock_ratio"],
            "raw_anchor_return": opportunity["raw_anchor_return"],
            "normalized_anchor_sign": opportunity["normalized_anchor_sign"],
            "target_exposure_sign": target_exposure_sign(opportunity["target"], opportunity["transmitted_currency"]),
            "target_atr": opportunity["target_atr"],
            "spread_filter": "NONE_ALL_OBSERVED_SPREADS_CHARGED",
            "exposure_gate": "PASS",
        },
    }


def pair_sign(value: int) -> str:
    return "LONG" if value > 0 else "SHORT"


def pbo_proxy(results: dict[str, dict[str, Any]]) -> float:
    ids = sorted(results)
    failures = splits = 0
    for training in itertools.combinations(range(6), 3):
        testing = set(range(6)) - set(training)
        def average(candidate: str, folds: Iterable[int]) -> float:
            values = [results[candidate]["base_after_cost"]["fold_expectancy_r"][str(fold)] for fold in folds]
            return math.fsum(values) / len(values)
        selected = max(ids, key=lambda item: (average(item, training), item))
        ranking = sorted((average(item, testing), item) for item in ids)
        rank = next(index for index, (_, item) in enumerate(ranking) if item == selected)
        failures += rank < len(ranking) / 2
        splits += 1
    return failures / splits


def failure_causes(gates: dict[str, bool], gross: float, net: float, simple_baseline_pass: bool) -> list[str]:
    mapping = {
        "gross_edge": "NO_GROSS_EDGE", "after_cost": "COST_DESTROYED_EDGE",
        "profit_factor": "AFTER_COST_PROFIT_FACTOR_FAILURE", "drawdown": "EXCESSIVE_DRAWDOWN",
        "trades": "INSUFFICIENT_TRADES", "direction": "DIRECTION_CONCENTRATION",
        "breadth": "INSUFFICIENT_BREADTH", "folds": "WALK_FORWARD_FAILURE",
        "stress": "COST_STRESS_FAILURE", "baseline": "BASELINE_FAILURE",
        "concentration": "PAIR_OR_CURRENCY_CONCENTRATION", "leakage": "LEAKAGE",
        "accounting": "INVALID_EXPERIMENT",
    }
    failures = []
    for gate, passed in gates.items():
        if passed:
            continue
        if gate == "after_cost" and not (gross > 0 and net <= 0):
            continue
        failures.append(mapping[gate])
    priority = [
        "INVALID_EXPERIMENT", "LEAKAGE", "NO_GROSS_EDGE", "COST_DESTROYED_EDGE",
        "BASELINE_FAILURE", "WALK_FORWARD_FAILURE",
        "COST_STRESS_FAILURE", "EXCESSIVE_DRAWDOWN", "INSUFFICIENT_TRADES",
        "INSUFFICIENT_BREADTH", "PAIR_OR_CURRENCY_CONCENTRATION",
        "DIRECTION_CONCENTRATION", "AFTER_COST_PROFIT_FACTOR_FAILURE",
    ]
    return [item for item in priority if item in failures]


def reverse_pair_audit(left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]]) -> dict[str, Any]:
    left = {row["event_id"]: row["direction"] for row in left_rows}
    right = {row["event_id"]: row["direction"] for row in right_rows}
    identity_pass = set(left) == set(right)
    opposite_pass = identity_pass and all(
        {left[event_id], right[event_id]} == {"LONG", "SHORT"} for event_id in left
    )
    identity_hash = sha256_bytes(canonical_bytes(sorted(left)))
    return {
        "left_count": len(left_rows),
        "right_count": len(right_rows),
        "unique_left_count": len(left),
        "unique_right_count": len(right),
        "opportunity_identity_sha256": identity_hash,
        "identity_pass": identity_pass and len(left) == len(left_rows) and len(right) == len(right_rows),
        "opposite_direction_pass": opposite_pass,
        "pass": identity_pass and opposite_pass and len(left) == len(left_rows) and len(right) == len(right_rows),
    }


def event_identity_audit(candidate_rows: list[dict[str, Any]], baseline_rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_ids = [row["event_id"] for row in candidate_rows]
    baseline_ids = [row["event_id"] for row in baseline_rows]
    candidate_set = set(candidate_ids)
    baseline_set = set(baseline_ids)
    return {
        "candidate_count": len(candidate_ids),
        "baseline_count": len(baseline_ids),
        "candidate_unique_count": len(candidate_set),
        "baseline_unique_count": len(baseline_set),
        "candidate_event_ids_sha256": sha256_bytes(canonical_bytes(sorted(candidate_set))),
        "baseline_event_ids_sha256": sha256_bytes(canonical_bytes(sorted(baseline_set))),
        "pass": (
            candidate_set == baseline_set
            and len(candidate_set) == len(candidate_ids)
            and len(baseline_set) == len(baseline_ids)
        ),
    }


def required_baseline_comparison(
    *, candidate_expectancy: float, random_expectancy: float,
    strength_expectancy: float, target_subset_candidate_expectancy: float,
    target_momentum_expectancy: float, wrong_anchor_expectancy: float,
    population_valid: bool,
) -> bool:
    return (
        candidate_expectancy > 0.0
        and candidate_expectancy > random_expectancy
        and candidate_expectancy > strength_expectancy
        and target_subset_candidate_expectancy > target_momentum_expectancy
        and candidate_expectancy > wrong_anchor_expectancy
        and population_valid
    )


def research(repo_root: Path, prereg_path: Path) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    verify_dependencies(repo_root)
    prereg = verify_preregistration(prereg_path)
    corpus_root = repo_root / ".aios/runtime/forex_m5_immutable_corpus_v2"
    manifest = verify_manifest(corpus_root)
    verification: dict[str, Any] = {}
    shocks_by_anchor: dict[str, list[dict[str, Any]]] = {}
    unique_rows_opened = 0
    for anchor in sorted(ANCHORS):
        bars = read_pair_bars(corpus_root, manifest, anchor, verification)
        unique_rows_opened += len(bars)
        shocks_by_anchor[anchor] = anchor_shocks(bars, anchor)

    links = directed_links()
    original_opportunities: list[dict[str, Any]] = []
    wrong_opportunities: list[dict[str, Any]] = []
    for target in TARGETS:
        bars = read_pair_bars(corpus_root, manifest, target, verification)
        unique_rows_opened += len(bars)
        original_shocks = [
            shock for anchor, shocks in shocks_by_anchor.items()
            if target in links[anchor] for shock in shocks
        ]
        wrong_shocks = [
            shock for shocks in shocks_by_anchor.values() for shock in shocks
            if ROTATED_CURRENCY[shock["anchor_currency"]] in target.split("_")
        ]
        original, wrong = build_opportunities_for_target(target, bars, original_shocks, wrong_shocks)
        original_opportunities.extend(original)
        wrong_opportunities.extend(wrong)

    definitions = sorted(prereg["candidates"], key=lambda row: row["candidate_id"])
    selections: dict[tuple[str, float, int], list[dict[str, Any]]] = {}
    capacity: dict[str, Any] = {}
    for definition in definitions:
        threshold = float(definition["shock_threshold_atr"])
        hold = int(definition["holding_m5_bars"])
        key = ("ORIGINAL", threshold, hold)
        if key not in selections:
            selections[key] = select_opportunities(original_opportunities, threshold, hold)
        wrong_key = ("WRONG", threshold, hold)
        if wrong_key not in selections:
            selections[wrong_key] = select_opportunities(wrong_opportunities, threshold, hold)
        capacity[definition["candidate_id"]] = capacity_audit(selections[key])

    capacity_pass = all(row["pass"] for row in capacity.values())
    capacity_artifact = {
        "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE1_CAPACITY.v1",
        "packet_id": PACKET_ID,
        "candidate_capacity": capacity,
        "original_synchronized_opportunities_before_selection": len(original_opportunities),
        "wrong_anchor_synchronized_opportunities_before_selection": len(wrong_opportunities),
        "forward_returns_calculated_before_capacity_verdict": 0,
        "outcome_guard_enforced": True,
        "actual_trials_added_if_failed": 0,
        "status": "PASS_TO_SCORE" if capacity_pass else "STAGE0_INSUFFICIENT_CAPACITY_ZERO_TRIALS_ADDED",
    }
    if not capacity_pass:
        result = {
            "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE1_RESULTS.v1",
            "packet_id": PACKET_ID,
            "status": "STAGE0_INSUFFICIENT_CAPACITY_ZERO_TRIALS_ADDED",
            "candidate_results": {},
            "candidate_count_scored": 0,
            "prior_actual_attempt_lower_bound": PRIOR_ATTEMPTS,
            "cumulative_actual_attempt_lower_bound": PRIOR_ATTEMPTS,
            "development_rows_opened": unique_rows_opened,
            "validation_rows_opened": 0,
            "holdout_rows_opened": 0,
            "holdout_status": "NOT_EVALUATED",
            "capacity": capacity_artifact,
        }
        return result, journal_bytes([]), capacity_artifact

    selected_original = {
        row["opportunity_id"]: row
        for key, rows in selections.items() if key[0] == "ORIGINAL" for row in rows
    }
    required_strength = {
        (row["anchor_currency"], row["bar_start"]) for row in selected_original.values()
    }
    strengths = aggregate_currency_strength(repo_root, manifest, required_strength, verification)
    unique_rows_opened = sum(
        int(artifact["records"])
        for pair in manifest["eligible_pairs"] for artifact in development_artifacts(manifest, pair)
    )

    needs: dict[str, set[tuple[str, str, int, float]]] = defaultdict(set)
    for definition in definitions:
        threshold = float(definition["shock_threshold_atr"])
        hold = int(definition["holding_m5_bars"])
        fingerprint = definition["candidate_fingerprint"]
        for row in selections[("ORIGINAL", threshold, hold)]:
            directions = {
                pair_sign(order_sign(row["raw_anchor_sign"], row["anchor"], row["target"], "CONTINUATION")),
                pair_sign(order_sign(row["raw_anchor_sign"], row["anchor"], row["target"], "EXACT_REVERSE")),
                pair_sign(deterministic_random_sign(fingerprint, row)),
            }
            if row["target_momentum_sign"]:
                directions.add(pair_sign(row["target_momentum_sign"]))
            strength = strengths.get((row["anchor_currency"], row["bar_start"]), 0.0)
            if strength:
                directions.add(pair_sign((1 if strength > 0 else -1) * target_exposure_sign(row["target"], row["anchor_currency"])))
            for direction in directions:
                needs[row["target"]].add((row["bar_start"], direction, hold, row["target_atr"]))
        for row in selections[("WRONG", threshold, hold)]:
            direction = pair_sign(row["normalized_anchor_sign"] * target_exposure_sign(row["target"], row["transmitted_currency"]))
            needs[row["target"]].add((row["bar_start"], direction, hold, row["target_atr"]))
        for row in selections[("ORIGINAL", threshold, hold)]:
            anchor_opportunity = {
                **row, "target": row["anchor"], "target_atr": row["anchor_atr"],
                "transmitted_currency": row["anchor_currency"], "entry_spread_to_atr": 0.0,
                "signal_close_spread_pips": 0.0,
            }
            direction = pair_sign(row["raw_anchor_sign"])
            needs[row["anchor"]].add((row["bar_start"], direction, hold, row["anchor_atr"]))
    outcomes = outcome_lookup(
        repo_root, manifest, needs, verification, capacity_verdict=capacity_pass
    )

    candidate_results: dict[str, Any] = {}
    candidate_journals: dict[str, list[dict[str, Any]]] = {}
    journal: list[dict[str, Any]] = []
    for definition_index, definition in enumerate(definitions):
        candidate_id = definition["candidate_id"]
        fingerprint = definition["candidate_fingerprint"]
        threshold = float(definition["shock_threshold_atr"])
        hold = int(definition["holding_m5_bars"])
        arm = definition["arm"]
        selected = selections[("ORIGINAL", threshold, hold)]
        rows = []
        random_rows = []
        target_rows = []
        target_candidate_rows = []
        strength_rows = []
        same_pair_rows = []
        for opportunity in selected:
            direction = pair_sign(order_sign(opportunity["raw_anchor_sign"], opportunity["anchor"], opportunity["target"], arm))
            rows.append(make_row(opportunity, direction, hold, candidate_id, fingerprint, outcomes))
            random_rows.append(make_row(
                opportunity, pair_sign(deterministic_random_sign(fingerprint, opportunity)), hold,
                f"RANDOM-{candidate_id}", "BASELINE", outcomes, "BASELINE_RANDOM_SIGN",
            ))
            if opportunity["target_momentum_sign"]:
                target_candidate_rows.append(rows[-1])
                target_rows.append(make_row(
                    opportunity, pair_sign(opportunity["target_momentum_sign"]), hold,
                    f"TARGET-MOMENTUM-{candidate_id}", "BASELINE", outcomes, "BASELINE_TARGET_OWN_MOMENTUM",
                ))
            strength = strengths.get((opportunity["anchor_currency"], opportunity["bar_start"]), 0.0)
            if strength:
                strength_direction = pair_sign(
                    (1 if strength > 0 else -1)
                    * target_exposure_sign(opportunity["target"], opportunity["anchor_currency"])
                )
                strength_rows.append(make_row(
                    opportunity, strength_direction, hold, f"STRENGTH-{candidate_id}",
                    "BASELINE", outcomes, "BASELINE_POOLED_CURRENCY_STRENGTH",
                ))
            anchor_opportunity = {
                **opportunity, "target": opportunity["anchor"], "target_atr": opportunity["anchor_atr"],
                "transmitted_currency": opportunity["anchor_currency"], "entry_spread_to_atr": 0.0,
                "signal_close_spread_pips": 0.0,
            }
            same_pair_rows.append(make_row(
                anchor_opportunity, pair_sign(opportunity["raw_anchor_sign"]), hold,
                f"ANCHOR-{candidate_id}", "BASELINE", outcomes, "BASELINE_SAME_PAIR_ANCHOR_MOMENTUM",
            ))
        wrong_rows = []
        for opportunity in selections[("WRONG", threshold, hold)]:
            direction = pair_sign(
                opportunity["normalized_anchor_sign"]
                * target_exposure_sign(opportunity["target"], opportunity["transmitted_currency"])
            )
            wrong_rows.append(make_row(
                opportunity, direction, hold, f"WRONG-{candidate_id}", "BASELINE", outcomes,
                "BASELINE_WRONG_CURRENCY_ANCHOR",
            ))
        journal.extend(rows)
        candidate_journals[candidate_id] = rows
        base = metrics(rows, "net_result_r", RANDOM_SEED + definition_index)
        gross = metrics(rows, "gross_result_r", RANDOM_SEED + definition_index)
        stress = metrics(rows, "stress_result_r", RANDOM_SEED + definition_index)
        baseline_metrics = {
            "no_trade_expectancy_r": 0.0,
            "deterministic_random_sign": metrics(random_rows, "net_result_r", RANDOM_SEED + 100 + definition_index),
            "same_pair_anchor_momentum_diagnostic": metrics(same_pair_rows, "net_result_r", RANDOM_SEED + 200 + definition_index),
            "target_own_one_bar_momentum": metrics(target_rows, "net_result_r", RANDOM_SEED + 300 + definition_index),
            "candidate_on_target_momentum_identical_subset": metrics(target_candidate_rows, "net_result_r", RANDOM_SEED + 350 + definition_index),
            "pooled_currency_strength": metrics(strength_rows, "net_result_r", RANDOM_SEED + 400 + definition_index),
            "wrong_currency_anchor": metrics(wrong_rows, "net_result_r", RANDOM_SEED + 500 + definition_index),
        }
        identity_audits = {
            "random_identical_population": event_identity_audit(rows, random_rows),
            "pooled_strength_identical_population": event_identity_audit(rows, strength_rows),
            "target_momentum_identical_nonzero_subset": event_identity_audit(target_candidate_rows, target_rows),
        }
        wrong_capacity = capacity_audit(selections[("WRONG", threshold, hold)])
        population_pass = all(row["pass"] for row in identity_audits.values()) and wrong_capacity["pass"]
        required_baseline_pass = required_baseline_comparison(
            candidate_expectancy=base["expectancy_r"],
            random_expectancy=baseline_metrics["deterministic_random_sign"]["expectancy_r"],
            strength_expectancy=baseline_metrics["pooled_currency_strength"]["expectancy_r"],
            target_subset_candidate_expectancy=baseline_metrics["candidate_on_target_momentum_identical_subset"]["expectancy_r"],
            target_momentum_expectancy=baseline_metrics["target_own_one_bar_momentum"]["expectancy_r"],
            wrong_anchor_expectancy=baseline_metrics["wrong_currency_anchor"]["expectancy_r"],
            population_valid=population_pass,
        )
        simple_baseline_pass = base["expectancy_r"] > baseline_metrics["same_pair_anchor_momentum_diagnostic"]["expectancy_r"]
        accounting = all(
            row["entry_timestamp"] >= row["signal_timestamp"]
            and row["exit_timestamp"] > row["entry_timestamp"]
            and row["filter_results"]["completed_anchor_candle"]
            and row["filter_results"]["exact_target_timestamp"]
            and row["filter_results"]["rollover_clear"]
            for row in rows
        ) and population_pass
        gates = {
            "gross_edge": gross["expectancy_r"] > 0,
            "after_cost": base["expectancy_r"] > 0,
            "profit_factor": base["profit_factor"] >= 1.05,
            "drawdown": base["maximum_drawdown_pct"] <= 15.0,
            "trades": base["trade_count"] >= 100,
            "direction": base["long_trades"] >= 40 and base["short_trades"] >= 40,
            "breadth": base["contributing_instruments"] >= 10 and base["contributing_currencies"] >= 5,
            "folds": base["positive_folds"] >= 4,
            "stress": stress["expectancy_r"] > 0,
            "baseline": required_baseline_pass,
            "concentration": base["largest_pair_trade_share"] <= 0.25 and base["largest_currency_trade_share"] <= 0.40 and base["top_five_positive_result_share"] <= 0.30,
            "leakage": True,
            "accounting": accounting,
        }
        critical = NormalDist().inv_cdf(1.0 - 0.05 / CUMULATIVE_ATTEMPTS)
        adjusted_lower = base["expectancy_r"] - critical * base["block_bootstrap_standard_error_r"]
        candidate_results[candidate_id] = {
            "definition": definition,
            "capacity": capacity[candidate_id],
            "gross_midpoint": gross,
            "base_after_cost": base,
            "stress_after_cost": stress,
            "break_even": break_even_cost(gross["expectancy_r"], base["expectancy_r"], stress["expectancy_r"]),
            "baselines": baseline_metrics,
            "baseline_population_audit": {
                "candidate": len(rows), "random": len(random_rows), "target_momentum": len(target_rows),
                "candidate_on_target_momentum_identical_subset": len(target_candidate_rows),
                "target_momentum_coverage": len(target_rows) / len(rows) if rows else 0.0,
                "pooled_strength": len(strength_rows), "wrong_anchor": len(wrong_rows),
                "event_identity_audits": identity_audits,
                "wrong_anchor_capacity_audit": wrong_capacity,
                "wrong_anchor_role": "NON_IDENTITY_PLACEBO_WITH_FULL_FROZEN_CAPACITY_AND_BREADTH_GATES",
                "pass": population_pass,
            },
            "diagnostic_simple_baseline_pass": simple_baseline_pass,
            "diagnostic_findings": [] if simple_baseline_pass else ["SIMPLE_BASELINE_FAILURE_NOT_A_STAGE1_GATE"],
            "gates": gates,
            "stage1_pass": all(gates.values()),
            "failure_causes": failure_causes(gates, gross["expectancy_r"], base["expectancy_r"], simple_baseline_pass),
            "multiple_testing": {
                "prior_actual_attempt_lower_bound": PRIOR_ATTEMPTS,
                "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPTS,
                "bonferroni_one_sided_critical_z": critical,
                "search_adjusted_expectancy_lower_bound_r": adjusted_lower,
                "block_bootstrap_lower_bound_r": base["block_bootstrap_lower_bound_r"],
            },
        }

    pbo = pbo_proxy(candidate_results)
    for row in candidate_results.values():
        row["multiple_testing"]["probability_of_backtest_overfitting_proxy"] = pbo
        row["multiple_testing"]["stage2_precheck_pass"] = (
            row["multiple_testing"]["search_adjusted_expectancy_lower_bound_r"] > 0
            and row["multiple_testing"]["block_bootstrap_lower_bound_r"] > 0 and pbo <= 0.5
        )
    survivors = sorted(candidate for candidate, row in candidate_results.items() if row["stage1_pass"])
    reverse_audit = {}
    for threshold in ("T1P0", "T1P5"):
        for hold in (1, 3):
            left = f"DACL-{threshold}-CONTINUATION-H{hold}"
            right = f"DACL-{threshold}-EXACT_REVERSE-H{hold}"
            reverse_audit[f"{threshold}-H{hold}"] = reverse_pair_audit(candidate_journals[left], candidate_journals[right])
    best = max(candidate_results, key=lambda item: (candidate_results[item]["base_after_cost"]["expectancy_r"], item))
    result = {
        "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE1_RESULTS.v1",
        "packet_id": PACKET_ID,
        "status": "STAGE1_SURVIVOR" if survivors else "CLOSED_FAILED_POSTMORTEM_COMPLETE",
        "strategy_id": STRATEGY_ID,
        "strategy_mechanism_fingerprint": MECHANISM_FINGERPRINT,
        "preregistration_sha256": PREREGISTRATION_SHA256,
        "corpus_id": CORPUS_ID,
        "corpus_sha256": CORPUS_SHA256,
        "candidate_count_scored": CANDIDATE_COUNT,
        "prior_actual_attempt_lower_bound": PRIOR_ATTEMPTS,
        "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPTS,
        "governed_after_cost_candidates_before": 135,
        "governed_after_cost_candidates_after": 143,
        "development_rows_opened": unique_rows_opened,
        "verified_partition_count": len(verification),
        "capacity": capacity_artifact,
        "candidate_results": candidate_results,
        "family_pbo_proxy": pbo,
        "best_candidate": best,
        "survivors": survivors,
        "exact_reverse_audit": reverse_audit,
        "journal_row_count": len(journal),
        "validation_rows_opened": 0,
        "holdout_rows_opened": 0,
        "holdout_status": "NOT_EVALUATED",
        "safety": {key: False for key in ("network", "broker", "credentials", "collector", "paper", "practice", "live", "orders", "money_movement")},
    }
    ordered_journal = sorted(journal, key=lambda row: (row["candidate_id"], row["signal_timestamp"], row["instrument"], row["event_id"]))
    return result, journal_bytes(ordered_journal), capacity_artifact


def parameter_sensitivity(candidate_id: str, results: dict[str, Any]) -> dict[str, Any]:
    current = results[candidate_id]
    definition = current["definition"]
    neighbors = []
    for other_id, other in sorted(results.items()):
        if other_id == candidate_id:
            continue
        changed = [
            field for field in ("shock_threshold_atr", "arm", "holding_m5_bars")
            if definition[field] != other["definition"][field]
        ]
        if len(changed) == 1:
            neighbors.append({
                "candidate_id": other_id,
                "changed_dimension": changed[0],
                "after_cost_expectancy_r": other["base_after_cost"]["expectancy_r"],
                "expectancy_difference_r": other["base_after_cost"]["expectancy_r"] - current["base_after_cost"]["expectancy_r"],
                "same_expectancy_sign": (other["base_after_cost"]["expectancy_r"] > 0) == (current["base_after_cost"]["expectancy_r"] > 0),
            })
    return {"neighbor_count": len(neighbors), "neighbors": neighbors}


def build_artifacts(
    result: dict[str, Any], journal: bytes, capacity: dict[str, Any],
    prereg: dict[str, Any], code_path: Path,
) -> dict[str, bytes]:
    results = result["candidate_results"]
    sensitivities = {candidate: parameter_sensitivity(candidate, results) for candidate in sorted(results)}
    all_causes = sorted({cause for row in results.values() for cause in row["failure_causes"]})
    priority = [
        "INVALID_EXPERIMENT", "LEAKAGE", "NO_GROSS_EDGE", "COST_DESTROYED_EDGE",
        "BASELINE_FAILURE", "SIMPLE_BASELINE_FAILURE", "WALK_FORWARD_FAILURE",
        "COST_STRESS_FAILURE", "EXCESSIVE_DRAWDOWN", "INSUFFICIENT_TRADES",
        "INSUFFICIENT_BREADTH", "PAIR_OR_CURRENCY_CONCENTRATION",
        "DIRECTION_CONCENTRATION", "AFTER_COST_PROFIT_FACTOR_FAILURE",
    ]
    ordered_causes = [cause for cause in priority if cause in all_causes]
    if results:
        best_causes = results[result["best_candidate"]]["failure_causes"]
        primary = best_causes[0] if best_causes else None
    else:
        primary = "INSUFFICIENT_CAPACITY"
    postmortem = {
        "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_POSTMORTEM.v1",
        "status": "NOT_APPLICABLE_STAGE1_SURVIVOR" if result.get("survivors") else "POSTMORTEM_COMPLETE_REJECTED",
        "strategy_id": STRATEGY_ID,
        "strategy_mechanism_fingerprint": MECHANISM_FINGERPRINT,
        "economic_mechanism": prereg["economic_mechanism"],
        "dataset_identity": {
            "corpus_id": CORPUS_ID, "corpus_sha256": CORPUS_SHA256,
            "development_start": "2024-01-01T00:00:00Z",
            "development_end_exclusive": "2025-04-01T00:00:00Z",
        },
        "pair_universe": prereg["pair_universe"],
        "timeframes": prereg["timeframes"],
        "capacity": capacity,
        "candidate_rows": {
            candidate: {
                "candidate_fingerprint": row["definition"]["candidate_fingerprint"],
                "exact_rules": row["definition"],
                "gross": row["gross_midpoint"],
                "net": row["base_after_cost"],
                "stress": row["stress_after_cost"],
                "break_even": row["break_even"],
                "baselines": row["baselines"],
                "baseline_population_audit": row["baseline_population_audit"],
                "gates": row["gates"],
                "multiple_testing": row["multiple_testing"],
                "parameter_sensitivity": sensitivities[candidate],
                "primary_failure_cause": row["failure_causes"][0] if row["failure_causes"] else None,
                "secondary_failure_causes": row["failure_causes"][1:],
                "disposition": "ADVANCE_STAGE2" if row["stage1_pass"] else "REJECTED_DO_NOT_RETEST",
            }
            for candidate, row in sorted(results.items())
        },
        "root_causes": ordered_causes,
        "primary_family_failure_cause": primary,
        "secondary_family_failure_causes": [cause for cause in ordered_causes if cause != primary],
        "rejection_fingerprint": sha256_bytes(canonical_bytes({
            "mechanism": MECHANISM_FINGERPRINT,
            "failures": {candidate: row["failure_causes"] for candidate, row in sorted(results.items())},
        })),
        "prohibited_repeats": [
            "SAME_SIGNAL_AND_TARGET_MOMENTUM_RENAME",
            "CURRENCY_AGGREGATION_THEN_RANK_RESCUE",
            "TARGET_RESIDUAL_COINTEGRATION_OR_TRIANGULAR_CONVERGENCE",
            "POST_HOC_PAIR_SESSION_DIRECTION_VOLATILITY_REGIME_OR_SPREAD_FILTER",
            "COSMETIC_THRESHOLD_HOLD_OR_STOP_CHANGE",
            "REMOVE_OBSERVED_SPREAD_OR_SLIPPAGE",
        ],
        "salvageable_evidence": "Only mechanism-level timing and cost findings may inform a materially distinct preregistered hypothesis; no candidate may be retuned against these outcomes.",
        "next_distinct_hypothesis": "INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_STAGE0_ADOPT_EXISTING_F7_CONTRACT",
        "validation_rows_opened": 0,
        "holdout_rows_opened": 0,
        "holdout_status": "NOT_EVALUATED",
    }
    best = results[result["best_candidate"]] if results else None
    report = (
        "# Directed USD-Anchor To Non-USD Cross Lead-Lag Stage-1 Screen\n\n"
        f"Status: `{result['status']}`\n\n"
        + (
            f"Eight frozen candidates were scored. The best candidate was `{result['best_candidate']}` "
            f"with gross expectancy {best['gross_midpoint']['expectancy_r']:.9f}R, after-cost expectancy "
            f"{best['base_after_cost']['expectancy_r']:.9f}R, profit factor {best['base_after_cost']['profit_factor']:.9f}, "
            f"maximum drawdown {best['base_after_cost']['maximum_drawdown_pct']:.9f}%, and "
            f"{best['base_after_cost']['trade_count']} trades. Survivors: {len(result['survivors'])}.\n\n"
            if best else "The frozen capacity gate failed before any forward returns were calculated.\n\n"
        )
        + "The final holdout remained sealed. Results are historical simulations, not realized profit.\n"
    ).encode("utf-8")
    contract = {
        "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE1_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "preregistration_sha256": PREREGISTRATION_SHA256,
        "preregistration": prereg,
        "prior_actual_attempt_lower_bound": PRIOR_ATTEMPTS,
        "cumulative_actual_attempt_lower_bound": result["cumulative_actual_attempt_lower_bound"],
        "holdout_rule": "SEALED_NOT_EVALUATED",
    }
    checkpoint = {
        "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_CHECKPOINT.v1",
        "packet_id": PACKET_ID,
        "status": result["status"],
        "completed_candidate_ids": sorted(results),
        "survivors": result.get("survivors", []),
        "cumulative_actual_attempt_lower_bound": result["cumulative_actual_attempt_lower_bound"],
        "governed_after_cost_candidates": result.get("governed_after_cost_candidates_after", 135),
        "holdout_status": "NOT_EVALUATED",
        "next_action": "ADVANCE_SURVIVOR_TO_STAGE2" if result.get("survivors") else postmortem["next_distinct_hypothesis"],
    }
    primary = {
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_CAPACITY.json": canonical_bytes(capacity),
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_CHECKPOINT.json": canonical_bytes(checkpoint),
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_CONTRACT.json": canonical_bytes(contract),
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_RESULTS.json": canonical_bytes(result),
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_TRADE_JOURNAL.jsonl.gz": journal,
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_POSTMORTEM.json": canonical_bytes(postmortem),
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE1_REPORT.md": report,
    }
    code = code_path.read_bytes()
    manifest = {
        "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_MANIFEST.v1",
        "files": {name: {"bytes": len(data), "sha256": sha256_bytes(data)} for name, data in sorted(primary.items())},
        "code": {"path": code_path.as_posix(), "bytes": len(code), "sha256": sha256_bytes(code)},
        "dependencies": {
            relative: {"sha256": expected} for relative, expected in sorted(DEPENDENCY_HASHES.items())
        },
        "verified_partition_count": result.get("verified_partition_count", 0),
        "journal_rows": result.get("journal_row_count", 0),
        "validation_rows_opened": 0,
        "holdout_rows_opened": 0,
    }
    primary["AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_MANIFEST.json"] = canonical_bytes(manifest)
    journal_audit = audit_journal_bytes(journal, result.get("journal_row_count", 0)) if result.get("journal_row_count", 0) else {
        "pass": result["status"].startswith("STAGE0_INSUFFICIENT_CAPACITY"), "row_count": 0, "losing_rows": 0,
    }
    acceptance = {
        "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_ACCEPTANCE.v1",
        "packet_id": PACKET_ID,
        "checks": {
            "capacity_gate_before_forward_returns": (
                capacity["forward_returns_calculated_before_capacity_verdict"] == 0
                and capacity["outcome_guard_enforced"] is True
            ),
            "exact_eight_candidates_if_scored": len(results) in (0, 8),
            "trial_memory": result["cumulative_actual_attempt_lower_bound"] in (1187, 1195),
            "valid_complete_journal": journal_audit["pass"],
            "baseline_population_identity": all(
                row["baseline_population_audit"]["pass"]
                and all(audit["pass"] for audit in row["baseline_population_audit"]["event_identity_audits"].values())
                and row["baseline_population_audit"]["wrong_anchor_capacity_audit"]["pass"]
                for row in results.values()
            ),
            "negative_or_zero_cannot_pass_no_trade": all((row["base_after_cost"]["expectancy_r"] > 0) == row["gates"]["after_cost"] for row in results.values()),
            "exact_reverse_same_opportunities_opposite_directions": (
                len(result.get("exact_reverse_audit", {})) == 4
                and all(row["pass"] for row in result["exact_reverse_audit"].values())
            ),
            "validation_rows_zero": result["validation_rows_opened"] == 0,
            "holdout_rows_zero": result["holdout_rows_opened"] == 0,
            "postmortem_complete": (
                {
                    "strategy_id", "strategy_mechanism_fingerprint", "economic_mechanism",
                    "dataset_identity", "pair_universe", "timeframes", "capacity",
                    "candidate_rows", "root_causes", "primary_family_failure_cause",
                    "secondary_family_failure_causes", "rejection_fingerprint",
                    "prohibited_repeats", "salvageable_evidence", "next_distinct_hypothesis",
                    "validation_rows_opened", "holdout_rows_opened", "holdout_status",
                } <= set(postmortem)
                and all(
                    {
                        "candidate_fingerprint", "exact_rules", "gross", "net", "stress",
                        "break_even", "baselines", "baseline_population_audit", "gates",
                        "multiple_testing", "parameter_sensitivity", "primary_failure_cause",
                        "secondary_failure_causes", "disposition",
                    } <= set(row)
                    for row in postmortem["candidate_rows"].values()
                )
                and (bool(postmortem["root_causes"]) or bool(result.get("survivors")))
            ),
        },
        "journal_audit": journal_audit,
    }
    acceptance["status"] = "PASS" if all(acceptance["checks"].values()) else "FAIL"
    primary["AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_ACCEPTANCE.json"] = canonical_bytes(acceptance)
    return primary


def write_artifacts(output: Path, artifacts: dict[str, bytes]) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    for name, data in sorted(artifacts.items()):
        (output / name).write_bytes(data)
    receipt = {
        "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "files": {name: {"bytes": len(data), "sha256": sha256_bytes(data)} for name, data in sorted(artifacts.items())},
        "aggregate_sha256": sha256_bytes(b"".join(
            name.encode("utf-8") + b"\0" + hashlib.sha256(data).digest()
            for name, data in sorted(artifacts.items())
        )),
        "status": "PASS",
    }
    payload = canonical_bytes(receipt)
    (output / "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_RECEIPT.json").write_bytes(payload)
    return {"receipt_sha256": sha256_bytes(payload), **receipt}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--preregistration", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    prereg_path = (args.preregistration or repo / ".aios/staging/PKT_FOREX_031/run1/AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_PREREGISTRATION.json").resolve()
    result, journal, capacity = research(repo, prereg_path)
    prereg = verify_preregistration(prereg_path)
    artifacts = build_artifacts(result, journal, capacity, prereg, Path(__file__).resolve())
    receipt = write_artifacts(args.output.resolve(), artifacts)
    summary = {
        "status": result["status"],
        "best_candidate": result.get("best_candidate"),
        "survivors": result.get("survivors", []),
        "candidate_count_scored": result["candidate_count_scored"],
        "journal_rows": result.get("journal_row_count", 0),
        "cumulative_actual_attempt_lower_bound": result["cumulative_actual_attempt_lower_bound"],
        "validation_rows_opened": result["validation_rows_opened"],
        "holdout_rows_opened": result["holdout_rows_opened"],
        "receipt_sha256": receipt["receipt_sha256"],
        "aggregate_sha256": receipt["aggregate_sha256"],
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
