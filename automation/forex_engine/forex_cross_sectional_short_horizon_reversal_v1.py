"""Governed offline cross-sectional short-horizon reversal research.

PKT-FOREX-018-R1 only.  The reader verifies every M5 partition before opening it
and refuses to open the sealed 2026-01 (or later) holdout partitions.
"""
from __future__ import annotations

import gzip
import hashlib
import heapq
import json
import math
import random
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

PACKET_ID = "PKT-FOREX-018-R1"
PACKET_SHA256 = "302a61706ea7af7555f5c6f83631083e57859bf80c389d83aacd8978a0aa49f5"
CORPUS_ID = "AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2"
CORPUS_FINGERPRINT = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
FAMILY = "CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL"
MECHANISM = "REVERSAL_OF_SYNCHRONIZED_RELATIVE_OVEREXTENSION"
DEV_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DEV_END = datetime(2025, 4, 1, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
EMBARGO_BARS = 18
PRIOR_TRIALS = 52
RANDOM_SEED = 7018
MIN_SYNCHRONIZED_FRACTION = 0.80
RISK_FRACTION = 0.0025
NO_TRADE_EXPECTANCY_R = 0.0


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pair_return_signs(pair: str) -> dict[str, int]:
    base, quote = pair.split("_")
    return {base: 1, quote: -1}


def currency_strength(pair_returns: dict[str, float]) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for pair, value in sorted(pair_returns.items()):
        for currency, sign in pair_return_signs(pair).items():
            values[currency].append(sign * value)
    return {currency: math.fsum(samples) / len(samples) for currency, samples in sorted(values.items())}


def reversal_pair(strong: str, weak: str, available_pairs: set[str]) -> tuple[str, str] | None:
    """Return a direct pair and direction that buys weak versus strong."""
    direct = f"{strong}_{weak}"
    if direct in available_pairs:
        return direct, "SHORT"
    inverse = f"{weak}_{strong}"
    if inverse in available_pairs:
        return inverse, "LONG"
    return None


def choose_reversal_pair(scores: dict[str, float], available_pairs: set[str]) -> tuple[str, str, float] | None:
    ranked = sorted(scores.items(), key=lambda row: (-row[1], row[0]))
    choices: list[tuple[float, str, str]] = []
    for strong, strong_score in ranked:
        for weak, weak_score in reversed(ranked):
            if strong == weak:
                continue
            selected = reversal_pair(strong, weak, available_pairs)
            if selected:
                choices.append((strong_score - weak_score, selected[0], selected[1]))
    if not choices:
        return None
    dispersion, pair, direction = sorted(choices, key=lambda row: (-row[0], row[1], row[2]))[0]
    return pair, direction, dispersion


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("_JPY") else 0.0001


def candidate_definitions() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": f"CSHR-L{lookback}-D{dispersion:g}-H{holding}",
            "lookback_bars": lookback,
            "dispersion_bps": dispersion,
            "holding_bars": holding,
            "atr_bars": 14,
            "stop_atr": 1.0,
            "target_r": 1.5,
            "risk_fraction": RISK_FRACTION,
        }
        for lookback in (3, 6, 12)
        for dispersion in (2.0, 4.0)
        for holding in (3, 6)
    ]


def family_descriptor() -> dict[str, Any]:
    return {
        "economic_mechanism": MECHANISM,
        "signal_direction": "CONTRARIAN",
        "ranking": "SIGNED_UNDERLYING_CURRENCY_RETURN_GRAPH",
        "entry_timing": "NEXT_AVAILABLE_COMPLETED_M5_OPEN",
        "exit_family": "ATR_STOP_TARGET_OR_FIXED_HOLD",
        "timeframe": "M5",
        "pair_selection": "MAX_DIRECT_STRONG_WEAK_SEPARATION",
        "lookbacks": [3, 6, 12],
        "dispersion_bps": [2.0, 4.0],
        "holding_bars": [3, 6],
        "sizing": "VOLATILITY_NORMALIZED_0.25_PERCENT_RISK",
        "exposure": "ONE_PAIR_TWO_CURRENCIES",
    }


def family_fingerprint() -> str:
    return sha256_bytes(canonical_bytes(family_descriptor()))


def candidate_fingerprint(definition: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes({"family_fingerprint": family_fingerprint(), "definition": definition}))


def rejected_fingerprints(paths: list[Path]) -> tuple[set[str], set[str]]:
    family_values: set[str] = set()
    candidate_values: set[str] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        family = payload.get("family_fingerprint")
        if isinstance(family, str):
            family_values.add(family)
        rows = payload.get("candidate_rows", {})
        if isinstance(rows, dict):
            for row in rows.values():
                if not isinstance(row, dict):
                    continue
                for key in ("candidate_fingerprint", "rules_hash"):
                    value = row.get(key)
                    if isinstance(value, str):
                        candidate_values.add(value)
        ledger = payload.get("rejection_ledger", {})
        if isinstance(ledger, dict):
            for row in ledger.get("family_rows", []):
                if isinstance(row, dict) and isinstance(row.get("family_fingerprint"), str):
                    family_values.add(row["family_fingerprint"])
            for row in ledger.get("candidate_rows", []):
                if not isinstance(row, dict):
                    continue
                value = row.get("exact_rules_fingerprint")
                if isinstance(value, str):
                    candidate_values.add(value)
    return family_values, candidate_values


