"""Packet 030 affected Packet 027 evidence rerun.

This module reuses the Packet 027 executable registry/scorer against the frozen
corpus after Packet 030 trace-backed family controls are certified. It preserves
Packet 027 evidence and writes new versioned V2 evidence only.

The Packet 027 scorer returns realized R under its executable bid/ask and
financing-stress model; it does not expose an independent midpoint/zero-cost
gross path. This module therefore records gross/cost decomposition as limited
rather than inventing unavailable gross fields.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine import forex_next_generation_edge_program_v1 as p27


PACKET_ID = "PKT-EAST-FOREX-TRACE-BACKED-FIDELITY-030"
ROOT = Path(".aios/runtime/forex_repaired_family_evidence_v2")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_REPAIRED_FAMILY_EVIDENCE_V2_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_REPAIRED_FAMILY_EVIDENCE_V2_REPORT.md")
FAILURE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_FAILURE_DECOMPOSITION_V3_STATE.json")
FAILURE_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_FAILURE_DECOMPOSITION_V3_REPORT.md")
CONTROLS_STATE = Path("Reports/forex_delivery/AIOS_FOREX_TRACE_BACKED_FAMILY_CONTROLS_V2_STATE.json")
M5_STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_DAY_TRADING_ADAPTER_V2_STATE.json")


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


def certified_families(control_state: dict[str, Any]) -> set[str]:
    if control_state.get("status") != "TRACE_BACKED_FAMILY_CONTROLS_CERTIFIED":
        return set()
    return {
        str(row["family_id"])
        for row in control_state.get("rows", [])
        if row.get("trace_backed_control_valid") is True
    }


def classify_failure(summary: dict[str, Any]) -> list[str]:
    classes: list[str] = []
    trades = int(summary.get("trades", 0))
    expectancy = float(summary.get("expectancy", 0.0))
    profit_factor = float(summary.get("profit_factor", 0.0))
    drawdown = float(summary.get("max_drawdown_percent", 0.0))
    win_rate = float(summary.get("win_rate", 0.0))
    positive_fold_share = float(summary.get("folds", {}).get("positive_fold_share", 0.0))

    if trades < 50:
        classes.append("LOW_SAMPLE_ONLY")
    if expectancy <= 0 and profit_factor < 1.0:
        classes.append("NO_GROSS_SIGNAL_EDGE_UNDER_PACKET027_NET_R_SCORER")
    if expectancy > 0 and profit_factor < 1.15:
        classes.append("EDGE_BELOW_DEVELOPMENT_PROFIT_FACTOR_GATE")
    if drawdown > 10:
        classes.append("DRAWDOWN_GATE_FAILURE")
    if positive_fold_share < 0.75:
        classes.append("REGIME_INSTABILITY")
    if trades >= 50 and win_rate < 0.25 and expectancy <= 0:
        classes.append("TARGET_UNREACHABLE_OR_EXIT_CAPTURE_FAILURE")
    if not classes:
        classes.append("FAILED_REQUIRED_DEVELOPMENT_GATE")
    return classes


def family_result(rows: list[dict[str, Any]]) -> str:
    if any(row["summary"].get("pass") for row in rows):
        return "FAMILY_EDGE_FOUND"
    if rows and all(int(row["summary"].get("trades", 0)) < 50 for row in rows):
        return "FAMILY_LOW_SAMPLE"
    if any(float(row["summary"].get("expectancy", 0.0)) > 0 for row in rows):
        return "FAMILY_REGIME_OR_GATE_CONDITIONAL"
    if any("TARGET_UNREACHABLE_OR_EXIT_CAPTURE_FAILURE" in row["failure_classes"] for row in rows):
        return "FAMILY_EXIT_KILLED"
    return "FAMILY_NEGATIVE_EDGE_CONFIRMED"


def score_repaired_evidence(
    registry: list[dict[str, Any]],
    instruments: list[str],
    score_fn: Callable[[dict[str, Any], list[str], int, int], dict[str, Any]],
    certified: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in registry:
        if candidate.get("family") not in certified:
            continue
        scored = score_fn(candidate, instruments, 2005, 2018)
        summary = dict(scored["summary"])
        rows.append(
            {
                "candidate_id": scored["candidate_id"],
                "family": scored["family"],
                "direction": scored["direction"],
                "trace_status": "REUSED_PACKET027_SCORER_WITH_PACKET030_CERTIFIED_FAMILY_PRECONDITION",
                "event_count": len(scored.get("records", [])),
                "accepted_trades": int(summary.get("trades", 0)),
                "gross_expectancy": None,
                "net_expectancy": summary.get("expectancy"),
                "gross_net_decomposition": "LIMITED_BY_PACKET027_SCORER_NET_R_ONLY",
                "summary": summary,
                "failure_classes": classify_failure(summary),
            }
        )
    return rows


def build_states(max_events_per_pair: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    control_state = read_json(CONTROLS_STATE)
    certified = certified_families(control_state)
    if not certified:
        state = {
            "schema": "AIOS_FOREX_REPAIRED_FAMILY_EVIDENCE_V2_STATE",
            "packet_id": PACKET_ID,
            "status": "TRACE_CONTROLS_REQUIRED",
            "candidate_count": 0,
            "families_rerun": [],
            "state_hash": "",
        }
        state["state_hash"] = sha256_text(stable(state))
        failure = {
            "schema": "AIOS_FOREX_FAILURE_DECOMPOSITION_V3_STATE",
            "packet_id": PACKET_ID,
            "status": "NOT_RUN_TRACE_CONTROLS_REQUIRED",
            "rows": [],
            "state_hash": "",
        }
        failure["state_hash"] = sha256_text(stable(failure))
        return state, failure

    coverage = read_json(p27.COVERAGE_STATE)
    instruments = list(coverage.get("research_eligible_pairs", []))
    registry = p27.build_registry()

    def scorer(candidate: dict[str, Any], pairs: list[str], start: int, end: int) -> dict[str, Any]:
        return p27.score_candidate(candidate, pairs, start, end, max_events_per_pair=max_events_per_pair or 220)

    rows = score_repaired_evidence(registry, instruments, scorer, certified)
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_family.setdefault(row["family"], []).append(row)
    family_results = {family: family_result(family_rows) for family, family_rows in sorted(by_family.items())}
    passers = [row["candidate_id"] for row in rows if row["summary"].get("pass") is True]
    long_passers = [row["candidate_id"] for row in rows if row["direction"] == "LONG" and row["summary"].get("pass") is True]
    short_passers = [row["candidate_id"] for row in rows if row["direction"] == "SHORT" and row["summary"].get("pass") is True]

    state = {
        "schema": "AIOS_FOREX_REPAIRED_FAMILY_EVIDENCE_V2_STATE",
        "packet_id": PACKET_ID,
        "status": "AFFECTED_PACKET027_EVIDENCE_RERUN_COMPLETE",
        "input_packet027_registry_count": len(registry),
        "families_rerun": sorted(certified),
        "candidate_count": len(rows),
        "eligible_pair_count": len(instruments),
        "development_passers": passers,
        "long_development_passers": long_passers,
        "short_development_passers": short_passers,
        "family_results": family_results,
        "gross_cost_decomposition_status": "LIMITED_BY_PACKET027_SCORER_NET_R_ONLY",
        "m5_bridge_status": read_json(M5_STATE).get("status"),
        "rows": rows,
        "state_hash": "",
    }
    state["state_hash"] = sha256_text(stable(state))
    failure = {
        "schema": "AIOS_FOREX_FAILURE_DECOMPOSITION_V3_STATE",
        "packet_id": PACKET_ID,
        "status": "FAILURE_DECOMPOSITION_COMPLETE_WITH_PACKET027_GROSS_COST_LIMITATION",
        "gross_cost_decomposition_status": state["gross_cost_decomposition_status"],
        "candidate_count": len(rows),
        "class_counts": {},
        "rows": [
            {
                "candidate_id": row["candidate_id"],
                "family": row["family"],
                "direction": row["direction"],
                "accepted_trades": row["accepted_trades"],
                "net_expectancy": row["net_expectancy"],
                "failure_classes": row["failure_classes"],
            }
            for row in rows
        ],
        "state_hash": "",
    }
    counts: dict[str, int] = {}
    for row in rows:
        for klass in row["failure_classes"]:
            counts[klass] = counts.get(klass, 0) + 1
    failure["class_counts"] = dict(sorted(counts.items()))
    failure["state_hash"] = sha256_text(stable(failure))
    return state, failure


def render_report(state: dict[str, Any], failure: dict[str, Any]) -> str:
    family_lines = "\n".join(f"- {family}: {result}" for family, result in state.get("family_results", {}).items())
    return f"""# AIOS Forex Repaired Family Evidence V2

Packet: {PACKET_ID}

Status: {state['status']}

Candidates rerun: {state.get('candidate_count', 0)}

Families rerun:
{family_lines}

Development passers:
- LONG: {len(state.get('long_development_passers', []))}
- SHORT: {len(state.get('short_development_passers', []))}

Gross/cost decomposition: {state.get('gross_cost_decomposition_status')}

No Paper, LIVE, funding, broker, credential, or compounding action was performed.

State hash: {state['state_hash']}
Failure decomposition hash: {failure['state_hash']}
"""


def execute(max_events_per_pair: int | None = None) -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    state, failure = build_states(max_events_per_pair=max_events_per_pair)
    atomic_json(STATE, state)
    atomic_json(FAILURE_STATE, failure)
    REPORT.write_text(render_report(state, failure), encoding="utf-8")
    FAILURE_REPORT.write_text(render_report(state, failure), encoding="utf-8")
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-events-per-pair", type=int, default=None)
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = execute(max_events_per_pair=args.max_events_per_pair)
    print(stable({"status": state["status"], "candidate_count": state.get("candidate_count"), "long_passers": len(state.get("long_development_passers", [])), "short_passers": len(state.get("short_development_passers", []))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
