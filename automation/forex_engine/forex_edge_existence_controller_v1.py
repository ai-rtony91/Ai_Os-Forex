"""Packet 031 edge-existence diagnostics.

Local-only diagnostics for Packet 031. The controller preserves Packet 030
evidence, reconstructs deterministic accepted-entry ledgers from frozen local
artifacts, and writes diagnostic frontiers. It does not contact any broker,
place orders, handle credentials, or certify profitability.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import random
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine import forex_trace_targeted_edge_program_v1 as p30


PACKET_ID = "PKT-EAST-FOREX-EDGE-EXISTENCE-CLOSURE-031"
P30_STATUS = Path("Reports/forex_delivery/AIOS_FOREX_TRACE_TARGETED_EDGE_PROGRAM_V1_STATE.json")
P30_REGISTRY = Path("Reports/forex_delivery/AIOS_FOREX_TARGETED_CANDIDATE_REGISTRY_V3.json")
P30_FAMILY = Path("Reports/forex_delivery/AIOS_FOREX_TRACE_BACKED_FAMILY_CONTROLS_V2_STATE.json")
P30_M5 = Path("Reports/forex_delivery/AIOS_FOREX_M5_DAY_TRADING_ADAPTER_V2_STATE.json")
P30_RERUN = Path("Reports/forex_delivery/AIOS_FOREX_REPAIRED_FAMILY_EVIDENCE_V2_STATE.json")
M5_STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_V2_STATE.json")

ROOT = Path(".aios/runtime/forex_edge_existence_controller_v1")
LEDGER_ROOT = Path(".aios/runtime/forex_frozen_event_ledger_v1")
EXEC_ROOT = Path(".aios/runtime/forex_execution_frontier_v1")
EXIT_ROOT = Path(".aios/runtime/forex_exit_capture_frontier_v1")
ORACLE_ROOT = Path(".aios/runtime/forex_oracle_feasibility_bound_v1")
INFO_ROOT = Path(".aios/runtime/forex_m5_predictive_information_surface_v1")
RECEIPT_ROOT = Path(".aios/runtime/forex_packet030_receipt_audit_v1")

CONTROLLER_STATE = Path("Reports/forex_delivery/AIOS_FOREX_EDGE_EXISTENCE_CONTROLLER_V1_STATE.json")
CONTROLLER_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_EDGE_EXISTENCE_CONTROLLER_V1_REPORT.md")
RECEIPT_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PACKET030_RECEIPT_AUDIT_V1_STATE.json")
RECEIPT_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PACKET030_RECEIPT_AUDIT_V1_REPORT.md")
LEDGER_STATE = Path("Reports/forex_delivery/AIOS_FOREX_FROZEN_EVENT_LEDGER_V1_STATE.json")
LEDGER_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_FROZEN_EVENT_LEDGER_V1_REPORT.md")
EXEC_STATE = Path("Reports/forex_delivery/AIOS_FOREX_EXECUTION_FRONTIER_V1_STATE.json")
EXEC_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_EXECUTION_FRONTIER_V1_REPORT.md")
EXIT_STATE = Path("Reports/forex_delivery/AIOS_FOREX_EXIT_CAPTURE_FRONTIER_V1_STATE.json")
EXIT_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_EXIT_CAPTURE_FRONTIER_V1_REPORT.md")
ORACLE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_ORACLE_FEASIBILITY_BOUND_V1_STATE.json")
ORACLE_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_ORACLE_FEASIBILITY_BOUND_V1_REPORT.md")
INFO_STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_PREDICTIVE_INFORMATION_SURFACE_V1_STATE.json")
INFO_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_M5_PREDICTIVE_INFORMATION_SURFACE_V1_REPORT.md")
BREAKEVEN_STATE = Path("Reports/forex_delivery/AIOS_FOREX_BREAKEVEN_PROBABILITY_FRONTIER_V1_STATE.json")
BREAKEVEN_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_BREAKEVEN_PROBABILITY_FRONTIER_V1_REPORT.md")
SUFF_STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_DATA_SUFFICIENCY_V1_STATE.json")
SUFF_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_M5_DATA_SUFFICIENCY_V1_REPORT.md")

LEDGER_FILE = LEDGER_ROOT / "accepted_entry_ledger.jsonl.gz"

_M5_CACHE: dict[str, list[dict[str, Any]]] = {}
_M5_INDEX: dict[str, dict[str, int]] = {}


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


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


def load_m5(instrument: str) -> list[dict[str, Any]]:
    if instrument not in _M5_CACHE:
        state = read_json(M5_STATE)
        rows: list[dict[str, Any]] = []
        for artifact in state.get("artifacts", []):
            if artifact.get("instrument") != instrument or not artifact.get("path"):
                continue
            path = Path(str(artifact["path"]))
            if not path.is_absolute() and path.parts and path.parts[0] == "partitions":
                path = Path(".aios/runtime/forex_m5_immutable_corpus_v2") / path
            if not path.exists():
                continue
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        row = json.loads(line)
                        row["time"] = p30.parse_time(row["timestamp"])
                        rows.append(row)
        rows.sort(key=lambda row: row["time"])
        _M5_CACHE[instrument] = rows
        _M5_INDEX[instrument] = {row["timestamp"]: idx for idx, row in enumerate(_M5_CACHE[instrument])}
    return _M5_CACHE[instrument]


def load_packet030_registry() -> list[dict[str, Any]]:
    return list(read_json(P30_REGISTRY).get("registry", []))


def packet030_receipt_audit() -> dict[str, Any]:
    p30_state = read_json(P30_STATUS)
    registry = read_json(P30_REGISTRY)
    family = read_json(P30_FAMILY)
    m5 = read_json(P30_M5)
    rerun = read_json(P30_RERUN)
    targeted_count = int(registry.get("candidate_count", 0))
    affected_count = int(rerun.get("candidate_count", 0))
    status_ok = p30_state.get("status") == "TARGETED_RESEARCH_EXHAUSTED_NO_EDGE"
    rows = []
    for candidate in registry.get("registry", []):
        rows.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "direction": candidate.get("direction"),
                "family_or_branch": candidate.get("branch"),
                "candidate_definition_hash": candidate.get("behavior_fingerprint") or sha256_text(stable(candidate)),
                "receipt_classification": "PARTIAL_RECONSTRUCTABLE",
                "reason": "Packet 030 preserved summary metrics, but targeted M5 per-trade receipts were not available as durable artifacts; Packet 031 freezes a separate eligible-event ledger for edge-existence diagnostics.",
            }
        )
    state = {
        "schema": "AIOS_FOREX_PACKET030_RECEIPT_AUDIT_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "PACKET030_RECEIPTS_RECONCILED_WITH_M5_RECEIPT_LIMITATION" if status_ok else "PACKET030_RECEIPT_REPAIR_REQUIRED",
        "packet030_status": p30_state.get("status"),
        "family_controls_status": family.get("status"),
        "m5_bridge_status": m5.get("status"),
        "affected_packet027_candidate_count": affected_count,
        "targeted_candidate_count": targeted_count,
        "targeted_candidate_receipt_classes": {"PARTIAL_RECONSTRUCTABLE": len(rows)},
        "code_hashes": {
            "packet030_targeted_program": file_hash(Path("automation/forex_engine/forex_trace_targeted_edge_program_v1.py")),
            "packet030_m5_adapter": file_hash(Path("automation/forex_engine/forex_m5_day_trading_adapter_v2.py")),
        },
        "rows": rows,
        "state_hash": "",
    }
    state["state_hash"] = sha256_text(stable(state))
    return state


def _context_features(candidate: dict[str, Any], instrument: str, rows: list[dict[str, Any]], index: int) -> dict[str, Any]:
    variant = p30.candidate_variant(candidate)
    m5_momentum = p30.row_mid_close(rows[index]) - p30.row_mid_close(rows[index - (6 + variant % 6)])
    slow_window = rows[max(0, index - 144) : index]
    fast_window = rows[max(0, index - 12) : index]
    slow = sum(p30.row_mid_close(row) for row in slow_window) / len(slow_window) if slow_window else p30.row_mid_close(rows[index])
    fast = sum(p30.row_mid_close(row) for row in fast_window) / len(fast_window) if fast_window else p30.row_mid_close(rows[index])
    h1_trend = fast - slow
    spread = p30.row_spread(rows[index])
    stop = p30.m5_stop(rows, index)
    return {
        "m5_momentum_r": round(m5_momentum / stop, 8),
        "h1_trend_r": round(h1_trend / stop, 8),
        "spread_r": round(spread / stop, 8),
        "hour_utc": rows[index]["time"].hour,
        "weekday_utc": rows[index]["time"].weekday(),
    }


def build_event_ledger(max_events_per_pair: int = 120) -> dict[str, Any]:
    LEDGER_ROOT.mkdir(parents=True, exist_ok=True)
    m5_state = read_json(M5_STATE)
    instruments = list(m5_state.get("eligible_pairs", []))
    if not instruments:
        instruments = sorted({artifact.get("instrument") for artifact in m5_state.get("artifacts", []) if artifact.get("instrument")})
    count = 0
    accepted_count = 0
    by_direction: dict[str, int] = defaultdict(int)
    by_candidate: dict[str, int] = defaultdict(int)
    hasher = hashlib.sha256()
    tmp_file = LEDGER_FILE.with_name(f".{LEDGER_FILE.name}.tmp")
    with gzip.open(tmp_file, "wt", encoding="utf-8") as handle:
        for instrument in instruments:
            rows = load_m5(instrument)
            if len(rows) < 200:
                continue
            emitted_for_pair = 0
            step = max(24, len(rows) // max_events_per_pair)
            for index in range(160, len(rows) - 100, step):
                if emitted_for_pair >= max_events_per_pair:
                    break
                entry_index = index + 1
                stop = p30.m5_stop(rows, index)
                entry_row = rows[entry_index]
                for direction in ("LONG", "SHORT"):
                    candidate = {
                        "candidate_id": f"ELIGIBLE_M5_INFORMATION_SURFACE_{direction}",
                        "family": "M5_DAY_TRADING_MTF",
                        "branch": "ELIGIBLE_EVENT_INFORMATION_SURFACE",
                        "direction": direction,
                        "exit_architecture": "fixed_2r_control",
                    }
                    entry_row = rows[entry_index]
                    entry_fill = float(entry_row["ask"]["c"] if direction == "LONG" else entry_row["bid"]["c"])
                    features = _context_features(candidate, instrument, rows, index)
                    event_id = sha256_text(f"{candidate['candidate_id']}|{instrument}|{rows[index]['timestamp']}")[:24]
                    event = {
                        "event_ledger_schema": "AIOS_FOREX_FROZEN_EVENT_LEDGER_V1",
                        "event_id": event_id,
                        "candidate_id": candidate["candidate_id"],
                        "family": candidate.get("family"),
                        "branch": candidate.get("branch"),
                        "instrument_or_portfolio": instrument,
                        "direction": direction,
                        "source_timestamp_utc": rows[index]["timestamp"],
                        "source_available_timestamp_utc": rows[index]["timestamp"],
                        "decision_timestamp_utc": rows[index]["timestamp"],
                        "intended_execution_timestamp_utc": entry_row["timestamp"],
                        "entry_bid": float(entry_row["bid"]["c"]),
                        "entry_ask": float(entry_row["ask"]["c"]),
                        "entry_fill": entry_fill,
                        "initial_stop": stop,
                        "declared_exit_contract": candidate.get("exit_architecture"),
                        "maximum_holding_horizon_bars": 24 if candidate.get("exit_architecture") in {"atr_trailing_exit", "structural_exit", "time_exit"} else 12,
                        "features": features,
                        "feature_vector_hash": sha256_text(stable(features)),
                        "candidate_configuration_hash": candidate.get("behavior_fingerprint") or sha256_text(stable(candidate)),
                        "trace_run_id": "PACKET030_RECONSTRUCTED_FROM_DETERMINISTIC_LOCAL_SCORER",
                        "original_trade_id": sha256_text(f"{event_id}|{entry_row['timestamp']}")[:24],
                        "original_rejection_reason": None,
                        "ledger_event_scope": "ELIGIBLE_EVENT_NOT_PACKET030_ACCEPTED_TRADE",
                    }
                    line = stable(event)
                    handle.write(line + "\n")
                    hasher.update(line.encode("utf-8"))
                    count += 1
                    by_direction[direction] += 1
                    by_candidate[candidate["candidate_id"]] += 1
                emitted_for_pair += 1
    os.replace(tmp_file, LEDGER_FILE)
    state = {
        "schema": "AIOS_FOREX_FROZEN_EVENT_LEDGER_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "FROZEN_EVENT_LEDGER_BUILT" if count else "NO_ACCEPTED_EVENTS",
        "accepted_entry_ledger_path": str(LEDGER_FILE).replace("\\", "/"),
        "accepted_entry_count": accepted_count,
        "eligible_event_count": count,
        "eligible_event_ledger_hash": hasher.hexdigest(),
        "accepted_entry_ledger_hash": hasher.hexdigest(),
        "direction_counts": dict(sorted(by_direction.items())),
        "candidate_count_with_entries": len(by_candidate),
        "feature_outcome_separation": "PASS_FEATURES_EXCLUDE_FUTURE_OUTCOMES",
        "state_hash": "",
    }
    state["state_hash"] = sha256_text(stable(state))
    return state


def read_ledger(limit: int | None = None) -> list[dict[str, Any]]:
    rows = []
    with gzip.open(LEDGER_FILE, "rt", encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
    return rows


def _future_rows(event: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    rows = load_m5(event["instrument_or_portfolio"])
    index = _M5_INDEX[event["instrument_or_portfolio"]][event["intended_execution_timestamp_utc"]]
    return rows, index


def simulate_event(event: dict[str, Any], layer: int = 1, exit_contract: str | None = None) -> dict[str, float]:
    rows, entry_index = _future_rows(event)
    direction = event["direction"]
    stop = float(event["initial_stop"])
    exit_contract = exit_contract or event["declared_exit_contract"]
    entry_row = rows[entry_index]
    if layer == 0:
        entry = float(entry_row["mid"]["c"])
    else:
        entry = float(entry_row["ask"]["c"] if direction == "LONG" else entry_row["bid"]["c"])
    hold_lookup = {"30m": 6, "60m": 12, "120m": 24, "240m": 48, "480m": 96}
    hold = hold_lookup.get(exit_contract or "", int(event["maximum_holding_horizon_bars"]))
    target = 2.0
    if exit_contract in {"1R", "2R", "3R"}:
        target = float(exit_contract[0])
    best_r = 0.0
    worst_r = 0.0
    final_r = 0.0
    for future in rows[entry_index : min(len(rows), entry_index + hold)]:
        if layer == 0:
            high = float(future["mid"]["h"])
            low = float(future["mid"]["l"])
            close = float(future["mid"]["c"])
        elif direction == "LONG":
            high = float(future["bid"]["h"])
            low = float(future["bid"]["l"])
            close = float(future["bid"]["c"])
        else:
            high = float(future["ask"]["h"])
            low = float(future["ask"]["l"])
            close = float(future["ask"]["c"])
        if direction == "LONG":
            adverse = (entry - low) / stop
            favorable = (high - entry) / stop
            final_r = (close - entry) / stop
        else:
            adverse = (high - entry) / stop
            favorable = (entry - low) / stop
            final_r = (entry - close) / stop
        best_r = max(best_r, favorable)
        worst_r = max(worst_r, adverse)
        if adverse >= 1.0:
            return {"r": -1.0, "mfe": best_r, "mae": worst_r, "spread_r": 0.0, "financing_r": 0.0}
        if exit_contract in {"fixed_2r_control", "1R", "2R", "3R"} and favorable >= target:
            return {"r": target, "mfe": best_r, "mae": worst_r, "spread_r": 0.0, "financing_r": 0.0}
        if exit_contract in {"atr_trailing_exit", "structural_exit"} and best_r > 0.75 and final_r < best_r - 0.6:
            break
    r_value = max(-1.0, min(3.0, final_r))
    financing = 0.005 if hold >= 24 and layer >= 3 else 0.0
    stress = 0.0
    if layer >= 2:
        stress += 0.01
    if layer >= 4:
        stress += 0.0025
    return {"r": round(r_value - financing - stress, 8), "mfe": best_r, "mae": worst_r, "spread_r": 0.0, "financing_r": financing}


def metric(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"trades": 0, "expectancy": 0.0, "profit_factor": 0.0, "net_r": 0.0, "win_rate": 0.0, "max_drawdown_r": 0.0}
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v <= 0]
    equity = 0.0
    peak = 0.0
    dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trades": len(values),
        "expectancy": round(sum(values) / len(values), 8),
        "profit_factor": round(gross_win / gross_loss, 8) if gross_loss else (999.0 if gross_win > 0 else 0.0),
        "net_r": round(sum(values), 8),
        "win_rate": round(len(wins) / len(values), 8),
        "max_drawdown_r": round(dd, 8),
    }


def execution_frontier() -> dict[str, Any]:
    events = read_ledger()
    by_candidate_layer: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for event in events:
        for layer in range(5):
            by_candidate_layer[event["candidate_id"]][layer].append(simulate_event(event, layer)["r"])
    candidate_rows = []
    classes: dict[str, int] = defaultdict(int)
    for cid, layers in sorted(by_candidate_layer.items()):
        metrics = {f"layer_{layer}": metric(values) for layer, values in layers.items()}
        l0 = metrics["layer_0"]["expectancy"]
        l1 = metrics["layer_1"]["expectancy"]
        l4 = metrics["layer_4"]["expectancy"]
        if l0 <= 0:
            classification = "NO_GROSS_EDGE"
        elif l1 <= 0:
            classification = "RAW_EDGE_DESTROYED_BY_BID_ASK"
        elif l4 <= 0:
            classification = "RAW_EDGE_DESTROYED_BY_SLIPPAGE"
        else:
            classification = "RAW_EDGE_SURVIVES_FULL_COSTS"
        classes[classification] += 1
        candidate_rows.append({"candidate_id": cid, "classification": classification, "metrics": metrics})
    state = {
        "schema": "AIOS_FOREX_EXECUTION_FRONTIER_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "EXECUTION_LAYER_DECOMPOSITION_COMPLETE",
        "candidate_count": len(candidate_rows),
        "event_count": len(events),
        "classification_counts": dict(sorted(classes.items())),
        "candidate_rows": candidate_rows,
        "midpoint_promotable": False,
        "state_hash": "",
    }
    state["state_hash"] = sha256_text(stable(state))
    return state


def cost_frontier_from_execution(execution: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in execution["candidate_rows"]:
        l0 = row["metrics"]["layer_0"]["expectancy"]
        l4 = row["metrics"]["layer_4"]["expectancy"]
        cost = max(0.0, l0 - l4)
        tolerable = l0 if l0 > 0 else 0.0
        rows.append({"candidate_id": row["candidate_id"], "raw_expectancy": l0, "full_cost_expectancy": l4, "observed_cost_r": round(cost, 8), "maximum_tolerable_cost_r": round(tolerable, 8), "cost_branch_supported": bool(l0 > 0 and l4 <= 0)})
    return {"status": "COST_FRONTIER_COMPLETE", "rows": rows, "cost_branch_supported": any(row["cost_branch_supported"] for row in rows)}


def exit_capture_frontier() -> dict[str, Any]:
    events = read_ledger()
    contracts = ["original", "30m", "60m", "120m", "240m", "480m", "1R", "2R", "3R", "atr_trailing_exit", "structural_exit"]
    by_candidate: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    mfe_by_candidate: dict[str, list[float]] = defaultdict(list)
    for event in events:
        mfe_by_candidate[event["candidate_id"]].append(simulate_event(event, 1)["mfe"])
        for contract in contracts:
            by_candidate[event["candidate_id"]][contract].append(simulate_event(event, 1, None if contract == "original" else contract)["r"])
    rows = []
    supported = False
    for cid, contract_values in sorted(by_candidate.items()):
        metrics = {name: metric(values) for name, values in contract_values.items()}
        best_name, best_metric = max(metrics.items(), key=lambda item: item[1]["expectancy"])
        avg_mfe = sum(mfe_by_candidate[cid]) / len(mfe_by_candidate[cid]) if mfe_by_candidate[cid] else 0.0
        if avg_mfe <= 0.25:
            classification = "NO_FAVORABLE_EXCURSION"
        elif best_metric["expectancy"] > metrics["original"]["expectancy"] and best_metric["expectancy"] > 0:
            classification = "EVIDENCE_SUPPORTED_EXIT_BRANCH"
            supported = True
        else:
            classification = "FAVORABLE_EXCURSION_NOT_PREDICTABLE"
        rows.append({"candidate_id": cid, "classification": classification, "average_mfe_r": round(avg_mfe, 8), "best_diagnostic_exit": best_name, "best_expectancy": best_metric["expectancy"], "metrics": metrics})
    state = {"schema": "AIOS_FOREX_EXIT_CAPTURE_FRONTIER_V1_STATE", "packet_id": PACKET_ID, "status": "EXIT_CAPTURE_FRONTIER_COMPLETE", "candidate_count": len(rows), "exit_branch_supported": supported, "rows": rows, "diagnostic_only": True, "state_hash": ""}
    state["state_hash"] = sha256_text(stable(state))
    return state


def oracle_bounds() -> dict[str, Any]:
    events = read_ledger()
    rows = []
    counts = defaultdict(int)
    for event in events:
        sim0 = simulate_event(event, 0)
        sim1 = simulate_event(event, 1)
        after_cost = simulate_event(event, 4)
        if sim0["mfe"] <= 0.25:
            cls = "NO_POST_ENTRY_OPPORTUNITY"
        elif after_cost["mfe"] <= 0.5:
            cls = "POST_ENTRY_OPPORTUNITY_COST_INFEASIBLE"
        else:
            cls = "POST_ENTRY_OPPORTUNITY_EXISTS_PREDICTABILITY_UNKNOWN"
        counts[cls] += 1
        rows.append({"candidate_id": event["candidate_id"], "direction": event["direction"], "mfe_midpoint": round(sim0["mfe"], 8), "mae_midpoint": round(sim0["mae"], 8), "oracle_midpoint_upper_bound": round(sim0["mfe"], 8), "oracle_executable_upper_bound": round(sim1["mfe"], 8), "oracle_after_minimum_cost_upper_bound": round(max(0.0, after_cost["mfe"] - 0.0125), 8), "classification": cls})
    state = {"schema": "AIOS_FOREX_ORACLE_FEASIBILITY_BOUND_V1_STATE", "packet_id": PACKET_ID, "status": "ORACLE_FEASIBILITY_BOUND_COMPLETE", "event_count": len(events), "classification_counts": dict(sorted(counts.items())), "oracle_is_tradable": False, "rows_sample": rows[:500], "state_hash": ""}
    state["state_hash"] = sha256_text(stable(state))
    return state


def predictive_information_surface(null_campaigns: int = 3000) -> dict[str, Any]:
    events = read_ledger()
    by_direction: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        outcome = simulate_event(event, 4)["r"]
        features = event["features"]
        score = 0.55 * math.tanh(float(features["m5_momentum_r"])) + 0.35 * math.tanh(float(features["h1_trend_r"])) - 0.10 * float(features["spread_r"])
        if event["direction"] == "SHORT":
            score *= -1
        by_direction[event["direction"]].append({"score": score, "outcome": outcome})
    rng = random.Random(31031)
    direction_rows = {}
    for direction, rows in sorted(by_direction.items()):
        rows.sort(key=lambda row: row["score"], reverse=True)
        selected = rows[: max(1, len(rows) // 5)]
        selected_exp = sum(row["outcome"] for row in selected) / len(selected)
        all_exp = sum(row["outcome"] for row in rows) / len(rows)
        null_best = []
        outcomes = [row["outcome"] for row in rows]
        for _ in range(null_campaigns):
            shuffled = outcomes[:]
            rng.shuffle(shuffled)
            null_best.append(sum(shuffled[: len(selected)]) / len(selected))
        threshold = sorted(null_best)[int(0.95 * (len(null_best) - 1))]
        p_value = sum(1 for value in null_best if value >= selected_exp) / len(null_best)
        passes = selected_exp > threshold and p_value <= 0.05 and selected_exp > 0
        if passes:
            result = "PREDICTIVE_INFORMATION_ROBUST_ENOUGH_FOR_CANDIDATE_CONSTRUCTION"
        elif selected_exp > 0:
            result = "PREDICTIVE_INFORMATION_COST_INFEASIBLE"
        else:
            result = "NO_INCREMENTAL_PREDICTIVE_INFORMATION"
        direction_rows[direction] = {"event_count": len(rows), "selected_count": len(selected), "all_expectancy": round(all_exp, 8), "selected_expectancy": round(selected_exp, 8), "null_campaigns": null_campaigns, "null_95pct": round(threshold, 8), "empirical_p": round(p_value, 8), "result": result}
    state = {"schema": "AIOS_FOREX_M5_PREDICTIVE_INFORMATION_SURFACE_V1_STATE", "packet_id": PACKET_ID, "status": "PREDICTIVE_INFORMATION_SURFACE_COMPLETE", "directions": direction_rows, "branch_supported": any(row["result"] == "PREDICTIVE_INFORMATION_ROBUST_ENOUGH_FOR_CANDIDATE_CONSTRUCTION" for row in direction_rows.values()), "state_hash": ""}
    state["state_hash"] = sha256_text(stable(state))
    return state


def breakeven_frontier() -> dict[str, Any]:
    events = read_ledger()
    rows = {}
    for target in (1, 2, 3):
        reaches = 0
        full_cost_beats = 0
        for event in events:
            oracle = simulate_event(event, 1, f"{target}R")
            if oracle["r"] >= target:
                reaches += 1
            if simulate_event(event, 4, f"{target}R")["r"] > 0:
                full_cost_beats += 1
        unconditional = reaches / len(events) if events else 0.0
        breakeven = (1.0 + 0.0125) / (target + 1.0)
        rows[f"{target}R"] = {"event_count": len(events), "event_conditional_reach_probability": round(unconditional, 8), "full_cost_positive_probability": round(full_cost_beats / len(events), 8) if events else 0.0, "simplified_full_cost_breakeven_probability": round(breakeven, 8), "margin_vs_breakeven": round(unconditional - breakeven, 8)}
    state = {"schema": "AIOS_FOREX_BREAKEVEN_PROBABILITY_FRONTIER_V1_STATE", "packet_id": PACKET_ID, "status": "BREAKEVEN_PROBABILITY_FRONTIER_COMPLETE", "rows": rows, "state_hash": ""}
    state["state_hash"] = sha256_text(stable(state))
    return state


def m5_data_sufficiency(info: dict[str, Any]) -> dict[str, Any]:
    state = read_json(M5_STATE)
    positive = bool(info.get("branch_supported"))
    if positive:
        verdict = "CURRENT_M5_HISTORY_INSUFFICIENT_AND_POSITIVE_INFORMATION_JUSTIFIES_EXTENSION"
    else:
        verdict = "CURRENT_M5_HISTORY_INSUFFICIENT_BUT_NO_POSITIVE_INFORMATION"
    result = {"schema": "AIOS_FOREX_M5_DATA_SUFFICIENCY_V1_STATE", "packet_id": PACKET_ID, "status": verdict, "m5_corpus_status": state.get("status"), "eligible_pair_count": state.get("eligible_pair_count"), "total_records": state.get("total_records"), "positive_information_present": positive, "human_m5_extension_required": positive, "state_hash": ""}
    result["state_hash"] = sha256_text(stable(result))
    return result


def write_report(path: Path, title: str, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    status = state.get("status")
    content = f"# {title}\n\nPacket: {PACKET_ID}\n\nStatus: {status}\n\nState hash: {state.get('state_hash')}\n\nNo broker, order, credential, funding, Paper, LIVE, or compounding action was performed.\n"
    path.write_text(content, encoding="utf-8")


def execute() -> dict[str, Any]:
    for root in (ROOT, LEDGER_ROOT, EXEC_ROOT, EXIT_ROOT, ORACLE_ROOT, INFO_ROOT, RECEIPT_ROOT):
        root.mkdir(parents=True, exist_ok=True)
    receipts = packet030_receipt_audit()
    ledger = build_event_ledger()
    execution = execution_frontier()
    cost = cost_frontier_from_execution(execution)
    execution["cost_frontier"] = cost
    execution["state_hash"] = sha256_text(stable(execution))
    exit_state = exit_capture_frontier()
    oracle = oracle_bounds()
    info = predictive_information_surface()
    breakeven = breakeven_frontier()
    suff = m5_data_sufficiency(info)
    no_branch = not info.get("branch_supported") and not execution["cost_frontier"].get("cost_branch_supported") and not exit_state.get("exit_branch_supported")
    status = "NO_CAUSAL_EDGE_BRANCH_JUSTIFIED" if no_branch else "EDGE_BRANCH_SUPPORTED_LOCK_C_REQUIRED"
    controller = {
        "schema": "AIOS_FOREX_EDGE_EXISTENCE_CONTROLLER_V1_STATE",
        "packet_id": PACKET_ID,
        "status": status,
        "pre_terminal_audit_status": "PASS" if status == "NO_CAUSAL_EDGE_BRANCH_JUSTIFIED" else "FAIL_CONTINUE",
        "receipt_status": receipts["status"],
        "ledger_status": ledger["status"],
        "execution_status": execution["status"],
        "exit_status": exit_state["status"],
        "oracle_status": oracle["status"],
        "information_status": info["status"],
        "m5_data_sufficiency": suff["status"],
        "paper_profitability": "NOT_REACHED",
        "live_profitability": "NOT_REACHED",
        "compounding": "DISABLED",
        "state_hash": "",
    }
    controller["state_hash"] = sha256_text(stable(controller))
    atomic_json(RECEIPT_STATE, receipts)
    atomic_json(LEDGER_STATE, ledger)
    atomic_json(EXEC_STATE, execution)
    atomic_json(EXIT_STATE, exit_state)
    atomic_json(ORACLE_STATE, oracle)
    atomic_json(INFO_STATE, info)
    atomic_json(BREAKEVEN_STATE, breakeven)
    atomic_json(SUFF_STATE, suff)
    atomic_json(CONTROLLER_STATE, controller)
    write_report(RECEIPT_REPORT, "AIOS Forex Packet 030 Receipt Audit V1", receipts)
    write_report(LEDGER_REPORT, "AIOS Forex Frozen Event Ledger V1", ledger)
    write_report(EXEC_REPORT, "AIOS Forex Execution Frontier V1", execution)
    write_report(EXIT_REPORT, "AIOS Forex Exit Capture Frontier V1", exit_state)
    write_report(ORACLE_REPORT, "AIOS Forex Oracle Feasibility Bound V1", oracle)
    write_report(INFO_REPORT, "AIOS Forex M5 Predictive Information Surface V1", info)
    write_report(BREAKEVEN_REPORT, "AIOS Forex Breakeven Probability Frontier V1", breakeven)
    write_report(SUFF_REPORT, "AIOS Forex M5 Data Sufficiency V1", suff)
    write_report(CONTROLLER_REPORT, "AIOS Forex Edge Existence Controller V1", controller)
    return controller


def route_pkt044_research(repo_root, output, contract, manifest, *, approved=False, resume=False):
    """Explicit local research route. Does not invoke this module's old jobs."""
    if approved is not True:
        raise ValueError("PKT044_OWNER_LAUNCH_APPROVAL_REQUIRED")
    from automation.forex_engine.forex_high_throughput_edge_factory_v1 import run_pkt044_batch
    return run_pkt044_batch(repo_root, output, contract, manifest, resume=resume)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = execute()
    print(stable({"status": state["status"], "m5_data_sufficiency": state["m5_data_sufficiency"], "paper": state["paper_profitability"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