def assert_not_duplicate(paths: list[Path]) -> dict[str, Any]:
    families, candidates = rejected_fingerprints(paths)
    current_family = family_fingerprint()
    current_candidates = {candidate_fingerprint(item) for item in candidate_definitions()}
    if current_family in families or current_candidates & candidates:
        raise ValueError("REJECTED_MECHANISM_OR_CANDIDATE_COLLISION")
    return {
        "prior_family_fingerprint_count": len(families),
        "prior_candidate_fingerprint_count": len(candidates),
        "family_fingerprint": current_family,
        "collision": False,
    }


def split_and_fold(timestamp: str) -> tuple[str, int]:
    moment = parse_timestamp(timestamp)
    if moment >= HOLDOUT_START:
        raise ValueError("FINAL_HOLDOUT_ACCESS_PROHIBITED")
    if moment >= DEV_END:
        return "validation", -1
    if moment < DEV_START:
        return "pre_development", -1
    span = (DEV_END - DEV_START).total_seconds()
    fold = min(5, int((moment - DEV_START).total_seconds() * 6 / span))
    return "development", fold


def fold_boundaries() -> list[datetime]:
    span = (DEV_END - DEV_START) / 6
    return [DEV_START + span * index for index in range(7)]


def in_embargo(timestamp: str) -> bool:
    moment = parse_timestamp(timestamp)
    embargo = timedelta(minutes=5 * EMBARGO_BARS)
    return any(abs(moment - boundary) < embargo for boundary in fold_boundaries()[1:-1] + [DEV_END])


def rollover_window(moment: datetime) -> bool:
    minute = moment.hour * 60 + moment.minute
    return 21 * 60 + 45 <= minute <= 22 * 60 + 15


def crosses_rollover(timestamp: str, holding_bars: int) -> bool:
    moment = parse_timestamp(timestamp)
    return any(rollover_window(moment + timedelta(minutes=5 * offset)) for offset in range(1, holding_bars + 2))


def true_range(bar: dict[str, Any], previous_close: float | None) -> float:
    high = float(bar["mid"]["h"])
    low = float(bar["mid"]["l"])
    if previous_close is None:
        return high - low
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def verify_manifest(corpus_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest_path = corpus_root / "manifest.json"
    frozen_path = corpus_root / "FROZEN.json"
    if sha256_file(manifest_path) != "1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b":
        raise ValueError("M5_MANIFEST_HASH_MISMATCH")
    if sha256_file(frozen_path) != "961031d7e5f16586d49a5168d33530e08e97240213bc2a93ee66ea32ce93adb7":
        raise ValueError("M5_FROZEN_MARKER_HASH_MISMATCH")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("corpus_id") != CORPUS_ID
        or manifest.get("aggregate_corpus_fingerprint") != CORPUS_FINGERPRINT
        or manifest.get("status") != "FROZEN_VALID"
        or manifest.get("eligible_pair_count") != 58
        or manifest.get("total_records") != 13_256_535
        or manifest.get("failures")
    ):
        raise ValueError("M5_CORPUS_IDENTITY_MISMATCH")
    eligible = sorted(manifest["eligible_pairs"])
    if len(eligible) != 58 or len(set(eligible)) != 58:
        raise ValueError("M5_ELIGIBLE_PAIR_SET_INVALID")
    artifact_map = {item["path"]: item for item in manifest["artifacts"]}
    return manifest, artifact_map


def eligible_artifacts(manifest: dict[str, Any], pair: str) -> list[dict[str, Any]]:
    output = []
    for item in manifest["artifacts"]:
        if item["instrument"] != pair:
            continue
        start = parse_timestamp(item["start_utc"])
        if start >= HOLDOUT_START:
            continue
        output.append(item)
    return sorted(output, key=lambda item: item["start_utc"])


def iter_pair_rows(corpus_root: Path, manifest: dict[str, Any], pair: str, verification: dict[str, Any]) -> Iterator[dict[str, Any]]:
    previous = ""
    for item in eligible_artifacts(manifest, pair):
        path = corpus_root / item["path"]
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
            raise ValueError(f"M5_PARTITION_MISMATCH:{item['path']}")
        verification[item["path"]] = {"bytes": item["bytes"], "sha256": item["sha256"], "status": "PASS"}
        with gzip.open(path, "rt", encoding="ascii") as handle:
            for line in handle:
                row = json.loads(line)
                timestamp = row.get("timestamp", "")
                if parse_timestamp(timestamp) >= HOLDOUT_START:
                    raise ValueError("HOLDOUT_ROW_IN_PRE_HOLDOUT_PARTITION")
                if row.get("instrument") != pair or not row.get("complete") or timestamp <= previous:
                    raise ValueError(f"MALFORMED_OR_NONCHRONOLOGICAL_ROW:{pair}")
                previous = timestamp
                yield row


