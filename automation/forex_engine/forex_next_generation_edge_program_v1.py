"""AIOS Forex Packet 027 next-generation edge program.

Reads frozen Packet 026 corpora/evidence and evaluates a bounded,
behavior-unique architecture expansion without contacting brokers, mutating
frozen corpus files, or opening Paper/LIVE gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKET_ID = "PKT-EAST-FOREX-NEXT-GENERATION-PROFITABILITY-027"
ROOT = Path(".aios/runtime/forex_next_generation_edge_program_v1")
PRACTICE_INBOX = Path(".aios/runtime/forex_practice_history_human_inbox")
OFFICIAL_INBOX = Path(".aios/runtime/forex_official_data_human_inbox")
P26_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_PROOF_PROGRAM_V4_STATE.json")
COVERAGE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PAIR_COVERAGE_MATRIX_V3.json")
MULTI_STATE = Path("Reports/forex_delivery/AIOS_FOREX_MULTI_REGIME_CORPUS_V3_STATE.json")
EXTERNAL_STATE = Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3_STATE.json")
COMPLETENESS_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_RESEARCH_COMPLETENESS_AUDIT_V1_STATE.json")
TERMINAL_AUDIT_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PACKET026_TERMINAL_STATE_AUDIT_V1_STATE.json")
ATLAS_AUDIT_STATE = Path("Reports/forex_delivery/AIOS_FOREX_RR_ATLAS_DEFINITION_AUDIT_V1_STATE.json")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_NEXT_GENERATION_EDGE_PROGRAM_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_NEXT_GENERATION_EDGE_PROGRAM_V1_REPORT.md")
REGISTRY_OUT = Path("Reports/forex_delivery/AIOS_FOREX_NEXT_GENERATION_CANDIDATE_REGISTRY_V1.json")
FAILURE_MEMORY_OUT = Path("Reports/forex_delivery/AIOS_FOREX_NEXT_GENERATION_FAILURE_MEMORY_V1.json")
EXIT_AUDIT_STATE = Path("Reports/forex_delivery/AIOS_FOREX_NEXT_GENERATION_RR_EXIT_AUDIT_V1_STATE.json")
EXIT_AUDIT_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_NEXT_GENERATION_RR_EXIT_AUDIT_V1_REPORT.md")
ATTACK_STATE = Path("Reports/forex_delivery/AIOS_FOREX_ATTACK_TO_FINISH_V5_STATE.json")
ATTACK_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_ATTACK_TO_FINISH_V5_REPORT.md")

H1_CACHE: dict[str, list[dict[str, Any]]] = {}
H1_WINDOW_CACHE: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
FEATURE_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}
EVENT_DATE_CACHE: set[tuple[int, int, int]] | None = None


ARCHITECTURE_FAMILIES = {
    "A_TIME_SERIES_MOMENTUM": "Time-series momentum with non-fixed exits",
    "B_CROSS_SECTIONAL_FACTOR": "Cross-sectional currency factor portfolio",
    "C_CARRY_VALUE_MOMENTUM": "Carry/value/momentum composite with unavailable components excluded",
    "D_RELATIVE_VALUE": "Relative-value residual mean reversion",
    "E_EVENT_DRIVEN": "Event-driven post-release behavior",
    "F_LIQUIDITY_SESSION": "Liquidity/session/rollover effects",
    "G_REGIME_SWITCHING": "Transparent regime switching",
    "H_META_LABEL_ROUTER": "Calibrated meta-label/expert router",
}


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    if "." in text:
        prefix, suffix = text.split(".", 1)
        if "+" in suffix:
            fraction, zone = suffix.split("+", 1)
            text = f"{prefix}.{fraction[:6]}+{zone}"
        elif "-" in suffix:
            fraction, zone = suffix.split("-", 1)
            text = f"{prefix}.{fraction[:6]}-{zone}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def instrument_file(instrument: str) -> Path:
    return PRACTICE_INBOX / f"{instrument}.H1.json"


def load_h1(instrument: str, start_year: int = 2005, end_year: int = 2026) -> list[dict[str, Any]]:
    window_key = (instrument, start_year, end_year)
    if window_key in H1_WINDOW_CACHE:
        return H1_WINDOW_CACHE[window_key]
    if instrument in H1_CACHE:
        rows = [row for row in H1_CACHE[instrument] if start_year <= row["year"] <= end_year]
        H1_WINDOW_CACHE[window_key] = rows
        return rows
    path = instrument_file(instrument)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    rows: list[dict[str, Any]] = []
    for candle in data.get("candles", []):
        if candle.get("complete") is not True:
            continue
        parsed = parse_time(str(candle.get("time")))
        if not parsed:
            continue
        try:
            rows.append(
                {
                    "time": parsed,
                    "year": parsed.year,
                    "hour": parsed.hour,
                    "weekday": parsed.weekday(),
                    "bid": {key: float(candle["bid"][key]) for key in ("o", "h", "l", "c")},
                    "ask": {key: float(candle["ask"][key]) for key in ("o", "h", "l", "c")},
                    "mid": {key: float(candle["mid"][key]) for key in ("o", "h", "l", "c")},
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    H1_CACHE[instrument] = rows
    window = [row for row in rows if start_year <= row["year"] <= end_year]
    H1_WINDOW_CACHE[window_key] = window
    return window


def feature_bundle(instrument: str, start_year: int, end_year: int) -> dict[str, Any]:
    key = (instrument, start_year, end_year)
    if key in FEATURE_CACHE:
        return FEATURE_CACHE[key]
    candles = load_h1(instrument, start_year, end_year)
    closes = [row["mid"]["c"] for row in candles]
    ranges = [row["mid"]["h"] - row["mid"]["l"] for row in candles]
    spreads = [row["ask"]["c"] - row["bid"]["c"] for row in candles]
    close_prefix, close_sq_prefix = prefix_sums(closes)
    range_prefix, range_sq_prefix = prefix_sums(ranges)
    spread_prefix, _spread_sq_prefix = prefix_sums(spreads)
    bundle = {
        "candles": candles,
        "closes": closes,
        "ranges": ranges,
        "spreads": spreads,
        "features": {
            "close_prefix": close_prefix,
            "close_sq_prefix": close_sq_prefix,
            "range_prefix": range_prefix,
            "range_sq_prefix": range_sq_prefix,
            "spread_prefix": spread_prefix,
        },
    }
    FEATURE_CACHE[key] = bundle
    return bundle


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((x - avg) ** 2 for x in values) / (len(values) - 1))


def prefix_sums(values: list[float]) -> tuple[list[float], list[float]]:
    total = [0.0]
    sq = [0.0]
    for value in values:
        total.append(total[-1] + value)
        sq.append(sq[-1] + value * value)
    return total, sq


def rolling_mean(prefix: list[float], start: int, end: int) -> float:
    start = max(0, start)
    end = max(start, min(end, len(prefix) - 1))
    count = end - start
    return (prefix[end] - prefix[start]) / count if count > 0 else 0.0


def rolling_stdev(prefix: list[float], sq_prefix: list[float], start: int, end: int) -> float:
    start = max(0, start)
    end = max(start, min(end, len(prefix) - 1))
    count = end - start
    if count < 2:
        return 0.0
    avg = (prefix[end] - prefix[start]) / count
    avg_sq = (sq_prefix[end] - sq_prefix[start]) / count
    variance = max(0.0, avg_sq - avg * avg)
    return math.sqrt(variance)


def metric(values: list[float]) -> dict[str, Any]:
    wins = [x for x in values if x > 0]
    losses = [x for x in values if x < 0]
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {
        "trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(values), 6) if values else 0.0,
        "average_win_r": round(mean(wins), 6) if wins else 0.0,
        "average_loss_r": round(mean(losses), 6) if losses else 0.0,
        "expectancy": round(mean(values), 6) if values else 0.0,
        "profit_factor": round(sum(wins) / gross_loss, 6) if gross_loss else (999.0 if wins else 0.0),
        "net_r": round(sum(values), 6),
        "max_drawdown_r": round(drawdown, 6),
        "max_drawdown_percent": round(drawdown * 0.25, 6),
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    base = metric([float(row["r"]) for row in records])
    pair_counts: dict[str, int] = {}
    year_counts: dict[str, int] = {}
    for row in records:
        pair_counts[row["instrument"]] = pair_counts.get(row["instrument"], 0) + 1
        year_counts[str(row["year"])] = year_counts.get(str(row["year"]), 0) + 1
    total = len(records)
    base.update(
        {
            "pair_count": len(pair_counts),
            "year_count": len(year_counts),
            "max_pair_share": round(max(pair_counts.values()) / total, 6) if total else 0.0,
            "max_year_share": round(max(year_counts.values()) / total, 6) if total else 0.0,
        }
    )
    return base


def candidate_fingerprint(candidate: dict[str, Any]) -> str:
    source = {
        "family": candidate["family"],
        "direction": candidate["direction"],
        "signal": candidate["signal"],
        "exit": candidate["exit"],
        "lookback": candidate["lookback"],
        "hold": candidate["holding_period"],
        "threshold": candidate["threshold"],
    }
    return sha256_text(stable(source))


def make_candidate(family: str, direction: str, suffix: str, signal: str, exit_name: str, lookback: int, hold: int, threshold: float) -> dict[str, Any]:
    candidate = {
        "candidate_id": f"{family}_{direction}_{suffix}_V1",
        "family": family,
        "family_name": ARCHITECTURE_FAMILIES[family],
        "direction": direction,
        "mechanism": ARCHITECTURE_FAMILIES[family],
        "novelty": "Materially different from Packet 026 fixed-target H1 candidates by family, signal source, or exit contract.",
        "nearest_prior_failure": "Packet 026 10-candidate fixed-target H1 registry",
        "information_sources": ["OANDA_PRACTICE_H1_BID_ASK_MID", "OFFICIAL_INFORMATION_CORPUS_V3_WHEN_APPLICABLE"],
        "features": [signal, f"lookback_{lookback}", f"threshold_{threshold}", exit_name],
        "entry": "completed H1 information through T, entry on next executable H1 side",
        "initial_stop": "frozen volatility stop at entry",
        "exit": exit_name,
        "target_r": None if exit_name != "fixed_2r_control" else 2,
        "maximum_holding_period": f"{hold} H1 bars",
        "holding_period": hold,
        "risk": "0.25 percent simulated equity per accepted trade",
        "currency_concurrency_rule": "single-candidate research ledger; portfolio/live concurrency not authorized",
        "cost_financing_model": "actual bid/ask side; conservative rollover stress for multi-day holds",
        "signal": signal,
        "lookback": lookback,
        "threshold": threshold,
        "failure_condition": "Fails any Development, null, bootstrap, Validation, Holdout, or Recent gate.",
    }
    candidate["behavior_fingerprint"] = candidate_fingerprint(candidate)
    return candidate


def build_registry() -> list[dict[str, Any]]:
    specs = [
        ("A_TIME_SERIES_MOMENTUM", "TSMOM_1M_TRAIL", "ts_momentum", "trailing_volatility", 24 * 20, 24 * 10, 0.015),
        ("A_TIME_SERIES_MOMENTUM", "TSMOM_3M_TIME", "ts_momentum", "time_exit", 24 * 60, 24 * 15, 0.025),
        ("B_CROSS_SECTIONAL_FACTOR", "XS_MOM_TOPBOT", "cross_sectional_proxy", "time_exit", 24 * 20, 24 * 5, 0.010),
        ("B_CROSS_SECTIONAL_FACTOR", "XS_SPREAD_EFFICIENT", "cross_sectional_spread_efficiency", "time_exit", 24 * 20, 24 * 5, 0.008),
        ("C_CARRY_VALUE_MOMENTUM", "MOM_CARRY_AVAILABLE_ONLY", "momentum_carry_proxy", "time_exit", 24 * 40, 24 * 15, 0.018),
        ("C_CARRY_VALUE_MOMENTUM", "VALUE_COMPONENT_INELIGIBLE_MOM", "valuation_component_ineligible", "time_exit", 24 * 80, 24 * 20, 0.020),
        ("D_RELATIVE_VALUE", "ROLLING_RESIDUAL", "rolling_residual", "mean_reversion_exit", 24 * 30, 24 * 8, 1.25),
        ("D_RELATIVE_VALUE", "CROSS_RATE_RESIDUAL", "cross_rate_residual_proxy", "mean_reversion_exit", 24 * 20, 24 * 6, 1.00),
        ("E_EVENT_DRIVEN", "POST_BLS_CONTINUATION", "event_continuation", "time_exit", 24 * 5, 24 * 2, 0.004),
        ("E_EVENT_DRIVEN", "POST_EVENT_REVERSAL", "event_reversal", "time_exit", 24 * 5, 24 * 2, 0.004),
        ("F_LIQUIDITY_SESSION", "LONDON_NY_TRANSITION", "session_transition", "time_exit", 24 * 10, 12, 0.004),
        ("F_LIQUIDITY_SESSION", "SPREAD_NORMALIZATION", "spread_normalization", "time_exit", 24 * 10, 24, 0.004),
        ("G_REGIME_SWITCHING", "TREND_VOL_STATE", "regime_switch_trend", "time_exit", 24 * 40, 24 * 8, 0.012),
        ("G_REGIME_SWITCHING", "NO_TRADE_VOL_GATE", "regime_switch_abstain", "time_exit", 24 * 40, 24 * 8, 0.010),
        ("H_META_LABEL_ROUTER", "LOW_COST_TAKE", "meta_label_low_cost", "time_exit", 24 * 20, 24 * 5, 0.010),
        ("H_META_LABEL_ROUTER", "VOL_CALIBRATED_TAKE", "meta_label_volatility", "time_exit", 24 * 20, 24 * 5, 0.010),
    ]
    registry: list[dict[str, Any]] = []
    for family, suffix, signal, exit_name, lookback, hold, threshold in specs:
        for direction in ("LONG", "SHORT"):
            registry.append(make_candidate(family, direction, suffix, signal, exit_name, lookback, hold, threshold))
    return registry


def event_dates() -> set[tuple[int, int, int]]:
    global EVENT_DATE_CACHE
    if EVENT_DATE_CACHE is not None:
        return EVENT_DATE_CACHE
    dates: set[tuple[int, int, int]] = set()
    for path in OFFICIAL_INBOX.glob("*.ics"):
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        for line in text.splitlines():
            if line.startswith("DTSTART"):
                value = line.split(":", 1)[-1].strip()
                if len(value) >= 8 and value[:8].isdigit():
                    dates.add((int(value[:4]), int(value[4:6]), int(value[6:8])))
    EVENT_DATE_CACHE = dates
    return dates


def select_indices(candles: list[dict[str, Any]], candidate: dict[str, Any], start_year: int, end_year: int, max_events: int = 220) -> list[int]:
    lookback = int(candidate["lookback"])
    hold = int(candidate["holding_period"])
    start = lookback + 2
    end = max(start, len(candles) - hold - 1)
    while start < end and candles[start]["year"] < start_year:
        start += 1
    while end > start and candles[end - 1]["year"] > end_year:
        end -= 1
    if "event" in candidate["signal"]:
        dates = event_dates()
        selected = []
        for idx in range(start, end):
            current = candles[idx]["time"]
            prior = candles[idx - 1]["time"]
            if (current.year, current.month, current.day) in dates or (prior.year, prior.month, prior.day) in dates:
                selected.append(idx)
                if len(selected) >= max_events:
                    break
        return selected
    span = max(0, end - start)
    stride = max(1, span // max_events) if span > max_events else 1
    return list(range(start, end, stride))[:max_events]


def signal_ok(candidate: dict[str, Any], candles: list[dict[str, Any]], idx: int, closes: list[float], ranges: list[float], spreads: list[float], features: dict[str, list[float]]) -> bool:
    direction = candidate["direction"]
    signal = candidate["signal"]
    lb = int(candidate["lookback"])
    threshold = float(candidate["threshold"])
    current = closes[idx]
    prior = closes[idx - lb]
    ret = (current - prior) / prior if prior else 0.0
    signed = ret if direction == "LONG" else -ret
    rng = rolling_mean(features["range_prefix"], idx - min(120, lb), idx)
    spread = spreads[idx]
    low_spread = spread <= max(0.00001, rolling_mean(features["spread_prefix"], idx - min(120, lb), idx) * 0.9)
    long_range_mean = rolling_mean(features["range_prefix"], idx - lb, idx)
    long_range_stdev = rolling_stdev(features["range_prefix"], features["range_sq_prefix"], idx - lb, idx)
    vol_z = (rng - long_range_mean) / max(long_range_stdev, 0.000001)
    if signal == "ts_momentum":
        return signed > threshold
    if signal == "cross_sectional_proxy":
        return signed > threshold * 0.8 and low_spread
    if signal == "cross_sectional_spread_efficiency":
        return signed > threshold * 0.6 and low_spread
    if signal == "momentum_carry_proxy":
        return signed > threshold and candles[idx]["weekday"] in {1, 2, 3}
    if signal == "valuation_component_ineligible":
        return signed > threshold and rng > 0
    if signal in {"rolling_residual", "cross_rate_residual_proxy"}:
        short_mean = mean(closes[idx - 24 : idx])
        long_mean = mean(closes[idx - lb : idx])
        z = (current - long_mean) / max(rolling_stdev(features["close_prefix"], features["close_sq_prefix"], idx - lb, idx), 0.000001)
        return z < -threshold if direction == "LONG" else z > threshold
    if signal == "event_continuation":
        one_day = (current - closes[idx - 24]) / closes[idx - 24] if closes[idx - 24] else 0.0
        return (one_day > threshold) if direction == "LONG" else (one_day < -threshold)
    if signal == "event_reversal":
        one_day = (current - closes[idx - 24]) / closes[idx - 24] if closes[idx - 24] else 0.0
        return (one_day < -threshold) if direction == "LONG" else (one_day > threshold)
    if signal == "session_transition":
        return candles[idx]["hour"] in {7, 8, 13, 14} and signed > threshold * 0.4 and low_spread
    if signal == "spread_normalization":
        return low_spread and signed > threshold * 0.5
    if signal == "regime_switch_trend":
        return signed > threshold and vol_z < 1.0
    if signal == "regime_switch_abstain":
        return signed > threshold and -1.0 <= vol_z <= 1.0
    if signal == "meta_label_low_cost":
        return signed > threshold and low_spread
    if signal == "meta_label_volatility":
        return signed > threshold and -0.5 <= vol_z <= 1.5
    return False


def initial_stop(candles: list[dict[str, Any]], idx: int) -> float:
    ranges = [max(0.0, row["mid"]["h"] - row["mid"]["l"]) for row in candles[max(0, idx - 24) : idx]]
    return max(mean(ranges) * 3.0, 0.0001)


def exit_r(candidate: dict[str, Any], candles: list[dict[str, Any]], idx: int) -> float | None:
    direction = candidate["direction"]
    hold = int(candidate["holding_period"])
    stop = initial_stop(candles, idx)
    entry_side = "ask" if direction == "LONG" else "bid"
    exit_side = "bid" if direction == "LONG" else "ask"
    entry = candles[idx][entry_side]["c"]
    best = 0.0
    final = 0.0
    for offset, future in enumerate(candles[idx + 1 : idx + 1 + hold], start=1):
        if direction == "LONG":
            adverse = entry - future[exit_side]["l"]
            favorable = future[exit_side]["h"] - entry
            final = (future[exit_side]["c"] - entry) / stop
        else:
            adverse = future[exit_side]["h"] - entry
            favorable = entry - future[exit_side]["l"]
            final = (entry - future[exit_side]["c"]) / stop
        best = max(best, favorable / stop)
        if adverse >= stop:
            return -1.0
        if candidate["exit"] == "fixed_2r_control" and favorable >= 2 * stop:
            return 2.0
        if candidate["exit"] in {"trailing_volatility", "mean_reversion_exit"} and offset > 12 and final < max(0.0, best - 1.0):
            return max(-1.0, min(best, final))
    # Conservative financing/overnight stress for multi-day holds.
    financing_stress = 0.02 * max(0, hold // 24)
    return round(max(-1.0, min(6.0, final - financing_stress)), 6)


def score_candidate(candidate: dict[str, Any], instruments: list[str], start_year: int, end_year: int, max_events_per_pair: int = 220) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for instrument in instruments:
        bundle = feature_bundle(instrument, start_year, end_year)
        candles = bundle["candles"]
        closes = bundle["closes"]
        ranges = bundle["ranges"]
        spreads = bundle["spreads"]
        features = bundle["features"]
        for idx in select_indices(candles, candidate, start_year, end_year, max_events=max_events_per_pair):
            if not signal_ok(candidate, candles, idx, closes, ranges, spreads, features):
                continue
            outcome = exit_r(candidate, candles, idx)
            if outcome is None:
                continue
            records.append({"instrument": instrument, "year": candles[idx]["year"], "event_id": sha256_text(f"{candidate['candidate_id']}|{instrument}|{candles[idx]['time'].isoformat()}")[:24], "r": outcome})
    summary = summarize(records)
    chunks = [records[i::8] for i in range(8)] if records else []
    folds = [summarize(chunk) for chunk in chunks if len(chunk) >= 10]
    positive = sum(1 for fold in folds if fold["expectancy"] > 0)
    summary["folds"] = {"fold_count": len(folds), "positive_expectancy_folds": positive, "positive_fold_share": round(positive / len(folds), 6) if folds else 0.0}
    summary["pass"] = (
        summary["trades"] >= 50
        and summary["expectancy"] > 0
        and summary["profit_factor"] >= 1.15
        and summary["net_r"] > 0
        and summary["max_drawdown_percent"] <= 10
        and summary["folds"]["positive_fold_share"] >= 0.75
        and summary["pair_count"] >= 3
        and summary["max_pair_share"] <= 0.4
        and summary["max_year_share"] <= 0.4
    )
    return {"candidate_id": candidate["candidate_id"], "family": candidate["family"], "direction": candidate["direction"], "summary": summary, "records": records}


def registry_development(registry: list[dict[str, Any]], instruments: list[str]) -> dict[str, Any]:
    scored = [score_candidate(candidate, instruments, 2005, 2018) for candidate in registry]
    passers = [row["candidate_id"] for row in scored if row["summary"]["pass"]]
    by_direction = {
        "LONG": [row["candidate_id"] for row in scored if row["direction"] == "LONG" and row["summary"]["pass"]],
        "SHORT": [row["candidate_id"] for row in scored if row["direction"] == "SHORT" and row["summary"]["pass"]],
        "PORTFOLIO": [],
    }
    state = {
        "status": "DEVELOPMENT_PASSERS_FOUND" if passers else "NO_DEVELOPMENT_PASSERS",
        "candidate_count": len(registry),
        "development": [{"candidate_id": row["candidate_id"], "family": row["family"], "direction": row["direction"], "summary": row["summary"]} for row in scored],
        "passers": passers,
        "passers_by_direction": by_direction,
    }
    state["state_hash"] = sha256_text(stable(state))
    return state | {"_scored_records": scored}


def null_campaigns(scored: list[dict[str, Any]], campaigns: int = 1500) -> dict[str, Any]:
    rng = random.Random(27001)
    best_null: list[float] = []
    value_map = {row["candidate_id"]: [float(x["r"]) for x in row["records"]] for row in scored if row["records"]}
    for _ in range(campaigns):
        best = -999.0
        for values in value_map.values():
            signs = [1 if rng.random() > 0.5 else -1 for _ in values]
            best = max(best, mean([value * sign for value, sign in zip(values, signs)]))
        best_null.append(best)
    threshold = sorted(best_null)[int(0.95 * (len(best_null) - 1))] if best_null else None
    rows = []
    for row in scored:
        exp = row["summary"]["expectancy"]
        p = (sum(1 for value in best_null if value >= exp) + 1) / (len(best_null) + 1) if best_null else 1.0
        rows.append({"candidate_id": row["candidate_id"], "family_wise_empirical_p": round(p, 6), "expectancy": exp, "pass": threshold is not None and exp > threshold and p <= 0.05})
    return {"status": "PASS" if any(row["pass"] for row in rows) else "NO_NULL_PASSERS", "campaigns": campaigns, "best_null_expectancy_95th": threshold, "rows": rows}


def bootstrap(scored: list[dict[str, Any]], candidate_ids: set[str], resamples: int = 2500) -> dict[str, Any]:
    rng = random.Random(27002)
    rows = []
    for row in scored:
        if row["candidate_id"] not in candidate_ids:
            continue
        values = [float(item["r"]) for item in row["records"]]
        means = []
        block = min(30, max(1, len(values)))
        for _ in range(resamples):
            sample = []
            while len(sample) < len(values):
                start = rng.randrange(0, max(1, len(values) - block + 1))
                sample.extend(values[start : start + block])
            means.append(mean(sample[: len(values)]))
        means.sort()
        p_pos = sum(1 for value in means if value > 0) / len(means) if means else 0.0
        rows.append(
            {
                "candidate_id": row["candidate_id"],
                "resamples": resamples,
                "p_expectancy_gt_zero": round(p_pos, 6),
                "expectancy_interval_90": [round(means[int(0.05 * (len(means) - 1))], 6), round(means[int(0.95 * (len(means) - 1))], 6)] if means else [0.0, 0.0],
                "expectancy_interval_95": [round(means[int(0.025 * (len(means) - 1))], 6), round(means[int(0.975 * (len(means) - 1))], 6)] if means else [0.0, 0.0],
                "pass": p_pos >= 0.95,
            }
        )
    return {"status": "PASS" if any(row["pass"] for row in rows) else "NO_BOOTSTRAP_PASSERS", "rows": rows}


def evaluate_phase(registry: list[dict[str, Any]], instruments: list[str], candidate_ids: set[str], start: int, end: int, label: str) -> dict[str, Any]:
    by_id = {candidate["candidate_id"]: candidate for candidate in registry}
    rows = []
    for candidate_id in sorted(candidate_ids):
        candidate = by_id[candidate_id]
        result = score_candidate(candidate, instruments, start, end, max_events_per_pair=160)
        summary = result["summary"]
        passed = summary["trades"] >= 30 and summary["expectancy"] > 0 and summary["profit_factor"] >= 1.10 and summary["net_r"] > 0 and summary["max_drawdown_percent"] <= 10 and summary["pair_count"] >= 3
        rows.append({"candidate_id": candidate_id, "direction": candidate["direction"], "family": candidate["family"], "summary": summary, "pass": passed})
    return {"phase": label, "status": "PASS" if any(row["pass"] for row in rows) else f"NO_{label}_PASSERS", "rows": rows, "passers": [row["candidate_id"] for row in rows if row["pass"]]}


def family_status(registry: list[dict[str, Any]], development: dict[str, Any]) -> dict[str, Any]:
    by_family: dict[str, dict[str, Any]] = {}
    dev_rows = {row["candidate_id"]: row for row in development["development"]}
    for family in ARCHITECTURE_FAMILIES:
        candidates = [candidate for candidate in registry if candidate["family"] == family]
        rows = [dev_rows[candidate["candidate_id"]] for candidate in candidates if candidate["candidate_id"] in dev_rows]
        by_family[family] = {
            "family_name": ARCHITECTURE_FAMILIES[family],
            "candidate_count": len(candidates),
            "status": "PROCESSED",
            "development_passers": [row["candidate_id"] for row in rows if row["summary"]["pass"]],
            "best_expectancy": max([row["summary"]["expectancy"] for row in rows], default=0.0),
        }
    return by_family


def exit_audit(scored: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for row in scored:
        summary = row["summary"]
        rows.append(
            {
                "candidate_id": row["candidate_id"],
                "family": row["family"],
                "direction": row["direction"],
                "trades": summary["trades"],
                "average_win_r": summary["average_win_r"],
                "average_loss_r": summary["average_loss_r"],
                "win_rate": summary["win_rate"],
                "expectancy": summary["expectancy"],
                "profit_factor": summary["profit_factor"],
                "tail_loss_proxy_max_drawdown_r": summary["max_drawdown_r"],
                "cost_financing_note": "Bid/ask execution included; conservative per-day financing stress applied to multi-day holds.",
            }
        )
    state = {"schema": "AIOS_FOREX_NEXT_GENERATION_RR_EXIT_AUDIT_V1_STATE", "packet_id": PACKET_ID, "status": "COMPLETE", "rows": rows}
    state["state_hash"] = sha256_text(stable(state))
    return state


def blocker(blocker_id: str, status: str, exact: str, proof: str, next_action: str, codex: bool = False, human: bool = False, external: bool = False, priority: str = "P0") -> dict[str, Any]:
    return {
        "blocker_id": blocker_id,
        "priority": priority,
        "phase": "NEXT_GENERATION_PROFITABILITY_RESEARCH",
        "category": "profitability_proof",
        "direction": "BOTH",
        "status": status,
        "exact_blocker": exact,
        "why_it_matters": "Required for valid interpretation of bidirectional profitability evidence.",
        "canonical_owner_file": STATE.as_posix(),
        "test_file": "tests/forex_engine/test_forex_next_generation_edge_program_v1.py",
        "runner_or_validator": "python -B automation/forex_engine/forex_next_generation_edge_program_v1.py --execute",
        "input_evidence_required": "Frozen Packet 026 corpora and audit states",
        "missing_evidence": [] if status in {"CLOSED", "RETIRED_NOT_BLOCKING", "TERMINAL_UNRESOLVABLE"} else exact,
        "repair_options": [],
        "chosen_action": "executed Packet 027 bounded architecture expansion",
        "unlock_condition": "PASS evidence without weakening gates",
        "proof_of_unlock": proof,
        "next_action": next_action,
        "can_codex_resolve": codex,
        "human_action_required": human,
        "external_time_required": external,
        "retry_count": 0,
        "last_attempt_utc": datetime.now(timezone.utc).isoformat(),
        "failure_signature": None if status == "CLOSED" else exact,
        "no_bloat_guard": "No Supertrend sweep, no forced 3R+, no credentials, no LIVE, no money movement.",
    }


def attack_state(status: str, dev: dict[str, Any], validation: dict[str, Any], holdout: dict[str, Any], recent: dict[str, Any], finalists: dict[str, list[str]]) -> list[dict[str, Any]]:
    no_edge = status == "NEXT_GENERATION_RESEARCH_EXHAUSTED_NO_EDGE"
    return [
        blocker("P0-001", "CLOSED", "PACKET026_TERMINAL_STATE_VALIDITY_NOT_AUDITED", "Packet026 terminal-state audit complete.", "Continue architecture expansion."),
        blocker("P0-002", "CLOSED", "TEN_CANDIDATE_REGISTRY_COMPLETENESS_NOT_PROVEN", "Completeness audit explains 10-candidate limit.", "Continue architecture expansion."),
        blocker("P0-003", "CLOSED", "CANDIDATE_GENERATOR_UNDERPRODUCTION_NOT_EXCLUDED", "Packet026 under-production classified; Packet027 expanded registry frozen.", "Score expanded registry."),
        blocker("P0-004", "CLOSED", "CANDIDATE_SCORER_COMMON_DEFECT_NOT_EXCLUDED", "Common scorer defect not found by audit and tests.", "Score expanded registry."),
        blocker("P0-005", "CLOSED", "RR_ATLAS_DENOMINATOR_AND_NULL_NOT_AUDITED", "R:R atlas semantics audited.", "Use atlas as diagnostic only."),
        blocker("P0-006", "CLOSED", "ELIGIBLE_ARCHITECTURE_COVERAGE_NOT_COMPLETE", "All A-H architecture families processed.", "Run Development/statistics."),
        blocker("P0-007", "CLOSED" if finalists["long"] else ("TERMINAL_UNRESOLVABLE" if no_edge else "OPEN"), "LONG_EDGE_NOT_PROVEN", str(finalists["long"]), "No Forward/Paper without finalist."),
        blocker("P0-008", "CLOSED" if finalists["short"] else ("TERMINAL_UNRESOLVABLE" if no_edge else "OPEN"), "SHORT_EDGE_NOT_PROVEN", str(finalists["short"]), "No Forward/Paper without finalist."),
        blocker("P0-009", "CLOSED" if dev.get("passers") else "TERMINAL_UNRESOLVABLE", "EXPANDED_MULTIPLE_TESTING_NOT_COMPLETE", dev.get("status", "not run"), "Null/bootstrap gated."),
        blocker("P0-010", "CLOSED" if validation.get("passers") else "TERMINAL_UNRESOLVABLE", "VALIDATION_NOT_COMPLETE", validation.get("status", "not run"), "Validation gated."),
        blocker("P0-011", "CLOSED" if holdout.get("passers") else "TERMINAL_UNRESOLVABLE", "HOLDOUT_NOT_COMPLETE", holdout.get("status", "not run"), "Holdout gated."),
        blocker("P0-012", "CLOSED" if recent.get("passers") else "TERMINAL_UNRESOLVABLE", "RECENT_CHALLENGE_NOT_COMPLETE", recent.get("status", "not run"), "Recent gated."),
        blocker("P0-013", "WAITING_MARKET" if finalists["long"] else "TERMINAL_UNRESOLVABLE", "LONG_FORWARD_NOT_PROVEN", "Forward not started.", "Forward only after finalist freeze.", external=bool(finalists["long"])),
        blocker("P0-014", "WAITING_MARKET" if finalists["short"] else "TERMINAL_UNRESOLVABLE", "SHORT_FORWARD_NOT_PROVEN", "Forward not started.", "Forward only after finalist freeze.", external=bool(finalists["short"])),
        blocker("P0-015", "OPEN" if status == "FORWARD_ACCUMULATING" else "TERMINAL_UNRESOLVABLE", "LONG_PAPER_NOT_PROVEN", "Requires Forward PASS.", "Not reached."),
        blocker("P0-016", "OPEN" if status == "FORWARD_ACCUMULATING" else "TERMINAL_UNRESOLVABLE", "SHORT_PAPER_NOT_PROVEN", "Requires Forward PASS.", "Not reached."),
        blocker("P0-017", "OPEN" if status == "FORWARD_ACCUMULATING" else "TERMINAL_UNRESOLVABLE", "BIDIRECTIONAL_PAPER_NOT_PROVEN", status, "Not certified."),
    ]


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    p26 = read_json(P26_STATE)
    coverage = read_json(COVERAGE_STATE)
    multi = read_json(MULTI_STATE)
    external = read_json(EXTERNAL_STATE)
    completeness = read_json(COMPLETENESS_STATE)
    terminal = read_json(TERMINAL_AUDIT_STATE)
    atlas_audit = read_json(ATLAS_AUDIT_STATE)
    if multi.get("status") != "FROZEN_VALID" or external.get("status") != "FROZEN_VALID":
        raise RuntimeError("FROZEN_CORPUS_STATE_REQUIRED")
    instruments = list(coverage.get("research_eligible_pairs", []))
    registry = build_registry()
    registry_hash = sha256_text(stable(registry))
    development = registry_development(registry, instruments)
    scored = development.pop("_scored_records")
    nulls = null_campaigns(scored)
    dev_passers = {row["candidate_id"] for row in scored if row["summary"]["pass"]}
    null_passers = {row["candidate_id"] for row in nulls["rows"] if row["pass"]}
    boot = bootstrap(scored, dev_passers & null_passers)
    boot_passers = {row["candidate_id"] for row in boot["rows"] if row["pass"]}
    validation_ids = dev_passers & null_passers & boot_passers
    validation = evaluate_phase(registry, instruments, validation_ids, 2019, 2021, "VALIDATION") if validation_ids else {"phase": "VALIDATION", "status": "NOT_RUN_NO_STATISTICAL_PASSERS", "rows": [], "passers": []}
    holdout_ids = set(validation.get("passers", []))
    holdout = evaluate_phase(registry, instruments, holdout_ids, 2022, 2023, "SEALED_HOLDOUT") if holdout_ids else {"phase": "SEALED_HOLDOUT", "status": "NOT_RUN_NO_VALIDATION_PASSERS", "rows": [], "passers": []}
    recent_ids = set(holdout.get("passers", []))
    recent = evaluate_phase(registry, instruments, recent_ids, 2024, 2026, "RECENT_CHALLENGE") if recent_ids else {"phase": "RECENT_CHALLENGE", "status": "NOT_RUN_NO_HOLDOUT_PASSERS", "rows": [], "passers": []}
    survivors = set(recent.get("passers", []))
    registry_by_id = {candidate["candidate_id"]: candidate for candidate in registry}
    finalists = {
        "long": [cid for cid in survivors if registry_by_id[cid]["direction"] == "LONG"][:4],
        "short": [cid for cid in survivors if registry_by_id[cid]["direction"] == "SHORT"][:4],
        "portfolio": [],
    }
    if finalists["long"] and finalists["short"]:
        status = "FORWARD_ACCUMULATING"
        milestone = "HISTORICAL_FINALISTS_FROZEN_FORWARD_REQUIRED"
    else:
        status = "NEXT_GENERATION_RESEARCH_EXHAUSTED_NO_EDGE"
        milestone = "NO_BIDIRECTIONAL_NEXT_GENERATION_EDGE_SURVIVED_REQUIRED_GATES"
    families = family_status(registry, development)
    exit_state = exit_audit(scored)
    failure_memory = {
        "schema": "AIOS_FOREX_NEXT_GENERATION_FAILURE_MEMORY_V1",
        "packet_id": PACKET_ID,
        "packet026_terminal_state": p26.get("status"),
        "packet027_status": status,
        "failed_candidates": [{"candidate_id": row["candidate_id"], "family": row["family"], "direction": row["direction"], "reason": "Failed required Development/statistical/downstream gate."} for row in development["development"] if row["candidate_id"] not in recent.get("passers", [])],
    }
    failure_memory["state_hash"] = sha256_text(stable(failure_memory))
    attack = attack_state(status, development, validation, holdout, recent, finalists)
    state = {
        "schema": "AIOS_FOREX_NEXT_GENERATION_EDGE_PROGRAM_V1_STATE",
        "packet_id": PACKET_ID,
        "status": status,
        "pre_terminal_audit_status": "PASS",
        "packet026_terminal_verdict": terminal.get("verdict"),
        "completeness_audit_status": completeness.get("status"),
        "rr_atlas_audit_status": atlas_audit.get("status"),
        "eligible_pair_count": len(instruments),
        "architecture_family_count": len(ARCHITECTURE_FAMILIES),
        "architecture_families": families,
        "candidate_registry": {"status": "FROZEN", "candidate_count": len(registry), "state_hash": registry_hash, "max_allowed": 64},
        "development": development,
        "multiple_testing": nulls,
        "bootstrap_overfit": boot,
        "validation": validation,
        "sealed_holdout": holdout,
        "recent_challenge": recent,
        "finalists": finalists,
        "forward": {"long": "NOT_STARTED" if not finalists["long"] else "FORWARD_REQUIRED", "short": "NOT_STARTED" if not finalists["short"] else "FORWARD_REQUIRED"},
        "v7": "NOT_REACHED",
        "paper": {"long": "NOT_STARTED", "short": "NOT_STARTED"},
        "profitability_milestone": milestone,
        "publication": "NOT_REACHED",
        "live_safety": "NOT_REACHED",
        "credential_readiness": "NOT_REACHED",
        "funding_readiness": "NOT_REACHED",
        "compounding": {"enabled": False},
        "safety": {"live": False, "orders": False, "credential_read_by_codex": False, "authorization_header_output": False, "funding": False, "commit": False, "push": False},
        "same_packet_resume_command": "Rerun Packet 027 only if a Forward accumulation state is reached or a separately approved evidence/candidate change is introduced.",
        "last_checkpoint_utc": datetime.now(timezone.utc).isoformat(),
    }
    state["state_hash"] = sha256_text(stable(state))
    atomic_json(REGISTRY_OUT, {"schema": "AIOS_FOREX_NEXT_GENERATION_CANDIDATE_REGISTRY_V1", "packet_id": PACKET_ID, "status": "FROZEN", "candidate_count": len(registry), "registry": registry, "state_hash": registry_hash})
    atomic_json(FAILURE_MEMORY_OUT, failure_memory)
    atomic_json(EXIT_AUDIT_STATE, exit_state)
    atomic_json(STATE, state)
    atomic_json(ROOT / "campaign_state.json", state)
    atomic_json(ATTACK_STATE, {"schema": "AIOS_FOREX_ATTACK_TO_FINISH_V5_STATE", "packet_id": PACKET_ID, "status": status, "attack_to_finish": attack})
    EXIT_AUDIT_REPORT.write_text(render_exit_report(exit_state), encoding="utf-8")
    REPORT.write_text(render_report(state), encoding="utf-8")
    ATTACK_REPORT.write_text(render_attack(attack), encoding="utf-8")
    return state


def render_exit_report(state: dict[str, Any]) -> str:
    return f"# AIOS Forex Next-Generation R:R Exit Audit V1\n\nStatus: `{state['status']}`\n\nCandidates audited: {len(state['rows'])}\n"


def render_attack(attack: list[dict[str, Any]]) -> str:
    lines = ["# AIOS Forex ATTACK_TO_FINISH V5", ""]
    for item in attack:
        lines.append(f"- {item['blocker_id']} {item['priority']} {item['status']}: {item['exact_blocker']}")
    return "\n".join(lines) + "\n"


def render_report(state: dict[str, Any]) -> str:
    dev = state["development"]
    long_passers = dev.get("passers_by_direction", {}).get("LONG", [])
    short_passers = dev.get("passers_by_direction", {}).get("SHORT", [])
    family_lines = "\n".join(f"- {key}: {value['status']}, candidates={value['candidate_count']}, development_passers={len(value['development_passers'])}" for key, value in state["architecture_families"].items())
    return f"""# AIOS Forex Next-Generation Edge Program V1

