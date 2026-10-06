"""Deterministic, PAPER-only candidate research on the immutable M5 corpus."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from automation.forex_engine.indicators import supertrend
from automation.forex_engine.models import Candle


CORPUS_ROOT = Path(".aios/runtime/forex_m5_immutable_corpus_v1")
RESEARCH_ROOT = Path(".aios/runtime/forex_candidate_research_v2")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_V2_RESEARCH_REPORT.md")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_V2_RESEARCH_STATE.json")
ATR_PERIOD = 5
SUPERTREND_FACTOR = 2.0
STARTING_EQUITY = 100_000.0
RISK_FRACTION = 0.0025
MIN_DIRECTION_TRADES = 30


@dataclass(frozen=True)
class AlternativeFamily:
    family_id: str
    implementation_path: str
    lookback: int
    threshold: float = 0.0


ALTERNATIVE_FAMILIES = (
    AlternativeFamily(
        "MEAN_REVERSION_V1",
        "automation/forex_engine/strategies/mean_reversion_v1.py",
        20,
        0.005,
    ),
    AlternativeFamily(
        "DAY_TRADING_BREAKOUT_V1",
        "automation/forex_engine/strategies/day_trading_breakout_v1.py",
        20,
    ),
)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    confirmation_closes: int = 2
    max_extension_atr: float | None = None
    structure_lookback: int = 0
    long_target_r: float = 10.0
    short_target_r: float = 2.0
    long_enabled: bool = True
    short_enabled: bool = True
    family: str = "BASELINE"


CANDIDATES = (
    Candidate("V1_BASELINE"),
    Candidate("H-LONG-TARGET-2R", long_target_r=2.0, short_enabled=False, family="TARGET"),
    Candidate("H-CONFIRM-4", confirmation_closes=4, family="TREND_FILTER"),
    Candidate("H-EXTENSION-1_5ATR", max_extension_atr=1.5, family="ENTRY"),
    Candidate("H-STRUCTURE-STOP-3", structure_lookback=3, family="STOP"),
    Candidate("H-CONFIRM-4-EXTENSION-1_5ATR", confirmation_closes=4, max_extension_atr=1.5, family="LIMITED_COMBINATION"),
)


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="ascii")
    os.replace(temporary, path)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value.rstrip() + "\n", encoding="ascii")
    os.replace(temporary, path)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def session(timestamp: str) -> str:
    hour = parse_time(timestamp).hour
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 13:
        return "LONDON"
    if 13 <= hour < 21:
        return "NEW_YORK"
    return "ROLLOVER"


def partitions(start: str, end: str) -> dict[str, dict[str, str]]:
    left, right = parse_time(start), parse_time(end)
    span = right - left
    development_end = left + span * 0.5
    validation_end = left + span * 0.75
    stamp = lambda value: value.isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "development": {"start_utc": stamp(left), "end_utc": stamp(development_end)},
        "validation": {"start_utc": stamp(development_end), "end_utc": stamp(validation_end)},
        "holdout": {"start_utc": stamp(validation_end), "end_utc": stamp(right)},
    }


def load_rows(path: Path, start: str, end: str, include_end: bool = False) -> list[dict[str, Any]]:
    result = []
    with gzip.open(path, "rt", encoding="ascii") as stream:
        for line in stream:
            row = json.loads(line)
            timestamp = row["timestamp"]
            if timestamp < start or timestamp > end or (timestamp == end and not include_end):
                continue
            result.append(row)
    return result


def candle(row: dict[str, Any]) -> Candle:
    mid = row["mid"]
    return Candle(symbol=row["instrument"].replace("_", ""), timeframe="5m", timestamp=row["timestamp"], open=mid["o"], high=mid["h"], low=mid["l"], close=mid["c"], volume=float(row["volume"]), source="OANDA_PRACTICE_GET_ONLY_IMMUTABLE_CORPUS")


def prepared(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candles = [candle(row) for row in rows]
    trend = supertrend(candles, ATR_PERIOD, SUPERTREND_FACTOR)
    output = []
    for row, item in zip(rows, trend):
        output.append({**row, "atr": item["atr"], "direction": item["direction"], "upper_band": item["upper_band"], "lower_band": item["lower_band"]})
    return output


def initial_stop(rows: list[dict[str, Any]], index: int, direction: str, candidate: Candidate) -> float:
    row = rows[index]
    band = float(row["lower_band"] if direction == "BUY" else row["upper_band"])
    if not candidate.structure_lookback:
        return band
    recent = rows[max(0, index - candidate.structure_lookback + 1) : index + 1]
    if direction == "BUY":
        return min(band, min(float(item["bid"]["l"]) for item in recent))
    return max(band, max(float(item["ask"]["h"]) for item in recent))


def backtest_pair(rows: list[dict[str, Any]], candidate: Candidate, direction: str) -> tuple[list[dict[str, Any]], Counter[str]]:
    if direction == "BUY" and not candidate.long_enabled or direction == "SELL" and not candidate.short_enabled:
        return [], Counter()
    trades: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    confirmed = 0
    run_direction = 0
    run_count = 0
    pending: dict[str, Any] | None = None
    position: dict[str, Any] | None = None
    for index, row in enumerate(rows):
        raw_direction = int(row["direction"])
        if raw_direction == run_direction:
            run_count += 1
        else:
            run_direction, run_count = raw_direction, 1
        event = None
        if run_count >= candidate.confirmation_closes and run_direction != confirmed:
            confirmed = run_direction
            event = "BUY" if confirmed > 0 else "SELL"
        if pending is not None:
            entry = float(row["ask"]["o"] if direction == "BUY" else row["bid"]["o"])
            stop = float(pending["stop"])
            risk = entry - stop if direction == "BUY" else stop - entry
            if risk <= 0:
                rejected["INVALID_R"] += 1
            else:
                target_r = candidate.long_target_r if direction == "BUY" else candidate.short_target_r
                position = {"instrument": row["instrument"], "signal_time": pending["signal_time"], "entry_time": row["timestamp"], "entry": entry, "initial_stop": stop, "active_stop": stop, "risk": risk, "target": entry + target_r * risk if direction == "BUY" else entry - target_r * risk, "mfe_r": 0.0, "mae_r": 0.0, "session": session(row["timestamp"]), "atr_ratio": pending["atr_ratio"]}
            pending = None
        if position is not None:
            entry, risk = position["entry"], position["risk"]
            if direction == "BUY":
                favorable, adverse = float(row["bid"]["h"]), float(row["bid"]["l"])
                position["mfe_r"] = max(position["mfe_r"], (favorable - entry) / risk)
                position["mae_r"] = min(position["mae_r"], (adverse - entry) / risk)
                band = row["lower_band"]
                if band is not None and position["active_stop"] < float(band) < float(row["bid"]["c"]):
                    position["active_stop"] = float(band)
                target_hit, stop_hit = favorable >= position["target"], adverse <= position["active_stop"]
                opposite = event == "SELL"
                if stop_hit:
                    exit_price, reason = position["active_stop"], "SUPERTREND_STOP"
                elif target_hit:
                    exit_price, reason = position["target"], "TAKE_PROFIT"
                elif opposite:
                    exit_price, reason = float(row["bid"]["c"]), "OPPOSITE_TRUE_CLOSE"
                else:
                    continue
                realized = (exit_price - entry) / risk
            else:
                favorable, adverse = float(row["ask"]["l"]), float(row["ask"]["h"])
                position["mfe_r"] = max(position["mfe_r"], (entry - favorable) / risk)
                position["mae_r"] = min(position["mae_r"], (entry - adverse) / risk)
                band = row["upper_band"]
                if band is not None and float(row["ask"]["c"]) < float(band) < position["active_stop"]:
                    position["active_stop"] = float(band)
                target_hit, stop_hit = favorable <= position["target"], adverse >= position["active_stop"]
                opposite = event == "BUY"
                if stop_hit:
                    exit_price, reason = position["active_stop"], "SUPERTREND_STOP"
                elif target_hit:
                    exit_price, reason = position["target"], "TAKE_PROFIT"
                elif opposite:
                    exit_price, reason = float(row["ask"]["c"]), "OPPOSITE_TRUE_CLOSE"
                else:
                    continue
                realized = (entry - exit_price) / risk
            trades.append({**position, "exit_time": row["timestamp"], "exit_reason": reason, "realized_r": realized, "direction": direction})
            position = None
        if event == direction and position is None and pending is None and row["atr"] and index + 1 < len(rows):
            stop = initial_stop(rows, index, direction, candidate)
            close = float(row["mid"]["c"])
            atr_value = float(row["atr"])
            extension = abs(close - stop) / atr_value if atr_value > 0 else math.inf
            if candidate.max_extension_atr is not None and extension > candidate.max_extension_atr:
                rejected["ENTRY_EXTENDED_FROM_BAND"] += 1
            else:
                pending = {"signal_time": row["timestamp"], "stop": stop, "atr_ratio": atr_value / close}
    return trades, rejected


def metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(trades, key=lambda trade: (trade["exit_time"], trade["instrument"]))
    values = [float(trade["realized_r"]) for trade in ordered]
    wins, losses = [value for value in values if value > 0], [value for value in values if value < 0]
    equity = peak = STARTING_EQUITY
    maximum_drawdown_pct = 0.0
    for value in values:
        equity *= max(0.0, 1.0 + RISK_FRACTION * value)
        peak = max(peak, equity)
        maximum_drawdown_pct = max(maximum_drawdown_pct, 100.0 * (peak - equity) / peak)
    pairs = Counter(trade["instrument"] for trade in ordered)
    sessions = Counter(trade["session"] for trade in ordered)
    exits = Counter(trade["exit_reason"] for trade in ordered)
    gross_profit, gross_loss = sum(wins), -sum(losses)
    return {
        "trades": len(values), "wins": len(wins), "losses": len(losses), "win_rate": len(wins) / len(values) if values else 0.0,
        "average_win_r": sum(wins) / len(wins) if wins else 0.0, "average_loss_r": sum(losses) / len(losses) if losses else 0.0,
        "expectancy_r": sum(values) / len(values) if values else 0.0, "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "net_r": sum(values), "maximum_drawdown_pct": maximum_drawdown_pct, "ending_equity": equity,
        "pair_count": len(pairs), "largest_pair_share": max(pairs.values()) / len(values) if values else 0.0,
        "pair_distribution": dict(sorted(pairs.items())), "session_distribution": dict(sorted(sessions.items())), "exit_reasons": dict(sorted(exits.items())),
        "mfe_reached_1r": sum(float(trade["mfe_r"]) >= 1.0 for trade in ordered), "mfe_reached_2r": sum(float(trade["mfe_r"]) >= 2.0 for trade in ordered),
    }


def gate(value: dict[str, Any]) -> tuple[bool, list[str]]:
    blockers = []
    if value["trades"] < MIN_DIRECTION_TRADES:
        blockers.append("TRADE_COUNT_BELOW_30")
    if value["expectancy_r"] <= 0:
        blockers.append("EXPECTANCY_NOT_POSITIVE")
    if value["profit_factor"] is None or value["profit_factor"] < 1.10:
        blockers.append("PROFIT_FACTOR_BELOW_1_10")
    if value["maximum_drawdown_pct"] > 10.0:
        blockers.append("DRAWDOWN_ABOVE_10_PERCENT")
    if value["pair_count"] < 5 or value["largest_pair_share"] > 0.35:
        blockers.append("PAIR_DIVERSITY_FAILURE")
    if len([count for count in value["session_distribution"].values() if count]) < 3:
        blockers.append("SESSION_DIVERSITY_FAILURE")
    return not blockers, blockers


def alternative_signal(
    rows: list[dict[str, Any]], index: int, family: AlternativeFamily, direction: str
) -> tuple[float, float] | None:
    """Return canonical-family stop and target from completed candles only."""
    if index < family.lookback:
        return None
    current = float(rows[index]["mid"]["c"])
    prior = rows[index - family.lookback : index]
    if family.family_id == "MEAN_REVERSION_V1":
        average = sum(float(item["mid"]["c"]) for item in prior) / len(prior)
        lower, upper = average * (1.0 - family.threshold), average * (1.0 + family.threshold)
        if direction == "BUY" and current < lower:
            return current - (average - current), average
        if direction == "SELL" and current > upper:
            return current + (current - average), average
        return None
    high = max(float(item["mid"]["h"]) for item in prior)
    low = min(float(item["mid"]["l"]) for item in prior)
    width = high - low
    if width <= 0:
        return None
    if direction == "BUY" and current > high:
        return low, current + width
    if direction == "SELL" and current < low:
        return high, current - width
    return None


def backtest_alternative_pair(
    rows: list[dict[str, Any]], family: AlternativeFamily, direction: str
) -> tuple[list[dict[str, Any]], Counter[str]]:
    trades: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    pending: dict[str, Any] | None = None
    position: dict[str, Any] | None = None
    last_signal_time: str | None = None
    for index, row in enumerate(rows):
        if pending is not None:
            entry = float(row["ask"]["o"] if direction == "BUY" else row["bid"]["o"])
            stop, target = float(pending["stop"]), float(pending["target"])
            risk = entry - stop if direction == "BUY" else stop - entry
            reward = target - entry if direction == "BUY" else entry - target
            if risk <= 0 or reward <= 0:
                rejected["INVALID_R"] += 1
            else:
                position = {
                    "instrument": row["instrument"],
                    "signal_time": pending["signal_time"],
                    "entry_time": row["timestamp"],
                    "entry": entry,
                    "initial_stop": stop,
                    "risk": risk,
                    "target": target,
                    "mfe_r": 0.0,
                    "mae_r": 0.0,
                    "session": session(row["timestamp"]),
                }
            pending = None
        if position is not None:
            entry, risk = position["entry"], position["risk"]
            if direction == "BUY":
                favorable, adverse = float(row["bid"]["h"]), float(row["bid"]["l"])
                position["mfe_r"] = max(position["mfe_r"], (favorable - entry) / risk)
                position["mae_r"] = min(position["mae_r"], (adverse - entry) / risk)
                stop_hit, target_hit = adverse <= position["initial_stop"], favorable >= position["target"]
                exit_price = position["initial_stop"] if stop_hit else position["target"] if target_hit else None
                realized = (exit_price - entry) / risk if exit_price is not None else None
            else:
                favorable, adverse = float(row["ask"]["l"]), float(row["ask"]["h"])
                position["mfe_r"] = max(position["mfe_r"], (entry - favorable) / risk)
                position["mae_r"] = min(position["mae_r"], (entry - adverse) / risk)
                stop_hit, target_hit = adverse >= position["initial_stop"], favorable <= position["target"]
                exit_price = position["initial_stop"] if stop_hit else position["target"] if target_hit else None
                realized = (entry - exit_price) / risk if exit_price is not None else None
            if realized is not None:
                reason = "STOP" if stop_hit else "TARGET"
                trades.append({**position, "exit_time": row["timestamp"], "exit_reason": reason, "realized_r": realized, "direction": direction})
                position = None
        if position is None and pending is None and index + 1 < len(rows):
            signal_spec = alternative_signal(rows, index, family, direction)
            if signal_spec is not None and row["timestamp"] != last_signal_time:
                pending = {"signal_time": row["timestamp"], "stop": signal_spec[0], "target": signal_spec[1]}
                last_signal_time = row["timestamp"]
    return trades, rejected


def fold_boundaries(start: str, end: str, count: int = 4) -> list[dict[str, str]]:
    left, right = parse_time(start), parse_time(end)
    span = (right - left) / count
    stamp = lambda value: value.isoformat(timespec="seconds").replace("+00:00", "Z")
    return [
        {"start_utc": stamp(left + span * index), "end_utc": stamp(left + span * (index + 1))}
        for index in range(count)
    ]


def evaluate_alternative_families(manifest: dict[str, Any], split: dict[str, dict[str, str]]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    development_folds = fold_boundaries(split["development"]["start_utc"], split["development"]["end_utc"])
    for family in ALTERNATIVE_FAMILIES:
        family_result: dict[str, Any] = {"implementation_path": family.implementation_path, "directions": {}}
        for direction, label in (("BUY", "LONG"), ("SELL", "SHORT")):
            development_trades: list[dict[str, Any]] = []
            validation_trades: list[dict[str, Any]] = []
            fold_trades: list[list[dict[str, Any]]] = [[] for _ in development_folds]
            rejections: Counter[str] = Counter()
            for artifact in manifest["artifacts"]:
                path = CORPUS_ROOT / artifact["relative_path"]
                dev_rows = load_rows(path, split["development"]["start_utc"], split["development"]["end_utc"])
                val_rows = load_rows(path, split["validation"]["start_utc"], split["validation"]["end_utc"])
                if len(dev_rows) > family.lookback + 2:
                    trades, rejected = backtest_alternative_pair(dev_rows, family, direction)
                    development_trades.extend(trades)
                    rejections.update(rejected)
                    for fold_index, boundary in enumerate(development_folds):
                        fold_trades[fold_index].extend(
                            trade for trade in trades if boundary["start_utc"] <= trade["signal_time"] < boundary["end_utc"]
                        )
                if len(val_rows) > family.lookback + 2:
                    trades, rejected = backtest_alternative_pair(val_rows, family, direction)
                    validation_trades.extend(trades)
                    rejections.update(rejected)
            dev_metrics = metrics(development_trades)
            val_metrics = metrics(validation_trades)
            fold_metrics = [metrics(items) for items in fold_trades]
            dev_pass, dev_blockers = gate(dev_metrics)
            val_pass, val_blockers = gate(val_metrics)
            positive_folds = sum(item["expectancy_r"] > 0 for item in fold_metrics)
            if positive_folds < 3:
                dev_pass = False
                dev_blockers.append("FEWER_THAN_THREE_POSITIVE_DEVELOPMENT_FOLDS")
            family_result["directions"][label] = {
                "development": dev_metrics,
                "development_folds": fold_metrics,
                "development_gate": {"passed": dev_pass, "blockers": list(dict.fromkeys(dev_blockers))},
                "provisional_validation": val_metrics,
                "provisional_validation_gate": {"passed": val_pass, "blockers": val_blockers},
                "signal_rejections": dict(rejections),
                "finalist_eligible": dev_pass and val_pass,
            }
        results[family.family_id] = family_result
    return {"development_folds": development_folds, "families": results}


def hypothesis(candidate: Candidate, observed: str, mechanism: str, primary_change: str) -> dict[str, Any]:
    return {"hypothesis_id": candidate.candidate_id, "family": candidate.family, "observed_failure": observed, "mechanism": mechanism, "one_primary_change": primary_change, "unchanged_variables": "ATR period 5, Supertrend factor 2, completed M5, next-candle bid/ask entry, conservative stop precedence, 0.25% equity risk", "expected_result": "Improve signal/entry/stop viability without leakage", "overfit_risk": "Bounded fixed parameter; reject if validation or one-time holdout fails"}


HYPOTHESES = {
    "V1_BASELINE": hypothesis(CANDIDATES[0], "Paper60 failed", "Reproduce unchanged architecture", "None"),
    "H-LONG-TARGET-2R": hypothesis(CANDIDATES[1], "BUY target was 10R", "Test downstream target causality", "LONG target 10R to 2R only"),
    "H-CONFIRM-4": hypothesis(CANDIDATES[2], "False/short trend persistence may trigger early", "Require longer trend persistence", "2 closes to 4 closes"),
    "H-EXTENSION-1_5ATR": hypothesis(CANDIDATES[3], "Entries may occur after extension", "Reject late entries", "Maximum band extension 1.5 ATR"),
    "H-STRUCTURE-STOP-3": hypothesis(CANDIDATES[4], "Band stop may be poorly located", "Include recent structure in initial stop", "3-candle structure stop"),
    "H-CONFIRM-4-EXTENSION-1_5ATR": hypothesis(CANDIDATES[5], "Persistence and extension may be independently useful", "Limited evidence-supported combination", "Combine fixed persistence and extension filters"),
}

NEXT_PACKET_PROMPT = """CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AIOS_FOREX_ALTERNATIVE_STRATEGY_RESEARCH_V1
SUPERVISOR IDENTITY: Codex East
WORKER IDENTITY: EAST_OCC_01
MODE: APPLY
ZONE: EAST
LANE: FOREX_ALTERNATIVE_STRATEGY_RESEARCH
WORKTREE: C:\\Dev\\Ai.Os
BRANCH: resolve after mandatory preflight; do not switch when dirty
APPROVAL AUTHORITY: Human Owner approval required before execution
LOCK ID: LOCK_EAST_FOREX_ALT_STRATEGY_OCC01
PACKET ID: PKT-EAST-FOREX-NEXT-STRATEGY-FAMILY-008
PACKET NAME: Existing Alternative Strategy Family Research
MISSION ID: AIOS-FOREX-LIVE-AUTONOMY
MISSION NAME: AIOS Forex Profitable Live Autonomy
PROGRAM ID: AIOS-FOREX
PROGRAM NAME: AIOS Forex
EPIC ID: AIOS-FOREX-LIVE-CERT
EPIC NAME: Profitable Live Autonomy And Scale Certification
BUCKET ID: AIOS-FOREX-ALTERNATIVE-STRATEGY
BUCKET NAME: Non-Supertrend Architecture Research