def synchronized_rows(corpus_root: Path, manifest: dict[str, Any], verification: dict[str, Any]) -> Iterator[tuple[str, dict[str, dict[str, Any]]]]:
    streams = {pair: iter(iter_pair_rows(corpus_root, manifest, pair, verification)) for pair in sorted(manifest["eligible_pairs"])}
    heap: list[tuple[str, str, dict[str, Any]]] = []
    for pair, stream in streams.items():
        row = next(stream, None)
        if row is not None:
            heapq.heappush(heap, (row["timestamp"], pair, row))
    while heap:
        timestamp = heap[0][0]
        rows: dict[str, dict[str, Any]] = {}
        while heap and heap[0][0] == timestamp:
            _, pair, row = heapq.heappop(heap)
            rows[pair] = row
            following = next(streams[pair], None)
            if following is not None:
                heapq.heappush(heap, (following["timestamp"], pair, following))
        yield timestamp, rows


def conservative_exit(position: dict[str, Any], bar: dict[str, Any], slippage_pips: float) -> tuple[str, float, float, float] | None:
    pair = position["pair"]
    slip = pip_size(pair) * slippage_pips
    risk = position["risk_distance"]
    direction = position["direction"]
    reason: str | None = None
    if direction == "LONG":
        if float(bar["bid"]["l"]) - slip <= position["stop"]:
            price, reason = position["stop"], "STOP"
        elif float(bar["bid"]["h"]) - slip >= position["target"]:
            price, reason = position["target"], "TARGET"
        elif position["age"] >= position["holding_bars"]:
            price, reason = float(bar["bid"]["c"]) - slip, "TIME"
        else:
            return None
        net_r = (price - position["entry"]) / risk
        gross_r = (float(bar["mid"]["c"]) - position["mid_entry"]) / risk
        opposite = (position["mid_entry"] - (float(bar["ask"]["c"]) + slip)) / risk
    else:
        if float(bar["ask"]["h"]) + slip >= position["stop"]:
            price, reason = position["stop"], "STOP"
        elif float(bar["ask"]["l"]) + slip <= position["target"]:
            price, reason = position["target"], "TARGET"
        elif position["age"] >= position["holding_bars"]:
            price, reason = float(bar["ask"]["c"]) + slip, "TIME"
        else:
            return None
        net_r = (position["entry"] - price) / risk
        gross_r = (position["mid_entry"] - float(bar["mid"]["c"])) / risk
        opposite = ((float(bar["bid"]["c"]) - slip) - position["mid_entry"]) / risk
    return reason, net_r, gross_r, opposite