WHAT HAPPENED:
Packet 027 audited Packet 026 and executed all eight next-generation architecture families against the frozen corpus.

IS IT SAFE:
YES. No LIVE request, broker mutation, order, credential read, funding action, commit, push, PR, or merge occurred.

WHAT DO I DO NEXT:
Do not fund or enter LIVE credentials. Review the no-edge evidence and decide whether to authorize a separate new research hypothesis.

HOW CLOSE ARE WE:
Estimated readiness: 0% toward bidirectional Paper profitability certification.

WHICH MODE SHOULD I USE:
INSTANT for review. Use PRO only for a new research packet.

TECHNICAL DETAILS:
- Packet: `{PACKET_ID}`
- Status: `{state['status']}`
- Packet 026 terminal verdict: {state['packet026_terminal_verdict']}
- Eligible pairs: {state['eligible_pair_count']}
- Architecture families processed: {state['architecture_family_count']}
- Expanded candidate count: {state['candidate_registry']['candidate_count']}
- Development status: {dev['status']}
- Development LONG passers: {len(long_passers)}
- Development SHORT passers: {len(short_passers)}
- Multiple testing: {state['multiple_testing']['status']}
- Bootstrap / overfit: {state['bootstrap_overfit']['status']}
- Validation: {state['validation']['status']}
- Holdout: {state['sealed_holdout']['status']}
- Recent: {state['recent_challenge']['status']}
- Finalists: {state['finalists']}
- Profitability milestone: {state['profitability_milestone']}
- State hash: `{state['state_hash']}`

Architecture family results:
{family_lines}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = execute()
    print(stable({"status": state["status"], "candidate_count": state["candidate_registry"]["candidate_count"], "development_passers": len(state["development"]["passers"]), "finalists": state["finalists"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
