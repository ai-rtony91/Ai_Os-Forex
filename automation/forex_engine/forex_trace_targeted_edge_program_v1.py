"""Packet 030 targeted branch freeze.

This file freezes targeted branch/candidate definitions only after trace-backed
family controls, M5 bridge certification, and affected-evidence rerun state are
present. It does not claim profitability and does not open Paper/LIVE gates.
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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine import forex_next_generation_edge_program_v1 as p27


PACKET_ID = "PKT-EAST-FOREX-TRACE-BACKED-FIDELITY-030"
ROOT = Path(".aios/runtime/forex_trace_targeted_edge_program_v1")
BRANCH_STATE = Path("Reports/forex_delivery/AIOS_FOREX_TARGETED_BRANCH_SELECTION_V3_STATE.json")
BRANCH_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_TARGETED_BRANCH_SELECTION_V3_REPORT.md")
REGISTRY = Path("Reports/forex_delivery/AIOS_FOREX_TARGETED_CANDIDATE_REGISTRY_V3.json")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_TRACE_TARGETED_EDGE_PROGRAM_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_TRACE_TARGETED_EDGE_PROGRAM_V1_REPORT.md")
ATTACK_STATE = Path("Reports/forex_delivery/AIOS_FOREX_ATTACK_TO_FINISH_V8_STATE.json")
ATTACK_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_ATTACK_TO_FINISH_V8_REPORT.md")
M5_STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_DAY_TRADING_ADAPTER_V2_STATE.json")
EVIDENCE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_REPAIRED_FAMILY_EVIDENCE_V2_STATE.json")
FAILURE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_FAILURE_DECOMPOSITION_V3_STATE.json")
M5_CORPUS_STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_V2_STATE.json")


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


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


def row_mid_close(row: dict[str, Any]) -> float:
    return float(row["mid"]["c"])


def row_spread(row: dict[str, Any]) -> float:
    return max(0.0, float(row["ask"]["c"]) - float(row["bid"]["c"]))


def m5_artifact_paths(instrument: str) -> list[Path]:
    state = read_json(M5_CORPUS_STATE)
    paths: list[Path] = []
    for artifact in state.get("artifacts", []):
        if artifact.get("instrument") == instrument and artifact.get("path"):
            path = Path(str(artifact["path"]))
            paths.append(path if path.is_absolute() else Path(path))
    return sorted(paths)


def load_m5_rows(instrument: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in m5_artifact_paths(instrument):
        if not path.exists():
            continue
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    row = json.loads(line)
                    row["time"] = parse_time(row["timestamp"])
                    rows.append(row)
    rows.sort(key=lambda row: row["time"])
    return rows


def completed_h1_closes(instrument: str, decision: datetime, lookback: int = 72) -> list[float]:
    h1_rows = p27.load_h1(instrument, 2024, 2026)
    eligible = [
        float(row["mid"]["c"])
        for row in h1_rows
        if row.get("time") and row["time"] + timedelta(hours=1) <= decision
    ]
    return eligible[-lookback:]


def m5_stop(rows: list[dict[str, Any]], index: int) -> float:
    window = rows[max(0, index - 12) : index]
    ranges = [max(0.0, float(row["mid"]["h"]) - float(row["mid"]["l"])) for row in window]
    avg_range = sum(ranges) / len(ranges) if ranges else 0.0001
    return max(avg_range * 3.0, row_spread(rows[index]) * 3.0, 0.0001)


def candidate_variant(candidate: dict[str, Any]) -> int:
    text = str(candidate["candidate_id"]).split("_")[-2]
    try:
        return int(text)
    except ValueError:
        return 1


def signal_accepts(candidate: dict[str, Any], instrument: str, rows: list[dict[str, Any]], index: int) -> bool:
    if index < 80 or index + 2 >= len(rows):
        return False
    decision = rows[index]["time"]
    h1 = completed_h1_closes(instrument, decision)
    if len(h1) < 48:
        return False
    direction = candidate["direction"]
    variant = candidate_variant(candidate)
    m5_momentum = row_mid_close(rows[index]) - row_mid_close(rows[index - (6 + variant % 6)])
    h1_fast = sum(h1[-12:]) / 12
    h1_slow = sum(h1[-48:]) / 48
    h1_trend = h1_fast - h1_slow
    spread_now = row_spread(rows[index])
    recent_spreads = [row_spread(row) for row in rows[max(0, index - 36) : index]]
    spread_limit = sorted(recent_spreads)[int(0.7 * (len(recent_spreads) - 1))] if recent_spreads else spread_now
    if spread_now > spread_limit:
        return False
    threshold = max(spread_now * (1.0 + 0.1 * variant), 0.0)
    if direction == "LONG":
        return h1_trend > 0 and m5_momentum > threshold
    return h1_trend < 0 and m5_momentum < -threshold


def exit_r(candidate: dict[str, Any], rows: list[dict[str, Any]], signal_index: int) -> float | None:
    direction = candidate["direction"]
    entry_index = signal_index + 1
    if entry_index >= len(rows):
        return None
    entry_row = rows[entry_index]
    stop = m5_stop(rows, signal_index)
    entry = float(entry_row["ask"]["c"] if direction == "LONG" else entry_row["bid"]["c"])
    exit_arch = candidate.get("exit_architecture", "fixed_2r_control")
    hold = 12 if exit_arch in {"fixed_2r_control", "session_exit"} else 24
    best_r = 0.0
    final_r = 0.0
    for future in rows[entry_index : min(len(rows), entry_index + hold)]:
        if direction == "LONG":
            adverse_r = (entry - float(future["bid"]["l"])) / stop
            favorable_r = (float(future["bid"]["h"]) - entry) / stop
            final_r = (float(future["bid"]["c"]) - entry) / stop
        else:
            adverse_r = (float(future["ask"]["h"]) - entry) / stop
            favorable_r = (entry - float(future["ask"]["l"])) / stop
            final_r = (entry - float(future["ask"]["c"])) / stop
        best_r = max(best_r, favorable_r)
        if adverse_r >= 1.0:
            return -1.0
        if exit_arch == "fixed_2r_control" and favorable_r >= 2.0:
            return 2.0
        if exit_arch in {"atr_trailing_exit", "structural_exit"} and best_r > 0.75 and final_r < best_r - 0.6:
            return round(max(-1.0, min(3.0, final_r)), 6)
    financing_stress = 0.005 if hold >= 24 else 0.0
    return round(max(-1.0, min(3.0, final_r - financing_stress)), 6)


def score_m5_candidate(candidate: dict[str, Any], instruments: list[str], max_events_per_pair: int = 120) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for instrument in instruments:
        rows = load_m5_rows(instrument)
        accepted_for_pair = 0
        step = 12 + (candidate_variant(candidate) % 6)
        for index in range(80, max(80, len(rows) - 30), step):
            if accepted_for_pair >= max_events_per_pair:
                break
            if not signal_accepts(candidate, instrument, rows, index):
                continue
            result = exit_r(candidate, rows, index)
            if result is None:
                continue
            records.append(
                {
                    "instrument": instrument,
                    "year": rows[index]["time"].year,
                    "event_id": sha256_text(f"{candidate['candidate_id']}|{instrument}|{rows[index]['timestamp']}")[:24],
                    "r": result,
                }
            )
            accepted_for_pair += 1
    summary = p27.summarize(records)
    chunks = [records[i::8] for i in range(8)] if records else []
    folds = [p27.summarize(chunk) for chunk in chunks if len(chunk) >= 10]
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


def run_targeted_development(registry: list[dict[str, Any]], instruments: list[str]) -> dict[str, Any]:
    scored = [score_m5_candidate(candidate, instruments) for candidate in registry if candidate["branch"] == "M5_DAY_TRADING_MTF"]
    development_rows = [
        {"candidate_id": row["candidate_id"], "family": row["family"], "direction": row["direction"], "summary": row["summary"]}
        for row in scored
    ]
    passers = [row["candidate_id"] for row in scored if row["summary"].get("pass")]
    return {
        "status": "DEVELOPMENT_PASSERS_FOUND" if passers else "NO_DEVELOPMENT_PASSERS",
        "candidate_count": len(scored),
        "rows": development_rows,
        "passers": passers,
        "long_passers": [row["candidate_id"] for row in scored if row["direction"] == "LONG" and row["summary"].get("pass")],
        "short_passers": [row["candidate_id"] for row in scored if row["direction"] == "SHORT" and row["summary"].get("pass")],
        "_scored": scored,
    }


def null_campaigns(scored: list[dict[str, Any]], campaigns: int = 2500) -> dict[str, Any]:
    rng = random.Random(30030)
    value_map = {row["candidate_id"]: [float(record["r"]) for record in row.get("records", [])] for row in scored}
    best_nulls: list[float] = []
    for _ in range(campaigns):
        campaign_best = -999.0
        for values in value_map.values():
            if not values:
                continue
            shifted = values[:]
            rng.shuffle(shifted)
            signs = [1 if rng.random() >= 0.5 else -1 for _ in shifted]
            null_values = [abs(value) * sign for value, sign in zip(shifted, signs)]
            campaign_best = max(campaign_best, sum(null_values) / len(null_values))
        best_nulls.append(campaign_best if campaign_best > -999.0 else 0.0)
    threshold = sorted(best_nulls)[int(0.95 * (len(best_nulls) - 1))] if best_nulls else None
    rows = []
    for row in scored:
        exp = float(row["summary"].get("expectancy", 0.0))
        p_value = sum(1 for value in best_nulls if value >= exp) / len(best_nulls) if best_nulls else 1.0
        rows.append(
            {
                "candidate_id": row["candidate_id"],
                "expectancy": exp,
                "family_wise_empirical_p": round(p_value, 6),
                "pass": bool(threshold is not None and exp > threshold and p_value <= 0.05),
            }
        )
    return {"status": "NULL_CAMPAIGNS_COMPLETE", "campaigns": campaigns, "best_null_95pct": threshold, "rows": rows}


def choose_optional_branch(evidence: dict[str, Any], failure: dict[str, Any]) -> str | None:
    family_results = evidence.get("family_results", {})
    if any(result == "FAMILY_REGIME_OR_GATE_CONDITIONAL" for result in family_results.values()):
        return "REGIME_ROUTER"
    if any(result == "FAMILY_EXIT_KILLED" for result in family_results.values()):
        return "EXIT_CAPTURE"
    class_counts = failure.get("class_counts", {})
    if class_counts.get("TARGET_UNREACHABLE_OR_EXIT_CAPTURE_FAILURE", 0) >= 8:
        return "EXIT_CAPTURE"
    return None


def build_targeted_registry(branches: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    exits = ["fixed_2r_control", "time_exit", "atr_trailing_exit", "session_exit", "structural_exit"]
    contexts = ["D1_H4_H1", "H4_H1", "D1_H1", "H1_ONLY_CONTROL", "D1_H4_POLICY_H1"]
    for direction in ("LONG", "SHORT"):
        for index in range(10):
            candidate = {
                "candidate_id": f"M5_MTF_{direction}_{index + 1:02d}_V1",
                "branch": "M5_DAY_TRADING_MTF",
                "family": "M5_DAY_TRADING_MTF",
                "direction": direction,
                "novelty": "Packet030 trace-backed M5 execution bridge with completed higher-timeframe context.",
                "supporting_diagnostic_evidence": "M5_DAY_TRADING_BRIDGE_CERTIFIED; historical M5 is observed development/provisional validation only.",
                "base_event": "completed M5 candle aligned to completed higher-timeframe context",
                "context_timeframes": contexts[index % len(contexts)],
                "execution_timeframe": "M5",
                "features": ["completed_htf_context", "m5_break_or_reject", "spread_filter", "session_filter"],
                "entry": "next executable M5 interval",
                "initial_stop": "recent M5/H1 volatility stop",
                "exit_architecture": exits[index % len(exits)],
                "target_r": 2 if exits[index % len(exits)] == "fixed_2r_control" else None,
                "maximum_holding_period": "intraday",
                "risk": "0.25_percent_simulated_equity",
                "cost_financing_model": "bid_ask_single_charge_financing_stress_when_applicable",
                "currency_concurrency_rule": "bounded one position per instrument and capped currency exposure",
                "failure_condition": "fails development/statistical/forward gates or violates trace contract",
            }
            candidate["behavior_fingerprint"] = sha256_text(stable(candidate))
            candidates.append(candidate)
    if "EXIT_CAPTURE" in branches:
        for direction in ("LONG", "SHORT"):
            for index in range(3):
                candidate = {
                    "candidate_id": f"EXIT_CAPTURE_{direction}_{index + 1:02d}_V1",
                    "branch": "EXIT_CAPTURE",
                    "family": "FAITHFUL_FAMILY_CONTINUATION",
                    "direction": direction,
                    "novelty": "Uses repaired family evidence failure decomposition to test predeclared exit capture variants.",
                    "supporting_diagnostic_evidence": "Failure decomposition flagged target/exit capture pressure.",
                    "base_event": "trace-certified repaired-family base event",
                    "context_timeframes": "H1_H4_D1",
                    "execution_timeframe": "H1",
                    "features": ["repaired_family_signal", "mfe_capture_filter"],
                    "entry": "next executable interval",
                    "initial_stop": "frozen volatility stop",
                    "exit_architecture": ["time_exit", "atr_trailing_exit", "structural_exit"][index],
                    "target_r": None,
                    "maximum_holding_period": "bounded by frozen exit",
                    "risk": "0.25_percent_simulated_equity",
                    "cost_financing_model": "bid_ask_single_charge_financing_stress_when_applicable",
                    "currency_concurrency_rule": "bounded exposure",
                    "failure_condition": "fails development/statistical/forward gates",
                }
                candidate["behavior_fingerprint"] = sha256_text(stable(candidate))
                candidates.append(candidate)
    return candidates[:32]


def build_states(run_development: bool = True) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    m5 = read_json(M5_STATE)
    evidence = read_json(EVIDENCE_STATE)
    failure = read_json(FAILURE_STATE)
    branches: list[str] = []
    rejected: list[str] = []
    if m5.get("status") == "M5_DAY_TRADING_BRIDGE_CERTIFIED":
        branches.append("M5_DAY_TRADING_MTF")
    else:
        rejected.append("M5_DAY_TRADING_MTF")
    optional = choose_optional_branch(evidence, failure)
    if optional:
        branches.append(optional)
    else:
        rejected.extend(["COST_FILTERED_LIQUIDITY", "EXIT_CAPTURE", "REGIME_ROUTER", "DIRECTION_ASYMMETRY", "CROSS_SECTIONAL_PORTFOLIO", "EVENT_DRIVEN", "RELATIVE_VALUE"])
    candidates = build_targeted_registry(branches) if branches else []
    registry_hash = sha256_text(stable(candidates))
    branch_state = {
        "schema": "AIOS_FOREX_TARGETED_BRANCH_SELECTION_V3_STATE",
        "packet_id": PACKET_ID,
        "status": "TARGETED_BRANCH_FROZEN" if branches else "NO_TARGETED_BRANCH_JUSTIFIED",
        "branches": branches,
        "rejected_branches": sorted(set(rejected)),
        "selection_basis": {
            "m5_bridge_status": m5.get("status"),
            "affected_evidence_status": evidence.get("status"),
            "failure_decomposition_status": failure.get("status"),
        },
        "state_hash": "",
    }
    branch_state["state_hash"] = sha256_text(stable(branch_state))
    registry = {
        "schema": "AIOS_FOREX_TARGETED_CANDIDATE_REGISTRY_V3",
        "packet_id": PACKET_ID,
        "status": "FROZEN" if candidates else "NOT_CREATED",
        "candidate_count": len(candidates),
        "max_allowed": 32,
        "registry_hash": registry_hash,
        "registry": candidates,
    }
    coverage = read_json(p27.COVERAGE_STATE)
    instruments = list(coverage.get("research_eligible_pairs", []))
    development = {"status": "NOT_RUN_IMPLEMENTATION_PENDING", "long_passers": [], "short_passers": [], "rows": []}
    multiple_testing = {"status": "NOT_RUN_DEVELOPMENT_PENDING", "campaigns": 0, "rows": []}
    scored: list[dict[str, Any]] = []
    if candidates and run_development:
        development = run_targeted_development(candidates, instruments)
        scored = development.pop("_scored")
        multiple_testing = null_campaigns(scored)
    statistical_passers = {row["candidate_id"] for row in multiple_testing.get("rows", []) if row.get("pass")}
    development_passers = set(development.get("passers", []))
    gated_passers = development_passers & statistical_passers
    status = "TARGETED_RESEARCH_EXHAUSTED_NO_EDGE"
    if not candidates:
        status = "NO_TARGETED_BRANCH_JUSTIFIED"
    elif gated_passers:
        status = "TARGETED_DEVELOPMENT_AND_NULL_PASSERS_FOUND_VALIDATION_PENDING"

    state = {
        "schema": "AIOS_FOREX_TRACE_TARGETED_EDGE_PROGRAM_V1_STATE",
        "packet_id": PACKET_ID,
        "status": status,
        "candidate_count": len(candidates),
        "development": development,
        "multiple_testing": multiple_testing,
        "bootstrap_overfit": {"status": "NOT_RUN_DEVELOPMENT_PENDING"},
        "validation": {"status": "NOT_OPENED"},
        "holdout": {"status": "NOT_OPENED"},
        "forward": {"status": "NOT_STARTED"},
        "paper": {"status": "NOT_REACHED"},
        "profitability_milestone": "NOT_CERTIFIED",
        "state_hash": "",
    }
    state["state_hash"] = sha256_text(stable(state))
    attack = [
        {
            "blocker_id": "P0-016",
            "priority": "P0",
            "phase": "TARGETED_DEVELOPMENT",
            "family": "M5_DAY_TRADING_MTF",
            "direction": "BOTH",
            "status": "OPEN" if gated_passers else "TERMINAL_UNRESOLVABLE",
            "exact_blocker": "LONG_EDGE_NOT_PROVEN / SHORT_EDGE_NOT_PROVEN",
            "why_it_matters": "Frozen targeted candidates require Development, nulls, bootstrap, Validation, Forward, and Paper before any profitability claim.",
            "canonical_owner_file": "automation/forex_engine/forex_trace_targeted_edge_program_v1.py",
            "test_file": "tests/forex_engine/test_forex_trace_targeted_edge_program_v1.py",
            "runner_or_validator": "python -B automation/forex_engine/forex_trace_targeted_edge_program_v1.py --execute",
            "missing_evidence": "Validation, Holdout/Forward, and Paper are unavailable without Development plus null passers.",
            "repair_options": ["preserve no-edge result", "design a future separately authorized research packet if owner wants new hypotheses"],
            "chosen_action": "Run targeted Development and null campaigns; do not claim profitability.",
            "unlock_condition": "Development plus statistical controls identify valid passers.",
            "proof_of_unlock": state["status"],
            "next_action": "Implement targeted Development scorer inside the same authorized module.",
            "can_codex_resolve": True,
            "human_action_required": False,
            "external_time_required": False,
            "retry_count": 0,
            "failure_signature": "",
            "no_bloat_guard": "No candidate 33; no Paper/LIVE without gates.",
        }
    ]
    return branch_state, registry, state, attack


def render_report(branch_state: dict[str, Any], state: dict[str, Any]) -> str:
    branches = ", ".join(branch_state.get("branches", [])) or "none"
    return f"""# AIOS Forex Trace Targeted Edge Program V1

Packet: {PACKET_ID}

Branch status: {branch_state['status']}

Branches frozen: {branches}

Candidate count: {state['candidate_count']}

Development status: {state['development']['status']}

Profitability milestone: {state['profitability_milestone']}

No Paper, LIVE, funding, credential, broker, or compounding action was performed.

State hash: {state['state_hash']}
"""


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    branch_state, registry, state, attack = build_states()
    atomic_json(BRANCH_STATE, branch_state)
    atomic_json(REGISTRY, registry)
    atomic_json(STATE, state)
    atomic_json(ATTACK_STATE, {"schema": "AIOS_FOREX_ATTACK_TO_FINISH_V8_STATE", "packet_id": PACKET_ID, "status": state["status"], "blockers": attack})
    BRANCH_REPORT.write_text(render_report(branch_state, state), encoding="utf-8")
    REPORT.write_text(render_report(branch_state, state), encoding="utf-8")
    ATTACK_REPORT.write_text(render_report(branch_state, state), encoding="utf-8")
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = execute()
    print(stable({"status": state["status"], "candidate_count": state["candidate_count"], "profitability_milestone": state["profitability_milestone"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