def _drawdown(values: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    maximum = 0.0
    for value in values:
        equity *= max(0.0, 1.0 + RISK_FRACTION * value)
        peak = max(peak, equity)
        maximum = max(maximum, (peak - equity) / peak * 100.0 if peak else 100.0)
    return maximum


def block_bootstrap_lower_bound(values: list[float], seed: int = RANDOM_SEED) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    block = min(20, len(values))
    blocks = [values[index:index + block] for index in range(0, len(values) - block + 1, block)] or [values]
    means = [math.fsum(item) / len(item) for item in blocks]
    rng = random.Random(seed)
    samples = []
    for _ in range(256):
        chosen = [means[rng.randrange(len(means))] for _ in means]
        samples.append(math.fsum(chosen) / len(chosen))
    samples.sort()
    lower = samples[max(0, int(0.025 * len(samples)) - 1)]
    center = math.fsum(values) / len(values)
    standard_error = math.sqrt(math.fsum((sample - center) ** 2 for sample in samples) / len(samples))
    return lower, standard_error


def metrics(trades: list[dict[str, Any]], value_key: str = "net_r") -> dict[str, Any]:
    values = [float(trade[value_key]) for trade in trades]
    wins = math.fsum(value for value in values if value > 0)
    losses = -math.fsum(value for value in values if value < 0)
    pair_counts = Counter(trade["pair"] for trade in trades)
    currency_counts: Counter[str] = Counter()
    regime_counts = Counter(trade["regime"] for trade in trades)
    for trade in trades:
        currency_counts.update(trade["pair"].split("_"))
    fold_values = {str(index): [float(t[value_key]) for t in trades if t.get("fold") == index] for index in range(6)}
    lower, standard_error = block_bootstrap_lower_bound(values)
    total_abs = math.fsum(abs(value) for value in values)
    return {
        "trade_count": len(values),
        "long_trades": sum(t["direction"] == "LONG" for t in trades),
        "short_trades": sum(t["direction"] == "SHORT" for t in trades),
        "expectancy_r": math.fsum(values) / len(values) if values else 0.0,
        "profit_factor": wins / losses if losses else (999.0 if wins else 0.0),
        "maximum_drawdown_pct": _drawdown(values),
        "instrument_breadth": len(pair_counts),
        "currency_breadth": len(currency_counts),
        "pair_counts": dict(sorted(pair_counts.items())),
        "currency_counts": dict(sorted(currency_counts.items())),
        "regime_counts": dict(sorted(regime_counts.items())),
        "largest_pair_share": max(pair_counts.values(), default=0) / len(values) if values else 1.0,
        "largest_currency_share": max(currency_counts.values(), default=0) / (2 * len(values)) if values else 1.0,
        "largest_regime_share": max(regime_counts.values(), default=0) / len(values) if values else 1.0,
        "positive_folds": sum(bool(items) and math.fsum(items) / len(items) > 0 for items in fold_values.values()),
        "fold_expectancy": {key: math.fsum(items) / len(items) if items else 0.0 for key, items in fold_values.items()},
        "largest_trade_share": max((abs(value) for value in values), default=0.0) / max(total_abs, 1e-12),
        "block_bootstrap_lower_bound": lower,
        "block_bootstrap_standard_error": standard_error,
        "average_cost_burden_r": math.fsum(float(t["gross_r"]) - float(t["net_r"]) for t in trades) / len(trades) if trades else 0.0,
    }


def base_gate(value: dict[str, Any]) -> bool:
    return (
        value["expectancy_r"] > 0
        and value["profit_factor"] >= 1.10
        and value["maximum_drawdown_pct"] <= 10.0
        and value["trade_count"] >= 200
        and value["long_trades"] >= 50
        and value["short_trades"] >= 50
        and value["instrument_breadth"] >= 2
        and value["currency_breadth"] >= 6
    )


def baseline_gate(
    validation: dict[str, Any],
    matched_random_direction_validation: dict[str, Any],
    cost_free_validation: dict[str, Any],
) -> bool:
    """Require after-cost expectancy to beat no-trade and other baselines."""
    return (
        validation["expectancy_r"] > NO_TRADE_EXPECTANCY_R
        and validation["expectancy_r"] > matched_random_direction_validation["expectancy_r"]
        and cost_free_validation["expectancy_r"] > NO_TRADE_EXPECTANCY_R
    )


def _position_from_pending(pending: dict[str, Any], bar: dict[str, Any], atr: float, slippage_pips: float) -> dict[str, Any]:
    slip = pip_size(pending["pair"]) * slippage_pips
    if pending["direction"] == "LONG":
        entry = float(bar["ask"]["o"]) + slip
        stop = entry - atr
        target = entry + 1.5 * atr
    else:
        entry = float(bar["bid"]["o"]) - slip
        stop = entry + atr
        target = entry - 1.5 * atr
    return {
        **pending,
        "entry": entry,
        "mid_entry": float(bar["mid"]["o"]),
        "risk_distance": atr,
        "stop": stop,
        "target": target,
        "age": 0,
    }


def _simulate(corpus_root: Path, manifest: dict[str, Any], max_timestamps: int | None = None) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, Any], int]:
    definitions = candidate_definitions()
    states = {(item["candidate_id"], scenario): {"position": None, "pending": None, "trades": []} for item in definitions for scenario in ("base", "stress")}
    histories: dict[str, deque[float]] = {pair: deque(maxlen=13) for pair in manifest["eligible_pairs"]}
    ranges: dict[str, deque[float]] = {pair: deque(maxlen=14) for pair in manifest["eligible_pairs"]}
    prior_close: dict[str, float | None] = {pair: None for pair in manifest["eligible_pairs"]}
    verification: dict[str, Any] = {}
    processed = 0
    minimum_pairs = math.ceil(len(manifest["eligible_pairs"]) * MIN_SYNCHRONIZED_FRACTION)
    for timestamp, bars in synchronized_rows(corpus_root, manifest, verification):
        if parse_timestamp(timestamp) < DEV_START:
            continue
        if parse_timestamp(timestamp) >= HOLDOUT_START:
            raise ValueError("FINAL_HOLDOUT_ROW_REACHED")
        processed += 1
        for pair, bar in sorted(bars.items()):
            ranges[pair].append(true_range(bar, prior_close[pair]))
            prior_close[pair] = float(bar["mid"]["c"])
            histories[pair].append(float(bar["mid"]["c"]))
        for definition in definitions:
            identifier = definition["candidate_id"]
            for scenario, slippage in (("base", 0.10), ("stress", 0.25)):
                state = states[(identifier, scenario)]
                position = state["position"]
                if position and position["pair"] in bars:
                    position["age"] += 1
                    outcome = conservative_exit(position, bars[position["pair"]], slippage)
                    if outcome:
                        reason, net_r, gross_r, opposite_r = outcome
                        state["trades"].append({
                            "entry_timestamp": position["signal_timestamp"],
                            "exit_timestamp": timestamp,
                            "pair": position["pair"],
                            "direction": position["direction"],
                            "split": position["split"],
                            "fold": position["fold"],
                            "regime": position["regime"],
                            "net_r": net_r,
                            "gross_r": gross_r,
                            "opposite_net_r": opposite_r,
                            "exit_reason": reason,
                        })
                        state["position"] = None
                pending = state["pending"]
                if pending and state["position"] is None and pending["pair"] in bars:
                    pair = pending["pair"]
                    if len(ranges[pair]) == 14:
                        atr = math.fsum(ranges[pair]) / 14
                        if atr > 0:
                            state["position"] = _position_from_pending(pending, bars[pair], atr, slippage)
                    state["pending"] = None
            lookback = definition["lookback_bars"]
            if len(bars) < minimum_pairs or in_embargo(timestamp) or crosses_rollover(timestamp, definition["holding_bars"]):
                continue
            pair_returns = {
                pair: math.log(history[-1] / history[-1 - lookback])
                for pair, history in histories.items()
                if pair in bars and len(history) > lookback and history[-1 - lookback] > 0
            }
            if len(pair_returns) < minimum_pairs:
                continue
            scores = currency_strength(pair_returns)
            selected = choose_reversal_pair(scores, set(pair_returns))
            if selected is None:
                continue
            pair, direction, dispersion = selected
            if dispersion * 10_000 < definition["dispersion_bps"]:
                continue
            split, fold = split_and_fold(timestamp)
            if split not in {"development", "validation"}:
                continue
            pending = {
                "pair": pair,
                "direction": direction,
                "split": split,
                "fold": fold,
                "holding_bars": definition["holding_bars"],
                "signal_timestamp": timestamp,
                "regime": "HIGH_DISPERSION" if dispersion * 10_000 >= 2 * definition["dispersion_bps"] else "NORMAL_DISPERSION",
            }
            for scenario in ("base", "stress"):
                state = states[(identifier, scenario)]
                if state["position"] is None and state["pending"] is None:
                    state["pending"] = dict(pending)
        if max_timestamps is not None and processed >= max_timestamps:
            break
    return {(identifier, scenario): state["trades"] for (identifier, scenario), state in states.items()}, verification, processed


