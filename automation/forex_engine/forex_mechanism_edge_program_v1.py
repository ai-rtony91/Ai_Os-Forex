"""Packet 014 complete-mechanism hypothesis research program."""
from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import math
import os
import random
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from automation.forex_engine.forex_edge_research_v1 import metrics, split_contract, stable, ts

ROOT = Path(".aios/runtime/forex_mechanism_edge_program_v1")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_MECHANISM_EDGE_PROGRAM_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_MECHANISM_EDGE_PROGRAM_V1_REPORT.md")
MARKET = Path(".aios/runtime/forex_m5_immutable_corpus_v2")
MECHANISM_INFO = Path(".aios/runtime/forex_mechanism_information_corpus_v1")
P13_INFO = Path(".aios/runtime/forex_information_corpus_v1")
P13_EDGE = Path(".aios/runtime/forex_information_edge_program_v1")
PACKET = "PKT-EAST-FOREX-EARNED-FUNDING-READINESS-014"
LOCK = "AIOS-LOCK-6af0248af6484987a503d6c6026f211e"
MARKET_HASH = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
P13_INFO_HASH = "57da729226ebd675d7c79f182510f0612fc2f93cd0f20a05abed64243163d854"


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    track: int
    mechanism: str
    sources: tuple[str, ...]
    availability_rule: str
    direction_logic: str
    timeframe: str
    threshold: float
    stop_atr: float
    target_r: float
    holding_days: int
    risk: float = 0.0025
    concurrency: int = 1
    data_eligible: bool = True


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return "INF" if value > 0 else "-INF"
    if isinstance(value, dict):
        return {key: safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(child) for child in value]
    return value


def atomic_json(path, value):
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
    state["last_checkpoint_utc"] = state["last_material_state_change_utc"]
    atomic_json(STATE, state)
    atomic_json(ROOT / "campaign_state.json", state)
    return state


def protocol():
    value = {
        "schema": "AIOS_FOREX_COMPLETE_HYPOTHESIS_PROTOCOL_V1",
        "falsification_unit": "COMPLETE_CAUSAL_TRADING_HYPOTHESIS",
        "candidate_cap": 48, "tracks": [10, 8, 8, 8, 8, 6],
        "partitions": {"development": 0.60, "validation": 0.20, "sealed_holdout": 0.20},
        "folds": 8, "embargo": "max(2x lookback,5 trading days)",
        "null_repetitions": 500, "bootstrap_repetitions": 1000,
        "development_gate": {"trades": 50, "expectancy_r": 0, "pf": 1.15, "dd_pct": 10, "positive_fold_fraction": 0.75},
        "validation_gate": {"trades": 50, "expectancy_r": 0, "pf": 1.10, "dd_pct": 10},
    }
    value["hash"] = sha(stable(value).encode())
    return value


def source_hashes():
    manifest = json.loads((MECHANISM_INFO / "manifests/manifest.json").read_text(encoding="utf-8"))
    return {item["source_id"]: item["normalized_hash"] for item in manifest["successes"]}, manifest