MISSION:
Evaluate existing repository mean-reversion and breakout strategy families on the frozen AIOS_FOREX_M5_IMMUTABLE_CORPUS_V1 using the sealed chronological partitions. Do not tune or reopen the existing holdout. If new selection is required, define a new future holdout from newly acquired genuine data before promotion.

MANDATORY PREFLIGHT:
Run pwd, git status --short --branch, git branch --show-current, and git remote -v. Read AGENTS.md, RISK_POLICY.md, delegated identity/lock authority, the M5 corpus manifest, drawdown contract, and V2 research state. Verify corpus hashes and acquire LOCK_EAST_FOREX_ALT_STRATEGY_OCC01 through the existing lock system.

ALLOWED READ PATHS:
AGENTS.md
RISK_POLICY.md
docs/governance/aios-identity-and-lane-governance.md
docs/governance/AI_OS_REPO_MEMORY.md
automation/forex_engine/
tests/forex_engine/
.aios/runtime/forex_m5_immutable_corpus_v1/
Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_STATE.json
Reports/forex_delivery/AIOS_FOREX_DRAWDOWN_CONTRACT_STATE.json
Reports/forex_delivery/AIOS_FOREX_V2_RESEARCH_STATE.json

ALLOWED WRITE PATHS:
automation/forex_engine/forex_alternative_strategy_research_v1.py
tests/forex_engine/test_forex_alternative_strategy_research_v1.py
Reports/forex_delivery/AIOS_FOREX_ALTERNATIVE_STRATEGY_RESEARCH_REPORT.md
Reports/forex_delivery/AIOS_FOREX_ALTERNATIVE_STRATEGY_RESEARCH_STATE.json
.aios/runtime/forex_alternative_strategy_research_v1/