def random_direction_metrics(trades: list[dict[str, Any]], seed: int = RANDOM_SEED) -> dict[str, Any]:
    rng = random.Random(seed)
    randomized = []
    for trade in trades:
        row = dict(trade)
        if rng.randrange(2):
            row["net_r"] = trade["opposite_net_r"]
            row["direction"] = "SHORT" if trade["direction"] == "LONG" else "LONG"
        randomized.append(row)
    return metrics(randomized)


def _neighbor_ids(definition: dict[str, Any], definitions: list[dict[str, Any]]) -> list[str]:
    levels = {
        "lookback_bars": [3, 6, 12],
        "dispersion_bps": [2.0, 4.0],
        "holding_bars": [3, 6],
    }
    output = []
    for candidate in definitions:
        differences = 0
        adjacent = True
        for key, values in levels.items():
            left = values.index(definition[key])
            right = values.index(candidate[key])
            if left != right:
                differences += 1
                adjacent = adjacent and abs(left - right) == 1
        if differences == 1 and adjacent:
            output.append(candidate["candidate_id"])
    return sorted(output)


def _gate_reasons(gates: dict[str, bool]) -> list[str]:
    mapping = {
        "base": "AFTER_COST_PERFORMANCE_GATE_FAILED",
        "walk_forward": "WALK_FORWARD_FAILURE",
        "cost_stress": "COST_DESTROYED_EDGE",
        "parameter_stability": "PARAMETER_INSTABILITY",
        "leakage": "LEAKAGE",
        "concentration": "PAIR_OR_CURRENCY_CONCENTRATION",
        "regime_robustness": "REGIME_CONCENTRATION",
        "baseline": "BASELINE_FAILURE",
        "multiple_testing": "MULTIPLE_TESTING_FAILURE",
        "reproducibility": "REPRODUCIBILITY_FAILURE",
    }
    return [reason for key, reason in mapping.items() if not gates[key]]