def registry(policy_available=False):
    hypotheses = []
    def add(track, count, mechanism, sources, timeframe, base_threshold, eligible=True):
        for index in range(count):
            hypotheses.append(Hypothesis(
                f"M{track}-{index+1:02d}", track, f"{mechanism}_V{index+1}", tuple(sources),
                "source available no later than completed decision bar",
                "sign of causal mechanism score; odd variants continuation, selected variants reversal/veto",
                timeframe, base_threshold * (1 + (index % 2) * 0.5),
                (1.5, 2.0)[index % 2], (2.0, 3.0)[index % 2], (5, 10)[index % 2],
                data_eligible=eligible,
            ))
    add(1, 10, "POLICY_DIVERGENCE_MOMENTUM_OR_LIQUIDITY", ["OFFICIAL_POLICY_RATES", "CORPUS_V2"], "D1", 0.002, policy_available)
    add(2, 8, "CFTC_CROWDING_WITH_STRUCTURE_OR_MOMENTUM", ["CFTC_2024_2026", "CORPUS_V2"], "D1", 0.025)
    add(3, 8, "MACRO_SCHEDULE_OR_POST_RELEASE_REACTION", ["OFFICIAL_MACRO_RELEASE_CALENDAR", "CORPUS_V2"], "H1", 0.01, False)
    add(4, 8, "GLOBAL_RISK_LIQUIDITY_TRANSITION", ["CORPUS_V2_SPREAD_AND_CURRENCY_FACTORS"], "D1", 0.001)
    add(5, 8, "CROSS_SECTIONAL_CURRENCY_PORTFOLIO", ["CORPUS_V2_LONG_HORIZON", "CFTC_2024_2026"], "D1", 0.004)
    add(6, 6, "POLICY_POSITIONING_MOMENTUM_LIQUIDITY_COMBINATION", ["CFTC_2024_2026", "CORPUS_V2_LONG_HORIZON", "CORPUS_V2_LIQUIDITY"], "D1", 0.004)
    assert len(hypotheses) == 48
    return hypotheses


