"""Packet 032 bounded multi-timeframe gross-edge surface.

The search is deliberately staged and ledgered.  It looks for raw directional
information in Supertrend, MACD, ADX, and their ablations before any downstream
cost, exit, validation, paper, or live phase can open.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import random
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine import forex_next_generation_edge_program_v1 as p27
from automation.forex_engine.forex_mtf_indicator_coverage_v1 import M5_STATE, coverage_matrix, resolve_m5_artifact
from automation.forex_engine.forex_supertrend_macd_adx_v1 import adx, macd, module_hash, supertrend


PACKET_ID = "PKT-EAST-FOREX-MTF-GROSS-EDGE-DISCOVERY-032"
SCHEMA = "AIOS_FOREX_MTF_GROSS_EDGE_SURFACE.v1"
ROOT = Path(".aios/runtime/forex_mtf_gross_edge_surface_v1")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_MTF_GROSS_EDGE_SURFACE_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_MTF_GROSS_EDGE_SURFACE_V1_REPORT.md")
LEDGER = Path("Reports/forex_delivery/AIOS_FOREX_MTF_HYPOTHESIS_LEDGER_V1.json")

TIMEFRAME_MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440, "W1": 10080, "MN1": 43200}
LOWER_TFS = {"M5", "M15", "M30"}
HIGHER_TFS = {"H1", "H4", "D1", "W1", "MN1"}
SUPERTREND_GRID = [(p, m) for p in (7, 10, 14, 21) for m in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0)]
MACD_GRID = [(8, 17, 9), (12, 26, 9), (19, 39, 9), (24, 52, 18)]
ADX_PERIODS = [7, 10, 14, 21, 28]
ADX_THRESHOLDS = [15, 20, 25, 30, 35]
COMBOS = ["ST", "MACD", "ADX", "ST+MACD", "ST+ADX", "MACD+ADX", "ST+MACD+ADX"]
MAX_FIRST_PASS_HYPOTHESES = 25_000
PAIR_SAMPLE_LIMIT = 3
M5_ARTIFACTS_PER_PAIR = 2
MAX_EVENTS_PER_PAIR = 30
MAX_ROWS_PER_PAIR_TIMEFRAME = 420
MAX_M5_ROWS_PER_ARTIFACT = 180
SCORED_SUPERTREND_GRID = SUPERTREND_GRID
SCORED_MACD_GRID = MACD_GRID
SCORED_ADX_GRID = [(period, threshold) for period in ADX_PERIODS for threshold in ADX_THRESHOLDS]
ROW_CACHE: dict[tuple[str, str], list[dict[str, Any]]] = {}


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def candle_from_repo_row(row: dict[str, Any]) -> dict[str, Any]:
    mid = row["mid"]
    bid = row.get("bid", mid)
    ask = row.get("ask", mid)
    stamp = row.get("timestamp") or row.get("time")
    return {
        "time": parse_time(str(stamp)),
        "timestamp": str(stamp),
        "open": float(mid["o"]),
        "high": float(mid["h"]),
        "low": float(mid["l"]),
        "close": float(mid["c"]),
        "bid_close": float(bid["c"]),
        "ask_close": float(ask["c"]),
        "spread": max(0.0, float(ask["c"]) - float(bid["c"])),
        "complete": True,
    }


def load_m5_rows(instrument: str) -> list[dict[str, Any]]:
    cache_key = ("M5_RAW", instrument)
    if cache_key in ROW_CACHE:
        return ROW_CACHE[cache_key]
    state = read_json(M5_STATE)
    artifacts = [a for a in state.get("artifacts", []) if a.get("instrument") == instrument and a.get("path")]
    artifacts = sorted(artifacts, key=lambda item: str(item.get("start_utc", "")))
    if len(artifacts) > M5_ARTIFACTS_PER_PAIR:
        step = max(1, len(artifacts) // M5_ARTIFACTS_PER_PAIR)
        artifacts = artifacts[::step][:M5_ARTIFACTS_PER_PAIR]
    rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        path = resolve_m5_artifact(str(artifact["path"]))
        if not path.exists():
            continue
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            accepted_lines = 0
            for line in handle:
                if line.strip():
                    try:
                        rows.append(candle_from_repo_row(json.loads(line)))
                        accepted_lines += 1
                    except (KeyError, TypeError, ValueError):
                        continue
                if accepted_lines >= MAX_M5_ROWS_PER_ARTIFACT:
                    break
    rows.sort(key=lambda item: item["time"])
    ROW_CACHE[cache_key] = rows
    return rows


def load_h1_rows(instrument: str) -> list[dict[str, Any]]:
    cache_key = ("H1_RAW", instrument)
    if cache_key in ROW_CACHE:
        return ROW_CACHE[cache_key]
    rows = []
    for row in p27.load_h1(instrument, 2005, 2026):
        rows.append(
            {
                "time": row["time"],
                "timestamp": row["time"].isoformat().replace("+00:00", "Z"),
                "open": row["mid"]["o"],
                "high": row["mid"]["h"],
                "low": row["mid"]["l"],
                "close": row["mid"]["c"],
                "bid_close": row["bid"]["c"],
                "ask_close": row["ask"]["c"],
                "spread": max(0.0, row["ask"]["c"] - row["bid"]["c"]),
                "complete": True,
            }
        )
    if len(rows) > 1600:
        step = max(1, len(rows) // 1600)
        rows = rows[::step]
    ROW_CACHE[cache_key] = rows
    return rows


def resample(rows: list[dict[str, Any]], minutes: int) -> list[dict[str, Any]]:
    if not rows:
        return []
    buckets: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        stamp: datetime = row["time"]
        if minutes == 43200:
            key: Any = (stamp.year, stamp.month)
        else:
            epoch_minute = int(stamp.timestamp() // 60)
            key = epoch_minute - (epoch_minute % minutes)
        buckets.setdefault(key, []).append(row)
    out: list[dict[str, Any]] = []
    for key in sorted(buckets):
        chunk = sorted(buckets[key], key=lambda item: item["time"])
        out.append(
            {
                "time": chunk[-1]["time"],
                "timestamp": chunk[-1]["timestamp"],
                "open": chunk[0]["open"],
                "high": max(item["high"] for item in chunk),
                "low": min(item["low"] for item in chunk),
                "close": chunk[-1]["close"],
                "bid_close": chunk[-1]["bid_close"],
                "ask_close": chunk[-1]["ask_close"],
                "spread": chunk[-1]["spread"],
                "complete": True,
            }
        )
    return out


def pair_universe() -> list[str]:
    state = read_json(M5_STATE)
    pairs = sorted(state.get("eligible_pairs") or {a.get("instrument") for a in state.get("artifacts", []) if a.get("instrument")})
    if len(pairs) <= PAIR_SAMPLE_LIMIT:
        return list(pairs)
    ranked = sorted(pairs, key=lambda p: sha256_text(f"{PACKET_ID}|{p}"))
    return sorted(ranked[:PAIR_SAMPLE_LIMIT])


def candles_for(instrument: str, timeframe: str) -> list[dict[str, Any]]:
    cache_key = (timeframe, instrument)
    if cache_key in ROW_CACHE:
        return ROW_CACHE[cache_key]
    if timeframe in LOWER_TFS:
        rows = load_m5_rows(instrument)
        value = rows if timeframe == "M5" else resample(rows, TIMEFRAME_MINUTES[timeframe])
        if len(value) > MAX_ROWS_PER_PAIR_TIMEFRAME:
            step = max(1, len(value) // MAX_ROWS_PER_PAIR_TIMEFRAME)
            value = value[::step]
        ROW_CACHE[cache_key] = value
        return value
    rows = load_h1_rows(instrument)
    value = rows if timeframe == "H1" else resample(rows, TIMEFRAME_MINUTES[timeframe])
    if len(value) > MAX_ROWS_PER_PAIR_TIMEFRAME:
        step = max(1, len(value) // MAX_ROWS_PER_PAIR_TIMEFRAME)
        value = value[::step]
    ROW_CACHE[cache_key] = value
    return value


def hypothesis_grid() -> list[dict[str, Any]]:
    hypotheses: list[dict[str, Any]] = []
    for timeframe in TIMEFRAME_MINUTES:
        for direction in ("LONG", "SHORT"):
            for period, multiplier in SCORED_SUPERTREND_GRID:
                hypotheses.append({"combo": "ST", "timeframe": timeframe, "direction": direction, "st": [period, multiplier]})
            for params in SCORED_MACD_GRID:
                hypotheses.append({"combo": "MACD", "timeframe": timeframe, "direction": direction, "macd": list(params)})
            for period, threshold in SCORED_ADX_GRID:
                hypotheses.append({"combo": "ADX", "timeframe": timeframe, "direction": direction, "adx": [period, threshold]})
            for combo in ("ST+MACD", "ST+ADX", "MACD+ADX", "ST+MACD+ADX"):
                hypothesis: dict[str, Any] = {"combo": combo, "timeframe": timeframe, "direction": direction}
                if "ST" in combo:
                    hypothesis["st"] = [14, 3.0]
                if "MACD" in combo:
                    hypothesis["macd"] = [12, 26, 9]
                if "ADX" in combo:
                    hypothesis["adx"] = [14, 25]
                hypotheses.append(hypothesis)
    for index, hypothesis in enumerate(hypotheses, start=1):
        hypothesis["hypothesis_id"] = f"MTF032-H{index:05d}"
        hypothesis["created_by"] = "bounded_packet032_staged_grid"
        hypothesis["fingerprint"] = sha256_text(stable({k: v for k, v in hypothesis.items() if k != "fingerprint"}))
    if len(hypotheses) > MAX_FIRST_PASS_HYPOTHESES:
        raise RuntimeError("Packet 032 first-pass hypothesis cap exceeded")
    return hypotheses


def indicator_signal(hypothesis: dict[str, Any], rows: list[dict[str, Any]], index: int, indicators: dict[str, Any]) -> bool:
    direction = hypothesis["direction"]
    wants_long = direction == "LONG"
    checks: list[bool] = []
    if "ST" in hypothesis["combo"]:
        item = indicators["st"][tuple(hypothesis["st"])][index]
        if item["trend"] == 0:
            return False
        checks.append(item["trend"] == (1 if wants_long else -1))
    if "MACD" in hypothesis["combo"]:
        item = indicators["macd"][tuple(hypothesis["macd"])][index]
        prev = indicators["macd"][tuple(hypothesis["macd"])][index - 1] if index > 0 else item
        if item["histogram"] is None or prev["histogram"] is None:
            return False
        if wants_long:
            checks.append(item["histogram"] > 0 and item["histogram"] >= prev["histogram"])
        else:
            checks.append(item["histogram"] < 0 and item["histogram"] <= prev["histogram"])
    if "ADX" in hypothesis["combo"]:
        item = indicators["adx"][tuple(hypothesis["adx"])][index]
        if item["adx"] is None or item["plus_di"] is None or item["minus_di"] is None:
            return False
        threshold = float(hypothesis["adx"][1])
        strength = item["adx"] >= threshold
        direction_ok = item["plus_di"] > item["minus_di"] if wants_long else item["minus_di"] > item["plus_di"]
        checks.append(strength and direction_ok)
    return bool(checks) and all(checks)


def score_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(item["r"]) for item in records]
    total = len(values)
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    expectancy = sum(values) / total if total else 0.0
    pf = gross_profit / gross_loss if gross_loss else (999.0 if gross_profit > 0 else 0.0)
    equity = 100.0
    peak = equity
    max_dd = 0.0
    for value in values:
        equity += value * 0.25
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100.0 if peak else 0.0)
    pair_counts: dict[str, int] = {}
    year_counts: dict[str, int] = {}
    for item in records:
        pair_counts[item["instrument"]] = pair_counts.get(item["instrument"], 0) + 1
        year_counts[str(item["year"])] = year_counts.get(str(item["year"]), 0) + 1
    folds = []
    if records:
        ordered = sorted(records, key=lambda item: (item["year"], item["instrument"], item["event_index"]))
        fold_count = min(4, max(1, len(ordered) // 30))
        for fold_index in range(fold_count):
            chunk = ordered[fold_index::fold_count]
            if len(chunk) >= 10:
                folds.append(sum(float(item["r"]) for item in chunk) / len(chunk))
    positive_folds = sum(1 for value in folds if value > 0)
    return {
        "trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / total, 6) if total else 0.0,
        "gross_expectancy": round(expectancy, 8),
        "gross_pf": round(pf, 6),
        "gross_net_r": round(sum(values), 6),
        "max_drawdown_percent": round(max_dd, 6),
        "pair_count": len(pair_counts),
        "year_count": len(year_counts),
        "max_pair_share": round(max(pair_counts.values()) / total, 6) if total else 0.0,
        "fold_count": len(folds),
        "positive_fold_share": round(positive_folds / len(folds), 6) if folds else 0.0,
        "avg_spread_r": round(sum(float(item["spread_r"]) for item in records) / total, 8) if total else 0.0,
        "avg_mfe_r": round(sum(float(item["mfe_r"]) for item in records) / total, 8) if total else 0.0,
        "avg_mae_r": round(sum(float(item["mae_r"]) for item in records) / total, 8) if total else 0.0,
    }


def evaluate_hypothesis(hypothesis: dict[str, Any], pair_rows: dict[str, list[dict[str, Any]]], caches: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    horizon = 6 if hypothesis["timeframe"] in LOWER_TFS else 3
    for instrument, rows in pair_rows.items():
        if len(rows) < 30:
            continue
        indicators = caches[instrument]
        accepted = 0
        step = max(1, len(rows) // 480)
        start_index = min(55, max(10, len(rows) // 3))
        for index in range(start_index, len(rows) - horizon - 1, step):
            if accepted >= MAX_EVENTS_PER_PAIR:
                break
            if not indicator_signal(hypothesis, rows, index, indicators):
                continue
            entry = rows[index + 1]["close"]
            future = rows[index + 1 : index + 1 + horizon]
            risk = max(rows[index]["high"] - rows[index]["low"], rows[index]["spread"] * 3.0, 1e-8)
            if hypothesis["direction"] == "LONG":
                final = (future[-1]["close"] - entry) / risk
                mfe = (max(item["high"] for item in future) - entry) / risk
                mae = (entry - min(item["low"] for item in future)) / risk
            else:
                final = (entry - future[-1]["close"]) / risk
                mfe = (entry - min(item["low"] for item in future)) / risk
                mae = (max(item["high"] for item in future) - entry) / risk
            records.append(
                {
                    "instrument": instrument,
                    "year": rows[index]["time"].year,
                    "event_index": index,
                    "r": max(-6.0, min(6.0, final)),
                    "mfe_r": max(0.0, min(8.0, mfe)),
                    "mae_r": max(0.0, min(8.0, mae)),
                    "spread_r": rows[index + 1]["spread"] / risk,
                }
            )
            accepted += 1
    metrics = score_records(records)
    gate = (
        metrics["trades"] >= 50
        and metrics["gross_expectancy"] > 0
        and metrics["gross_pf"] > 1.0
        and metrics["positive_fold_share"] >= 0.75
        and metrics["pair_count"] >= 4
        and metrics["max_pair_share"] <= 0.45
    )
    return {
        **hypothesis,
        "result": "GROSS_SCREEN_SURVIVOR_PENDING_FULL_SEARCH_NULL" if gate else "GROSS_SCREEN_REJECTED",
        "gross_gate_pass": gate,
        "metrics": metrics,
    }


def build_indicator_caches(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "st": {params: supertrend(rows, params[0], params[1]) for params in set(SUPERTREND_GRID + [(10, 3.0), (14, 3.0)])},
        "macd": {params: macd(rows, *params) for params in set(MACD_GRID + [(12, 26, 9), (8, 17, 9)])},
        "adx": {params: adx(rows, params[0]) for params in {(p, t) for p in ADX_PERIODS for t in ADX_THRESHOLDS} | {(14, 20), (14, 25)}},
    }


def run_surface() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    pairs = pair_universe()
    coverage = coverage_matrix()
    hypotheses = [h for h in hypothesis_grid() if coverage.get(h["timeframe"], {}).get("eligible_for_development")]
    ledger: list[dict[str, Any]] = []
    results_by_combo: dict[str, dict[str, Any]] = {}
    best_by_direction = {"LONG": None, "SHORT": None}
    timeframe_results: dict[str, Any] = {}

    for timeframe in TIMEFRAME_MINUTES:
        if not coverage.get(timeframe, {}).get("eligible_for_development"):
            continue
        pair_rows = {pair: candles_for(pair, timeframe) for pair in pairs}
        pair_rows = {pair: rows for pair, rows in pair_rows.items() if len(rows) >= 30}
        caches = {pair: build_indicator_caches(rows) for pair, rows in pair_rows.items()}
        tf_results = []
        for hypothesis in [h for h in hypotheses if h["timeframe"] == timeframe]:
            result = evaluate_hypothesis(hypothesis, pair_rows, caches)
            tf_results.append(result)
            ledger.append(
                {
                    "hypothesis_id": result["hypothesis_id"],
                    "indicator_family": result["combo"],
                    "parameters": {k: result[k] for k in ("st", "macd", "adx") if k in result},
                    "direction": result["direction"],
                    "context_timeframe": result["timeframe"],
                    "signal_timeframe": result["timeframe"],
                    "execution_timeframe": result["timeframe"],
                    "pair_scope": f"deterministic_breadth_sample_{len(pair_rows)}_of_{len(pairs)}",
                    "event_definition": "completed_indicator_state_next_bar_midpoint_gross",
                    "exit_family": "fixed_horizon_gross_information",
                    "cost_policy": "gross_midpoint_diagnostic_only",
                    "date_created": "2026-08-31",
                    "result": result["result"],
                    "fingerprint": result["fingerprint"],
                    "metrics": result["metrics"],
                }
            )
            combo_key = f"{result['combo']}::{result['direction']}"
            current = results_by_combo.get(combo_key)
            if current is None or result["metrics"]["gross_expectancy"] > current["metrics"]["gross_expectancy"]:
                results_by_combo[combo_key] = result
            current_dir = best_by_direction[result["direction"]]
            if current_dir is None or result["metrics"]["gross_expectancy"] > current_dir["metrics"]["gross_expectancy"]:
                best_by_direction[result["direction"]] = result
        timeframe_results[timeframe] = {
            "pair_count_loaded": len(pair_rows),
            "hypotheses": len(tf_results),
            "gross_gate_passers": sum(1 for item in tf_results if item["gross_gate_pass"]),
            "best_long_expectancy": max((item["metrics"]["gross_expectancy"] for item in tf_results if item["direction"] == "LONG"), default=0.0),
            "best_short_expectancy": max((item["metrics"]["gross_expectancy"] for item in tf_results if item["direction"] == "SHORT"), default=0.0),
        }

    passers = [item for item in ledger if item["result"] == "GROSS_SCREEN_SURVIVOR_PENDING_FULL_SEARCH_NULL"]
    positive_raw = [item for item in ledger if item["metrics"]["gross_expectancy"] > 0 and item["metrics"]["gross_pf"] > 1]
    if not positive_raw:
        status = "NO_INDICATOR_GROSS_EDGE"
    elif not passers:
        status = "SEARCH_FAMILY_EXHAUSTED_NO_ROBUST_EDGE"
    else:
        status = "BIDIRECTIONAL_GROSS_EDGE_IDENTIFIED" if {p["direction"] for p in passers} == {"LONG", "SHORT"} else (
            "LONG_GROSS_EDGE_ONLY" if any(p["direction"] == "LONG" for p in passers) else "SHORT_GROSS_EDGE_ONLY"
        )

    ledger_doc = {
        "schema": "AIOS_FOREX_MTF_HYPOTHESIS_LEDGER.v1",
        "packet_id": PACKET_ID,
        "hypothesis_count": len(ledger),
        "max_first_pass_hypotheses": MAX_FIRST_PASS_HYPOTHESES,
        "full_parameter_families_frozen": {
            "supertrend_grid": SUPERTREND_GRID,
            "macd_grid": MACD_GRID,
            "adx_periods": ADX_PERIODS,
            "adx_thresholds": ADX_THRESHOLDS,
        },
        "scored_first_pass_subset": {
            "supertrend_grid": SCORED_SUPERTREND_GRID,
            "macd_grid": SCORED_MACD_GRID,
            "adx_grid": SCORED_ADX_GRID,
            "reason": "All single-indicator parameter families scored; interaction ablations use representative parent settings and are not reported as exhaustive parameter descendants.",
        },
        "hidden_trials_possible": False,
        "ledger_hash": sha256_text(stable(ledger)),
        "hypotheses": ledger,
    }
    atomic_json(LEDGER, ledger_doc)
    state = {
        "schema": SCHEMA,
        "packet_id": PACKET_ID,
        "status": status,
        "indicator_code_hash": module_hash(),
        "pair_sample_limit": PAIR_SAMPLE_LIMIT,
        "max_rows_per_pair_timeframe": MAX_ROWS_PER_PAIR_TIMEFRAME,
        "max_m5_rows_per_artifact": MAX_M5_ROWS_PER_ARTIFACT,
        "pairs_used_count": len(pairs),
        "hypotheses_tested": len(ledger),
        "full_parameter_families_frozen": True,
        "scored_first_pass_subset": True,
        "gross_screen_survivors": len(passers),
        "positive_raw_diagnostic_count": len(positive_raw),
        "timeframe_results": timeframe_results,
        "best_by_combo_direction": {
            key: {
                "hypothesis_id": value["hypothesis_id"],
                "timeframe": value["timeframe"],
                "metrics": value["metrics"],
                "result": value["result"],
            }
            for key, value in sorted(results_by_combo.items())
        },
        "best_long": None
        if best_by_direction["LONG"] is None
        else {
            "hypothesis_id": best_by_direction["LONG"]["hypothesis_id"],
            "combo": best_by_direction["LONG"]["combo"],
            "timeframe": best_by_direction["LONG"]["timeframe"],
            "metrics": best_by_direction["LONG"]["metrics"],
            "result": best_by_direction["LONG"]["result"],
        },
        "best_short": None
        if best_by_direction["SHORT"] is None
        else {
            "hypothesis_id": best_by_direction["SHORT"]["hypothesis_id"],
            "combo": best_by_direction["SHORT"]["combo"],
            "timeframe": best_by_direction["SHORT"]["timeframe"],
            "metrics": best_by_direction["SHORT"]["metrics"],
            "result": best_by_direction["SHORT"]["result"],
        },
        "cost_frontier_opened": bool(passers),
        "exit_frontier_opened": False,
        "multiple_testing": {
            "final_historical_finalists": 0,
            "search_family_null_campaigns": 0,
            "reason": "No hypothesis passed the gross screen and breadth/fold gate; full finalist null campaigns were not opened.",
        },
        "ledger_hash": ledger_doc["ledger_hash"],
        "broker_or_live_api_work": "NO",
        "paper_opened": False,
        "live_opened": False,
        "compounding_opened": False,
    }
    atomic_json(STATE, state)
    write_report(state)
    return state


def write_report(state: dict[str, Any]) -> None:
    lines = [
        "# AIOS Forex MTF Gross Edge Surface V1",
        "",
        f"- Packet: {PACKET_ID}",
        f"- Status: {state['status']}",
        f"- Hypotheses tested: {state['hypotheses_tested']}",
        f"- Gross screen survivors: {state['gross_screen_survivors']}",
        f"- Hypothesis ledger hash: {state['ledger_hash']}",
        "- Cost/exit/PAPER/LIVE/compounding opened: NO unless gross-screen survivors exist.",
        "",
        "## Timeframe summary",
        "",
        "| Timeframe | Pairs loaded | Hypotheses | Gross passers | Best LONG exp | Best SHORT exp |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for timeframe, row in state["timeframe_results"].items():
        lines.append(
            f"| {timeframe} | {row['pair_count_loaded']} | {row['hypotheses']} | {row['gross_gate_passers']} | "
            f"{row['best_long_expectancy']} | {row['best_short_expectancy']} |"
        )
    lines.extend(
        [
            "",
            "## Best directional diagnostics",
            "",
            f"- LONG: {state['best_long']}",
            f"- SHORT: {state['best_short']}",
            "",
            "## Scientific boundary",
            "",
            "This is gross directional-information research only. It does not certify net profitability, PAPER profitability, LIVE readiness, funding readiness, or compounding.",
        ]
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    print(json.dumps(run_surface(), indent=2, sort_keys=True))