FORBIDDEN PATHS:
All paths not explicitly listed under ALLOWED WRITE PATHS. No historical evidence, corpus artifact, Supertrend v1/v2 research result, governance, risk authority, broker code, or runtime root may be modified.

RULES:
Use existing strategy families only. Development generates hypotheses and validation rejects them. The previously opened holdout is evidence-only and cannot select or tune a new family. Require a newly frozen untouched holdout before candidate promotion. Preserve peak-equity percentage drawdown, fixed risk accounting, bid/ask spread, completed candles, deterministic fills, and conservative same-candle precedence. No broad grids, future leakage, pair/session cherry-picking, broker write, Practice order, LIVE, credentials, money movement, stage, commit, push, PR, merge, reset, clean, scheduler, or startup task.

VALIDATOR CHAIN:
Run Python syntax validation, focused tests, discovered related strategy regressions, JSON validation, corpus hash verification, partition non-overlap verification, safety scan, and scoped git diff --check. No skip or xfail may be represented as PASS.

STOP POINT:
Stop only at ALTERNATIVE_ARCHITECTURE_RESEARCH_COMPLETE, NEW_GENUINE_HOLDOUT_REQUIRED, or GOVERNANCE_BLOCKED_WITH_NO_OTHER_SAFE_WORK. Do not implement or launch a candidate without a separately authorized conditional write scope and a genuinely untouched holdout.

