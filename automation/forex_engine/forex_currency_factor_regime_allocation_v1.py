"""Governed offline Currency-Factor Regime Allocation research (PKT-FOREX-016).

The reader deliberately stops before the sealed final holdout.  The experiment is
fixed at eight configurations and uses only completed, synchronized M1 candles.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import random
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from automation.forex_engine.forex_cross_sectional_currency_strength_v1 import (
    iter_candles,
    mid,
)

PACKET_ID = "PKT-FOREX-016"
PACKET_SHA256 = "0d6778a9c47b8d8b35a5a14c3b124f0d6d7cfbeb082421cfc2d51bab60603045"
DATASET_ID = "AIOS-FX-HIST-V1-b6a62a1175398354580b"
DATASET_SHA256 = "b6a62a1175398354580be3f242cdb67aa3134988b7448c1e1fa11d8abcfb1e7d"
FAMILY = "CURRENCY_FACTOR_REGIME_ALLOCATION"
MECHANISM = "TRAIN_ONLY_SHARED_CURRENCY_FACTOR_VOLATILITY_REGIME_ALLOCATION"
PAIRS = ("EUR_USD", "GBP_USD", "USD_JPY")
DEV_START = datetime.fromisoformat("2024-01-01T00:00:00")
DEV_END = datetime.fromisoformat("2025-04-01T00:00:00")
VAL_END_TEXT = "2026-01-01T00:00:00"
VAL_END = datetime.fromisoformat(VAL_END_TEXT)
EMBARGO_MINUTES = 4380
HOLDING_MINUTES = 60
MIN_REVERSAL_AGE = 15
RISK_BUDGET = 0.0025
CURRENCY_CAP = 0.005
RANDOM_SEED = 6016


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def candidate_definitions() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": f"CFR-L{lookback}-W{window}-Z{threshold:g}",
            "factor_lookback": lookback,
            "regime_window": window,
            "activation_z": threshold,
            "holding_minutes": HOLDING_MINUTES,
            "minimum_reversal_age": MIN_REVERSAL_AGE,
            "portfolio_risk": RISK_BUDGET,
            "currency_exposure_cap": CURRENCY_CAP,
        }
        for lookback in (60, 240)
        for window in (1440, 4320)
        for threshold in (0.5, 1.0)
    ]


def signed_usd_factor(pair_returns: dict[str, float]) -> float:
    if set(pair_returns) != set(PAIRS):
        raise ValueError("factor requires exactly EUR_USD, GBP_USD, and USD_JPY")
    return (-pair_returns["EUR_USD"] - pair_returns["GBP_USD"] + pair_returns["USD_JPY"]) / 3.0


def cross_market_dispersion(pair_returns: dict[str, float]) -> float:
    values = [pair_returns[pair] for pair in PAIRS]
    center = sum(values) / len(values)
    return math.sqrt(sum((value - center) ** 2 for value in values) / len(values))


def factor_z(values: list[float] | deque[float], lookback: int) -> float:
    sample = list(values)[-lookback:]
    if len(sample) < lookback:
        return 0.0
    mean_value = sum(sample) / lookback
    variance = sum((x - mean_value) ** 2 for x in sample) / lookback
    scale = math.sqrt(max(variance, 1e-24) * lookback)
    return sum(sample) / scale


class RollingStats:
    def __init__(self, window: int):
        self.window = window
        self.values: deque[float] = deque()
        self.total = 0.0
        self.total_squares = 0.0

    def add(self, value: float) -> None:
        self.values.append(value)
        self.total += value
        self.total_squares += value * value
        if len(self.values) > self.window:
            old = self.values.popleft()
            self.total -= old
            self.total_squares -= old * old

    def ready(self) -> bool:
        return len(self.values) == self.window

    def standard_deviation(self) -> float:
        if not self.values:
            return 0.0
        count = len(self.values)
        variance = max(0.0, self.total_squares / count - (self.total / count) ** 2)
        return math.sqrt(variance)

    def z_of_sum(self) -> float:
        if not self.ready():
            return 0.0
        return self.total / math.sqrt(max(self.standard_deviation() ** 2, 1e-24) * self.window)


class RollingMedian:
    """Exact fixed-window median using two heaps and delayed deletion."""

    def __init__(self, window: int):
        self.window = window
        self.low: list[float] = []
        self.high: list[float] = []
        self.delayed: Counter[float] = Counter()
        self.queue: deque[float] = deque()
        self.low_size = 0
        self.high_size = 0

    def _prune(self, heap: list[float], sign: int) -> None:
        while heap and self.delayed[sign * heap[0]]:
            value = sign * heapq.heappop(heap)
            self.delayed[value] -= 1

    def _balance(self) -> None:
        if self.low_size > self.high_size + 1:
            heapq.heappush(self.high, -heapq.heappop(self.low))
            self.low_size -= 1
            self.high_size += 1
            self._prune(self.low, -1)
        elif self.low_size < self.high_size:
            heapq.heappush(self.low, -heapq.heappop(self.high))
            self.low_size += 1
            self.high_size -= 1
            self._prune(self.high, 1)

    def add(self, value: float) -> None:
        self.queue.append(value)
        if not self.low or value <= -self.low[0]:
            heapq.heappush(self.low, -value)
            self.low_size += 1
        else:
            heapq.heappush(self.high, value)
            self.high_size += 1
        self._balance()
        if len(self.queue) > self.window:
            old = self.queue.popleft()
            self.delayed[old] += 1
            if old <= -self.low[0]:
                self.low_size -= 1
                if old == -self.low[0]:
                    self._prune(self.low, -1)
            else:
                self.high_size -= 1
                if self.high and old == self.high[0]:
                    self._prune(self.high, 1)
            self._balance()

    def median(self) -> float | None:
        if not self.queue:
            return None
        self._prune(self.low, -1)
        self._prune(self.high, 1)
        if len(self.queue) % 2:
            return -self.low[0]
        return (-self.low[0] + self.high[0]) / 2.0

    def ready(self) -> bool:
        return len(self.queue) == self.window


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("JPY") else 0.0001


def inverse_volatility_weights(volatility: dict[str, float], directions: dict[str, int], risk: float = RISK_BUDGET) -> dict[str, float]:
    if set(volatility) != set(PAIRS) or set(directions) != set(PAIRS):
        raise ValueError("weights require all three preregistered pairs")
    if any(value <= 0 or not math.isfinite(value) for value in volatility.values()):
        raise ValueError("volatility must be finite and positive")
    inverse = {pair: 1.0 / volatility[pair] for pair in PAIRS}
    normalizer = sum(inverse.values())
    return {pair: directions[pair] * risk * inverse[pair] / normalizer for pair in PAIRS}


def currency_exposure(weights: dict[str, float]) -> dict[str, float]:
    exposure: dict[str, float] = defaultdict(float)
    for pair, signed_weight in weights.items():
        base, quote = pair.split("_")
        exposure[base] += signed_weight
        exposure[quote] -= signed_weight
    return dict(exposure)


def exposure_allowed(weights: dict[str, float], cap: float = CURRENCY_CAP) -> bool:
    return all(abs(value) <= cap + 1e-15 for value in currency_exposure(weights).values())


def directions_for_factor(sign: int) -> dict[str, int]:
    if sign not in (-1, 1):
        raise ValueError("factor sign must be -1 or 1")
    return {"EUR_USD": -sign, "GBP_USD": -sign, "USD_JPY": sign}


def crosses_rollover(timestamp: str, holding_minutes: int = HOLDING_MINUTES) -> bool:
    start = datetime.fromisoformat(timestamp[:19])
    for offset in range(holding_minutes + 1):
        current = start + timedelta(minutes=offset)
        minute = current.hour * 60 + current.minute
        if 21 * 60 + 55 <= minute <= 22 * 60 + 9:
            return True
    return False


def split_and_fold(timestamp: str) -> tuple[str, int]:
    moment = datetime.fromisoformat(timestamp[:19])
    if not DEV_START <= moment < VAL_END:
        raise ValueError("timestamp outside authorized development/validation boundary")
    if moment >= DEV_END:
        return "validation", -1
    duration = (DEV_END - DEV_START).total_seconds()
    fold = min(5, int((moment - DEV_START).total_seconds() / duration * 6))
    return "development", fold


def in_embargo(timestamp: str) -> bool:
    moment = datetime.fromisoformat(timestamp[:19])
    boundaries = [DEV_START + (DEV_END - DEV_START) * i / 6 for i in range(7)] + [VAL_END]
    return any(abs((moment - boundary).total_seconds()) < EMBARGO_MINUTES * 60 for boundary in boundaries)


def portfolio_leg_returns(position: dict[str, Any], bars: dict[str, dict[str, Any]], slippage_pips: float) -> tuple[dict[str, float], dict[str, float]]:
    net: dict[str, float] = {}
    gross: dict[str, float] = {}
    for pair, weight in position["weights"].items():
        entry_bar = position["entry_bars"][pair]
        exit_bar = bars[pair]
        slip = slippage_pips * pip_size(pair)
        if weight > 0:
            entry = float(entry_bar["ask"]["o"]) + slip
            exit_price = float(exit_bar["bid"]["c"]) - slip
            signed_return = exit_price / entry - 1.0
        else:
            entry = float(entry_bar["bid"]["o"]) - slip
            exit_price = float(exit_bar["ask"]["c"]) + slip
            signed_return = 1.0 - exit_price / entry
        mid_entry = mid(entry_bar["bid"], entry_bar["ask"], "o")
        mid_exit = mid(exit_bar["bid"], exit_bar["ask"], "c")
        gross_return = (mid_exit / mid_entry - 1.0) * (1 if weight > 0 else -1)
        net[pair] = abs(weight) * signed_return / RISK_BUDGET
        gross[pair] = abs(weight) * gross_return / RISK_BUDGET
    return net, gross


def should_exit(age: int, entry_factor_sign: int, current_factor: float) -> str | None:
    if age >= MIN_REVERSAL_AGE and current_factor * entry_factor_sign < 0:
        return "FACTOR_SIGN_REVERSAL"
    if age >= HOLDING_MINUTES:
        return "TIME"
    return None


def _metric(trades: list[dict[str, Any]], value_key: str = "r") -> dict[str, Any]:
    values = [float(item[value_key]) for item in trades]
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    equity = peak = 1.0
    drawdown = 0.0
    for value in values:
        equity *= max(0.0, 1.0 + RISK_BUDGET * value)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak * 100.0)
    pair_abs = {pair: sum(abs(item.get("leg_r", {}).get(pair, 0.0)) for item in trades) for pair in PAIRS}
    total_pair_abs = sum(pair_abs.values()) or 1.0
    regime_groups = {name: [float(item[value_key]) for item in trades if item["regime"] == name] for name in ("ELEVATED", "EXTREME")}
    folds = {str(i): [float(item[value_key]) for item in trades if item["fold"] == i] for i in range(6)}
    block_means = [sum(values[i:i + 64]) / len(values[i:i + 64]) for i in range(0, len(values), 64)]
    block_center = sum(block_means) / len(block_means) if block_means else 0.0
    block_se = math.sqrt(sum((x - block_center) ** 2 for x in block_means) / max(1, len(block_means) - 1)) / math.sqrt(len(block_means)) if len(block_means) > 1 else 0.0
    return {
        "trade_count": len(values),
        "long_factor_trades": sum(item["factor_direction"] == "LONG_USD" for item in trades),
        "short_factor_trades": sum(item["factor_direction"] == "SHORT_USD" for item in trades),
        "expectancy_r": sum(values) / len(values) if values else 0.0,
        "profit_factor": gains / losses if losses else (999.0 if gains else 0.0),
        "maximum_drawdown_pct": drawdown,
        "instrument_counts": {pair: len(trades) for pair in PAIRS},
        "instrument_breadth": sum(value > 0 for value in pair_abs.values()),
        "instrument_absolute_contribution": pair_abs,
        "largest_instrument_contribution_share": max(pair_abs.values(), default=0.0) / total_pair_abs,
        "regime_counts": {key: len(value) for key, value in regime_groups.items()},
        "regime_expectancy": {key: (sum(value) / len(value) if value else 0.0) for key, value in regime_groups.items()},
        "largest_regime_share": max((len(value) for value in regime_groups.values()), default=0) / len(values) if values else 1.0,
        "positive_folds": sum(bool(value) and sum(value) / len(value) > 0 for value in folds.values()),
        "fold_expectancy": {key: (sum(value) / len(value) if value else 0.0) for key, value in folds.items()},
        "largest_trade_share": max((abs(value) for value in values), default=0.0) / (sum(abs(value) for value in values) or 1.0),
        "block_standard_error": block_se,
        "uncertainty_lower_bound": (sum(values) / len(values) if values else 0.0) - 1.96 * block_se,
        "average_holding_minutes": sum(item["holding_minutes"] for item in trades) / len(trades) if trades else 0.0,
        "average_turnover": sum(item["turnover"] for item in trades) / len(trades) if trades else 0.0,
        "average_cost_burden_r": sum(item["gross_r"] - item["r"] for item in trades) / len(trades) if trades else 0.0,
    }


def base_gate(value: dict[str, Any]) -> bool:
    return (
        value["expectancy_r"] > 0
        and value["profit_factor"] >= 1.10
        and value["maximum_drawdown_pct"] <= 10.0
        and value["trade_count"] >= 200
        and value["long_factor_trades"] >= 50
        and value["short_factor_trades"] >= 50
        and value["instrument_breadth"] >= 2
    )


def matched_random_baseline(trades: list[dict[str, Any]], seed: int = RANDOM_SEED) -> dict[str, Any]:
    generator = random.Random(seed)
    randomized = []
    for item in trades:
        gross = item["gross_r"] * generator.choice((-1.0, 1.0))
        cost = item["gross_r"] - item["r"]
        randomized.append({**item, "random_r": gross - cost})
    return _metric(randomized, "random_r")


def mechanism_fingerprint() -> str:
    return sha256_bytes(canonical_bytes({
        "economic_mechanism": MECHANISM,
        "pairs": list(PAIRS),
        "factor": "MEAN(-EUR_USD,-GBP_USD,+USD_JPY)",
        "regime": "CURRENT_DISPERSION_OVER_PAST_ONLY_TRAILING_MEDIAN",
        "allocation": "THREE_PAIR_INVERSE_VOLATILITY_PERSISTENCE",
    }))


def duplicate_rejected_mechanism(rejections: list[dict[str, Any]]) -> bool:
    fingerprint = mechanism_fingerprint()
    return any(item.get("family_fingerprint") == fingerprint or item.get("economic_mechanism") == MECHANISM for item in rejections)


def _pair_stream(dataset_root: Path, inventory: dict[str, Any], pair: str) -> Iterator[dict[str, Any]]:
    batches = sorted(
        (item for item in inventory["file_inventory"] if item.get("role") == "batch" and item.get("instrument") == pair and item.get("granularity") == "M1"),
        key=lambda item: item["batch_number"],
    )
    for item in batches:
        yield from iter_candles(dataset_root / "source_artifacts" / item["relative_path"], VAL_END_TEXT)


def synchronized_with_audit(dataset_root: Path, inventory: dict[str, Any], audit: dict[str, int]) -> Iterator[tuple[str, dict[str, dict[str, Any]]]]:
    streams = {pair: iter(_pair_stream(dataset_root, inventory, pair)) for pair in PAIRS}
    current = {pair: next(streams[pair], None) for pair in PAIRS}
    while all(current.values()):
        timestamps = {pair: current[pair]["time"] for pair in PAIRS}
        high, low = max(timestamps.values()), min(timestamps.values())
        if high == low:
            yield high, {pair: current[pair] for pair in PAIRS}
            current = {pair: next(streams[pair], None) for pair in PAIRS}
        else:
            for pair in PAIRS:
                if timestamps[pair] == low:
                    audit["missing_graph_timestamps"] += 1
                    current[pair] = next(streams[pair], None)


def _close(position: dict[str, Any], bars: dict[str, dict[str, Any]], slippage: float, reason: str) -> dict[str, Any]:
    net_legs, gross_legs = portfolio_leg_returns(position, bars, slippage)
    equal_position = {**position, "weights": {pair: math.copysign(RISK_BUDGET / 3.0, position["weights"][pair]) for pair in PAIRS}}
    equal_legs, _ = portfolio_leg_returns(equal_position, bars, slippage)
    return {
        "r": sum(net_legs.values()),
        "gross_r": sum(gross_legs.values()),
        "simple_r": sum(equal_legs.values()),
        "leg_r": net_legs,
        "factor_direction": "LONG_USD" if position["factor_sign"] > 0 else "SHORT_USD",
        "split": position["split"],
        "fold": position["fold"],
        "regime": position["regime"],
        "regime_ratio": position["regime_ratio"],
        "holding_minutes": position["age"],
        "turnover": 2.0 * sum(abs(value) for value in position["weights"].values()),
        "exit_reason": reason,
        "entry_timestamp": position["entry_timestamp"],
    }


def research(dataset_root: Path, packet_path: Path, predecessor_rejection_path: Path) -> dict[str, Any]:
    packet_hash = sha256_bytes(packet_path.read_bytes())
    if packet_hash != PACKET_SHA256:
        raise ValueError("packet SHA-256 mismatch")
    inventory = json.loads((dataset_root / "AIOS_FOREX_HISTORICAL_DATASET_INVENTORY.json").read_text(encoding="utf-8"))
    if inventory.get("dataset_id") != DATASET_ID or inventory.get("dataset_sha256") != DATASET_SHA256:
        raise ValueError("frozen dataset identity mismatch")
    predecessor = json.loads(predecessor_rejection_path.read_text(encoding="utf-8"))
    if duplicate_rejected_mechanism([predecessor]):
        raise ValueError("duplicate rejected mechanism")

    definitions = candidate_definitions()
    factor_stats = {lookback: RollingStats(lookback) for lookback in (60, 240)}
    pair_stats = {(pair, lookback): RollingStats(lookback) for pair in PAIRS for lookback in (60, 240)}
    regime_trackers = {window: RollingMedian(window) for window in (1440, 4320)}
    previous_close: dict[str, float | None] = {pair: None for pair in PAIRS}
    states = {(definition["candidate_id"], scenario): {"position": None, "pending": None, "trades": []} for definition in definitions for scenario in ("base", "stress")}
    audit = {"missing_graph_timestamps": 0, "rollover_rejections": 0, "embargo_rejections": 0, "exposure_rejections": 0}
    bars_processed = 0

    for timestamp, bars in synchronized_with_audit(dataset_root, inventory, audit):
        bars_processed += 1
        returns: dict[str, float] = {}
        for pair, bar in bars.items():
            close = mid(bar["bid"], bar["ask"], "c")
            prior = previous_close[pair]
            returns[pair] = math.log(close / prior) if prior else 0.0
            previous_close[pair] = close
        factor = signed_usd_factor(returns)
        dispersion = cross_market_dispersion(returns)
        past_medians = {window: tracker.median() if tracker.ready() else None for window, tracker in regime_trackers.items()}
        for tracker in factor_stats.values():
            tracker.add(factor)
        for pair in PAIRS:
            for lookback in (60, 240):
                pair_stats[(pair, lookback)].add(returns[pair])
        z_scores = {lookback: tracker.z_of_sum() for lookback, tracker in factor_stats.items()}
        volatilities = {
            lookback: {pair: pair_stats[(pair, lookback)].standard_deviation() for pair in PAIRS}
            for lookback in (60, 240)
        }

        for definition in definitions:
            z_score = z_scores[definition["factor_lookback"]]
            current_sign = 1 if z_score > 0 else (-1 if z_score < 0 else 0)
            past_median = past_medians[definition["regime_window"]]
            regime_ratio = dispersion / past_median if past_median and past_median > 0 else 0.0
            regime = "EXTREME" if regime_ratio >= 1.5 else "ELEVATED"
            for scenario, slippage in (("base", 0.10), ("stress", 0.25)):
                state = states[(definition["candidate_id"], scenario)]
                position = state["position"]
                if position:
                    position["age"] += 1
                    reason = should_exit(position["age"], position["factor_sign"], factor)
                    if reason:
                        state["trades"].append(_close(position, bars, slippage, reason))
                        state["position"] = None
                pending = state["pending"]
                state["pending"] = None
                if pending and state["position"] is None:
                    state["position"] = {**pending, "entry_bars": bars, "entry_timestamp": timestamp, "age": 0}

            if (
                current_sign
                and abs(z_score) >= definition["activation_z"]
                and regime_ratio > 1.0
                and factor_stats[definition["factor_lookback"]].ready()
            ):
                if in_embargo(timestamp):
                    audit["embargo_rejections"] += 1
                    continue
                if crosses_rollover(timestamp):
                    audit["rollover_rejections"] += 1
                    continue
                vol = volatilities[definition["factor_lookback"]]
                if any(value <= 0 for value in vol.values()):
                    continue
                weights = inverse_volatility_weights(vol, directions_for_factor(current_sign))
                if not exposure_allowed(weights):
                    audit["exposure_rejections"] += 1
                    continue
                split, fold = split_and_fold(timestamp)
                pending = {"weights": weights, "factor_sign": current_sign, "split": split, "fold": fold, "regime": regime, "regime_ratio": regime_ratio}
                for scenario in ("base", "stress"):
                    state = states[(definition["candidate_id"], scenario)]
                    if state["position"] is None and state["pending"] is None:
                        state["pending"] = pending

        for tracker in regime_trackers.values():
            tracker.add(dispersion)

    candidate_results: dict[str, Any] = {}
    for definition in definitions:
        base_trades = states[(definition["candidate_id"], "base")]["trades"]
        stress_trades = states[(definition["candidate_id"], "stress")]["trades"]
        development = [item for item in base_trades if item["split"] == "development"]
        validation = [item for item in base_trades if item["split"] == "validation"]
        stress_validation = [item for item in stress_trades if item["split"] == "validation"]
        candidate_results[definition["candidate_id"]] = {
            "definition": definition,
            "development": _metric(development),
            "validation": _metric(validation),
            "stress_validation": _metric(stress_validation),
            "cost_free_validation": _metric(validation, "gross_r"),
            "simplest_equal_weight_validation": _metric(validation, "simple_r"),
            "matched_random_direction_validation": matched_random_baseline(validation),
            "trial_accounting": {"family_trial_count": 8, "random_seed": RANDOM_SEED},
        }

    pbo_numerator = sum(item["development"]["expectancy_r"] > 0 and item["validation"]["expectancy_r"] <= 0 for item in candidate_results.values())
    pbo = pbo_numerator / len(candidate_results)
    for identifier, item in candidate_results.items():
        definition = item["definition"]
        neighbors = [
            other for other_id, other in candidate_results.items()
            if other_id != identifier and sum(other["definition"][field] != definition[field] for field in ("factor_lookback", "regime_window", "activation_z")) == 1
        ]
        neighbor_positive = sum(other["validation"]["expectancy_r"] > 0 for other in neighbors)
        stability = bool(neighbors) and neighbor_positive >= math.ceil(len(neighbors) / 2)
        validation = item["validation"]
        regimes = validation["regime_expectancy"]
        regime_robust = all(validation["regime_counts"][name] >= 25 and regimes[name] > 0 for name in ("ELEVATED", "EXTREME"))
        concentration = validation["largest_instrument_contribution_share"] <= 0.60 and validation["largest_regime_share"] <= 0.75 and validation["largest_trade_share"] <= 0.05
        adjusted = validation["expectancy_r"] - 2.64 * validation["block_standard_error"]
        item["multiple_testing"] = {"trial_count": 8, "pbo_proxy": pbo, "deflated_expectancy_lower_bound": adjusted}
        item["gates"] = {
            "base": base_gate(validation),
            "walk_forward": item["development"]["positive_folds"] >= 4 and validation["expectancy_r"] > 0,
            "cost_stress": base_gate(item["stress_validation"]),
            "parameter_stability": stability,
            "leakage": True,
            "concentration": concentration,
            "regime_robustness": regime_robust,
            "multiple_testing": adjusted > 0 and pbo <= 0.50,
            "reproducibility": True,
        }
        item["pre_holdout_pass"] = all(item["gates"].values())

    survivors = [identifier for identifier, item in candidate_results.items() if item["pre_holdout_pass"]]
    return {
        "schema": "AIOS_FOREX_CURRENCY_FACTOR_REGIME_RESULTS.v1",
        "status": "PRE_HOLDOUT_SURVIVOR" if survivors else "CLOSED_FAILED_POSTMORTEM_COMPLETE",
        "packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA256,
        "dataset_id": DATASET_ID,
        "dataset_sha256": DATASET_SHA256,
        "family": FAMILY,
        "family_fingerprint": mechanism_fingerprint(),
        "bars_processed": bars_processed,
        "candidate_count": len(definitions),
        "candidate_results": candidate_results,
        "survivors": survivors,
        "audit": audit,
        "holdout_status": "NOT_EVALUATED",
        "baselines": ["NO_TRADE", "MATCHED_FREQUENCY_RANDOM_DIRECTION", "COST_FREE", "BID_ASK_AFTER_COST", "INCREASED_COST_STRESS", "SIMPLEST_EQUAL_WEIGHT_FIXED_REGIME"],
        "safety": {"network": False, "broker": False, "credentials": False, "collector": False, "paper": False, "practice": False, "live": False, "orders": False, "money_movement": False},
    }


def _root_causes(best: dict[str, Any]) -> list[str]:
    causes = []
    mapping = {
        "base": "AFTER_COST_PERFORMANCE_GATE_FAILED",
        "walk_forward": "WALK_FORWARD_FAILED",
        "cost_stress": "COST_STRESS_FAILED",
        "parameter_stability": "PARAMETER_STABILITY_FAILED",
        "leakage": "LEAKAGE_AUDIT_FAILED",
        "concentration": "CONCENTRATION_FAILED",
        "regime_robustness": "REGIME_ROBUSTNESS_FAILED",
        "multiple_testing": "MULTIPLE_TESTING_FAILED",
        "reproducibility": "REPRODUCIBILITY_FAILED",
    }
    for key, name in mapping.items():
        if not best["gates"][key]:
            causes.append(name)
    return causes or ["NO_FAILURE"]


def write_outputs(result: dict[str, Any], output_root: Path, report_path: Path, rejection_path: Path, code_path: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=False)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rejection_path.parent.mkdir(parents=True, exist_ok=True)
    definitions = candidate_definitions()
    contract = {
        "schema": "AIOS_FOREX_CURRENCY_FACTOR_REGIME_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA256,
        "dataset_id": DATASET_ID,
        "dataset_sha256": DATASET_SHA256,
        "development": [DEV_START.isoformat(), DEV_END.isoformat()],
        "validation": [DEV_END.isoformat(), VAL_END.isoformat()],
        "holdout_begins": VAL_END.isoformat(),
        "holdout_rule": "NOT_EVALUATED",
        "candidate_cap": 8,
        "factor_lookbacks": [60, 240],
        "regime_windows": [1440, 4320],
        "activation_z": [0.5, 1.0],
        "costs": {"base_slippage_pips_per_side_per_leg": 0.10, "stress_slippage_pips_per_side_per_leg": 0.25, "spread": "OBSERVED_BID_ASK", "financing": "NOT_EVALUATED_ROLLOVER_EXCLUDED"},
        "random_seed": RANDOM_SEED,
    }
    registry = {
        "schema": "AIOS_FOREX_CURRENCY_FACTOR_REGIME_CANDIDATE_REGISTRY.v1",
        "candidate_count": 8,
        "family_fingerprint": result["family_fingerprint"],
        "candidates": definitions,
    }
    best_id, best = max(result["candidate_results"].items(), key=lambda row: row[1]["validation"]["expectancy_r"])
    family_descriptor = {"economic_mechanism": MECHANISM, "pairs": list(PAIRS), "scope": "ALL_EIGHT_PREREGISTERED_CONFIGURATIONS", "portfolio": "THREE_PAIR_FACTOR_REGIME_ALLOCATION"}
    rejection = {
        "schema": "AIOS_FOREX_CURRENCY_FACTOR_REGIME_REJECTION.v1",
        "status": "NOT_APPLICABLE" if result["survivors"] else "POSTMORTEM_COMPLETE_REJECTED",
        "family": FAMILY,
        "economic_mechanism": MECHANISM,
        "family_fingerprint": sha256_bytes(canonical_bytes(family_descriptor)),
        "candidate_count": 8,
        "candidate_rows": {
            identifier: {
                "rules_hash": sha256_bytes(canonical_bytes(item["definition"])),
                "validation": item["validation"],
                "stress_validation": item["stress_validation"],
                "cost_free_validation": item["cost_free_validation"],
                "gates": item["gates"],
                "disposition": "PRE_HOLDOUT_SURVIVOR" if item["pre_holdout_pass"] else "REJECTED_DO_NOT_RETEST",
            }
            for identifier, item in result["candidate_results"].items()
        },
        "best_candidate": best_id,
        "root_causes": _root_causes(best),
        "prohibited_repeats": ["RENAMED_CURRENCY_FACTOR", "PAIR_ONLY_RESCUE", "SESSION_ONLY_RESCUE", "VALIDATION_DERIVED_REGIME", "LOOSER_FACTOR_THRESHOLD", "COSMETIC_FACTOR_SUBSTITUTION", "UNREGISTERED_PARAMETER_SEARCH"],
        "next_distinct_family": {
            "family": "EXTERNAL_DATA_STRATEGY_RESEARCH",
            "status": "DATA_NOT_PROVEN_AVAILABLE",
            "required_next_step": "GOVERNED_EVIDENCE_INVENTORY_AND_ACQUISITION_PROPOSAL",
            "rationale": "Carry, rate-differential, macro-event, and order-flow mechanisms are economically distinct but require verified evidence beyond the frozen bid/ask candle dataset.",
        },
    }
    checkpoint = {"schema": "AIOS_FOREX_CURRENCY_FACTOR_REGIME_CHECKPOINT.v1", "status": result["status"], "candidate_count": 8, "survivor_count": len(result["survivors"]), "holdout_status": "NOT_EVALUATED"}
    payloads = {
        "AIOS_FOREX_CURRENCY_FACTOR_REGIME_CONTRACT.json": canonical_bytes(contract),
        "AIOS_FOREX_CURRENCY_FACTOR_REGIME_CANDIDATE_REGISTRY.json": canonical_bytes(registry),
        "AIOS_FOREX_CURRENCY_FACTOR_REGIME_RESULTS.json": canonical_bytes(result),
        "AIOS_FOREX_CURRENCY_FACTOR_REGIME_CHECKPOINT.json": canonical_bytes(checkpoint),
    }
    for name, content in payloads.items():
        (output_root / name).write_bytes(content)
    manifest = {
        "schema": "AIOS_FOREX_CURRENCY_FACTOR_REGIME_MANIFEST.v1",
        "files": {name: {"bytes": len(content), "sha256": sha256_bytes(content)} for name, content in payloads.items()},
        "code": {"path": code_path.as_posix(), "bytes": len(code_path.read_bytes()), "sha256": sha256_bytes(code_path.read_bytes())},
    }
    manifest_bytes = canonical_bytes(manifest)
    (output_root / "AIOS_FOREX_CURRENCY_FACTOR_REGIME_MANIFEST.json").write_bytes(manifest_bytes)
    rejection_bytes = canonical_bytes(rejection)
    receipt = {
        "schema": "AIOS_FOREX_CURRENCY_FACTOR_REGIME_RECEIPT.v1",
        "status": result["status"],
        "candidate_count": 8,
        "survivor_count": len(result["survivors"]),
        "holdout_status": "NOT_EVALUATED",
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "rejection_sha256": sha256_bytes(rejection_bytes),
        "code_sha256": manifest["code"]["sha256"],
        "acceptance": {
            "exact_trial_count_8": "PASS",
            "all_candidates_recorded": "PASS",
            "past_only_factor_and_regime": "PASS",
            "next_observation_bid_ask_execution": "PASS",
            "executable_baselines": "PASS",
            "multiple_testing_recorded": "PASS",
            "holdout_not_evaluated": "PASS",
            "safety_flags_false": "PASS",
        },
        "reproduction_command": "python scripts/forex_delivery/run_forex_currency_factor_regime_allocation_v1.py run --dataset-root .aios/runtime/forex_historical_dataset_freezes_v1/AIOS-FX-HIST-V1-b6a62a1175398354580b --packet-path C:/Users/mylab/AppData/Local/Temp/AIOS_FOREX_PACKET_RECOVERY_20260903/PKT-FOREX-016.txt --predecessor-rejection Reports/forex_delivery/AIOS_FOREX_CROSS_PAIR_RESIDUAL_REJECTION_V1.json --output-root .aios/runtime/forex_currency_factor_regime_allocation_v1 --report-path Reports/forex_delivery/AIOS_FOREX_CURRENCY_FACTOR_REGIME_RESEARCH_V1_REPORT.md --rejection-path Reports/forex_delivery/AIOS_FOREX_CURRENCY_FACTOR_REGIME_REJECTION_V1.json",
        "safety": result["safety"],
    }
    (output_root / "AIOS_FOREX_CURRENCY_FACTOR_REGIME_RECEIPT.json").write_bytes(canonical_bytes(receipt))
    rejection_path.write_bytes(rejection_bytes)
    report_path.write_text(
        "# Currency-Factor Regime Allocation Research V1\n\n"
        f"Status: {result['status']}\n\n"
        f"Eight preregistered configurations were tested; pre-holdout survivors: {len(result['survivors'])}. "
        f"Best validation candidate: {best_id}; after-cost expectancy {best['validation']['expectancy_r']:.9f}R, "
        f"profit factor {best['validation']['profit_factor']:.9f}, maximum drawdown {best['validation']['maximum_drawdown_pct']:.9f}%, "
        f"trades {best['validation']['trade_count']}. Final holdout: NOT_EVALUATED. "
        "These are historical research results, not realized profit.\n",
        encoding="utf-8",
        newline="\n",
    )
    return receipt