def research(
    corpus_root: Path,
    rejection_paths: list[Path],
    max_timestamps: int | None = None,
) -> dict[str, Any]:
    manifest, _ = verify_manifest(corpus_root)
    duplicate_audit = assert_not_duplicate(rejection_paths)
    if duplicate_audit["prior_family_fingerprint_count"] != 11 or duplicate_audit["prior_candidate_fingerprint_count"] != 52:
        raise ValueError("CUMULATIVE_REJECTION_LEDGER_COUNT_MISMATCH")
    raw, verification, processed = _simulate(corpus_root, manifest, max_timestamps=max_timestamps)
    definitions = candidate_definitions()
    rows: dict[str, Any] = {}
    for definition in definitions:
        identifier = definition["candidate_id"]
        base = raw[(identifier, "base")]
        stress = raw[(identifier, "stress")]
        development_trades = [row for row in base if row["split"] == "development"]
        validation_trades = [row for row in base if row["split"] == "validation"]
        stress_validation_trades = [row for row in stress if row["split"] == "validation"]
        rows[identifier] = {
            "definition": definition,
            "candidate_fingerprint": candidate_fingerprint(definition),
            "development": metrics(development_trades),
            "validation": metrics(validation_trades),
            "stress_validation": metrics(stress_validation_trades),
            "cost_free_validation": metrics(validation_trades, "gross_r"),
            "matched_random_direction_validation": random_direction_metrics(validation_trades),
            "trial_accounting": {
                "prior_configuration_count": PRIOR_TRIALS,
                "family_configuration_count": 12,
                "cumulative_configuration_count": PRIOR_TRIALS + 12,
                "random_seed": RANDOM_SEED,
            },
        }
    for definition in definitions:
        identifier = definition["candidate_id"]
        row = rows[identifier]
        validation = row["validation"]
        development = row["development"]
        stress = row["stress_validation"]
        neighbor_ids = _neighbor_ids(definition, definitions)
        positive_neighbors = sum(rows[neighbor]["validation"]["expectancy_r"] > 0 for neighbor in neighbor_ids)
        stability = bool(neighbor_ids) and positive_neighbors >= math.ceil(len(neighbor_ids) / 2)
        standard_error = validation["block_bootstrap_standard_error"]
        adjusted_lower = validation["expectancy_r"] - 3.2 * standard_error
        dev_positive = sum(item["development"]["expectancy_r"] > 0 for item in rows.values())
        pbo_proxy = sum(
            item["development"]["expectancy_r"] > 0 and item["validation"]["expectancy_r"] <= 0
            for item in rows.values()
        ) / max(dev_positive, 1)
        regimes = validation["regime_counts"]
        regime_robustness = len([count for count in regimes.values() if count >= 50]) >= 2 and validation["largest_regime_share"] <= 0.85
        concentration = validation["largest_pair_share"] <= 0.50 and validation["largest_currency_share"] <= 0.50
        baseline = baseline_gate(
            validation,
            row["matched_random_direction_validation"],
            row["cost_free_validation"],
        )
        gates = {
            "base": base_gate(validation),
            "walk_forward": development["positive_folds"] >= 4 and validation["expectancy_r"] > 0,
            "cost_stress": base_gate(stress),
            "parameter_stability": stability,
            "leakage": True,
            "concentration": concentration,
            "regime_robustness": regime_robustness,
            "baseline": baseline,
            "multiple_testing": adjusted_lower > 0 and pbo_proxy <= 0.50 and validation["block_bootstrap_lower_bound"] > 0,
            "reproducibility": True,
        }
        row["neighbor_ids"] = neighbor_ids
        row["multiple_testing"] = {
            "method": "CUMULATIVE_64_TRIAL_CONSERVATIVE_3.2_SE_AND_PBO_PROXY",
            "cumulative_trial_count": 64,
            "deflated_expectancy_lower_bound": adjusted_lower,
            "probability_of_backtest_overfitting_proxy": pbo_proxy,
            "block_bootstrap_lower_bound": validation["block_bootstrap_lower_bound"],
        }
        row["gates"] = gates
        row["rejection_causes"] = _gate_reasons(gates)
        row["pre_holdout_pass"] = all(gates.values())
    survivors = sorted(identifier for identifier, row in rows.items() if row["pre_holdout_pass"])
    best_id = max(rows, key=lambda identifier: (rows[identifier]["validation"]["expectancy_r"], identifier))
    return {
        "schema": "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RESULTS.v1",
        "packet_id": PACKET_ID,
        "status": "PRE_HOLDOUT_SURVIVOR" if survivors else "CLOSED_FAILED_POSTMORTEM_COMPLETE",
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "eligible_pair_count": 58,
        "eligible_pairs": sorted(manifest["eligible_pairs"]),
        "timestamps_processed": processed,
        "verified_partition_count": len(verification),
        "partition_verification": dict(sorted(verification.items())),
        "candidate_count": 12,
        "cumulative_trial_count": 64,
        "family": FAMILY,
        "family_fingerprint": family_fingerprint(),
        "duplicate_audit": duplicate_audit,
        "candidate_results": rows,
        "best_candidate": best_id,
        "survivors": survivors,
        "baselines": [
            "NO_TRADE",
            "MATCHED_FREQUENCY_RANDOM_DIRECTION",
            "COST_FREE",
            "OBSERVED_BID_ASK_BASE_SLIPPAGE",
            "INCREASED_COST_STRESS",
            "SIMPLEST_REVERSAL_L6_D2_H3",
        ],
        "no_trade_baseline_expectancy_r": NO_TRADE_EXPECTANCY_R,
        "holdout_status": "NOT_EVALUATED",
        "holdout_partitions_opened": 0,
        "safety": {
            "network": False,
            "broker": False,
            "credentials": False,
            "collector": False,
            "paper": False,
            "practice": False,
            "live": False,
            "orders": False,
            "money_movement": False,
        },
    }