FINAL REPORT FORMAT:
WHAT HAPPENED:
IS IT SAFE:
WHAT DO I DO NEXT:
HOW CLOSE ARE WE:
WHICH MODE SHOULD I USE:
TECHNICAL DETAILS:
PREFLIGHT:
CORPUS:
PARTITIONS:
STRATEGY FAMILIES:
DEVELOPMENT:
VALIDATION:
HOLDOUT STATUS:
FILES CHANGED:
VALIDATION:
REMAINING DIRTY FILES:
HIGHEST-PRIORITY BLOCKER:
EXACT NEXT EXECUTABLE ACTION:
STATUS:
"""


def evaluate() -> dict[str, Any]:
    manifest = json.loads((CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"))
    split = partitions(manifest["requested_start_utc"], manifest["requested_end_utc"])
    results: dict[str, dict[str, Any]] = {candidate.candidate_id: {} for candidate in CANDIDATES}
    candle_counts: dict[str, int] = Counter()
    for split_name, boundary in split.items():
        split_trades = {candidate.candidate_id: {"LONG": [], "SHORT": [], "rejections": Counter()} for candidate in CANDIDATES}
        for artifact in manifest["artifacts"]:
            rows = load_rows(CORPUS_ROOT / artifact["relative_path"], boundary["start_utc"], boundary["end_utc"], split_name == "holdout")
            if len(rows) < ATR_PERIOD + 10:
                continue
            candle_counts[split_name] += len(rows)
            rows = prepared(rows)
            for candidate in CANDIDATES:
                for direction, label in (("BUY", "LONG"), ("SELL", "SHORT")):
                    trades, rejected = backtest_pair(rows, candidate, direction)
                    split_trades[candidate.candidate_id][label].extend(trades)
                    split_trades[candidate.candidate_id]["rejections"].update(rejected)
        for candidate in CANDIDATES:
            item = split_trades[candidate.candidate_id]
            results[candidate.candidate_id][split_name] = {"LONG": metrics(item["LONG"]), "SHORT": metrics(item["SHORT"]), "signal_rejections": dict(item["rejections"])}
    decisions = {}
    for candidate in CANDIDATES:
        directions = {}
        for direction in ("LONG", "SHORT"):
            enabled = candidate.long_enabled if direction == "LONG" else candidate.short_enabled
            gates = {}
            for split_name in ("development", "validation", "holdout"):
                passed, blockers = gate(results[candidate.candidate_id][split_name][direction]) if enabled else (False, ["DIRECTION_DISABLED"])
                gates[split_name] = {"passed": passed, "blockers": blockers}
            directions[direction] = {"enabled": enabled, "gates": gates, "promotion_passed": enabled and all(item["passed"] for item in gates.values())}
        decisions[candidate.candidate_id] = directions
    promoted = [candidate.candidate_id for candidate in CANDIDATES if any(decisions[candidate.candidate_id][direction]["promotion_passed"] for direction in ("LONG", "SHORT")) and candidate.candidate_id != "V1_BASELINE"]
    alternative_research = evaluate_alternative_families(manifest, split)
    finalists = []
    for family_id, family_result in alternative_research["families"].items():
        enabled = [
            direction
            for direction, result in family_result["directions"].items()
            if result["finalist_eligible"]
        ]
        if enabled:
            finalists.append({"candidate_id": f"{family_id}_BASELINE_V1", "family_id": family_id, "enabled_directions": enabled})
    family_inventory = [
        {
            "family_id": family.family_id,
            "implementation_path": family.implementation_path,
            "classification": "ELIGIBLE_WITH_RESEARCH_ADAPTER",
            "paper_only": True,
            "broker_dependency": False,
            "deterministic": True,
        }
        for family in ALTERNATIVE_FAMILIES
    ]
    family_inventory.extend(
        [
            {
                "family_id": "MOVING_AVERAGE_TREND",
                "implementation_path": "automation/forex_engine/strategy_candidates.py",
                "classification": "NOT_ELIGIBLE_DATA",
                "reason": "Canonical implementation supports only three pairs and fixed absolute stop/target distances are not comparable across the frozen 68-pair universe.",
                "paper_only": True,
                "broker_dependency": False,
                "deterministic": True,
            },
            {
                "family_id": "EMA_VWAP_PULLBACK",
                "implementation_path": "apps/trading_lab/trading_lab/strategies/ema_vwap_pullback.py",
                "classification": "NOT_ELIGIBLE_DATA",
                "reason": "Canonical VWAP contract requires intraday reset/session semantics not preserved by the current immutable-corpus adapter.",
                "paper_only": True,
                "broker_dependency": False,
                "deterministic": True,
            },
        ]
    )
    family_order_hash = hashlib.sha256(stable_json(family_inventory).encode("ascii")).hexdigest()
    lock_id = os.environ.get("AIOS_PACKET009_LOCK_ID", "AIOS-LOCK-ff009a9f287e474bab255e0b241292ce")
    packet_state = {
        "packet_id": "PKT-EAST-FOREX-END-TO-END-LIVE-READINESS-009",
        "packet_phase": "FINALIST_FREEZE" if finalists else "COMPLETE_WITHIN_CURRENT_AUTHORITY",
        "lock_id": lock_id,
        "strategy_families_discovered": family_inventory,
        "family_priority_order": [family.family_id for family in ALTERNATIVE_FAMILIES],
        "family_order_hash": family_order_hash,
        "finalists": finalists,
        "candidate_freeze_hash": None,
        "forward_holdout_status": "NOT_STARTED",
        "promotion_status": "NOT_EARNED",
        "paper_v2_status": "NOT_STARTED",
        "broker_write_performed": False,
        "practice_order_performed": False,
        "live_performed": False,
        "money_movement_performed": False,
        "exact_blocker": "NEW_GENUINE_FORWARD_EVIDENCE_REQUIRED" if finalists else "NO_ALTERNATIVE_BASELINE_PASSED_DEVELOPMENT_AND_PROVISIONAL_VALIDATION",
        "exact_next_action": "Freeze eligible finalists before acquiring new forward evidence" if finalists else "Freeze next bounded research cycle without reusing validation outcomes",
        "resume_command": "python -B -m automation.forex_engine.forex_candidate_research_v2 --execute",
    }
    state = {
        "schema": "AIOS_FOREX_V2_RESEARCH_STATE_V1", "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "corpus_id": manifest["corpus_id"], "corpus_fingerprint": manifest["aggregate_corpus_fingerprint"], "partitions": split,
        "partition_candle_counts": dict(candle_counts), "partition_overlap": False, "risk_fraction": RISK_FRACTION,
        "drawdown_unit": "PERCENT_OF_RUNNING_PEAK_EQUITY", "hypotheses": HYPOTHESES, "results": results, "decisions": decisions,
        "promoted_candidates": promoted, "promotion_earned": bool(promoted),
        "alternative_research": alternative_research,
        "packet_009": packet_state,
        "status": "ALTERNATIVE_FINALISTS_REQUIRE_NEW_FORWARD_EVIDENCE" if finalists else "NO_CANDIDATE_NEW_FORWARD_CYCLE_REQUIRED",
        "next_packet": None if promoted else {"packet_id": "PKT-EAST-FOREX-NEXT-STRATEGY-FAMILY-008", "mode": "APPLY_REQUIRES_HUMAN_OWNER_APPROVAL", "objective": "Evaluate existing non-Supertrend AIOS strategy families on the frozen corpus without changing corpus or gates.", "codex_prompt": NEXT_PACKET_PROMPT},
        "safety": {"paper_only": True, "broker_write": False, "practice_order": False, "live": False, "money_movement": False, "credentials_persisted": False},
    }
    return state


def publish(state: dict[str, Any]) -> None:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_json(RESEARCH_ROOT / "research_results.json", state)
    atomic_json(STATE, state)
    baseline = state["results"]["V1_BASELINE"]
    rejected = [candidate_id for candidate_id in state["decisions"] if candidate_id != "V1_BASELINE" and candidate_id not in state["promoted_candidates"]]
    alternatives = state["alternative_research"]["families"]
    alternative_lines = []
    for family_id, family in alternatives.items():
        alternative_lines.append(f"### {family_id}")
        for direction, result in family["directions"].items():
            alternative_lines.append(
                f"- {direction}: development expectancy `{result['development']['expectancy_r']:.6f}R`, "
                f"PF `{result['development']['profit_factor']}`, drawdown `{result['development']['maximum_drawdown_pct']:.6f}%`; "
                f"provisional expectancy `{result['provisional_validation']['expectancy_r']:.6f}R`, "
                f"PF `{result['provisional_validation']['profit_factor']}`, "
                f"drawdown `{result['provisional_validation']['maximum_drawdown_pct']:.6f}%`; "
                f"finalist eligible `{result['finalist_eligible']}`."
            )
    atomic_text(REPORT, f"""# Forex V2 Research\n\n## Corpus And Split\n\nCorpus `{state['corpus_id']}` uses chronological development and provisional-validation segments. The old holdout is consumed and was not used for alternative-family promotion. Drawdown is percentage from running peak equity using fixed 0.25% risk per trade.\n\n## Preserved Supertrend Baseline\n\nDevelopment LONG: `{stable_json(baseline['development']['LONG'])}`\n\nDevelopment SHORT: `{stable_json(baseline['development']['SHORT'])}`\n\n## Alternative Family Inventory And Baselines\n\n{chr(10).join(alternative_lines)}\n\nFamily priority hash: `{state['packet_009']['family_order_hash']}`.\n\nFinalists: `{stable_json(state['packet_009']['finalists'])}`.\n\nStatus: `{state['status']}`. No candidate implementation, PAPER campaign, or LIVE action is permitted without genuinely new forward evidence and all later gates.\n""")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = evaluate()
    publish(state)
    print(stable_json({"status": state["status"], "promoted_candidates": state["promoted_candidates"], "broker_write": False, "live": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
