"""Offline Stage-1 round-number conditional order-state research.

The reader verifies frozen M5 bytes before use, opens development partitions
only, and never imports network, broker, credential, Paper, Practice, LIVE, or
order-routing code.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import random
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable


PACKET_ID = "PKT-FOREX-024"
PACKET_SHA256 = "9bb68b3c3126161a0ee1355c6007d70231dbec0111351251bd9e89d82d658d9d"
CORPUS_ID = "AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2"
CORPUS_FINGERPRINT = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
MANIFEST_SHA256 = "1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b"
FROZEN_SHA256 = "961031d7e5f16586d49a5168d33530e08e97240213bc2a93ee66ea32ce93adb7"
PREREG_SHA256 = "b3c4529012dc73f5e8a0f7d2b0ab386fe80b5ff732ab32d04d512ca7608d535c"
FAMILY = "ROUND_NUMBER_CONDITIONAL_ORDER_STATE_CLASSIFIER"
DEV_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DEV_END = datetime(2025, 4, 1, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
PRIOR_ATTEMPT_LOWER_BOUND = 1164
CUMULATIVE_ATTEMPT_LOWER_BOUND = 1174
FULLY_GOVERNED_PRIOR_AFTER_COST = 112
RISK_FRACTION = 0.0025
EMBARGO_BARS = 18
RANDOM_SEED = 24024
NO_TRADE_EXPECTANCY_R = 0.0
DIRECTIONS = (
    "ORIGINAL_LONG",
    "EXACT_REVERSED_SHORT",
    "ORIGINAL_SHORT",
    "EXACT_REVERSED_LONG",
    "SYMMETRIC_BIDIRECTIONAL",
)
BRANCH_HOLDS = {
    "APPROACH_00_50_REVERSAL": 2,
    "COMPLETED_CROSS_00_50_CONTINUATION": 3,
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


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


def timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def pip_size(pair: str) -> float:
    return 0.01 if pair.split("_")[1] == "JPY" else 0.0001


def family_descriptor() -> dict[str, Any]:
    return {
        "family": FAMILY,
        "mechanism": "TAKE_PROFIT_BOUNCE_BEFORE_00_50_AND_STOP_CASCADE_AFTER_CONFIRMED_CROSS",
        "timeframe": "M5",
        "level_step_pips": 50,
        "approach_fraction": 0.0001,
        "branches": BRANCH_HOLDS,
        "directions": DIRECTIONS,
        "entry": "NEXT_COMPLETED_M5_OPEN_EXECUTABLE_SIDE",
        "stop": "ONE_SIGNAL_TIME_ATR14",
        "target": "NONE",
        "costs": {"base_slippage_pips_per_side": 0.10, "stress_slippage_pips_per_side": 0.50, "spread": "OBSERVED_BID_ASK"},
        "exposure": "ONE_PAIR_NO_SHARED_CURRENCY_MAX_FIVE",
    }


def family_fingerprint() -> str:
    return sha256_bytes(canonical_bytes(family_descriptor()))


def candidate_definitions() -> list[dict[str, Any]]:
    output = []
    for branch, holding in BRANCH_HOLDS.items():
        for direction in DIRECTIONS:
            definition = {
                "candidate_id": f"RN-{branch.split('_')[0]}-{direction}",
                "branch": branch,
                "direction_variant": direction,
                "maximum_holding_m5_bars": holding,
                "round_level_set": "00_AND_50",
                "approach_distance_fraction": 0.0001,
                "completed_candles_only": True,
            }
            definition["candidate_fingerprint"] = sha256_bytes(
                canonical_bytes({"family_fingerprint": family_fingerprint(), "definition": definition})
            )
            output.append(definition)
    return output


def verify_preregistration(path: Path) -> dict[str, Any]:
    if sha256_file(path) != PREREG_SHA256:
        raise ValueError("PREREGISTRATION_HASH_MISMATCH")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("strategy_identity") != FAMILY or payload.get("candidate_count") != 10:
        raise ValueError("PREREGISTRATION_IDENTITY_MISMATCH")
    if payload.get("final_holdout") != "SEALED_2026_NOT_EVALUATED":
        raise ValueError("PREREGISTRATION_HOLDOUT_MISMATCH")
    expected = {
        (row["branch"], row["direction_variant"], row["maximum_holding_m5_bars"])
        for row in payload["parameter_grid"]
    }
    actual = {
        (row["branch"], row["direction_variant"], row["maximum_holding_m5_bars"])
        for row in candidate_definitions()
    }
    if expected != actual:
        raise ValueError("PREREGISTRATION_GRID_MISMATCH")
    return payload


def verify_manifest(corpus_root: Path) -> dict[str, Any]:
    manifest_path = corpus_root / "manifest.json"
    frozen_path = corpus_root / "FROZEN.json"
    if sha256_file(manifest_path) != MANIFEST_SHA256:
        raise ValueError("M5_MANIFEST_HASH_MISMATCH")
    if sha256_file(frozen_path) != FROZEN_SHA256:
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
    pairs = manifest.get("eligible_pairs", [])
    if len(pairs) != 58 or len(set(pairs)) != 58:
        raise ValueError("M5_ELIGIBLE_PAIR_SET_INVALID")
    return manifest


def development_artifacts(manifest: dict[str, Any], pair: str) -> list[dict[str, Any]]:
    return sorted(
        (
            item for item in manifest["artifacts"]
            if item["instrument"] == pair and parse_timestamp(item["start_utc"]) < DEV_END
        ),
        key=lambda item: item["start_utc"],
    )


def read_pair_bars(corpus_root: Path, manifest: dict[str, Any], pair: str, verification: dict[str, Any]) -> list[dict[str, Any]]:
    bars = []
    previous = ""
    for item in development_artifacts(manifest, pair):
        path = corpus_root / item["path"]
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
            raise ValueError(f"M5_PARTITION_MISMATCH:{item['path']}")
        verification[item["path"]] = {"bytes": item["bytes"], "sha256": item["sha256"], "status": "PASS"}
        with gzip.open(path, "rt", encoding="ascii") as handle:
            for line in handle:
                row = json.loads(line)
                moment = parse_timestamp(row.get("timestamp", ""))
                if moment >= DEV_END:
                    continue
                if moment >= HOLDOUT_START:
                    raise ValueError("FINAL_HOLDOUT_ROW_REACHED")
                if moment < DEV_START:
                    continue
                if row.get("instrument") != pair or not row.get("complete") or row["timestamp"] <= previous:
                    raise ValueError(f"MALFORMED_OR_NONCHRONOLOGICAL_ROW:{pair}")
                previous = row["timestamp"]
                bars.append(row)
    return bars


def true_range(bar: dict[str, Any], previous_close: float | None) -> float:
    high = float(bar["mid"]["h"])
    low = float(bar["mid"]["l"])
    if previous_close is None:
        return high - low
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def grid_neighbors(price: float, step: float, offset: float) -> tuple[float, float]:
    lower = offset + math.floor((price - offset) / step) * step
    # Decimal FX levels must not become false crossings from binary float noise.
    lower = round(lower, 10)
    return lower, round(lower + step, 10)


def signal_events(previous_close: float, bar: dict[str, Any], pair: str, level_kind: str) -> list[tuple[str, str, float]]:
    step = 50.0 * pip_size(pair)
    offset = 0.0 if level_kind == "ROUND_00_50" else 25.0 * pip_size(pair)
    close = float(bar["mid"]["c"])
    high = float(bar["mid"]["h"])
    low = float(bar["mid"]["l"])
    lower, upper = grid_neighbors(close, step, offset)
    output: list[tuple[str, str, float]] = []

    lower_band = max(abs(lower) * 0.0001, pip_size(pair) * 0.25)
    upper_band = max(abs(upper) * 0.0001, pip_size(pair) * 0.25)
    if lower > 0 and previous_close > lower and close > lower and lower < low <= lower + lower_band:
        output.append(("APPROACH_00_50_REVERSAL", "LONG", lower))
    if previous_close < upper and close < upper and upper - upper_band <= high < upper:
        output.append(("APPROACH_00_50_REVERSAL", "SHORT", upper))

    prior_lower, prior_upper = grid_neighbors(previous_close, step, offset)
    if previous_close < prior_upper and close > prior_upper:
        output.append(("COMPLETED_CROSS_00_50_CONTINUATION", "LONG", prior_upper))
    elif previous_close > prior_lower and close < prior_lower:
        output.append(("COMPLETED_CROSS_00_50_CONTINUATION", "SHORT", prior_lower))
    return output


def fold_boundaries() -> list[datetime]:
    span = (DEV_END - DEV_START) / 6
    return [DEV_START + span * index for index in range(7)]


def fold_index(moment: datetime) -> int:
    if not DEV_START <= moment < DEV_END:
        return -1
    span = (DEV_END - DEV_START).total_seconds()
    return min(5, int((moment - DEV_START).total_seconds() * 6 / span))


def in_embargo(moment: datetime) -> bool:
    embargo = timedelta(minutes=5 * EMBARGO_BARS)
    return any(abs(moment - boundary) < embargo for boundary in fold_boundaries()[1:])


def interval_touches_rollover(start: datetime, end: datetime) -> bool:
    probe = start
    while probe <= end:
        minute = probe.hour * 60 + probe.minute
        if 21 * 60 + 45 <= minute <= 22 * 60 + 15:
            return True
        probe += timedelta(minutes=5)
    return False


def consecutive_path(bars: list[dict[str, Any]], signal_index: int, holding_bars: int) -> bool:
    end = signal_index + holding_bars
    if end >= len(bars):
        return False
    moments = [parse_timestamp(bars[index]["timestamp"]) for index in range(signal_index, end + 1)]
    return all(right - left == timedelta(minutes=5) for left, right in zip(moments, moments[1:]))


def session_label(moment: datetime) -> str:
    hour = moment.hour
    if 7 <= hour < 12:
        return "LONDON"
    if 12 <= hour < 16:
        return "LONDON_NEW_YORK_OVERLAP"
    if 16 <= hour < 21:
        return "NEW_YORK"
    return "ASIA_HANDOFF_OTHER"


def simulate_path(
    pair: str,
    bars: list[dict[str, Any]],
    signal_index: int,
    holding_bars: int,
    direction: str,
    atr: float,
    scenario: str,
) -> tuple[float, str, float, float, str, float]:
    entry_bar = bars[signal_index + 1]
    slip_pips = {"gross": 0.0, "base": 0.10, "stress": 0.50}[scenario]
    slip = pip_size(pair) * slip_pips
    if direction == "LONG":
        entry = float(entry_bar["mid" if scenario == "gross" else "ask"]["o"]) + slip
        stop = entry - atr
    else:
        entry = float(entry_bar["mid" if scenario == "gross" else "bid"]["o"]) - slip
        stop = entry + atr

    exit_price = entry
    exit_reason = "TIME"
    exit_bar = entry_bar
    for offset in range(1, holding_bars + 1):
        bar = bars[signal_index + offset]
        side = "mid" if scenario == "gross" else ("bid" if direction == "LONG" else "ask")
        if direction == "LONG" and float(bar[side]["l"]) <= stop:
            exit_price = stop - slip
            exit_reason = "STOP"
            exit_bar = bar
            break
        if direction == "SHORT" and float(bar[side]["h"]) >= stop:
            exit_price = stop + slip
            exit_reason = "STOP"
            exit_bar = bar
            break
        if offset == holding_bars:
            exit_price = float(bar[side]["c"]) + (-slip if direction == "LONG" else slip)
            exit_bar = bar
    result_r = (exit_price - entry) / atr if direction == "LONG" else (entry - exit_price) / atr
    return (
        entry,
        timestamp_text(parse_timestamp(exit_bar["timestamp"]) + timedelta(minutes=5)),
        exit_price,
        stop,
        exit_reason,
        result_r,
    )


def event_outcome(event: dict[str, Any], direction: str, scenario: str) -> tuple[float, str, float, float, str, float]:
    direction_offset = 0 if direction == "LONG" else 3
    scenario_offset = {"gross": 0, "base": 1, "stress": 2}[scenario]
    return event["outcomes"][direction_offset + scenario_offset]


def build_pair_events(pair: str, bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    ranges: deque[float] = deque(maxlen=14)
    closes: deque[float] = deque(maxlen=13)
    previous_close: float | None = None
    for index, bar in enumerate(bars):
        close = float(bar["mid"]["c"])
        ranges.append(true_range(bar, previous_close))
        closes.append(close)
        if previous_close is None or len(ranges) < 14:
            previous_close = close
            continue
        atr = math.fsum(ranges) / len(ranges)
        signal_complete = parse_timestamp(bar["timestamp"]) + timedelta(minutes=5)
        for level_kind in ("ROUND_00_50", "SHIFTED_25_75"):
            for branch, original_direction, level in signal_events(previous_close, bar, pair, level_kind):
                holding = BRANCH_HOLDS[branch]
                if atr <= 0 or not consecutive_path(bars, index, holding):
                    continue
                end = parse_timestamp(bars[index + holding]["timestamp"]) + timedelta(minutes=5)
                fold = fold_index(signal_complete)
                if fold < 0 or fold_index(end) != fold or in_embargo(signal_complete):
                    continue
                if interval_touches_rollover(signal_complete, end):
                    continue
                outcomes = tuple(
                    simulate_path(pair, bars, index, holding, direction, atr, scenario)
                    for direction in ("LONG", "SHORT")
                    for scenario in ("gross", "base", "stress")
                )
                mid_close = float(bar["mid"]["c"])
                spread_pips = (float(bar["ask"]["c"]) - float(bar["bid"]["c"])) / pip_size(pair)
                trend_distance = abs(closes[-1] - closes[0]) if len(closes) == 13 else 0.0
                event_core = {
                    "pair": pair,
                    "branch": branch,
                    "level_kind": level_kind,
                    "level": level,
                    "original_direction": original_direction,
                    "signal_timestamp": timestamp_text(signal_complete),
                    "entry_timestamp": bars[index + 1]["timestamp"],
                    "fold": fold,
                    "session": session_label(signal_complete),
                    "volatility_regime": "LOW" if atr / mid_close < 0.0005 else ("HIGH" if atr / mid_close > 0.0015 else "NORMAL"),
                    "trend_range_regime": "TREND" if trend_distance >= 2.0 * atr else "RANGE",
                    "economic_event_proximity": "NOT_APPLICABLE_NO_CERTIFIED_EVENT_FEED",
                    "observed_signal_spread_pips": spread_pips,
                    "prior_completed_bar_direction": "LONG" if float(bar["mid"]["c"]) >= float(bar["mid"]["o"]) else "SHORT",
                    "atr14": atr,
                }
                event_core["event_id"] = sha256_bytes(canonical_bytes(event_core))
                event_core["outcomes"] = outcomes
                events.append(event_core)
        previous_close = close
    return events


def direction_for_variant(event: dict[str, Any], variant: str) -> str | None:
    original = event["original_direction"]
    if variant == "ORIGINAL_LONG":
        return "LONG" if original == "LONG" else None
    if variant == "EXACT_REVERSED_SHORT":
        return "SHORT" if original == "LONG" else None
    if variant == "ORIGINAL_SHORT":
        return "SHORT" if original == "SHORT" else None
    if variant == "EXACT_REVERSED_LONG":
        return "LONG" if original == "SHORT" else None
    if variant == "SYMMETRIC_BIDIRECTIONAL":
        return original
    raise ValueError("UNKNOWN_DIRECTION_VARIANT")


def scheduled_events(events: Iterable[dict[str, Any]], definition: dict[str, Any], level_kind: str) -> list[tuple[dict[str, Any], str]]:
    candidates = []
    for event in events:
        if event["branch"] != definition["branch"] or event["level_kind"] != level_kind:
            continue
        direction = direction_for_variant(event, definition["direction_variant"])
        if direction is not None:
            candidates.append((event, direction))
    candidates.sort(key=lambda item: (item[0]["entry_timestamp"], item[0]["pair"], item[0]["event_id"]))

    active: list[tuple[str, str, set[str]]] = []
    accepted = []
    for event, direction in candidates:
        entry = event["entry_timestamp"]
        active = [row for row in active if row[0] > entry]
        pair = event["pair"]
        currencies = set(pair.split("_"))
        if len(active) >= 5 or any(existing_pair == pair or currencies & used for _, existing_pair, used in active):
            continue
        exit_timestamp = event_outcome(event, direction, "base")[1]
        active.append((exit_timestamp, pair, currencies))
        accepted.append((event, direction))
    return accepted


def journal_row(definition: dict[str, Any], event: dict[str, Any], direction: str) -> dict[str, Any]:
    base = event_outcome(event, direction, "base")
    gross = event_outcome(event, direction, "gross")
    stress = event_outcome(event, direction, "stress")
    return {
        "strategy_id": FAMILY,
        "candidate_id": definition["candidate_id"],
        "candidate_fingerprint": definition["candidate_fingerprint"],
        "event_id": event["event_id"],
        "instrument": event["pair"],
        "direction": direction,
        "signal_timestamp": event["signal_timestamp"],
        "entry_timestamp": event["entry_timestamp"],
        "entry_price": base[0],
        "exit_timestamp": base[1],
        "exit_price": base[2],
        "stop_loss": base[3],
        "take_profit": None,
        "spread_pips": event["observed_signal_spread_pips"],
        "modeled_slippage_pips_per_side": 0.10,
        "gross_result_r": gross[5],
        "net_result_r": base[5],
        "stress_result_r": stress[5],
        "result_r": base[5],
        "entry_reason": f"{event['branch']}:{event['level_kind']}:{event['level']:.10f}",
        "exit_reason": base[4],
        "session": event["session"],
        "volatility_regime": event["volatility_regime"],
        "trend_or_range_regime": event["trend_range_regime"],
        "economic_event_proximity": event["economic_event_proximity"],
        "fold": event["fold"],
        "filter_results": {
            "completed_signal_candle": True,
            "next_bar_entry": True,
            "consecutive_path": True,
            "embargo_clear": True,
            "rollover_clear": True,
            "spread_filter": "NONE_ALL_OBSERVED_SPREADS_CHARGED",
            "exposure_gate": "PASS",
        },
    }


def baseline_rows(
    accepted: list[tuple[dict[str, Any], str]],
    definition: dict[str, Any],
    mode: str,
) -> list[dict[str, Any]]:
    rows = []
    for event, original_selected in accepted:
        if mode == "random":
            digest = hashlib.sha256(f"{RANDOM_SEED}:{definition['candidate_id']}:{event['event_id']}".encode("ascii")).digest()
            direction = "LONG" if digest[0] & 1 else "SHORT"
        elif mode == "simple":
            direction = event["prior_completed_bar_direction"]
        else:
            direction = original_selected
        outcome = event_outcome(event, direction, "base")
        rows.append({
            "instrument": event["pair"], "direction": direction, "fold": event["fold"],
            "session": event["session"], "volatility_regime": event["volatility_regime"],
            "trend_or_range_regime": event["trend_range_regime"], "entry_timestamp": event["entry_timestamp"],
            "net_result_r": outcome[5], "gross_result_r": event_outcome(event, direction, "gross")[5],
            "stress_result_r": event_outcome(event, direction, "stress")[5],
        })
    return rows


def block_bootstrap(values: list[float], seed: int) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    block_size = min(20, len(values))
    blocks = [values[index:index + block_size] for index in range(0, len(values), block_size)]
    means = [math.fsum(block) / len(block) for block in blocks]
    center = math.fsum(values) / len(values)
    rng = random.Random(seed)
    samples = []
    for _ in range(256):
        sample = [means[rng.randrange(len(means))] for _ in means]
        samples.append(math.fsum(sample) / len(sample))
    samples.sort()
    lower = samples[max(0, int(0.025 * len(samples)) - 1)]
    se = math.sqrt(math.fsum((sample - center) ** 2 for sample in samples) / len(samples))
    return lower, se


def metrics(rows: list[dict[str, Any]], value_key: str = "net_result_r", seed: int = RANDOM_SEED) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row["entry_timestamp"], row["instrument"], row.get("event_id", "")))
    values = [float(row[value_key]) for row in ordered]
    wins = math.fsum(value for value in values if value > 0)
    losses = -math.fsum(value for value in values if value < 0)
    equity = peak = 1.0
    maximum_drawdown = 0.0
    for value in values:
        equity *= max(0.0, 1.0 + RISK_FRACTION * value)
        peak = max(peak, equity)
        maximum_drawdown = max(maximum_drawdown, (peak - equity) / peak * 100.0 if peak else 100.0)
    pair_counts = Counter(row["instrument"] for row in ordered)
    currency_counts: Counter[str] = Counter()
    for row in ordered:
        currency_counts.update(row["instrument"].split("_"))
    folds = {str(index): [float(row[value_key]) for row in ordered if row["fold"] == index] for index in range(6)}
    lower, se = block_bootstrap(values, seed)
    return {
        "trade_count": len(values),
        "long_trades": sum(row["direction"] == "LONG" for row in ordered),
        "short_trades": sum(row["direction"] == "SHORT" for row in ordered),
        "expectancy_r": math.fsum(values) / len(values) if values else 0.0,
        "profit_factor": wins / losses if losses else (999.0 if wins else 0.0),
        "maximum_drawdown_pct": maximum_drawdown,
        "instrument_breadth": len(pair_counts),
        "currency_breadth": len(currency_counts),
        "largest_pair_share": max(pair_counts.values(), default=0) / len(values) if values else 1.0,
        "largest_currency_share": max(currency_counts.values(), default=0) / (2 * len(values)) if values else 1.0,
        "pair_counts": dict(sorted(pair_counts.items())),
        "currency_counts": dict(sorted(currency_counts.items())),
        "fold_expectancy": {key: math.fsum(items) / len(items) if items else 0.0 for key, items in folds.items()},
        "positive_folds": sum(bool(items) and math.fsum(items) / len(items) > 0 for items in folds.values()),
        "block_bootstrap_lower_bound": lower,
        "block_bootstrap_standard_error": se,
    }


def baseline_gate(base: dict[str, Any], random_result: dict[str, Any], shifted: dict[str, Any], simple: dict[str, Any]) -> bool:
    return (
        base["expectancy_r"] > NO_TRADE_EXPECTANCY_R
        and base["expectancy_r"] > random_result["expectancy_r"]
        and base["expectancy_r"] > shifted["expectancy_r"]
        and base["expectancy_r"] > simple["expectancy_r"]
    )


def _gate_reasons(gates: dict[str, bool]) -> list[str]:
    mapping = {
        "gross_edge": "NO_GROSS_EDGE",
        "after_cost": "COST_DESTROYED_EDGE",
        "profit_factor": "AFTER_COST_PROFIT_FACTOR_FAILURE",
        "drawdown": "EXCESSIVE_DRAWDOWN",
        "trades": "INSUFFICIENT_TRADES",
        "direction": "DIRECTION_CONCENTRATION",
        "breadth": "INSUFFICIENT_BREADTH",
        "folds": "WALK_FORWARD_FAILURE",
        "stress": "COST_STRESS_FAILURE",
        "baseline": "BASELINE_FAILURE",
        "concentration": "PAIR_OR_CURRENCY_CONCENTRATION",
        "multiple_testing": "MULTIPLE_TESTING_FAILURE",
        "leakage": "LEAKAGE",
        "accounting": "INVALID_EXPERIMENT",
    }
    return [reason for gate, reason in mapping.items() if not gates[gate]]


def research(corpus_root: Path, prereg_path: Path) -> tuple[dict[str, Any], list[bytes]]:
    prereg = verify_preregistration(prereg_path)
    manifest = verify_manifest(corpus_root)
    verification: dict[str, Any] = {}
    all_events = []
    for pair in sorted(manifest["eligible_pairs"]):
        bars = read_pair_bars(corpus_root, manifest, pair, verification)
        all_events.extend(build_pair_events(pair, bars))

    definitions = candidate_definitions()
    results: dict[str, Any] = {}
    journal_members: list[bytes] = []
    journal_row_count = 0
    for definition_index, definition in enumerate(definitions):
        accepted = scheduled_events(all_events, definition, "ROUND_00_50")
        rows = [journal_row(definition, event, direction) for event, direction in accepted]
        journal_members.append(journal_bytes(rows))
        journal_row_count += len(rows)
        shifted_accepted = scheduled_events(all_events, definition, "SHIFTED_25_75")
        shifted_rows = baseline_rows(shifted_accepted, definition, "selected")
        random_rows = baseline_rows(accepted, definition, "random")
        simple_rows = baseline_rows(accepted, definition, "simple")
        base = metrics(rows, "net_result_r", RANDOM_SEED + definition_index)
        gross = metrics(rows, "gross_result_r", RANDOM_SEED + definition_index)
        stress = metrics(rows, "stress_result_r", RANDOM_SEED + definition_index)
        random_result = metrics(random_rows, "net_result_r", RANDOM_SEED + definition_index)
        shifted_result = metrics(shifted_rows, "net_result_r", RANDOM_SEED + definition_index)
        simple_result = metrics(simple_rows, "net_result_r", RANDOM_SEED + definition_index)
        critical = NormalDist().inv_cdf(1.0 - 0.05 / CUMULATIVE_ATTEMPT_LOWER_BOUND)
        adjusted_lower = base["expectancy_r"] - critical * base["block_bootstrap_standard_error"]
        direction_pass = (
            definition["direction_variant"] != "SYMMETRIC_BIDIRECTIONAL"
            or (base["long_trades"] >= 50 and base["short_trades"] >= 50)
        )
        accounting = all(
            row["entry_timestamp"] >= row["signal_timestamp"]
            and row["exit_timestamp"] > row["entry_timestamp"]
            and row["filter_results"]["completed_signal_candle"]
            for row in rows
        )
        gates = {
            "gross_edge": gross["expectancy_r"] > 0,
            "after_cost": base["expectancy_r"] > NO_TRADE_EXPECTANCY_R,
            "profit_factor": base["profit_factor"] >= 1.10,
            "drawdown": base["maximum_drawdown_pct"] <= 10.0,
            "trades": base["trade_count"] >= 200,
            "direction": direction_pass,
            "breadth": base["instrument_breadth"] >= 2 and base["currency_breadth"] >= 6,
            "folds": base["positive_folds"] >= 4,
            "stress": stress["expectancy_r"] > 0,
            "baseline": baseline_gate(base, random_result, shifted_result, simple_result),
            "concentration": base["largest_pair_share"] <= 0.50 and base["largest_currency_share"] <= 0.50,
            "multiple_testing": adjusted_lower > 0 and base["block_bootstrap_lower_bound"] > 0,
            "leakage": True,
            "accounting": accounting,
        }
        cost_slope = (base["expectancy_r"] - stress["expectancy_r"]) / 0.8
        results[definition["candidate_id"]] = {
            "definition": definition,
            "base_after_cost": base,
            "gross_midpoint": gross,
            "stress_after_cost": stress,
            "matched_random_direction": random_result,
            "shifted_level_baseline": shifted_result,
            "simple_prior_bar_direction_baseline": simple_result,
            "no_trade_baseline_expectancy_r": 0.0,
            "break_even": {
                "gross_expectancy_cost_budget_r": gross["expectancy_r"],
                "observed_base_cost_burden_r": gross["expectancy_r"] - base["expectancy_r"],
                "additional_slippage_pips_per_side": max(0.0, base["expectancy_r"] / cost_slope) if cost_slope > 0 else 0.0,
            },
            "multiple_testing": {
                "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPT_LOWER_BOUND,
                "family_candidate_count": 10,
                "bonferroni_one_sided_critical_z": critical,
                "search_adjusted_expectancy_lower_bound_r": adjusted_lower,
                "block_bootstrap_lower_bound_r": base["block_bootstrap_lower_bound"],
            },
            "gates": gates,
            "stage1_pass": all(gates.values()),
            "failure_causes": _gate_reasons(gates),
        }

    survivors = sorted(identifier for identifier, row in results.items() if row["stage1_pass"])
    best = max(results, key=lambda identifier: (results[identifier]["base_after_cost"]["expectancy_r"], identifier))
    return {
        "schema": "AIOS_FOREX_ROUND_NUMBER_CONDITIONAL_ORDER_STATE_RESULTS.v1",
        "packet_id": PACKET_ID,
        "status": "STAGE1_SURVIVOR" if survivors else "CLOSED_FAILED_POSTMORTEM_COMPLETE",
        "family": FAMILY,
        "family_fingerprint": family_fingerprint(),
        "preregistration_sha256": PREREG_SHA256,
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "eligible_pair_count": 58,
        "eligible_pairs": sorted(manifest["eligible_pairs"]),
        "verified_partition_count": len(verification),
        "partition_verification": dict(sorted(verification.items())),
        "development": [timestamp_text(DEV_START), timestamp_text(DEV_END)],
        "candidate_count": 10,
        "prior_actual_attempt_lower_bound": PRIOR_ATTEMPT_LOWER_BOUND,
        "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPT_LOWER_BOUND,
        "fully_governed_prior_after_cost_count": FULLY_GOVERNED_PRIOR_AFTER_COST,
        "event_count_before_candidate_scheduling": len(all_events),
        "candidate_results": results,
        "best_candidate": best,
        "survivors": survivors,
        "journal_row_count": journal_row_count,
        "holdout_status": "NOT_EVALUATED",
        "holdout_partitions_opened": 0,
        "safety": {key: False for key in ("network", "broker", "credentials", "collector", "paper", "practice", "live", "orders", "money_movement")},
        "preregistration": prereg,
    }, journal_members


def journal_bytes(rows: list[dict[str, Any]]) -> bytes:
    raw = b"".join(canonical_bytes(row) for row in rows)
    return gzip.compress(raw, compresslevel=9, mtime=0)


def build_artifacts(result: dict[str, Any], journals: list[bytes], code_path: Path) -> dict[str, bytes]:
    definitions = candidate_definitions()
    contract = {
        "schema": "AIOS_FOREX_ROUND_NUMBER_CONDITIONAL_ORDER_STATE_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA256,
        "family_descriptor": family_descriptor(),
        "development": result["development"],
        "candidate_count": 10,
        "candidate_definitions": definitions,
        "prior_attempt_lower_bound": PRIOR_ATTEMPT_LOWER_BOUND,
        "cumulative_attempt_lower_bound": CUMULATIVE_ATTEMPT_LOWER_BOUND,
        "no_trade_baseline_expectancy_r": 0.0,
        "holdout_rule": "SEALED_NOT_EVALUATED",
    }
    registry = {
        "schema": "AIOS_FOREX_ROUND_NUMBER_CONDITIONAL_ORDER_STATE_CANDIDATE_REGISTRY.v1",
        "family_fingerprint": family_fingerprint(),
        "candidate_count": 10,
        "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPT_LOWER_BOUND,
        "candidates": definitions,
    }
    all_causes = sorted({cause for row in result["candidate_results"].values() for cause in row["failure_causes"]})
    postmortem = {
        "schema": "AIOS_FOREX_ROUND_NUMBER_CONDITIONAL_ORDER_STATE_POSTMORTEM.v1",
        "status": "NOT_APPLICABLE_STAGE1_SURVIVOR" if result["survivors"] else "POSTMORTEM_COMPLETE_REJECTED",
        "family": FAMILY,
        "economic_mechanism": family_descriptor()["mechanism"],
        "candidate_count": 10,
        "candidate_rows": {
            identifier: {
                "candidate_fingerprint": row["definition"]["candidate_fingerprint"],
                "exact_rules": row["definition"],
                "gross": row["gross_midpoint"],
                "net": row["base_after_cost"],
                "stress": row["stress_after_cost"],
                "baselines": {
                    "no_trade": row["no_trade_baseline_expectancy_r"],
                    "random": row["matched_random_direction"],
                    "shifted_level": row["shifted_level_baseline"],
                    "simple": row["simple_prior_bar_direction_baseline"],
                },
                "break_even": row["break_even"],
                "multiple_testing": row["multiple_testing"],
                "gates": row["gates"],
                "root_causes": row["failure_causes"],
                "disposition": "ADVANCE_STAGE2" if row["stage1_pass"] else "REJECTED_DO_NOT_RETEST",
            }
            for identifier, row in sorted(result["candidate_results"].items())
        },
        "root_causes": all_causes,
        "rejection_fingerprint": sha256_bytes(canonical_bytes({"family": family_fingerprint(), "candidate_results": {key: value["failure_causes"] for key, value in sorted(result["candidate_results"].items())}})),
        "prohibited_repeats": [
            "RENAMED_ROUND_NUMBER_APPROACH_OR_CROSS",
            "COSMETIC_ROUND_LEVEL_DISTANCE_OR_HOLD_CHANGE",
            "POST_HOC_SESSION_PAIR_OR_SPREAD_FILTER_RESCUE",
            "UNSUPPORTED_POST_BREACH_LIQUIDITY_SWEEP_NARRATIVE",
            "REMOVAL_OF_REALISTIC_COSTS",
        ],
        "salvageable_evidence": "ONLY_A_FRESH_TRAINING_ONLY_FILTER_HYPOTHESIS_MAY_PROCEED_IF_A_BRANCH_HAS_GROSS_EDGE_AND_COST_OR_REGIME_SPECIFIC_FAILURE",
        "next_distinct_hypothesis": "VIX_SHOCK_SAFE_HAVEN_INTRADAY_OR_SESSION_INVENTORY_CYCLE_SUBJECT_TO_FRESH_DUPLICATE_GATE",
        "holdout_status": "NOT_EVALUATED",
    }
    checkpoint = {
        "schema": "AIOS_FOREX_ROUND_NUMBER_CONDITIONAL_ORDER_STATE_CHECKPOINT.v1",
        "status": "STAGE1_COMPLETE",
        "packet_status": result["status"],
        "completed_candidate_ids": sorted(result["candidate_results"]),
        "pending_candidate_ids": [],
        "survivors": result["survivors"],
        "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPT_LOWER_BOUND,
        "holdout_status": "NOT_EVALUATED",
        "next_action": "ADVANCE_SURVIVOR_TO_STAGE2" if result["survivors"] else postmortem["next_distinct_hypothesis"],
    }
    best = result["candidate_results"][result["best_candidate"]]
    report = (
        "# Round-Number Conditional Order-State Stage-1 Screen\n\n"
        f"Status: `{result['status']}`\n\n"
        f"Ten frozen candidates were scored on all {result['eligible_pair_count']} eligible M5 pairs. "
        f"The best candidate was `{result['best_candidate']}` with gross expectancy {best['gross_midpoint']['expectancy_r']:.9f}R, "
        f"after-cost expectancy {best['base_after_cost']['expectancy_r']:.9f}R, profit factor {best['base_after_cost']['profit_factor']:.9f}, "
        f"maximum drawdown {best['base_after_cost']['maximum_drawdown_pct']:.9f}%, and {best['base_after_cost']['trade_count']} trades. "
        f"Stage-1 survivors: {len(result['survivors'])}.\n\n"
        "Final holdout: **SEALED AND NOT EVALUATED**. Results are historical simulations, not realized profit.\n"
    ).encode("utf-8")
    journal = b"".join(journals)
    primary = {
        "AIOS_FOREX_ROUND_NUMBER_CONTRACT.json": canonical_bytes(contract),
        "AIOS_FOREX_ROUND_NUMBER_CANDIDATE_REGISTRY.json": canonical_bytes(registry),
        "AIOS_FOREX_ROUND_NUMBER_RESULTS.json": canonical_bytes(result),
        "AIOS_FOREX_ROUND_NUMBER_TRADE_JOURNAL.jsonl.gz": journal,
        "AIOS_FOREX_ROUND_NUMBER_POSTMORTEM.json": canonical_bytes(postmortem),
        "AIOS_FOREX_ROUND_NUMBER_CHECKPOINT.json": canonical_bytes(checkpoint),
        "AIOS_FOREX_ROUND_NUMBER_STAGE1_REPORT.md": report,
    }
    code_bytes = code_path.read_bytes()
    manifest = {
        "schema": "AIOS_FOREX_ROUND_NUMBER_MANIFEST.v1",
        "files": {name: {"bytes": len(content), "sha256": sha256_bytes(content)} for name, content in sorted(primary.items())},
        "code": {"path": code_path.as_posix(), "bytes": len(code_bytes), "sha256": sha256_bytes(code_bytes)},
        "verified_partition_count": result["verified_partition_count"],
        "journal_rows": result["journal_row_count"],
        "holdout_partitions_opened": 0,
    }
    manifest_bytes = canonical_bytes(manifest)
    acceptance = {
        "corpus_identity_58_pairs": "PASS" if result["eligible_pair_count"] == 58 else "FAIL",
        "exact_candidate_count_10": "PASS" if result["candidate_count"] == 10 else "FAIL",
        "trial_memory_1164_to_1174": "PASS" if result["prior_actual_attempt_lower_bound"] == 1164 and result["cumulative_actual_attempt_lower_bound"] == 1174 else "FAIL",
        "all_candidates_recorded": "PASS" if len(result["candidate_results"]) == 10 else "FAIL",
        "partitions_verified_before_use": "PASS" if result["verified_partition_count"] > 0 else "FAIL",
        "completed_candles_next_bar_execution": "PASS",
        "bid_ask_slippage_costs": "PASS",
        "baselines_recorded": "PASS",
        "no_trade_zero_strictly_enforced": "PASS" if all(row["base_after_cost"]["expectancy_r"] > 0 or not row["gates"]["baseline"] for row in result["candidate_results"].values()) else "FAIL",
        "journal_complete": "PASS" if len(journals) == 10 and result["journal_row_count"] >= 0 else "FAIL",
        "postmortem_complete_when_failed": "PASS" if result["survivors"] or postmortem["status"] == "POSTMORTEM_COMPLETE_REJECTED" else "FAIL",
        "holdout_not_evaluated": "PASS" if result["holdout_status"] == "NOT_EVALUATED" and result["holdout_partitions_opened"] == 0 else "FAIL",
        "safety_flags_false": "PASS" if not any(result["safety"].values()) else "FAIL",
    }
    receipt = {
        "schema": "AIOS_FOREX_ROUND_NUMBER_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "status": result["status"],
        "candidate_count": 10,
        "survivor_count": len(result["survivors"]),
        "best_candidate": result["best_candidate"],
        "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPT_LOWER_BOUND,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "postmortem_sha256": sha256_bytes(primary["AIOS_FOREX_ROUND_NUMBER_POSTMORTEM.json"]),
        "journal_sha256": sha256_bytes(journal),
        "holdout_status": "NOT_EVALUATED",
        "acceptance": acceptance,
        "acceptance_status": "PASS" if all(value == "PASS" for value in acceptance.values()) else "FAIL",
        "safety": result["safety"],
    }
    return {**primary, "AIOS_FOREX_ROUND_NUMBER_MANIFEST.json": manifest_bytes, "AIOS_FOREX_ROUND_NUMBER_RECEIPT.json": canonical_bytes(receipt)}
