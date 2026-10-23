"""Bounded PAPER-only normalization research for moving_average_trend."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from automation.forex_engine.forex_candidate_research_v2 import (
    CORPUS_ROOT,
    RISK_FRACTION,
    atomic_json,
    atomic_text,
    fold_boundaries,
    gate,
    load_rows,
    metrics,
    partitions,
    session,
    stable_json,
)

PACKET_ID = "PKT-EAST-FOREX-BOUNDED-STRATEGY-RESEARCH-010"
FAMILY_ID = "MOVING_AVERAGE_TREND"
FAMILY_SOURCE = "automation/forex_engine/strategy_candidates.py"
ROOT = Path(".aios/runtime/forex_normalized_strategy_research_v3")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_NORMALIZED_STRATEGY_RESEARCH_V3_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_NORMALIZED_STRATEGY_RESEARCH_V3_REPORT.md")
ATR_PERIOD = 14


@dataclass(frozen=True)
class Config:
    candidate_id: str
    hypothesis_id: str
    stop_atr: float
    target_atr: float


CONFIGS = (
    Config("MA-NORM-BASELINE", "H1_SCALE_NORMALIZATION", 1.0, 2.0),
    Config("MA-NORM-STOP-1_5", "H2_STOP_GEOMETRY", 1.5, 3.0),
    Config("MA-NORM-STOP-2", "H2_STOP_GEOMETRY", 2.0, 4.0),
    Config("MA-NORM-TARGET-3", "H3_TARGET_GEOMETRY", 1.0, 3.0),
)


def true_range(rows: list[dict[str, Any]], index: int) -> float:
    current = rows[index]["mid"]
    previous = float(rows[index - 1]["mid"]["c"])
    return max(float(current["h"]) - float(current["l"]), abs(float(current["h"]) - previous), abs(float(current["l"]) - previous))


def atr(rows: list[dict[str, Any]], index: int) -> float | None:
    if index < ATR_PERIOD:
        return None
    values = [true_range(rows, item) for item in range(index - ATR_PERIOD + 1, index + 1)]
    return sum(values) / len(values)


def signal(rows: list[dict[str, Any]], index: int) -> str | None:
    """Preserve canonical 3/5 SMA plus latest-close momentum semantics."""
    if index < 4:
        return None
    closes = [float(item["mid"]["c"]) for item in rows[index - 4 : index + 1]]
    short_ma, long_ma = sum(closes[-3:]) / 3.0, sum(closes) / 5.0
    if short_ma > long_ma and closes[-1] > closes[-2]:
        return "BUY"
    if short_ma < long_ma and closes[-1] < closes[-2]:
        return "SELL"
    return None


def backtest(rows: list[dict[str, Any]], config: Config, direction: str, spread_multiplier: float = 1.0) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    position: dict[str, Any] | None = None
    for index, row in enumerate(rows):
        if pending is not None:
            raw_entry = float(row["ask"]["o"] if direction == "BUY" else row["bid"]["o"])
            spread = float(row["ask"]["o"]) - float(row["bid"]["o"])
            entry = raw_entry + (spread_multiplier - 1.0) * spread if direction == "BUY" else raw_entry - (spread_multiplier - 1.0) * spread
            risk = config.stop_atr * pending["atr"]
            position = {"instrument": row["instrument"], "signal_time": pending["time"], "entry_time": row["timestamp"], "entry": entry, "risk": risk, "initial_stop": entry - risk if direction == "BUY" else entry + risk, "target": entry + config.target_atr * pending["atr"] if direction == "BUY" else entry - config.target_atr * pending["atr"], "session": session(row["timestamp"]), "mfe_r": 0.0, "mae_r": 0.0}
            pending = None
        if position is not None:
            entry, risk = position["entry"], position["risk"]
            if direction == "BUY":
                favorable, adverse = float(row["bid"]["h"]), float(row["bid"]["l"])
                stop_hit, target_hit = adverse <= position["initial_stop"], favorable >= position["target"]
                exit_price = position["initial_stop"] if stop_hit else position["target"] if target_hit else None
                realized = (exit_price - entry) / risk if exit_price is not None else None
            else:
                favorable, adverse = float(row["ask"]["l"]), float(row["ask"]["h"])
                stop_hit, target_hit = adverse >= position["initial_stop"], favorable <= position["target"]
                exit_price = position["initial_stop"] if stop_hit else position["target"] if target_hit else None
                realized = (entry - exit_price) / risk if exit_price is not None else None
            position["mfe_r"] = max(position["mfe_r"], abs(favorable - entry) / risk)
            if realized is not None:
                trades.append({**position, "exit_time": row["timestamp"], "exit_reason": "STOP" if stop_hit else "TARGET", "realized_r": realized, "direction": direction})
                position = None
        value = atr(rows, index)
        if position is None and pending is None and value and signal(rows, index) == direction and index + 1 < len(rows):
            pending = {"time": row["timestamp"], "atr": value}
    return trades


def evaluate() -> dict[str, Any]:
    manifest = json.loads((CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"))
    split = partitions(manifest["requested_start_utc"], manifest["requested_end_utc"])
    folds = fold_boundaries(split["development"]["start_utc"], split["development"]["end_utc"])
    results: dict[str, Any] = {}
    for config in CONFIGS:
        results[config.candidate_id] = {"hypothesis_id": config.hypothesis_id, "parameters": {"stop_atr": config.stop_atr, "target_atr": config.target_atr}, "directions": {}}
        for direction, label in (("BUY", "LONG"), ("SELL", "SHORT")):
            development, validation, stress = [], [], []
            fold_items = [[] for _ in folds]
            for artifact in manifest["artifacts"]:
                path = CORPUS_ROOT / artifact["relative_path"]
                dev_rows = load_rows(path, split["development"]["start_utc"], split["development"]["end_utc"])
                val_rows = load_rows(path, split["validation"]["start_utc"], split["validation"]["end_utc"])
                dev_trades = backtest(dev_rows, config, direction)
                development.extend(dev_trades)
                for fold_index, boundary in enumerate(folds):
                    fold_items[fold_index].extend(item for item in dev_trades if boundary["start_utc"] <= item["signal_time"] < boundary["end_utc"])
                validation.extend(backtest(val_rows, config, direction))
                stress.extend(backtest(val_rows, config, direction, 1.25))
            dev, val, stressed = metrics(development), metrics(validation), metrics(stress)
            fold_metrics = [metrics(items) for items in fold_items]
            dev_pass, dev_blockers = gate(dev)
            if sum(item["expectancy_r"] > 0 for item in fold_metrics) < 3:
                dev_pass = False
                dev_blockers.append("FEWER_THAN_THREE_POSITIVE_FOLDS")
            val_pass, val_blockers = gate(val) if dev_pass else (False, ["DEVELOPMENT_GATE_FAILED"])
            if val_pass and (stressed["expectancy_r"] <= 0 or stressed["profit_factor"] is None or stressed["profit_factor"] < 1.10):
                val_pass = False
                val_blockers.append("ADVERSE_SPREAD_STRESS_FAILED")
            results[config.candidate_id]["directions"][label] = {"development": dev, "folds": fold_metrics, "development_gate": {"passed": dev_pass, "blockers": dev_blockers}, "provisional_validation": val, "spread_stress_125pct": stressed, "provisional_gate": {"passed": val_pass, "blockers": val_blockers}}
    finalists = [{"candidate_id": candidate_id, "enabled_directions": [direction for direction, item in result["directions"].items() if item["provisional_gate"]["passed"]], "parameters": result["parameters"]} for candidate_id, result in results.items() if any(item["provisional_gate"]["passed"] for item in result["directions"].values())][:2]
    family_identity = {"family_id": FAMILY_ID, "source": FAMILY_SOURCE, "signal": "SMA3>SMA5 and latest close rises; inverse for SHORT", "normalization": "ATR14 stop/target geometry only"}
    family_hash = hashlib.sha256(stable_json(family_identity).encode("ascii")).hexdigest()
    state = {"schema": "AIOS_FOREX_NORMALIZED_STRATEGY_RESEARCH_V3", "packet_id": PACKET_ID, "generated_utc": datetime.now(timezone.utc).isoformat(), "corpus_id": manifest["corpus_id"], "corpus_hash": manifest["aggregate_corpus_fingerprint"], "selected_family": family_identity, "family_identity_hash": family_hash, "folds": folds, "results": results, "finalists": finalists, "finalist_eligible": bool(finalists), "status": "FINALIST_ELIGIBLE" if finalists else "SELECTED_FAMILY_RETIRED", "failure_map": [] if finalists else ["SIGNAL_NO_EDGE", "NORMALIZATION_NO_EDGE"], "safety": {"broker_write": False, "practice_order": False, "live": False, "money_movement": False}, "next_packet": "PKT-EAST-FOREX-FORWARD-HOLDOUT-011" if finalists else "PKT-EAST-FOREX-PORTABLE-STRATEGY-SPEC-011"}
    return state


def publish(state: dict[str, Any]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    atomic_json(ROOT / "results.json", state)
    atomic_json(STATE, state)
    lines = ["# Normalized Moving-Average Strategy Research V3", "", f"Status: `{state['status']}`", f"Corpus: `{state['corpus_hash']}`", "", "## Results"]
    for candidate_id, result in state["results"].items():
        for direction, item in result["directions"].items():
            lines.append(f"- {candidate_id} {direction}: dev expectancy {item['development']['expectancy_r']:.6f}R, PF {item['development']['profit_factor']}, DD {item['development']['maximum_drawdown_pct']:.6f}%; provisional tested={item['development_gate']['passed']}, pass={item['provisional_gate']['passed']}")
    lines.extend(["", f"Finalists: `{stable_json(state['finalists'])}`", "", "Forward holdout, V2, PAPER V2, broker writes, and LIVE actions were not started."])
    atomic_text(REPORT, "\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    if not parser.parse_args().execute:
        parser.error("--execute is required")
    state = evaluate()
    publish(state)
    print(stable_json({"status": state["status"], "finalists": state["finalists"], "live": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
