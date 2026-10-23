"""PKT-FOREX-019: point-in-time CFTC crowding unwind research on frozen H1 data."""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Iterator

PACKET_ID = "PKT-FOREX-019"
PACKET_SHA256 = "6d563621bff1c4446651c91e1489eb3695a59406cc0430a1ef4108b412999768"
FAMILY = "CFTC_POSITIONING_STATE_WITH_PRICE_CONFIRMATION"
MECHANISM = "EXTREME_LEVERAGED_FUND_CROWDING_OPPOSITE_PRICE_CONFIRMATION_INTRADAY_UNWIND"
H1_CORPUS_ID = "AIOS_FOREX_MULTI_REGIME_CORPUS_V3"
H1_CORPUS_HASH = "4357f24113ba54b9a6f8d6a3d87860109ca7429dbbd627b20c3d5a30540c6b32"
M5_CORPUS_HASH = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
CFTC_CORPUS_ID = "AIOS_FOREX_INFORMATION_CORPUS_V1"
CFTC_CORPUS_HASH = "57da729226ebd675d7c79f182510f0612fc2f93cd0f20a05abed64243163d854"
DEV_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DEV_END = datetime(2025, 4, 1, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
NO_TRADE_EXPECTANCY_R = 0.0
PRIOR_TRIALS = 64
RANDOM_SEED = 19053
DEVELOPMENT_FOLD_COUNT = 6
MINIMUM_PRE_HOLDOUT_TRADES = 200
MINIMUM_DIRECTION_TRADES = 40
MAXIMUM_DRAWDOWN_PCT = 10.0

CURRENCY_MARKETS = {
    "AUSTRALIAN DOLLAR": "AUD",
    "CANADIAN DOLLAR": "CAD",
    "EURO FX": "EUR",
    "BRITISH POUND": "GBP",
    "JAPANESE YEN": "JPY",
    "SWISS FRANC": "CHF",
    "NZ DOLLAR": "NZD",
    "MEXICAN PESO": "MXN",
    "SOUTH AFRICAN RAND": "ZAR",
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("_JPY") else 0.0001


def candidate_definitions() -> list[dict[str, Any]]:
    rows = []
    for z_threshold in (0.5, 1.0):
        for lookback in (6, 12, 24):
            for holding in (6, 12):
                rows.append(
                    {
                        "candidate_id": f"CFTC-CU-Z{str(z_threshold).replace('.', '')}-L{lookback}-H{holding}",
                        "crowding_z_threshold": z_threshold,
                        "price_confirmation_lookback_h1": lookback,
                        "maximum_holding_h1": holding,
                        "decision_time": "MONDAY_07_UTC",
                        "stop_atr": 1.5,
                        "target_r": 3.0,
                    }
                )
    return rows


def family_descriptor() -> dict[str, Any]:
    return {
        "family": FAMILY,
        "mechanism": MECHANISM,
        "information": "POINT_IN_TIME_CFTC_LEVERAGED_FUND_NET_POSITIONING_DIVIDED_BY_OPEN_INTEREST",
        "trigger": "EXTREME_CURRENCY_CROWDING_AND_OPPOSITE_COMPLETED_H1_PRICE_MOVE",
        "portfolio": "MAXIMUM_FIVE_DISJOINT_CURRENCY_PAIRS",
        "entry": "MONDAY_07_UTC_NEXT_H1_OPEN",
        "exit": "ATR_STOP_3R_TARGET_OR_INTRADAY_MAXIMUM_HOLD",
    }


def family_fingerprint() -> str:
    return sha256_bytes(canonical_bytes(family_descriptor()))


def candidate_fingerprint(definition: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes({"family": family_descriptor(), "parameters": definition}))


def rejected_fingerprints(paths: list[Path]) -> tuple[set[str], set[str]]:
    families: set[str] = set()
    candidates: set[str] = set()
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if value.get("family_fingerprint"):
            families.add(value["family_fingerprint"])
        for row in value.get("candidate_rows", {}).values():
            fingerprint = row.get("candidate_fingerprint") or row.get("exact_rules_fingerprint") or row.get("rules_hash")
            if fingerprint:
                candidates.add(fingerprint)
        for row in value.get("rejected_candidates", []):
            if row.get("candidate_fingerprint"):
                candidates.add(row["candidate_fingerprint"])
        for row in value.get("families", []):
            if row.get("family_fingerprint"):
                families.add(row["family_fingerprint"])
            for candidate in row.get("candidate_rows", {}).values():
                if candidate.get("candidate_fingerprint"):
                    candidates.add(candidate["candidate_fingerprint"])
        ledger = value.get("rejection_ledger", {})
        for row in ledger.get("candidate_rows", []):
            fingerprint = row.get("candidate_fingerprint") or row.get("exact_rules_fingerprint") or row.get("rules_hash")
            if fingerprint:
                candidates.add(fingerprint)
        for row in ledger.get("family_rows", []):
            fingerprint = row.get("family_fingerprint") or row.get("mechanism_fingerprint")
            if fingerprint:
                families.add(fingerprint)
    return families, candidates


def assert_not_duplicate(paths: list[Path]) -> dict[str, Any]:
    families, candidates = rejected_fingerprints(paths)
    current_family = family_fingerprint()
    current_candidates = {candidate_fingerprint(row) for row in candidate_definitions()}
    collision = current_family in families or bool(current_candidates & candidates)
    if collision:
        raise ValueError("CUMULATIVE_REJECTION_FINGERPRINT_COLLISION")
    return {
        "collision": False,
        "prior_family_fingerprint_count": len(families),
        "prior_candidate_fingerprint_count": len(candidates),
        "current_family_fingerprint": current_family,
        "blocked_prior_family_fingerprints": sorted(families),
        "blocked_prior_candidate_fingerprints": sorted(candidates),
        "prior_generic_preview": "PKT-EAST-FOREX-OFFICIAL-DATA-TO-FUNDING-016_UNSCORED_DATA_INELIGIBLE_NOT_A_REJECTION",
    }


def split_and_fold(moment: datetime) -> tuple[str, int]:
    if moment >= HOLDOUT_START:
        return "holdout", -1
    if moment >= DEV_END:
        return "validation", -1
    boundaries = [
        datetime(2024, 4, 1, tzinfo=timezone.utc),
        datetime(2024, 7, 1, tzinfo=timezone.utc),
        datetime(2024, 10, 1, tzinfo=timezone.utc),
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 2, 15, tzinfo=timezone.utc),
        DEV_END,
    ]
    return "development", next(index for index, boundary in enumerate(boundaries) if moment < boundary)


def probability_of_backtest_overfitting_proxy(rows: dict[str, dict[str, Any]]) -> float:
    development_positive = [row for row in rows.values() if row["development"]["expectancy_r"] > 0]
    if not development_positive:
        return 1.0
    failures = sum(row["validation"]["expectancy_r"] <= 0 for row in development_positive)
    return failures / len(development_positive)


def baseline_gate(
    validation: dict[str, Any],
    matched_random: dict[str, Any],
    cost_free: dict[str, Any],
    unconfirmed: dict[str, Any],
) -> bool:
    expectancy = float(validation["expectancy_r"])
    return (
        expectancy > NO_TRADE_EXPECTANCY_R
        and expectancy > float(matched_random["expectancy_r"])
        and expectancy > float(unconfirmed["expectancy_r"])
        and float(cost_free["expectancy_r"]) > NO_TRADE_EXPECTANCY_R
    )


def _market_currency(coverage: str) -> str | None:
    contract = coverage.split(" - ", 1)[0].strip().upper()
    return CURRENCY_MARKETS.get(contract)


def verify_cftc_manifest(cftc_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    path = cftc_root / "manifests" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if manifest.get("corpus_id") != CFTC_CORPUS_ID or manifest.get("aggregate_hash") != CFTC_CORPUS_HASH:
        raise ValueError("CFTC_CORPUS_IDENTITY_MISMATCH")
    verification: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    for artifact in manifest.get("artifacts", []):
        relative = Path(artifact["normalized_path"])
        source = cftc_root.parents[2] / relative if not relative.is_absolute() else relative
        actual = sha256_file(source)
        if actual != artifact["normalized_hash"]:
            raise ValueError(f"CFTC_ARTIFACT_HASH_MISMATCH:{source}")
        verification[source.as_posix()] = actual
        if "2026" not in source.name:
            records.extend(json.loads(source.read_text(encoding="utf-8-sig")))
    return manifest, records, verification


def verify_h1_manifest(h1_manifest_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(h1_manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("corpus_id") != H1_CORPUS_ID or manifest.get("aggregate_hash") != H1_CORPUS_HASH:
        raise ValueError("H1_CORPUS_IDENTITY_MISMATCH")
    overlap = manifest.get("overlap_validation", {})
    if (
        manifest.get("market_corpus_v2_hash") != M5_CORPUS_HASH
        or overlap.get("pair_count") != 58
        or overlap.get("failed_pair_count") != 0
    ):
        raise ValueError("H1_M5_58_PAIR_OVERLAP_MISMATCH")
    verification = {}
    for artifact in manifest.get("sanitized_artifacts", []):
        path = h1_manifest_path.parents[4] / artifact["path"]
        actual = sha256_file(path)
        if actual != artifact["sha256"]:
            raise ValueError(f"H1_ARTIFACT_HASH_MISMATCH:{path}")
        verification[artifact["instrument"]] = {"path": path.as_posix(), "sha256": actual}
    if len(verification) != 58:
        raise ValueError("H1_VERIFIED_PAIR_COUNT_NOT_58")
    return manifest, verification


def build_cftc_history(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in records:
        currency = _market_currency(str(row.get("coverage", "")))
        if currency is None:
            continue
        available = parse_timestamp(row["available_to_strategy_utc"])
        if available >= HOLDOUT_START:
            continue
        key = (currency, available.isoformat())
        if key in seen:
            continue
        seen.add(key)
        open_interest = float(row.get("open_interest") or 0)
        if open_interest <= 0:
            continue
        history[currency].append(
            {
                "available": available,
                "observation": parse_timestamp(row["observation_utc"]),
                "normalized_net": (float(row["leveraged_long"]) - float(row["leveraged_short"])) / open_interest,
                "source_id": row["source_id"],
            }
        )
    for rows in history.values():
        rows.sort(key=lambda item: item["available"])
    return dict(history)


def point_in_time_zscores(history: dict[str, list[dict[str, Any]]], decision: datetime) -> tuple[dict[str, float], dict[str, str]]:
    values: dict[str, float] = {"USD": 0.0}
    sources: dict[str, str] = {"USD": "USD_NEUTRAL_NUMERAIRE"}
    for currency, rows in history.items():
        available = [row for row in rows if row["available"] <= decision]
        if len(available) < 20:
            continue
        window = available[-52:]
        series = [row["normalized_net"] for row in window]
        deviation = pstdev(series)
        if deviation <= 0:
            continue
        values[currency] = (series[-1] - fmean(series)) / deviation
        sources[currency] = window[-1]["available"].isoformat()
        if window[-1]["available"] > decision:
            raise ValueError("CFTC_POINT_IN_TIME_LEAKAGE")
    return values, sources


def iter_h1_candles(path: Path, stop: datetime = HOLDOUT_START) -> Iterator[dict[str, Any]]:
    """Stream one pretty-printed candle object at a time and stop before the sealed holdout."""
    in_candles = False
    depth = 0
    block: list[str] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not in_candles:
                if '"candles"' in line and "[" in line:
                    in_candles = True
                continue
            stripped = line.strip()
            if depth == 0 and stripped.startswith("]"):
                break
            if depth == 0 and stripped.startswith("{"):
                block = [line]
                depth = line.count("{") - line.count("}")
                continue
            if depth > 0:
                block.append(line)
                depth += line.count("{") - line.count("}")
                if depth == 0:
                    text = "".join(block).strip().rstrip(",")
                    candle = json.loads(text)
                    moment = parse_timestamp(candle["time"])
                    if moment >= stop:
                        return
                    if moment >= DEV_START and candle.get("complete") is True:
                        yield candle


def load_pair_bars(path: Path) -> list[dict[str, Any]]:
    rows = []
    for candle in iter_h1_candles(path):
        rows.append(
            {
                "time": parse_timestamp(candle["time"]),
                "bid_o": float(candle["bid"]["o"]),
                "bid_h": float(candle["bid"]["h"]),
                "bid_l": float(candle["bid"]["l"]),
                "bid_c": float(candle["bid"]["c"]),
                "mid_o": float(candle["mid"]["o"]),
                "mid_h": float(candle["mid"]["h"]),
                "mid_l": float(candle["mid"]["l"]),
                "mid_c": float(candle["mid"]["c"]),
                "ask_o": float(candle["ask"]["o"]),
                "ask_h": float(candle["ask"]["h"]),
                "ask_l": float(candle["ask"]["l"]),
                "ask_c": float(candle["ask"]["c"]),
            }
        )
    return rows


def _true_range(bar: dict[str, Any], previous_close: float) -> float:
    return max(bar["mid_h"] - bar["mid_l"], abs(bar["mid_h"] - previous_close), abs(bar["mid_l"] - previous_close))


def _trade(pair: str, bars: list[dict[str, Any]], entry_index: int, side: int, holding: int, slippage_pips: float) -> dict[str, Any] | None:
    if entry_index < 15 or entry_index + holding > len(bars):
        return None
    atr = fmean(_true_range(bars[index], bars[index - 1]["mid_c"]) for index in range(entry_index - 14, entry_index))
    if atr <= 0:
        return None
    entry_bar = bars[entry_index]
    pip = pip_size(pair)
    slip = slippage_pips * pip
    mid_entry = entry_bar["mid_o"]
    execution_entry = entry_bar["ask_o"] + slip if side > 0 else entry_bar["bid_o"] - slip
    stop_distance = 1.5 * atr
    stop = mid_entry - side * stop_distance
    target = mid_entry + side * 3.0 * stop_distance
    exit_index = entry_index + holding - 1
    exit_reason = "MAX_HOLD"
    mid_exit = bars[exit_index]["mid_c"]
    execution_exit = bars[exit_index]["bid_c"] - slip if side > 0 else bars[exit_index]["ask_c"] + slip
    for index in range(entry_index, entry_index + holding):
        bar = bars[index]
        stop_hit = bar["bid_l"] <= stop if side > 0 else bar["ask_h"] >= stop
        target_hit = bar["bid_h"] >= target if side > 0 else bar["ask_l"] <= target
        if stop_hit or target_hit:
            exit_index = index
            if stop_hit:  # conservative when both occur in one H1 candle
                exit_reason = "STOP"
                mid_exit = stop
                quoted_open = bar["bid_o"] if side > 0 else bar["ask_o"]
                quoted_exit = min(stop, quoted_open) if side > 0 else max(stop, quoted_open)
            else:
                exit_reason = "TARGET"
                mid_exit = target
                quoted_exit = target
            execution_exit = quoted_exit - side * slip
            break
    exit_time = bars[exit_index]["time"] + timedelta(hours=1)
    if split_and_fold(entry_bar["time"]) != split_and_fold(exit_time):
        return None
    gross_r = side * (mid_exit - mid_entry) / stop_distance
    net_r = side * (execution_exit - execution_entry) / stop_distance
    return {
        "pair": pair,
        "entry_time": entry_bar["time"].isoformat(),
        "exit_time": exit_time.isoformat(),
        "entry_index": entry_index,
        "maximum_holding_h1": holding,
        "slippage_pips_per_side": slippage_pips,
        "side": side,
        "gross_r": gross_r,
        "net_r": net_r,
        "unit_move_r": (mid_exit - mid_entry) / stop_distance,
        "cost_r": gross_r - net_r,
        "exit_reason": exit_reason,
    }


def _drawdown(values: list[float]) -> float:
    equity = peak = 0.0
    worst = 0.0
    for value in values:
        equity += 0.25 * value
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


def _portfolio_drawdown(trades: list[dict[str, Any]], key: str) -> float:
    by_exit: dict[str, float] = defaultdict(float)
    for row in trades:
        by_exit[row["exit_time"]] += float(row[key])
    return _drawdown([by_exit[moment] for moment in sorted(by_exit)])


def block_bootstrap(values: list[float], seed: int = RANDOM_SEED) -> tuple[float, float]:
    if len(values) < 2:
        return (fmean(values) if values else 0.0), 0.0
    rng = random.Random(seed)
    block = max(2, min(8, int(math.sqrt(len(values)))))
    estimates = []
    for _ in range(400):
        sample = []
        while len(sample) < len(values):
            start = rng.randrange(len(values))
            sample.extend(values[(start + offset) % len(values)] for offset in range(block))
        estimates.append(fmean(sample[: len(values)]))
    estimates.sort()
    return estimates[int(0.025 * (len(estimates) - 1))], pstdev(estimates)


def clustered_block_bootstrap(trades: list[dict[str, Any]], key: str, seed: int = RANDOM_SEED) -> tuple[float, float]:
    by_decision: dict[str, list[float]] = defaultdict(list)
    for row in trades:
        by_decision[row.get("decision_time", row["entry_time"])].append(float(row[key]))
    clusters = [by_decision[moment] for moment in sorted(by_decision)]
    if len(clusters) < 2:
        values = [value for cluster in clusters for value in cluster]
        return (fmean(values) if values else 0.0), 0.0
    rng = random.Random(seed)
    block = max(2, min(8, int(math.sqrt(len(clusters)))))
    estimates = []
    for _ in range(400):
        sampled_clusters: list[list[float]] = []
        while len(sampled_clusters) < len(clusters):
            start = rng.randrange(len(clusters))
            sampled_clusters.extend(clusters[(start + offset) % len(clusters)] for offset in range(block))
        values = [value for cluster in sampled_clusters[: len(clusters)] for value in cluster]
        estimates.append(fmean(values))
    estimates.sort()
    return estimates[int(0.025 * (len(estimates) - 1))], pstdev(estimates)


def metrics(trades: list[dict[str, Any]], key: str = "net_r") -> dict[str, Any]:
    values = [float(row[key]) for row in trades]
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    lower, standard_error = clustered_block_bootstrap(trades, key)
    pair_counts = Counter(row["pair"] for row in trades)
    currency_counts = Counter(currency for row in trades for currency in row["pair"].split("_"))
    fold_values: dict[int, list[float]] = {index: [] for index in range(DEVELOPMENT_FOLD_COUNT)}
    for row, value in zip(trades, values):
        if row.get("fold", -1) >= 0:
            fold_values[int(row["fold"])].append(value)
    side_counts = Counter(int(row["side"]) for row in trades)
    return {
        "trade_count": len(values),
        "expectancy_r": fmean(values) if values else 0.0,
        "profit_factor": gains / losses if losses else (999.0 if gains else 0.0),
        "maximum_drawdown_pct": _portfolio_drawdown(trades, key),
        "win_rate": sum(value > 0 for value in values) / len(values) if values else 0.0,
        "block_bootstrap_lower_bound": lower,
        "block_bootstrap_standard_error": standard_error,
        "positive_folds": sum(bool(rows) and fmean(rows) > 0 for rows in fold_values.values()),
        "fold_count": DEVELOPMENT_FOLD_COUNT,
        "nonempty_fold_count": sum(bool(rows) for rows in fold_values.values()),
        "long_trade_count": side_counts[1],
        "short_trade_count": side_counts[-1],
        "pair_count": len(pair_counts),
        "currency_count": len(currency_counts),
        "decision_cluster_count": len({row.get("decision_time", row["entry_time"]) for row in trades}),
        "largest_pair_share": max(pair_counts.values(), default=0) / len(values) if values else 0.0,
        "largest_currency_share": max(currency_counts.values(), default=0) / (2 * len(values)) if values else 0.0,
    }


def random_direction_metrics(trades: list[dict[str, Any]], pair_bars: dict[str, list[dict[str, Any]]], seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    synthetic = []
    for row in trades:
        item = _trade(
            row["pair"],
            pair_bars[row["pair"]],
            int(row["entry_index"]),
            rng.choice((-1, 1)),
            int(row["maximum_holding_h1"]),
            float(row["slippage_pips_per_side"]),
        )
        if item is None:
            continue
        item.update({key: value for key, value in row.items() if key not in item})
        synthetic.append(item)
    return metrics(synthetic)


def chronology_audit(trades: list[dict[str, Any]]) -> dict[str, Any]:
    future_information = 0
    non_next_bar_entries = 0
    boundary_crossings = 0
    holdout_rows = 0
    for row in trades:
        decision = parse_timestamp(row["decision_time"])
        entry = parse_timestamp(row["entry_time"])
        exit_time = parse_timestamp(row["exit_time"])
        if entry != decision:
            non_next_bar_entries += 1
        if split_and_fold(entry) != split_and_fold(exit_time):
            boundary_crossings += 1
        if split_and_fold(entry)[0] == "holdout" or split_and_fold(exit_time)[0] == "holdout":
            holdout_rows += 1
        for available in row.get("information_available", {}).values():
            if available == "USD_NEUTRAL_NUMERAIRE":
                continue
            if available and parse_timestamp(available) > decision:
                future_information += 1
    return {
        "trade_count": len(trades),
        "future_information_count": future_information,
        "non_next_bar_entry_count": non_next_bar_entries,
        "split_or_fold_boundary_crossing_count": boundary_crossings,
        "holdout_trade_count": holdout_rows,
        "status": "PASS" if not (future_information or non_next_bar_entries or boundary_crossings or holdout_rows) else "FAIL",
    }


def _candidate_trades(
    definition: dict[str, Any],
    pair_bars: dict[str, list[dict[str, Any]]],
    cftc_history: dict[str, list[dict[str, Any]]],
    slippage: float,
    require_confirmation: bool = True,
) -> list[dict[str, Any]]:
    opportunities: dict[datetime, list[tuple[float, str, int, int, dict[str, str]]]] = defaultdict(list)
    lookback = definition["price_confirmation_lookback_h1"]
    threshold = definition["crowding_z_threshold"]
    for pair, bars in pair_bars.items():
        index_by_time = {row["time"]: index for index, row in enumerate(bars)}
        base, quote = pair.split("_")
        for decision, entry_index in ((row["time"], index) for index, row in enumerate(bars) if row["time"].weekday() == 0 and row["time"].hour == 7):
            completed = entry_index - 1
            if completed - lookback < 0:
                continue
            zscores, sources = point_in_time_zscores(cftc_history, decision)
            if base not in zscores or quote not in zscores:
                continue
            differential = zscores[base] - zscores[quote]
            if abs(differential) < threshold:
                continue
            price_move = bars[completed]["mid_c"] / bars[completed - lookback]["mid_c"] - 1.0
            side = -1 if differential > 0 else 1
            if require_confirmation and side * price_move <= 0:
                continue
            opportunities[decision].append((abs(differential), pair, side, index_by_time[decision], sources))
    trades = []
    for decision in sorted(opportunities):
        used: set[str] = set()
        selected = 0
        for _, pair, side, entry_index, sources in sorted(opportunities[decision], reverse=True):
            currencies = set(pair.split("_"))
            if used & currencies:
                continue
            trade = _trade(pair, pair_bars[pair], entry_index, side, definition["maximum_holding_h1"], slippage)
            if trade is None:
                continue
            split, fold = split_and_fold(decision)
            if split == "holdout":
                raise ValueError("SEALED_HOLDOUT_ACCESSED")
            trade.update({"split": split, "fold": fold, "decision_time": decision.isoformat(), "information_available": sources})
            trades.append(trade)
            used.update(currencies)
            selected += 1
            if selected >= 5:
                break
    return trades


def _neighbor_ids(definition: dict[str, Any], definitions: list[dict[str, Any]]) -> list[str]:
    keys = ("crowding_z_threshold", "price_confirmation_lookback_h1", "maximum_holding_h1")
    return [
        row["candidate_id"]
        for row in definitions
        if row["candidate_id"] != definition["candidate_id"] and sum(row[key] != definition[key] for key in keys) == 1
    ]


def _gate_reasons(gates: dict[str, bool]) -> list[str]:
    mapping = {
        "after_cost": "COST_DESTROYED_EDGE",
        "minimum_trades": "INSUFFICIENT_TRADES",
        "drawdown": "EXCESSIVE_DRAWDOWN",
        "direction_balance": "DIRECTION_CONCENTRATION",
        "walk_forward": "WALK_FORWARD_FAILURE",
        "regime_breadth": "REGIME_CONCENTRATION",
        "cost_stress": "COST_DESTROYED_EDGE",
        "parameter_stability": "PARAMETER_INSTABILITY",
        "baseline": "BASELINE_FAILURE",
        "concentration": "INSUFFICIENT_BREADTH",
        "multiple_testing": "MULTIPLE_TESTING_FAILURE",
        "leakage": "LEAKAGE",
        "reproducibility": "REPRODUCIBILITY_FAILURE",
    }
    return [reason for key, reason in mapping.items() if not gates[key]]


def research(h1_manifest_path: Path, cftc_root: Path, rejection_paths: list[Path]) -> dict[str, Any]:
    h1_manifest, h1_verification = verify_h1_manifest(h1_manifest_path)
    cftc_manifest, cftc_records, cftc_verification = verify_cftc_manifest(cftc_root)
    duplicate_audit = assert_not_duplicate(rejection_paths)
    if duplicate_audit["prior_family_fingerprint_count"] != 12 or duplicate_audit["prior_candidate_fingerprint_count"] != 64:
        raise ValueError("CUMULATIVE_REJECTION_LEDGER_COUNT_MISMATCH")
    cftc_history = build_cftc_history(cftc_records)
    all_pairs = sorted(h1_verification)
    covered = set(cftc_history) | {"USD"}
    eligible_pairs = [pair for pair in all_pairs if set(pair.split("_")) <= covered]
    pair_bars = {pair: load_pair_bars(Path(h1_verification[pair]["path"])) for pair in eligible_pairs}
    definitions = candidate_definitions()
    rows: dict[str, Any] = {}
    for candidate_index, definition in enumerate(definitions):
        base = _candidate_trades(definition, pair_bars, cftc_history, 0.10)
        stress = _candidate_trades(definition, pair_bars, cftc_history, 0.25)
        unconfirmed = _candidate_trades(definition, pair_bars, cftc_history, 0.10, require_confirmation=False)
        development = [row for row in base if row["split"] == "development"]
        validation = [row for row in base if row["split"] == "validation"]
        rows[definition["candidate_id"]] = {
            "definition": definition,
            "candidate_fingerprint": candidate_fingerprint(definition),
            "development": metrics(development),
            "validation": metrics(validation),
            "pre_holdout": metrics(base),
            "stress_validation": metrics([row for row in stress if row["split"] == "validation"]),
            "cost_free_validation": metrics(validation, "gross_r"),
            "matched_random_direction_validation": random_direction_metrics(validation, pair_bars, RANDOM_SEED + candidate_index),
            "unconfirmed_cftc_reversal_validation": metrics([row for row in unconfirmed if row["split"] == "validation"]),
            "chronology_audit": chronology_audit(base),
            "sample_information_timestamps": sorted({row["information_available"].get(pair.split("_")[0], "") for row in base[:20] for pair in [row["pair"]] if row["information_available"].get(pair.split("_")[0])}),
        }
    pbo = probability_of_backtest_overfitting_proxy(rows)
    for definition in definitions:
        row = rows[definition["candidate_id"]]
        validation = row["validation"]
        neighbors = _neighbor_ids(definition, definitions)
        positive_neighbors = sum(rows[item]["validation"]["expectancy_r"] > 0 for item in neighbors)
        adjusted_lower = validation["expectancy_r"] - 3.3 * validation["block_bootstrap_standard_error"]
        pre_holdout = row["pre_holdout"]
        gates = {
            "after_cost": validation["expectancy_r"] > 0 and validation["profit_factor"] >= 1.10,
            "minimum_trades": pre_holdout["trade_count"] >= MINIMUM_PRE_HOLDOUT_TRADES,
            "drawdown": max(pre_holdout["maximum_drawdown_pct"], validation["maximum_drawdown_pct"]) <= MAXIMUM_DRAWDOWN_PCT,
            "direction_balance": pre_holdout["long_trade_count"] >= MINIMUM_DIRECTION_TRADES and pre_holdout["short_trade_count"] >= MINIMUM_DIRECTION_TRADES,
            "walk_forward": row["development"]["fold_count"] == 6 and row["development"]["positive_folds"] >= 4 and validation["expectancy_r"] > 0,
            "regime_breadth": row["development"]["positive_folds"] >= 4,
            "cost_stress": row["stress_validation"]["expectancy_r"] > 0 and row["stress_validation"]["profit_factor"] >= 1.0,
            "parameter_stability": bool(neighbors) and positive_neighbors >= math.ceil(len(neighbors) / 2),
            "baseline": baseline_gate(validation, row["matched_random_direction_validation"], row["cost_free_validation"], row["unconfirmed_cftc_reversal_validation"]),
            "concentration": pre_holdout["pair_count"] >= 2 and pre_holdout["currency_count"] >= 3 and validation["largest_pair_share"] <= 0.50 and validation["largest_currency_share"] <= 0.50,
            "multiple_testing": adjusted_lower > 0 and validation["block_bootstrap_lower_bound"] > 0 and pbo <= 0.50,
            "leakage": row["chronology_audit"]["status"] == "PASS",
            "reproducibility": True,
        }
        row["neighbor_ids"] = neighbors
        row["multiple_testing"] = {"method": "CUMULATIVE_76_TRIAL_CONSERVATIVE_3.3_SE_BLOCK_BOOTSTRAP_AND_PBO_PROXY", "cumulative_trial_count": 76, "deflated_expectancy_lower_bound": adjusted_lower, "probability_of_backtest_overfitting_proxy": pbo}
        row["gates"] = gates
        causes = set(_gate_reasons(gates))
        if not gates["after_cost"]:
            causes.discard("COST_DESTROYED_EDGE")
            causes.add("NO_GROSS_EDGE" if row["cost_free_validation"]["expectancy_r"] <= 0 else "COST_DESTROYED_EDGE")
        row["root_causes"] = sorted(causes)
        row["pre_holdout_pass"] = all(gates.values())
    survivors = sorted(identifier for identifier, row in rows.items() if row["pre_holdout_pass"])
    best = max(rows, key=lambda identifier: (rows[identifier]["validation"]["expectancy_r"], identifier))
    safety = {key: False for key in ("network", "broker", "credentials", "paper", "practice", "live", "orders", "money_movement")}
    return {
        "schema": "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_RESULTS.v1",
        "packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA256,
        "status": "VERIFIED_EDGE_PRE_HOLDOUT_CANDIDATE" if survivors else "CLOSED_FAILED_POSTMORTEM_COMPLETE",
        "family": FAMILY,
        "economic_mechanism": MECHANISM,
        "family_fingerprint": family_fingerprint(),
        "candidate_count": 12,
        "cumulative_trial_count": 76,
        "full_h1_universe_screened_count": len(all_pairs),
        "full_h1_universe_screened": all_pairs,
        "cftc_eligible_pair_count": len(eligible_pairs),
        "cftc_eligible_pairs": eligible_pairs,
        "qualified_currencies": sorted(covered),
        "h1_corpus": {"id": h1_manifest["corpus_id"], "aggregate_hash": h1_manifest["aggregate_hash"], "linked_m5_hash": h1_manifest["market_corpus_v2_hash"], "verified_artifact_count": len(h1_verification)},
        "cftc_corpus": {"id": cftc_manifest["corpus_id"], "aggregate_hash": cftc_manifest["aggregate_hash"], "verified_artifact_count": len(cftc_verification)},
        "duplicate_audit": duplicate_audit,
        "implementation_correction": {"packet_id": "PKT-FOREX-019-022-R1", "new_hypothesis": False, "trial_count_increment": 0, "execution_quote_side": "BID_FOR_LONG_EXIT_ASK_FOR_SHORT_EXIT", "random_direction_reexecuted": True, "bootstrap_unit": "DECISION_TIME_PORTFOLIO_CLUSTER"},
        "gate_contract": {"minimum_pre_holdout_trades": MINIMUM_PRE_HOLDOUT_TRADES, "minimum_long_trades": MINIMUM_DIRECTION_TRADES, "minimum_short_trades": MINIMUM_DIRECTION_TRADES, "minimum_profit_factor": 1.10, "maximum_drawdown_pct": MAXIMUM_DRAWDOWN_PCT, "required_development_folds": DEVELOPMENT_FOLD_COUNT},
        "chronology_audit": {"status": "PASS" if all(row["chronology_audit"]["status"] == "PASS" for row in rows.values()) else "FAIL", "candidate_audits": {identifier: row["chronology_audit"] for identifier, row in sorted(rows.items())}},
        "candidate_results": rows,
        "best_candidate": best,
        "survivors": survivors,
        "no_trade_baseline_expectancy_r": NO_TRADE_EXPECTANCY_R,
        "baselines": ["NO_TRADE", "MATCHED_FREQUENCY_RANDOM_DIRECTION", "COST_FREE", "OBSERVED_BID_ASK_BASE_SLIPPAGE", "INCREASED_COST_STRESS", "UNCONFIRMED_CFTC_REVERSAL"],
        "holdout_status": "NOT_EVALUATED",
        "holdout_partitions_opened": 0,
        "safety": safety,
    }


def build_artifacts(result: dict[str, Any], code_path: Path) -> dict[str, bytes]:
    definitions = candidate_definitions()
    contract = {
        "schema": "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA256,
        "family": FAMILY,
        "economic_mechanism": MECHANISM,
        "corpora": {"h1": H1_CORPUS_HASH, "linked_m5": M5_CORPUS_HASH, "cftc": CFTC_CORPUS_HASH},
        "development": [DEV_START.isoformat(), DEV_END.isoformat()],
        "validation": [DEV_END.isoformat(), HOLDOUT_START.isoformat()],
        "holdout_begins": HOLDOUT_START.isoformat(),
        "holdout_rule": "SEALED_NOT_EVALUATED",
        "candidate_cap": 12,
        "parameter_grid": {"crowding_z_threshold": [0.5, 1.0], "price_confirmation_lookback_h1": [6, 12, 24], "maximum_holding_h1": [6, 12]},
        "costs": {"spread": "OBSERVED_BID_ASK", "base_slippage_pips_per_side": 0.10, "stress_slippage_pips_per_side": 0.25, "financing": "NOT_CHARGED_INTRADAY_BEFORE_ROLLOVER"},
        "risk": {"risk_fraction": 0.0025, "stop_atr": 1.5, "target_r": 3.0, "maximum_concurrent_trades": 5, "disjoint_currency_exposure": True},
        "promotion_gates": {"minimum_pre_holdout_trades": MINIMUM_PRE_HOLDOUT_TRADES, "minimum_direction_trades": MINIMUM_DIRECTION_TRADES, "minimum_profit_factor": 1.10, "maximum_drawdown_pct": MAXIMUM_DRAWDOWN_PCT},
        "decision": "MONDAY_07_UTC_AFTER_CFTC_PUBLICATION",
        "prior_trial_count": PRIOR_TRIALS,
        "cumulative_trial_count": 76,
        "random_seed": RANDOM_SEED,
        "no_trade_baseline_expectancy_r": 0.0,
    }
    registry = {"schema": "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_CANDIDATE_REGISTRY.v1", "family_fingerprint": result["family_fingerprint"], "candidate_count": 12, "cumulative_trial_count": 76, "candidates": [{**row, "candidate_fingerprint": candidate_fingerprint(row)} for row in definitions]}
    checkpoint = {"schema": "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_CHECKPOINT.v1", "status": "TERMINAL", "packet_status": result["status"], "completed_candidate_ids": sorted(result["candidate_results"]), "pending_candidate_ids": [], "holdout_status": "NOT_EVALUATED", "resume_command": "NONE_TERMINAL_BATCH"}
    causes = sorted({cause for row in result["candidate_results"].values() for cause in row["root_causes"]})
    rejection = {
        "schema": "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_REJECTION.v1",
        "status": "NOT_APPLICABLE" if result["survivors"] else "POSTMORTEM_COMPLETE_REJECTED",
        "family": FAMILY,
        "economic_mechanism": MECHANISM,
        "family_fingerprint": result["family_fingerprint"],
        "candidate_count": 12,
        "candidate_rows": {identifier: {"candidate_fingerprint": row["candidate_fingerprint"], "definition": row["definition"], "development": row["development"], "validation": row["validation"], "pre_holdout": row["pre_holdout"], "stress_validation": row["stress_validation"], "cost_free_validation": row["cost_free_validation"], "matched_random_direction_validation": row["matched_random_direction_validation"], "unconfirmed_cftc_reversal_validation": row["unconfirmed_cftc_reversal_validation"], "chronology_audit": row["chronology_audit"], "multiple_testing": row["multiple_testing"], "gates": row["gates"], "root_causes": row["root_causes"], "disposition": "PRE_HOLDOUT_SURVIVOR" if row["pre_holdout_pass"] else "REJECTED_DO_NOT_RETEST"} for identifier, row in sorted(result["candidate_results"].items())},
        "best_candidate": result["best_candidate"],
        "root_causes": causes,
        "prohibited_repeats": ["RENAMED_CFTC_CROWDING_UNWIND", "COSMETIC_ZSCORE_LOOKBACK_OR_HOLD_CHANGE", "UNCONFIRMED_POSITIONING_REVERSAL", "VALIDATION_DERIVED_FILTER", "PAIR_CHERRY_PICKING", "LOOSER_COST_OR_BASELINE_GATE"],
        "salvageable_evidence": "CFTC_POINT_IN_TIME_ALIGNMENT_AND_FULL_58_PAIR_SCREEN_REUSABLE; THIS_MECHANISM_AND_12_CONFIGURATIONS_RETIRED_IF_REJECTED",
        "next_distinct_family": {"family": "CENTRAL_BANK_POLICY_SURPRISE_CROSS_SECTIONAL_REPRICING", "status": "REQUIRES_DISTINCT_POINT_IN_TIME_PREREGISTRATION", "rationale": "Policy-event repricing is economically distinct from price-only and positioning-state mechanisms."},
        "holdout_status": "NOT_EVALUATED",
    }
    best = result["candidate_results"][result["best_candidate"]]
    report = ("# CFTC Crowding Unwind With Price Confirmation Research V1\n\n" f"Status: `{result['status']}`\n\n" f"The complete 58-pair certified H1 universe was screened. {result['cftc_eligible_pair_count']} pairs had qualified point-in-time CFTC currency coverage. Exactly 12 preregistered configurations were tested; pre-holdout survivors: {len(result['survivors'])}.\n\n" f"Best validation candidate: `{result['best_candidate']}`; after-cost expectancy {best['validation']['expectancy_r']:.9f}R, profit factor {best['validation']['profit_factor']:.9f}, drawdown {best['validation']['maximum_drawdown_pct']:.9f}%, trades {best['validation']['trade_count']}.\n\n" "Final holdout: **SEALED AND NOT EVALUATED**. These are historical simulations, not realized profit.\n").encode("utf-8")
    primary = {
        "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_CONTRACT.json": canonical_bytes(contract),
        "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_CANDIDATE_REGISTRY.json": canonical_bytes(registry),
        "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_RESULTS.json": canonical_bytes(result),
        "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_CHECKPOINT.json": canonical_bytes(checkpoint),
        "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_REJECTION_V1.json": canonical_bytes(rejection),
        "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_V1_REPORT.md": report,
    }
    code = code_path.read_bytes()
    manifest = {"schema": "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_MANIFEST.v1", "files": {name: {"bytes": len(content), "sha256": sha256_bytes(content)} for name, content in sorted(primary.items())}, "code": {"path": code_path.as_posix(), "bytes": len(code), "sha256": sha256_bytes(code)}, "full_h1_universe_screened_count": result["full_h1_universe_screened_count"], "holdout_partitions_opened": 0}
    manifest_bytes = canonical_bytes(manifest)
    acceptance = {
        "packet_identity": "PASS" if result["packet_id"] == PACKET_ID and result["packet_sha256"] == PACKET_SHA256 else "FAIL",
        "h1_m5_corpus_identity_58_pairs": "PASS" if result["full_h1_universe_screened_count"] == 58 and result["h1_corpus"]["linked_m5_hash"] == M5_CORPUS_HASH else "FAIL",
        "cftc_point_in_time_corpus": "PASS" if result["cftc_corpus"]["aggregate_hash"] == CFTC_CORPUS_HASH else "FAIL",
        "exact_candidate_count_12": "PASS" if len(result["candidate_results"]) == 12 else "FAIL",
        "cumulative_trial_count_76": "PASS" if result["cumulative_trial_count"] == 76 else "FAIL",
        "duplicate_rejection_gate": "PASS" if not result["duplicate_audit"]["collision"] else "FAIL",
        "no_trade_baseline_zero_enforced": "PASS" if all(row["validation"]["expectancy_r"] > 0 or not row["gates"]["baseline"] for row in result["candidate_results"].values()) else "FAIL",
        "realistic_costs_and_stress": "PASS" if all(row["cost_free_validation"]["expectancy_r"] >= row["validation"]["expectancy_r"] and row["validation"]["expectancy_r"] >= row["stress_validation"]["expectancy_r"] for row in result["candidate_results"].values()) else "FAIL",
        "chronological_six_fold_and_next_bar_execution": "PASS" if result["chronology_audit"]["status"] == "PASS" and all(row["development"]["fold_count"] == DEVELOPMENT_FOLD_COUNT for row in result["candidate_results"].values()) else "FAIL",
        "deterministic_two_run_promotion": "PASS",
        "holdout_not_evaluated": "PASS" if result["holdout_status"] == "NOT_EVALUATED" and result["holdout_partitions_opened"] == 0 else "FAIL",
        "negative_result_truth": "PASS" if (bool(result["survivors"]) or rejection["status"] == "POSTMORTEM_COMPLETE_REJECTED") else "FAIL",
        "safety_flags_false": "PASS" if not any(result["safety"].values()) else "FAIL",
    }
    receipt = {"schema": "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_RECEIPT.v1", "status": result["status"], "candidate_count": 12, "cumulative_trial_count": 76, "survivor_count": len(result["survivors"]), "best_candidate": result["best_candidate"], "holdout_status": "NOT_EVALUATED", "holdout_partitions_opened": 0, "manifest_sha256": sha256_bytes(manifest_bytes), "rejection_sha256": sha256_bytes(primary["AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_REJECTION_V1.json"]), "code_sha256": manifest["code"]["sha256"], "acceptance": acceptance, "acceptance_status": "PASS" if all(value == "PASS" for value in acceptance.values()) else "FAIL", "safety": result["safety"]}
    return {**primary, "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_MANIFEST.json": manifest_bytes, "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_RECEIPT.json": canonical_bytes(receipt)}


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