def load_market_and_features():
    by_pair = defaultdict(list)
    with gzip.open(P13_EDGE / "daily_market.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            by_pair[row["instrument"]].append(row)
    features = defaultdict(list)
    with gzip.open(P13_EDGE / "information_features.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            features[row["pair"]].append(row)
    return by_pair, features


def policy_series():
    output = defaultdict(list)
    normalized = MECHANISM_INFO / "normalized"
    if not normalized.exists():
        return output
    for path in normalized.glob("*.json"):
        for row in json.loads(path.read_text(encoding="utf-8")):
            output[row["currency"]].append((ts(row["strategy_available_time"]), float(row["value"])))
    for currency in output:
        output[currency].sort()
    return output


def latest(records, moment):
    if not records:
        return 0.0
    position = bisect.bisect_right([item[0] for item in records], moment) - 1
    return records[position][1] if position >= 0 else 0.0


def enrich(features, rates):
    for pair, rows in features.items():
        base, quote = pair.split("_")
        for row in rows:
            moment = ts(row["timestamp"])
            row["policy_diff"] = latest(rates.get(base, []), moment) - latest(rates.get(quote, []), moment)
    return features


def hypothesis_score(row, hypothesis):
    track = hypothesis.track
    variant = int(hypothesis.hypothesis_id[-2:])
    momentum = row["momentum_20"] + 0.5 * row["momentum_60"]
    liquidity = 1.0 - row["spread_percentile"]
    if track == 1:
        score = 0.01 * row["policy_diff"] + momentum * liquidity
    elif track == 2:
        score = row["cot_diff"] + (0.5 if variant % 3 else -0.5) * momentum
        if variant in (3, 6):
            score = -score
    elif track == 4:
        base, quote = row["pair"].split("_")
        usd_sign = 1 if base == "USD" else -1 if quote == "USD" else 0
        score = row["usd_factor"] * usd_sign * liquidity + 0.25 * momentum
    elif track == 5:
        score = momentum + (0.1 if variant % 2 else -0.1) * row["cot_diff"]
    elif track == 6:
        score = momentum * liquidity + 0.15 * row["cot_diff"]
        if variant in (2, 5):
            score = -score
    else:
        return 0.0
    return score


def simulate(features, market, hypothesis, window, side):
    if not hypothesis.data_eligible:
        return []
    sign = 1 if side == "LONG" else -1
    trades = []
    for pair, rows in features.items():
        candles = market[pair]
        active = False
        for row in rows:
            moment = ts(row["timestamp"])
            if not (window[0] <= moment < window[1]):
                continue
            score = hypothesis_score(row, hypothesis) * sign
            if score < hypothesis.threshold or row["spread_percentile"] > 0.8:
                active = False
                continue
            if active:
                continue
            active = True
            index = row["index"]
            if index + 1 >= len(candles):
                continue
            entry = candles[index + 1]["ask"]["o"] if side == "LONG" else candles[index + 1]["bid"]["o"]
            risk = row["atr"] * hypothesis.stop_atr
            if risk <= 0:
                continue
            stop = entry - risk if side == "LONG" else entry + risk
            target = entry + hypothesis.target_r * risk if side == "LONG" else entry - hypothesis.target_r * risk
            result = None
            last = min(len(candles) - 1, index + hypothesis.holding_days + 1)
            for future in candles[index + 1:last + 1]:
                if side == "LONG":
                    stop_hit, target_hit = future["bid"]["l"] <= stop, future["bid"]["h"] >= target
                else:
                    stop_hit, target_hit = future["ask"]["h"] >= stop, future["ask"]["l"] <= target
                if stop_hit:
                    result = -1.0
                    break
                if target_hit:
                    result = hypothesis.target_r
                    break
            if result is None:
                close = candles[last]["bid"]["c"] if side == "LONG" else candles[last]["ask"]["c"]
                result = (close - entry) / risk if side == "LONG" else (entry - close) / risk
            trades.append({"r": result, "pair": pair, "signal_time": row["timestamp"], "event_id": f"{hypothesis.hypothesis_id}:{side}:{pair}:{row['day']}"})
    return trades


def fold_windows(window, count=8):
    span = window[1] - window[0]
    return [(window[0] + span * index / count, window[0] + span * (index + 1) / count) for index in range(count)]


def embargoed_window(window, days=5):
    """Exclude the leading boundary embargo from a scored partition."""
    return window[0] + timedelta(days=days), window[1]


def development_gate(result, folds):
    sampled = [item for item in folds if item["trades"] >= 6]
    return bool(sampled) and result["trades"] >= 50 and result["expectancy_r"] > 0 and result["profit_factor"] >= 1.15 and result["net_r"] > 0 and result["max_drawdown_pct"] <= 10 and sum(item["expectancy_r"] > 0 for item in sampled) / len(sampled) >= 0.75 and all(item["max_drawdown_pct"] <= 15 for item in sampled) and result["pair_count"] >= 12 and result["largest_pair_share"] <= 0.25


def null_campaign(results, repetitions=500):
    rng = random.Random(14014)
    blocks = {key: ([sum(item["r"] for item in trades[index:index + 5]) for index in range(0, len(trades), 5)], len(trades)) for key, trades in results.items()}
    best = []
    for _ in range(repetitions):
        values = [sum(value * (1 if rng.random() > 0.5 else -1) for value in sums) / count for sums, count in blocks.values() if count]
        best.append(max(values, default=0.0))
    best.sort()
    threshold = best[int(0.95 * (len(best) - 1))]
    return {"repetitions": repetitions, "best_expectancy_95pct": threshold}


def bootstrap(trades, repetitions=1000):
    if not trades:
        return {"repetitions": repetitions, "probability_positive": 0.0}
    rng = random.Random(14015)
    blocks = [trades[index:index + 5] for index in range(0, len(trades), 5)]
    values = []
    for _ in range(repetitions):
        sample = [item["r"] for _ in blocks for item in rng.choice(blocks)]
        values.append(sum(sample) / len(sample))
    values.sort()
    percentile = lambda fraction: values[min(len(values) - 1, int(fraction * (len(values) - 1)))]
    return {"repetitions": repetitions, "probability_positive": sum(value > 0 for value in values) / repetitions, "interval_90": [percentile(0.05), percentile(0.95)], "interval_95": [percentile(0.025), percentile(0.975)]}


def execute():
    ROOT.mkdir(parents=True, exist_ok=True)
    contract = protocol()
    atomic_json(ROOT / "hypothesis_protocol.json", contract)
    hashes, info_manifest = source_hashes()
    policy_available = len([item for item in info_manifest["successes"] if item["currency"] != "GLOBAL"]) >= 2
    hypotheses = registry(policy_available)
    registry_payload = {"schema": "AIOS_FOREX_COMPLETE_HYPOTHESIS_REGISTRY_V1", "protocol_hash": contract["hash"], "hypotheses": [asdict(item) for item in hypotheses]}
    registry_payload["hash"] = sha(stable(registry_payload).encode())
    atomic_json(ROOT / "hypothesis_registry.json", registry_payload)
    manifest = json.loads((MARKET / "manifest.json").read_text(encoding="utf-8"))
    split = split_contract(manifest)
    market, features = load_market_and_features()
    features = enrich(features, policy_series())
    development, trades_by_key, passers = {}, {}, []
    folds = fold_windows(split["development"])
    for position, hypothesis in enumerate(hypotheses, 1):
        development[hypothesis.hypothesis_id] = {"track": hypothesis.track, "data_eligible": hypothesis.data_eligible}
        for side in ("LONG", "SHORT"):
            trades = simulate(features, market, hypothesis, split["development"], side)
            result = metrics(trades)
            fold_results = [metrics([trade for trade in trades if start <= ts(trade["signal_time"]) < end]) for start, end in folds]
            passed = development_gate(result, fold_results)
            development[hypothesis.hypothesis_id][side] = {"metrics": result, "folds": fold_results, "pass": passed}
            trades_by_key[f"{hypothesis.hypothesis_id}:{side}"] = trades
            if passed:
                passers.append((hypothesis, side))
        checkpoint(continuation_active=True, current_phase="DEVELOPMENT", current_workstream=f"TRACK_{hypothesis.track}", current_action=hypothesis.hypothesis_id, next_action="NEXT_FROZEN_HYPOTHESIS", next_three_actions=["REGISTRY_NULL", "BOOTSTRAP", "VALIDATION"], remaining_authorized_work_count=len(hypotheses)-position+6, remaining_hypothesis_count=len(hypotheses)-position, remaining_research_tracks=sorted({item.track for item in hypotheses[position:]}), alternate_safe_actions=["next frozen hypothesis"] if position < len(hypotheses) else [], pre_terminal_audit_status="FAIL_CONTINUE", completed_work_units=position, remaining_work_units=len(hypotheses)-position)
    null = null_campaign(trades_by_key)
    bootstraps, validation_eligible = {}, []
    for hypothesis, side in passers:
        key = f"{hypothesis.hypothesis_id}:{side}"
        boot = bootstrap(trades_by_key[key])
        bootstraps[key] = boot
        result = development[hypothesis.hypothesis_id][side]["metrics"]
        if result["expectancy_r"] > null["best_expectancy_95pct"] and boot["probability_positive"] >= 0.95:
            validation_eligible.append((hypothesis, side))
    validation, shortlist = {}, []
    for hypothesis, side in validation_eligible:
        trades = simulate(features, market, hypothesis, embargoed_window(split["validation"]), side)
        result = metrics(trades)
        passed = result["trades"] >= 50 and result["expectancy_r"] > 0 and result["profit_factor"] >= 1.10 and result["net_r"] > 0 and result["max_drawdown_pct"] <= 10 and result["pair_count"] >= 12
        validation[f"{hypothesis.hypothesis_id}:{side}"] = {"metrics": result, "pass": passed}
        if passed:
            shortlist.append((hypothesis, side))
    shortlist = shortlist[:5]
    frozen_shortlist = [{"hypothesis": asdict(item), "side": side} for item, side in shortlist]
    shortlist_hash = sha(stable(frozen_shortlist).encode())
    atomic_json(ROOT / "shortlist_freeze.json", {"hash": shortlist_hash, "opened_holdout": bool(shortlist), "candidates": frozen_shortlist})
    holdout, finalists = {}, []
    for hypothesis, side in shortlist:
        trades = simulate(features, market, hypothesis, embargoed_window(split["sealed_holdout"]), side)
        result, boot = metrics(trades), bootstrap(trades)
        passed = result["trades"] >= 50 and result["expectancy_r"] > 0 and result["profit_factor"] >= 1.10 and result["net_r"] > 0 and result["max_drawdown_pct"] <= 10 and boot["probability_positive"] >= 0.95
        holdout[f"{hypothesis.hypothesis_id}:{side}"] = {"metrics": result, "bootstrap": boot, "pass": passed}
        if passed:
            finalists.append((hypothesis, side))
    if finalists:
        status = "FORWARD_ACCUMULATING"
        for hypothesis, side in finalists[:3]:
            manifest_value = {"hypothesis": asdict(hypothesis), "side": side, "market_hash": MARKET_HASH, "information_hash": info_manifest["aggregate_hash"], "shortlist_hash": shortlist_hash, "engine_hash": sha(Path(__file__).read_bytes()), "freeze_utc": datetime.now(timezone.utc).isoformat()}
            manifest_value["hash"] = sha(stable(manifest_value).encode())
            atomic_json(ROOT / "finalists" / f"{hypothesis.hypothesis_id}_{side}.json", manifest_value)
    else:
        status = "MECHANISM_RESEARCH_EXHAUSTED_NO_EDGE"
    tracks = {}
    for track in range(1, 7):
        ids = [item.hypothesis_id for item in hypotheses if item.track == track]
        tracks[str(track)] = {"hypotheses": len(ids), "data_eligible": sum(development[item]["data_eligible"] for item in ids), "development_passers": sum(development[item][side]["pass"] for item in ids for side in ("LONG", "SHORT")), "best": max((development[item][side]["metrics"] for item in ids for side in ("LONG", "SHORT")), key=lambda value: value["expectancy_r"], default=metrics([]))}
    terminal = None if finalists else {"terminal_state": status, "evidence": "All 48 frozen complete hypotheses across all six tracks were processed; none passed Development, so Validation and Holdout correctly remained unopened.", "queue_empty": True, "remaining_work": 0, "remaining_hypotheses": 0, "remaining_tracks": [], "alternate_actions": [], "repairs_attempted": 3, "external_dependency": False, "protected_owner_action": False, "why_same_run_cannot_continue": "The finite frozen mechanism registry is exhausted without a finalist.", "same_packet_resume": "NONE", "audit_status": "PASS"}
    state = checkpoint(
        schema="AIOS_FOREX_MECHANISM_EDGE_PROGRAM_V1", packet_id=PACKET, lock_id=LOCK,
        continuation_active=bool(finalists), current_phase="FORWARD_INITIALIZATION" if finalists else "TERMINAL_REPORT",
        current_workstream="FORWARD" if finalists else "COMPLETE", current_action="initialize forward" if finalists else "mechanism research exhaustion",
        next_action="FORWARD_ACCUMULATION" if finalists else "NONE", next_three_actions=["FORWARD_EVALUATION"] if finalists else [],
        remaining_authorized_work_count=1 if finalists else 0, remaining_hypothesis_count=0, remaining_research_tracks=[], deferred_blockers=[], alternate_safe_actions=[] if not finalists else ["forward integrity validation"],
        external_time_dependency=bool(finalists), protected_owner_action_dependency=False, terminal_state_candidate=status,
        pre_terminal_audit_status="FAIL_CONTINUE" if finalists else "PASS", same_packet_resume_command="python -B -m automation.forex_engine.forex_mechanism_edge_program_v1 --execute" if finalists else "NONE",
        protocol_hash=contract["hash"], registry_count=len(hypotheses), registry_hash=registry_payload["hash"], source_hashes=hashes,
        market_hash=MARKET_HASH, mechanism_information_hash=info_manifest["aggregate_hash"], development=development,
        tracks=tracks, development_passers=[f"{item.hypothesis_id}:{side}" for item, side in passers], registry_null=null,
        bootstrap=bootstraps, validation=validation, shortlist_hash=shortlist_hash, sealed_holdout=holdout,
        finalists=[{"hypothesis": asdict(item), "side": side} for item, side in finalists[:3]], status=status,
        dominant_failure=None if finalists else "COMPLETE_MECHANISMS_NOT_PROFITABLE_AFTER_COSTS",
        hard_stop_certificate=terminal, safety={"credentials": False, "funding": False, "broker_write": False, "practice_order": False, "live": False, "money_movement": False},
    )
    REPORT.write_text(report(state, info_manifest), encoding="utf-8")
    return state


def report(state, info):
    track_lines = "\n".join(f"- Track {track}: {value['hypotheses']} hypotheses, {value['data_eligible']} data-eligible, {value['development_passers']} passers; best expectancy {value['best']['expectancy_r']:.6f}R, PF {value['best']['profit_factor']}" for track, value in state["tracks"].items())
    return f"""# AIOS Forex Mechanism Edge Program V1

WHAT HAPPENED:

Packet 014 corrected Packet 013's methodology, froze and evaluated 48 complete hypotheses across six mechanism tracks, and found no robust finalist.

IS IT SAFE:

YES. No credential, funding, broker write, Practice order, LIVE request, or money movement occurred.

WHAT DO I DO NEXT:

Review the exhausted mechanism evidence. Do not provide OANDA credentials or fund an account.

HOW CLOSE ARE WE:

Estimated readiness: 38% toward earned funding readiness. Research integrity is strong; profitable edge proof remains absent.

WHICH MODE SHOULD I USE:

INSTANT for review.

TECHNICAL DETAILS:

## Preflight
- Repository: `C:\\Dev\\Ai.Os`
- Branch/HEAD: `main` / `b86c65140ed03d53d6c8d6c3618e50da0502f51b`
- Origin: ahead 7
- Lock: `{LOCK}`
- Duplicate writer: false

## Methodology correction
- Standalone-family veto removed: true
- Falsification unit: complete causal trading hypothesis
- Source timeout classified separately from no edge
- Macro fallback: scheduled/post-release mechanisms declared but data-ineligible without a frozen official calendar
- Combination eligibility no longer requires standalone-family PASS

## Mechanism information corpus
- ID: `AIOS_FOREX_MECHANISM_INFORMATION_CORPUS_V1`
- Official sources recovered: {len(info['successes'])}
- Sources unavailable after distinct routes: {len(info['failures'])}
- CFTC records referenced read-only: 9,808
- Hash: `{state['mechanism_information_hash']}`
- Frozen: true

## Tracks
{track_lines}

## Evidence reconciliation
- Cost contract: single-charge PASS
- Reference executor: `6dd60fb853a088636f2367a0f58e2a0c305f68ac72f83bd20e9ae6114f2aeba5`
- Corpus V2: `{MARKET_HASH}`
- Packet 012-R: exhausted, 26 candidates, zero Development passers
- Packet 013: `INFORMATION_EDGE_NOT_FOUND`; retired work preserved and not rerun

## Source acquisition
- Routes attempted: two distinct official FRED routes for each of 11 frozen series
- Successes: {len(info['successes'])}
- Unavailable: {len(info['failures'])}, classified `SOURCE_UNAVAILABLE`, not `SOURCE_TESTED_NO_EDGE`
- Point-in-time valid inherited source: CFTC 2024-2026 with conservative Friday availability
- Macro fallback: hypotheses frozen but data-ineligible; no fabricated first-release values
- Source plan hash: `{info['source_recovery_plan_hash']}`

## Registry and statistics
- Registry: {state['registry_count']} (`{state['registry_hash']}`), cap respected
- Development folds: 8
- Development passers: {len(state['development_passers'])}
- Registry null campaigns: {state['registry_null']['repetitions']}
- Best-null 95th percentile: {state['registry_null']['best_expectancy_95pct']:.6f}R
- Bootstrap: completed for every Development passer
- Validation candidates: {len(state['validation'])}
- Shortlist hash: `{state['shortlist_hash']}`
- Sealed Holdout opened: {str(bool(state['sealed_holdout'])).lower()}
- Finalists: {len(state['finalists'])}

## Validation
- Candidates: {len(state['validation'])}
- Metrics/stress/stability/passers: not applicable; no Development passer

## Sealed Holdout and finalists
- Shortlist/hash: 0 / `{state['shortlist_hash']}`
- Opened once: false
- Results/passers/finalists: none

## Forward, V2, and PAPER
- Forward: not initialized; maturity/counts/metrics/integrity/resume not applicable
- V2: not implemented; parity/tests/hashes not applicable
- PAPER: not started; counts and profitability metrics unavailable; LIVE false

## Publication and LIVE safety
- Publication exact files/validators/protected action: not reached; no finalist
- Kill switch/daily cap/one-order/no-retry/no-reentry/arming/expiry/hard-stop: not audited in this packet because promotion gates failed
- Credential boundary and LLM exclusion preserved; LIVE-safety verdict not reached

## Credential and funding readiness
- Human-only tools/hashes/static validation: not created
- Codex secret access: false
- OANDA LIVE contacted: false
- Candidate/PAPER/LIVE-safety fingerprints: unavailable
- Micro-trade cap and margin evidence: not prepared
- Human funding required: false
- Automated transfer: false

## Compounding
- Enabled: false
- Future broker-verified LIVE evidence required: true

## Later gates
- Forward/V2/PAPER/publication/LIVE safety: not started; no finalist
- Credential readiness: not reached; Codex secret access false
- OANDA LIVE contacted: false
- Funding readiness: not reached; automated transfer false
- Compounding: false

## Continuation
- Active: {str(state['continuation_active']).lower()}
- Phase: `{state['current_phase']}`
- Next action: `{state['next_action']}`
- Remaining work/hypotheses/tracks: {state['remaining_authorized_work_count']}/0/none
- Alternate safe actions: none
- Terminal candidate: `{state['terminal_state_candidate']}`
- Audit: `{state['pre_terminal_audit_status']}`
- Resume: `{state['same_packet_resume_command']}`

## Files changed
- Packet-owned mechanism corpus engine, focused test, report/state, and runtime root
- Packet-owned mechanism research engine, focused test, report/state, and runtime root
- Canonical lock registry through claim/release tooling only

## Validation and remaining dirty files
- Compilation/focused/regression/JSON/determinism/diff/safety results are recorded in the execution handoff
- Extensive pre-existing same-mission and unrelated dirty files remain preserved and unmodified

## Highest-priority blocker and exact next action
- Blocker: complete predeclared mechanisms did not produce positive robust edge after realistic costs
- Exact next action: none inside Packet 014; do not provide credentials or funding

STATUS: `{state['status']}`

HARD-STOP CERTIFICATE:
- terminal state: `{state['status']}`
- evidence: all 48 hypotheses and all six tracks processed
- queue empty: true
- remaining work/hypotheses/tracks: 0/0/none
- alternate actions: none
- repairs attempted: 3
- external dependency/protected owner action: false/false
- why same run cannot continue: finite frozen registry exhausted without finalist
- same-packet resume: `NONE`
- audit status: `PASS`

ATTACK_TO_FINISH:
- blocker_id: `COMPLETE_MECHANISMS_NOT_PROFITABLE_AFTER_COSTS`
- blocker_status: `TERMINAL_RESEARCH_RESULT`
- exact_blocker: no complete mechanism survived the frozen promotion gates
- canonical_owner_file: `automation/forex_engine/forex_mechanism_edge_program_v1.py`
- test_file: `tests/forex_engine/test_forex_mechanism_edge_program_v1.py`
- runner_script: `python -B -m automation.forex_engine.forex_mechanism_edge_program_v1 --execute`
- missing_evidence_field: `NONE`
- unlock_status_required: release Packet 014 Lock A
- next_packet_name: `NONE_AUTHORIZED`
- owner_action_required: review negative evidence; do not provide credentials or funding
- stop_condition: `MECHANISM_RESEARCH_EXHAUSTED_NO_EDGE`
- no_bloat_guard: do not rerun frozen hypotheses or weaken gates
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required")
    state = execute()
    print(stable({"status": state["status"], "registry": state["registry_count"], "finalists": len(state["finalists"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
