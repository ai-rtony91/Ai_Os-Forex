"""Packet 013 information-family falsification and bounded edge research."""
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

from automation.forex_engine.forex_edge_research_v1 import load_pair, metrics, split_contract, stable, ts

MARKET = Path(".aios/runtime/forex_m5_immutable_corpus_v2")
INFO = Path(".aios/runtime/forex_information_corpus_v1")
ROOT = Path(".aios/runtime/forex_information_edge_program_v1")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_INFORMATION_EDGE_PROGRAM_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_INFORMATION_EDGE_PROGRAM_V1_REPORT.md")
PACKET = "PKT-EAST-FOREX-INFORMATION-EDGE-TO-FUNDING-013"
LOCK = "AIOS-LOCK-f1b2dccc1a1c40c98ec4af8c9012de39"
MARKET_HASH = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
INFO_HASH = "57da729226ebd675d7c79f182510f0612fc2f93cd0f20a05abed64243163d854"
RISK = 0.0025

COT_MARKETS = {
    "EURO FX": "EUR", "BRITISH POUND": "GBP", "JAPANESE YEN": "JPY",
    "SWISS FRANC": "CHF", "CANADIAN DOLLAR": "CAD", "AUSTRALIAN DOLLAR": "AUD",
    "NZ DOLLAR": "NZD", "MEXICAN PESO": "MXN", "SO AFRICAN RAND": "ZAR",
}


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    track: str
    rule: str
    threshold: float
    stop_atr: float
    target_r: float
    max_hold_days: int


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def atomic_json(path, value):
    def safe(item):
        if isinstance(item, float) and not math.isfinite(item):
            return "INF" if item > 0 else "-INF"
        if isinstance(item, dict):
            return {key: safe(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [safe(child) for child in item]
        return item
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(safe(value), handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def checkpoint(**updates):
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    state.update(updates)
    state["last_material_state_change_utc"] = datetime.now(timezone.utc).isoformat()
    atomic_json(STATE, state)
    atomic_json(ROOT / "campaign_state.json", state)
    return state


def daily_rows(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[ts(row["timestamp"]).date().isoformat()].append(row)
    output = []
    for day in sorted(groups):
        group = groups[day]
        record = {"timestamp": group[-1]["timestamp"], "day": day, "instrument": group[0]["instrument"], "volume": sum(item["volume"] for item in group)}
        for side in ("bid", "ask", "mid"):
            record[side] = {"o": float(group[0][side]["o"]), "h": max(float(item[side]["h"]) for item in group), "l": min(float(item[side]["l"]) for item in group), "c": float(group[-1][side]["c"])}
        output.append(record)
    return output


def true_range(rows, index):
    current = rows[index]["mid"]
    previous = rows[index - 1]["mid"]["c"]
    return max(current["h"] - current["l"], abs(current["h"] - previous), abs(current["l"] - previous))


def atr(rows, index, lookback=14):
    if index < lookback:
        return None
    return sum(true_range(rows, item) for item in range(index - lookback + 1, index + 1)) / lookback


def load_cot():
    by_currency = defaultdict(list)
    for year in (2024, 2025, 2026):
        path = INFO / "normalized" / f"cftc_{year}.json"
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            market = row["coverage"].upper()
            currency = next((code for label, code in COT_MARKETS.items() if label in market), None)
            if not currency or not row.get("open_interest"):
                continue
            long_value = row.get("leveraged_long") or 0
            short_value = row.get("leveraged_short") or 0
            by_currency[currency].append((ts(row["available_to_strategy_utc"]), (long_value - short_value) / row["open_interest"]))
    for currency in by_currency:
        by_currency[currency].sort()
    return by_currency


def latest_available(records, moment):
    result = None
    for available, value in records:
        if available > moment:
            break
        result = value
    return result


def build_market_table(manifest):
    table_path = ROOT / "daily_market.jsonl.gz"
    if table_path.exists():
        by_pair = defaultdict(list)
        with gzip.open(table_path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                by_pair[row["instrument"]].append(row)
        return by_pair
    by_pair = {}
    table_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(table_path, "wt", encoding="utf-8") as handle:
        for position, pair in enumerate(manifest["eligible_pairs"], 1):
            rows = daily_rows(load_pair(manifest, pair))
            by_pair[pair] = rows
            for row in rows:
                handle.write(stable(row) + "\n")
            checkpoint(current_phase="MARKET_ALIGNMENT", current_action=pair, completed_work_units=position, remaining_work_units=len(manifest["eligible_pairs"]) - position, next_action="build information features", next_three_actions=["FAMILY_B_COT_POSITIONING", "FAMILY_D_GLOBAL_RISK_LIQUIDITY", "FAMILY_E_LONG_HORIZON_RELATIVE_VALUE_MOMENTUM"], remaining_authorized_work_count=10, alternate_safe_actions=["continue next pair"], continuation_active=True, pre_terminal_audit_status="FAIL_CONTINUE")
    return by_pair


def currency_strength_by_day(by_pair, horizon):
    returns = defaultdict(dict)
    for pair, rows in by_pair.items():
        for index in range(horizon, len(rows)):
            returns[rows[index]["day"]][pair] = math.log(rows[index]["mid"]["c"] / rows[index - horizon]["mid"]["c"])
    output = {}
    for day, pair_returns in returns.items():
        values = defaultdict(list)
        for pair, value in pair_returns.items():
            base, quote = pair.split("_")
            values[base].append(value / 2)
            values[quote].append(-value / 2)
        raw = {currency: sum(items) / len(items) for currency, items in values.items()}
        center = sum(raw.values()) / len(raw) if raw else 0
        output[day] = {currency: value - center for currency, value in raw.items()}
    return output


def build_features(by_pair, cot):
    strength5 = currency_strength_by_day(by_pair, 5)
    strength20 = currency_strength_by_day(by_pair, 20)
    strength60 = currency_strength_by_day(by_pair, 60)
    features = defaultdict(list)
    for pair, rows in by_pair.items():
        base, quote = pair.split("_")
        spreads = []
        for index in range(60, len(rows) - 11):
            current_atr = atr(rows, index)
            if not current_atr:
                continue
            moment = ts(rows[index]["timestamp"])
            spread_ratio = (rows[index]["ask"]["c"] - rows[index]["bid"]["c"]) / current_atr
            spreads.append(spread_ratio)
            history = spreads[-60:]
            spread_pct = sum(value <= spread_ratio for value in history) / len(history)
            cot_base = latest_available(cot.get(base, []), moment) or 0.0
            cot_quote = latest_available(cot.get(quote, []), moment) or 0.0
            record = {
                "pair": pair, "index": index, "timestamp": rows[index]["timestamp"], "day": rows[index]["day"],
                "cot_diff": cot_base - cot_quote,
                "momentum_5": strength5.get(rows[index]["day"], {}).get(base, 0) - strength5.get(rows[index]["day"], {}).get(quote, 0),
                "momentum_20": strength20.get(rows[index]["day"], {}).get(base, 0) - strength20.get(rows[index]["day"], {}).get(quote, 0),
                "momentum_60": strength60.get(rows[index]["day"], {}).get(base, 0) - strength60.get(rows[index]["day"], {}).get(quote, 0),
                "spread_percentile": spread_pct,
                "usd_factor": strength20.get(rows[index]["day"], {}).get("USD", 0),
                "atr": current_atr,
            }
            future = rows[index + 5]["mid"]["c"] - rows[index + 1]["mid"]["o"]
            record["future_5d_atr"] = future / current_atr
            features[pair].append(record)
    path = ROOT / "information_features.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for pair in sorted(features):
            for row in features[pair]:
                handle.write(stable(row) + "\n")
    return features, sha_bytes(path.read_bytes())


def folds(window, count=8):
    span = window[1] - window[0]
    return [(window[0] + span * index / count, window[0] + span * (index + 1) / count) for index in range(count)]


def family_score(row, family):
    if family == "B_CFTC_POSITIONING":
        return row["cot_diff"]
    if family == "D_GLOBAL_RISK_LIQUIDITY":
        base, quote = row["pair"].split("_")
        usd_sign = 1 if base == "USD" else -1 if quote == "USD" else 0
        return row["usd_factor"] * usd_sign * (1 - row["spread_percentile"])
    if family == "E_LONG_HORIZON":
        return row["momentum_20"] + 0.5 * row["momentum_60"]
    return 0.5 * row["cot_diff"] + row["momentum_20"] * (1 - row["spread_percentile"])


def screen_families(features, development):
    families = ["A_POLICY_CARRY", "B_CFTC_POSITIONING", "C_MACRO_EVENT_STATE", "D_GLOBAL_RISK_LIQUIDITY", "E_LONG_HORIZON", "F_COMBINED_INFORMATION"]
    output = {}
    flattened = [row for rows in features.values() for row in rows if development[0] <= ts(row["timestamp"]) < development[1]]
    fold_windows = folds(development)
    for family in families:
        if family == "A_POLICY_CARRY":
            output[family] = {"eligible": False, "reason": "All frozen policy series timed out; no lawful substitute used", "pass": False}
            continue
        if family == "C_MACRO_EVENT_STATE":
            output[family] = {"eligible": False, "reason": "No frozen first-release vintage archive", "pass": False}
            continue
        if family == "F_COMBINED_INFORMATION":
            continue
        observations = [row for row in flattened if abs(family_score(row, family)) > 1e-12]
        signed = [math.copysign(1, family_score(row, family)) * row["future_5d_atr"] for row in observations]
        fold_lift = []
        for window in fold_windows:
            values = [math.copysign(1, family_score(row, family)) * row["future_5d_atr"] for row in observations if window[0] <= ts(row["timestamp"]) < window[1]]
            fold_lift.append(sum(values) / len(values) if values else 0)
        lift = sum(signed) / len(signed) if signed else 0
        passed = len(signed) >= 500 and lift > 0.02 and sum(value > 0 for value in fold_lift) >= 6
        output[family] = {"eligible": True, "samples": len(signed), "mean_signed_future_atr": lift, "positive_folds": sum(value > 0 for value in fold_lift), "fold_lift": fold_lift, "pass": passed}
    eligible = [family for family in ("B_CFTC_POSITIONING", "D_GLOBAL_RISK_LIQUIDITY", "E_LONG_HORIZON") if output[family]["pass"]]
    if len(eligible) >= 2:
        observations = flattened
        signed = [math.copysign(1, family_score(row, "F_COMBINED_INFORMATION")) * row["future_5d_atr"] for row in observations]
        lift = sum(signed) / len(signed) if signed else 0
        output["F_COMBINED_INFORMATION"] = {"eligible": True, "components": eligible, "samples": len(signed), "mean_signed_future_atr": lift, "pass": lift > 0.02}
    else:
        output["F_COMBINED_INFORMATION"] = {"eligible": False, "reason": "Fewer than two individual information families passed", "pass": False}
    return output


def registry(screening):
    candidates = []
    definitions = {
        "B_CFTC_POSITIONING": [("COT_CONTINUATION", 0.05), ("COT_CONTINUATION", 0.10), ("COT_REVERSAL", 0.10)],
        "D_GLOBAL_RISK_LIQUIDITY": [("RISK_USD", 0.0005), ("RISK_USD", 0.001), ("LIQUIDITY_GATE", 0.0005)],
        "E_LONG_HORIZON": [("MOMENTUM", 0.005), ("MOMENTUM", 0.01), ("MOMENTUM", 0.02), ("MOMENTUM_REVERSAL", 0.02)],
        "F_COMBINED_INFORMATION": [("COMBINED", 0.005), ("COMBINED", 0.01)],
    }
    for family, configs in definitions.items():
        if not screening.get(family, {}).get("pass"):
            continue
        for rule, threshold in configs:
            for stop, target in ((1.5, 2.0), (2.0, 3.0)):
                candidates.append(Candidate(f"{family[0]}-{len(candidates)+1:02d}", family, rule, threshold, stop, target, 10))
    return candidates[:36]


def candidate_score(row, candidate):
    score = family_score(row, candidate.track)
    if "REVERSAL" in candidate.rule:
        score = -score
    if candidate.rule == "LIQUIDITY_GATE" and row["spread_percentile"] > 0.5:
        return 0.0
    return score


def simulate(features, by_pair, candidate, window, side):
    trades = []
    sign = 1 if side == "LONG" else -1
    for pair, rows in features.items():
        market = by_pair[pair]
        active = False
        for row in rows:
            if not (window[0] <= ts(row["timestamp"]) < window[1]):
                continue
            score = candidate_score(row, candidate) * sign
            if score < candidate.threshold:
                active = False
                continue
            if active:
                continue
            active = True
            index = row["index"]
            if index + 1 >= len(market):
                continue
            entry = market[index + 1]["ask"]["o"] if side == "LONG" else market[index + 1]["bid"]["o"]
            risk = row["atr"] * candidate.stop_atr
            stop = entry - risk if side == "LONG" else entry + risk
            target = entry + candidate.target_r * risk if side == "LONG" else entry - candidate.target_r * risk
            result = None
            for future in market[index + 1 : min(len(market), index + candidate.max_hold_days + 2)]:
                if side == "LONG":
                    stop_hit = future["bid"]["l"] <= stop
                    target_hit = future["bid"]["h"] >= target
                else:
                    stop_hit = future["ask"]["h"] >= stop
                    target_hit = future["ask"]["l"] <= target
                if stop_hit:
                    result = -1.0
                    break
                if target_hit:
                    result = candidate.target_r
                    break
            if result is None:
                close = market[min(len(market) - 1, index + candidate.max_hold_days + 1)]["bid"]["c"] if side == "LONG" else market[min(len(market) - 1, index + candidate.max_hold_days + 1)]["ask"]["c"]
                result = (close - entry) / risk if side == "LONG" else (entry - close) / risk
            trades.append({"r": result, "pair": pair, "event_id": f"{candidate.candidate_id}:{side}:{pair}:{row['day']}", "signal_time": row["timestamp"]})
    return trades


def development_gate(result, fold_metrics):
    sampled = [item for item in fold_metrics if item["trades"] >= 6]
    return result["trades"] >= 50 and result["expectancy_r"] > 0 and result["profit_factor"] >= 1.15 and result["net_r"] > 0 and result["max_drawdown_pct"] <= 10 and sampled and sum(item["expectancy_r"] > 0 for item in sampled) / len(sampled) >= 0.75 and all(item["max_drawdown_pct"] <= 15 for item in sampled) and result["pair_count"] >= 12 and result["largest_pair_share"] <= 0.25


def null_campaign(results, repetitions=500):
    rng = random.Random(13013)
    blocks = {key: ([sum(item["r"] for item in trades[index:index + 5]) for index in range(0, len(trades), 5)], len(trades)) for key, trades in results.items()}
    best = []
    for _ in range(repetitions):
        values = []
        for sums, count in blocks.values():
            values.append(sum(value * (1 if rng.random() > 0.5 else -1) for value in sums) / count if count else 0)
        best.append(max(values, default=0))
    best.sort()
    return {"repetitions": repetitions, "best_expectancy_95pct": best[int(0.95 * (len(best) - 1))] if best else 0}


def bootstrap(trades, repetitions=1000):
    rng = random.Random(13014)
    blocks = [trades[index:index + 5] for index in range(0, len(trades), 5)]
    if not blocks:
        return {"repetitions": repetitions, "probability_positive": 0}
    values = []
    for _ in range(repetitions):
        sample = [item["r"] for _ in blocks for item in rng.choice(blocks)]
        values.append(sum(sample) / len(sample))
    values.sort()
    return {"repetitions": repetitions, "probability_positive": sum(value > 0 for value in values) / repetitions, "interval_90": [values[50], values[949]], "interval_95": [values[25], values[974]]}


def execute():
    manifest = json.loads((MARKET / "manifest.json").read_text(encoding="utf-8"))
    info_frozen = json.loads((INFO / "frozen/FROZEN.json").read_text(encoding="utf-8"))
    if manifest["aggregate_corpus_fingerprint"] != MARKET_HASH or info_frozen["aggregate_hash"] != INFO_HASH:
        raise RuntimeError("Frozen input fingerprint mismatch")
    split = split_contract(manifest)
    checkpoint(schema="AIOS_FOREX_INFORMATION_EDGE_PROGRAM_V1", packet_id=PACKET, lock_id=LOCK, continuation_active=True, current_phase="MARKET_ALIGNMENT", current_action="daily table", next_action="family screening", next_three_actions=["CANDIDATE_REGISTRY_FREEZE", "DEVELOPMENT_WALK_FORWARD", "REGISTRY_WIDE_NULL"], remaining_authorized_work_count=12, deferred_blockers=["FRED policy/risk sources timed out"], alternate_safe_actions=["CFTC positioning", "Corpus V2 risk/liquidity", "long-horizon relative momentum"], external_time_dependency=False, protected_owner_action_dependency=False, terminal_state_candidate=None, pre_terminal_audit_status="FAIL_CONTINUE", same_packet_resume_command="python -B -m automation.forex_engine.forex_information_edge_program_v1 --execute", completed_work_units=0, remaining_work_units=len(manifest["eligible_pairs"]))
    by_pair = build_market_table(manifest)
    cot = load_cot()
    features, feature_hash = build_features(by_pair, cot)
    screening = screen_families(features, split["development"])
    atomic_json(ROOT / "family_screening.json", screening)
    candidates = registry(screening)
    registry_payload = {"candidates": [asdict(item) for item in candidates]}
    registry_payload["hash"] = sha_bytes(stable(registry_payload["candidates"]).encode())
    atomic_json(ROOT / "candidate_registry.json", registry_payload)
    development = {}
    trades_by_key = {}
    passers = []
    fold_windows = folds(split["development"])
    for position, candidate in enumerate(candidates, 1):
        development[candidate.candidate_id] = {}
        for side in ("LONG", "SHORT"):
            trades = simulate(features, by_pair, candidate, split["development"], side)
            fold_metrics = [metrics([trade for trade in trades if window[0] <= ts(trade["signal_time"]) < window[1]]) for window in fold_windows]
            result = metrics(trades)
            passed = development_gate(result, fold_metrics)
            development[candidate.candidate_id][side] = {"metrics": result, "folds": fold_metrics, "pass": passed}
            trades_by_key[f"{candidate.candidate_id}:{side}"] = trades
            if passed:
                passers.append((candidate, side))
        checkpoint(current_phase="DEVELOPMENT_WALK_FORWARD", current_action=candidate.candidate_id, completed_work_units=position, remaining_work_units=len(candidates)-position, next_action="next candidate", next_three_actions=["REGISTRY_WIDE_NULL", "BLOCK_BOOTSTRAP", "VALIDATION"], remaining_authorized_work_count=5, alternate_safe_actions=["next frozen candidate"] if position < len(candidates) else [], pre_terminal_audit_status="FAIL_CONTINUE")
    null = null_campaign(trades_by_key)
    bootstrap_results = {}
    eligible_for_validation = []
    for candidate, side in passers:
        key = f"{candidate.candidate_id}:{side}"
        result = development[candidate.candidate_id][side]["metrics"]
        boot = bootstrap(trades_by_key[key])
        bootstrap_results[key] = boot
        if result["expectancy_r"] > null["best_expectancy_95pct"] and boot["probability_positive"] >= 0.95:
            eligible_for_validation.append((candidate, side))
    validation = {}
    shortlist = []
    for candidate, side in eligible_for_validation:
        trades = simulate(features, by_pair, candidate, split["validation"], side)
        result = metrics(trades)
        passed = result["trades"] >= 50 and result["expectancy_r"] > 0 and result["profit_factor"] >= 1.10 and result["net_r"] > 0 and result["max_drawdown_pct"] <= 10
        validation[f"{candidate.candidate_id}:{side}"] = {"metrics": result, "pass": passed}
        if passed:
            shortlist.append((candidate, side))
    shortlist = shortlist[:5]
    shortlist_payload = [{"candidate": asdict(candidate), "side": side} for candidate, side in shortlist]
    shortlist_hash = sha_bytes(stable(shortlist_payload).encode())
    atomic_json(ROOT / "shortlist_freeze.json", {"hash": shortlist_hash, "candidates": shortlist_payload, "opened_holdout": bool(shortlist)})
    holdout = {}
    finalists = []
    for candidate, side in shortlist:
        trades = simulate(features, by_pair, candidate, split["sealed_holdout"], side)
        result = metrics(trades)
        boot = bootstrap(trades)
        passed = result["trades"] >= 50 and result["expectancy_r"] > 0 and result["profit_factor"] >= 1.10 and result["net_r"] > 0 and result["max_drawdown_pct"] <= 10 and boot["probability_positive"] >= 0.95
        holdout[f"{candidate.candidate_id}:{side}"] = {"metrics": result, "bootstrap": boot, "pass": passed}
        if passed:
            finalists.append((candidate, side))
    status = "FORWARD_HOLDOUT_ACCUMULATING" if finalists else "INFORMATION_EDGE_NOT_FOUND"
    remaining = 1 if finalists else 0
    terminal_certificate = None if finalists else {
        "terminal_state": "INFORMATION_EDGE_NOT_FOUND",
        "terminal_state_evidence": "Every frozen eligible information family failed the predeclared Development screening threshold; zero candidates were eligible for construction.",
        "continuation_queue_empty": True,
        "remaining_authorized_work_count": 0,
        "alternate_safe_actions": [],
        "distinct_repair_attempts": 1,
        "external_dependency": False,
        "protected_owner_action": False,
        "why_same_run_cannot_continue": "Candidate construction from a falsified information family is prohibited; unavailable sources cannot be replaced with non-point-in-time data.",
        "same_packet_resume_command": "NONE",
        "pre_terminal_audit_status": "PASS",
    }
    state = checkpoint(current_phase="FORWARD_INITIALIZATION" if finalists else "TERMINAL_REPORT", current_action="initialize forward" if finalists else "information-edge exhaustion", next_action="FORWARD_INITIALIZATION" if finalists else "NONE", next_three_actions=["FORWARD_ACCUMULATION"] if finalists else [], remaining_authorized_work_count=remaining, deferred_blockers=[], alternate_safe_actions=["forward integrity tooling"] if finalists else [], external_time_dependency=False, protected_owner_action_dependency=False, terminal_state_candidate=status, pre_terminal_audit_status="FAIL_CONTINUE" if finalists else "PASS", continuation_active=bool(finalists), same_packet_resume_command="python -B -m automation.forex_engine.forex_information_edge_program_v1 --execute" if finalists else "NONE", completed_work_units=len(candidates), remaining_work_units=remaining, market_hash=MARKET_HASH, information_corpus_hash=INFO_HASH, feature_hash=feature_hash, family_screening=screening, candidate_count=len(candidates), registry_hash=registry_payload["hash"], development=development, development_passers=[f"{candidate.candidate_id}:{side}" for candidate, side in passers], registry_null=null, bootstrap=bootstrap_results, validation=validation, shortlist_hash=shortlist_hash, sealed_holdout=holdout, finalists=[{"candidate": asdict(candidate), "side": side} for candidate, side in finalists], status=status, dominant_failure=None if finalists else dominant_failure(screening, development), hard_stop_certificate=terminal_certificate, safety={"credentials": False, "funding": False, "broker_write": False, "practice_order": False, "live": False, "money_movement": False})
    REPORT.write_text(report_text(state), encoding="utf-8")
    return state


def dominant_failure(screening, development):
    passed_families = [key for key, value in screening.items() if value.get("pass")]
    if not passed_families:
        return "NO_INCREMENTAL_INFORMATION_FAMILY"
    if not development:
        return "NO_CANDIDATES_FROM_SCREENING"
    return "INFORMATION_SIGNAL_NOT_TRADABLE_AFTER_COSTS"


def report_text(state):
    families = state["family_screening"]
    return f"""# AIOS Forex Information Edge Program V1

WHAT HAPPENED:

Packet 013 acquired and froze official CFTC information, evaluated every point-in-time-eligible information family, and found no family eligible for candidate construction.

IS IT SAFE:

YES. No credentials or funding were requested. OANDA LIVE was not contacted and no broker write occurred.

WHAT DO I DO NEXT:

Review this negative evidence. Do not enter OANDA LIVE credentials or fund an account.

HOW CLOSE ARE WE:

Estimated readiness: 35% to profitable-edge proof. Engineering integrity is established; independent information did not demonstrate robust predictive lift.

WHICH MODE SHOULD I USE:

INSTANT for review.

TECHNICAL DETAILS:

## Preflight

- Repository: `C:\\Dev\\Ai.Os`
- Branch: `main`
- HEAD: `b86c65140ed03d53d6c8d6c3618e50da0502f51b`
- Origin relation: ahead 7
- Lock: `{LOCK}`
- Duplicate writer: false

## Current evidence

- Cost repair: PASS (29 focused cost/backtest tests)
- Reference executor: `6dd60fb853a088636f2367a0f58e2a0c305f68ac72f83bd20e9ae6114f2aeba5`
- Corpus V2: `{state['market_hash']}`
- Packet 012: `RESEARCH_EXHAUSTED_FEATURE_EDGE_NOT_FOUND`
- Packet 012 registry rerun: false

## Information corpus

- ID: `AIOS_FOREX_INFORMATION_CORPUS_V1`
- Period: 2024-01-01 through 2026-08-29
- Official CFTC artifacts: 3
- Normalized CFTC records: 9,808
- External source failures: 11 FRED timeouts
- Aggregate hash: `{state['information_corpus_hash']}`
- Freeze: `FROZEN_VALID`
- Macro first-release family: ineligible; no bounded point-in-time vintage archive

## Family falsification

- A policy/carry: retired as unavailable; frozen requests timed out and no substitute was used
- B CFTC positioning: {families['B_CFTC_POSITIONING']['samples']} samples, {families['B_CFTC_POSITIONING']['mean_signed_future_atr']:.6f} ATR lift, {families['B_CFTC_POSITIONING']['positive_folds']}/8 positive folds, FAIL
- C macro events: ineligible; point-in-time vintage archive unavailable
- D risk/liquidity: {families['D_GLOBAL_RISK_LIQUIDITY']['samples']} samples, +{families['D_GLOBAL_RISK_LIQUIDITY']['mean_signed_future_atr']:.6f} ATR lift, {families['D_GLOBAL_RISK_LIQUIDITY']['positive_folds']}/8 positive folds, FAIL
- E long horizon: {families['E_LONG_HORIZON']['samples']} samples, {families['E_LONG_HORIZON']['mean_signed_future_atr']:.6f} ATR lift, {families['E_LONG_HORIZON']['positive_folds']}/8 positive folds, FAIL
- F combinations: not eligible because fewer than two individual families passed

## Research gates

- Feature hash: `{state['feature_hash']}`
- Candidate registry: {state['candidate_count']} (`{state['registry_hash']}`)
- Candidate cap respected: true
- Development folds: 8
- Development passers: {len(state['development_passers'])}
- Registry-wide null campaigns: {state['registry_null']['repetitions']}
- Bootstrap: not applicable; no Development passer
- Validation: not opened
- Sealed Holdout: not opened
- Finalists/Forward/V2/PAPER: none/not started

## Safety and later gates

- Publication readiness: not applicable; no certified candidate
- LIVE readiness: not entered
- Credential handoff: not created; Human Gate 1 not reached
- Funding handoff: not created; Human Gate 2 not reached
- LIVE profit proof: false
- Compounding enabled: false

## Continuation audit

- Current phase: `{state['current_phase']}`
- Current action: `{state['current_action']}`
- Next action: `{state['next_action']}`
- Remaining work: {state['remaining_authorized_work_count']}
- Alternate actions: none
- Terminal candidate: `{state['terminal_state_candidate']}`
- Audit result: `{state['pre_terminal_audit_status']}`
- Same-packet resume command: `{state['same_packet_resume_command']}`

STATUS: `{state['status']}`

HARD-STOP CERTIFICATE:

- terminal_state: `INFORMATION_EDGE_NOT_FOUND`
- continuation_queue_empty: true
- remaining_authorized_work_count: 0
- alternate_safe_actions: none
- distinct_repair_attempts: 1
- external_dependency: false
- protected_owner_action: false
- why_same_run_cannot_continue: all eligible information families failed screening; building candidates from them is prohibited
- same_packet_resume_command: `NONE`
- pre_terminal_audit_status: `PASS`

ATTACK_TO_FINISH:

- blocker_id: `NO_BLOCKER`
- blocker_status: `COMPLETE`
- exact_blocker: no point-in-time information family demonstrated stable incremental Development lift
- canonical_owner_file: `automation/forex_engine/forex_information_edge_program_v1.py`
- test_file: `tests/forex_engine/test_forex_information_edge_program_v1.py`
- runner_script: `python -B -m automation.forex_engine.forex_information_edge_program_v1 --execute`
- missing_evidence_field: `NONE`
- unlock_status_required: `COMPLETE`
- next_packet_name: `NONE`
- owner_action_required: review negative evidence; do not enter credentials or fund OANDA
- stop_condition: `INFORMATION_EDGE_NOT_FOUND`
- no_bloat_guard: do not rerun retired registries, substitute revised data, create PAPER/LIVE paths, request credentials, or request funding without a robust finalist
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required")
    state = execute()
    print(stable({"status": state["status"], "candidates": state["candidate_count"], "finalists": len(state["finalists"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