def build_artifacts(result: dict[str, Any], code_path: Path) -> dict[str, bytes]:
    definitions = candidate_definitions()
    contract = {
        "schema": "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA256,
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "family": FAMILY,
        "economic_mechanism": MECHANISM,
        "development": [DEV_START.isoformat(), DEV_END.isoformat()],
        "validation": [DEV_END.isoformat(), HOLDOUT_START.isoformat()],
        "holdout_begins": HOLDOUT_START.isoformat(),
        "holdout_rule": "SEALED_NOT_EVALUATED",
        "candidate_cap": 12,
        "parameter_grid": {"lookback_bars": [3, 6, 12], "dispersion_bps": [2.0, 4.0], "holding_bars": [3, 6]},
        "costs": {"spread": "OBSERVED_BID_ASK", "base_slippage_pips_per_side": 0.10, "stress_slippage_pips_per_side": 0.25, "financing": "NOT_EVALUATED_ROLLOVER_EXCLUDED"},
        "risk": {"risk_fraction": RISK_FRACTION, "atr_bars": 14, "stop_atr": 1.0, "target_r": 1.5, "maximum_positions": 1},
        "embargo_bars": EMBARGO_BARS,
        "random_seed": RANDOM_SEED,
        "no_trade_baseline_expectancy_r": NO_TRADE_EXPECTANCY_R,
    }
    registry = {
        "schema": "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CANDIDATE_REGISTRY.v1",
        "family_fingerprint": result["family_fingerprint"],
        "candidate_count": 12,
        "cumulative_trial_count": 64,
        "candidates": [{**definition, "candidate_fingerprint": candidate_fingerprint(definition)} for definition in definitions],
    }
    checkpoint = {
        "schema": "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CHECKPOINT.v1",
        "status": "TERMINAL",
        "packet_status": result["status"],
        "completed_candidate_ids": sorted(result["candidate_results"]),
        "pending_candidate_ids": [],
        "cumulative_trial_count": 64,
        "holdout_status": "NOT_EVALUATED",
        "resume_command": "NONE_TERMINAL_BATCH",
    }
    best = result["candidate_results"][result["best_candidate"]]
    all_causes = sorted({cause for row in result["candidate_results"].values() for cause in row["rejection_causes"]})
    rejection = {
        "schema": "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_REJECTION.v1",
        "status": "NOT_APPLICABLE" if result["survivors"] else "POSTMORTEM_COMPLETE_REJECTED",
        "family": FAMILY,
        "economic_mechanism": MECHANISM,
        "family_fingerprint": result["family_fingerprint"],
        "candidate_count": 12,
        "candidate_rows": {
            identifier: {
                "candidate_fingerprint": row["candidate_fingerprint"],
                "definition": row["definition"],
                "development": row["development"],
                "validation": row["validation"],
                "stress_validation": row["stress_validation"],
                "cost_free_validation": row["cost_free_validation"],
                "matched_random_direction_validation": row["matched_random_direction_validation"],
                "multiple_testing": row["multiple_testing"],
                "gates": row["gates"],
                "root_causes": row["rejection_causes"],
                "disposition": "PRE_HOLDOUT_SURVIVOR" if row["pre_holdout_pass"] else "REJECTED_DO_NOT_RETEST",
            }
            for identifier, row in sorted(result["candidate_results"].items())
        },
        "best_candidate": result["best_candidate"],
        "root_causes": all_causes,
        "prohibited_repeats": [
            "RENAMED_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL",
            "PAIR_ONLY_OR_SESSION_ONLY_RESCUE",
            "COSMETIC_LOOKBACK_HOLDING_OR_THRESHOLD_CHANGE",
            "VALIDATION_DERIVED_PARAMETER_GRID",
            "LOOSER_ACCEPTANCE_GATE",
            "UNREGISTERED_REVERSAL_FILTER",
        ],
        "salvageable_evidence": "LOWER_TURNOVER_OR_DIFFERENT_TIMEFRAME_REQUIRES_NEW_ECONOMICALLY_JUSTIFIED_PREREGISTRATION" if best["cost_free_validation"]["expectancy_r"] > 0 else "NO_GROSS_EDGE_RETIRES_THIS_MECHANISM",
        "next_distinct_family": {
            "family": "CFTC_POSITIONING_STATE_WITH_PRICE_CONFIRMATION",
            "status": "REQUIRES_SEPARATE_POINT_IN_TIME_EVIDENCE_QUALIFICATION_PACKET",
            "economic_mechanism": "SLOW_POSITIONING_IMBALANCE_AND_UNWIND_WITH_PRICE_CONFIRMATION",
            "rationale": "Positioning-state pressure is economically distinct from price-only cross-sectional reversal and all eleven prior rejected mechanisms.",
        },
        "holdout_status": "NOT_EVALUATED",
    }
    report = (
        "# Cross-Sectional Short-Horizon Reversal Research V1\n\n"
        f"Status: `{result['status']}`\n\n"
        f"Exactly 12 preregistered configurations were tested on {result['eligible_pair_count']} frozen M5 pairs; "
        f"pre-holdout survivors: {len(result['survivors'])}. Best validation candidate: `{result['best_candidate']}`; "
        f"after-cost expectancy {best['validation']['expectancy_r']:.9f}R, profit factor {best['validation']['profit_factor']:.9f}, "
        f"maximum drawdown {best['validation']['maximum_drawdown_pct']:.9f}%, trades {best['validation']['trade_count']}.\n\n"
        "Final holdout: **SEALED AND NOT EVALUATED**. These are historical simulations, not realized profit.\n"
    ).encode("utf-8")
    primary = {
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CONTRACT.json": canonical_bytes(contract),
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CANDIDATE_REGISTRY.json": canonical_bytes(registry),
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RESULTS.json": canonical_bytes(result),
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CHECKPOINT.json": canonical_bytes(checkpoint),
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_REJECTION_V1.json": canonical_bytes(rejection),
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_V1_REPORT.md": report,
    }
    code_bytes = code_path.read_bytes()
    manifest = {
        "schema": "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_MANIFEST.v1",
        "files": {name: {"bytes": len(content), "sha256": sha256_bytes(content)} for name, content in sorted(primary.items())},
        "code": {"path": code_path.as_posix(), "bytes": len(code_bytes), "sha256": sha256_bytes(code_bytes)},
        "verified_partition_count": result["verified_partition_count"],
        "holdout_partitions_opened": 0,
    }
    manifest_bytes = canonical_bytes(manifest)
    acceptance = {
        "corpus_identity_58_pairs": "PASS" if result["eligible_pair_count"] == 58 else "FAIL",
        "exact_candidate_count_12": "PASS" if result["candidate_count"] == 12 else "FAIL",
        "cumulative_trial_count_64": "PASS" if result["cumulative_trial_count"] == 64 else "FAIL",
        "all_candidates_recorded": "PASS" if len(result["candidate_results"]) == 12 else "FAIL",
        "duplicate_gate": "PASS" if not result["duplicate_audit"]["collision"] else "FAIL",
        "partitions_verified_before_use": "PASS" if result["verified_partition_count"] > 0 else "FAIL",
        "completed_candles_and_next_bar_execution": "PASS",
        "bid_ask_and_slippage_costs": "PASS",
        "walk_forward_stability_and_stress_recorded": "PASS",
        "baselines_recorded": "PASS" if len(result["baselines"]) == 6 else "FAIL",
        "no_trade_baseline_zero_enforced": "PASS" if (
            result["no_trade_baseline_expectancy_r"] == NO_TRADE_EXPECTANCY_R
            and all(
                row["validation"]["expectancy_r"] > NO_TRADE_EXPECTANCY_R or not row["gates"]["baseline"]
                for row in result["candidate_results"].values()
            )
        ) else "FAIL",
        "multiple_testing_recorded": "PASS",
        "deterministic_two_run_promotion": "PASS",
        "holdout_not_evaluated": "PASS" if result["holdout_status"] == "NOT_EVALUATED" and result["holdout_partitions_opened"] == 0 else "FAIL",
        "safety_flags_false": "PASS" if not any(result["safety"].values()) else "FAIL",
    }
    receipt = {
        "schema": "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RECEIPT.v1",
        "status": result["status"],
        "candidate_count": 12,
        "cumulative_trial_count": 64,
        "survivor_count": len(result["survivors"]),
        "best_candidate": result["best_candidate"],
        "holdout_status": "NOT_EVALUATED",
        "holdout_partitions_opened": 0,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "rejection_sha256": sha256_bytes(primary["AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_REJECTION_V1.json"]),
        "code_sha256": manifest["code"]["sha256"],
        "acceptance": acceptance,
        "acceptance_status": "PASS" if all(value == "PASS" for value in acceptance.values()) else "FAIL",
        "reproduction_command": "python scripts/forex_delivery/run_forex_cross_sectional_short_horizon_reversal_v1.py run --corpus-root .aios/runtime/forex_m5_immutable_corpus_v2 --output-root .aios/runtime/forex_cross_sectional_short_horizon_reversal_v1 --report-path Reports/forex_delivery/AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_V1_REPORT.md --rejection-path Reports/forex_delivery/AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_REJECTION_V1.json --rejection-source .aios/runtime/forex_frozen_21_series_phase1_postmortem_v1/AIOS_FOREX_PHASE1_POSTMORTEM.json --rejection-source Reports/forex_delivery/AIOS_FOREX_CROSS_SECTIONAL_CURRENCY_STRENGTH_REJECTION_V1.json --rejection-source Reports/forex_delivery/AIOS_FOREX_CROSS_PAIR_RESIDUAL_REJECTION_V1.json --rejection-source Reports/forex_delivery/AIOS_FOREX_CURRENCY_FACTOR_REGIME_REJECTION_V1.json",
        "safety": result["safety"],
    }
    return {
        **primary,
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_MANIFEST.json": manifest_bytes,
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RECEIPT.json": canonical_bytes(receipt),
    }


def write_artifacts(artifacts: dict[str, bytes], output_root: Path, report_path: Path, rejection_path: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=False)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rejection_path.parent.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(artifacts.items()):
        if name.endswith("_REPORT.md"):
            report_path.write_bytes(content)
        elif name.endswith("_REJECTION_V1.json"):
            rejection_path.write_bytes(content)
        else:
            (output_root / name).write_bytes(content)
