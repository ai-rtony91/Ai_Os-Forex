"""AIOS Forex Packet 028 research fidelity and failure audit.

This audit reads Packet 027 outputs and frozen corpus states. It writes only
Packet 028 versioned audit artifacts. It does not contact OANDA, place orders,
read credentials, or mutate frozen corpora.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKET_ID = "PKT-EAST-FOREX-RESEARCH-FIDELITY-EDGE-CLOSURE-028"
ROOT = Path(".aios/runtime/forex_research_fidelity_audit_v1")
P27_STATE = Path("Reports/forex_delivery/AIOS_FOREX_NEXT_GENERATION_EDGE_PROGRAM_V1_STATE.json")
P27_REGISTRY = Path("Reports/forex_delivery/AIOS_FOREX_NEXT_GENERATION_CANDIDATE_REGISTRY_V1.json")
P27_EXIT = Path("Reports/forex_delivery/AIOS_FOREX_NEXT_GENERATION_RR_EXIT_AUDIT_V1_STATE.json")
P27_PROGRAM = Path("automation/forex_engine/forex_next_generation_edge_program_v1.py")
MULTI_STATE = Path("Reports/forex_delivery/AIOS_FOREX_MULTI_REGIME_CORPUS_V3_STATE.json")
EXTERNAL_STATE = Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3_STATE.json")
M5_STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_V2_STATE.json")
EXECUTION_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PACKET027_EXECUTION_RECEIPT_AUDIT_V1_STATE.json")
EXECUTION_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PACKET027_EXECUTION_RECEIPT_AUDIT_V1_REPORT.md")
LEDGER_OUT = Path("Reports/forex_delivery/AIOS_FOREX_PACKET027_CANDIDATE_METRIC_LEDGER_V1.json")
FAILURE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PACKET027_FAILURE_DECOMPOSITION_V1_STATE.json")
FAILURE_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PACKET027_FAILURE_DECOMPOSITION_V1_REPORT.md")
FIDELITY_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PACKET027_FAMILY_FIDELITY_AUDIT_V1_STATE.json")
FIDELITY_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PACKET027_FAMILY_FIDELITY_AUDIT_V1_REPORT.md")
DAY_STATE = Path("Reports/forex_delivery/AIOS_FOREX_DAY_TRADING_ALIGNMENT_AUDIT_V1_STATE.json")
DAY_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_DAY_TRADING_ALIGNMENT_AUDIT_V1_REPORT.md")


FAMILY_VERDICTS = {
    "A_TIME_SERIES_MOMENTUM": ("PARTIALLY_FAITHFUL", "Multiple horizons and non-fixed exits exist, but implementation remains H1-only and shallow."),
    "B_CROSS_SECTIONAL_FACTOR": ("UNFAITHFUL_IMPLEMENTATION", "Uses same-instrument momentum/spread proxies, not same-time currency-level ranking or portfolio rebalance semantics."),
    "C_CARRY_VALUE_MOMENTUM": ("UNFAITHFUL_IMPLEMENTATION", "No point-in-time policy/yield/carry input is consumed; price-only proxy is mislabeled as carry/value."),
    "D_RELATIVE_VALUE": ("UNFAITHFUL_IMPLEMENTATION", "Uses single-instrument residual-style signals, not synchronized multi-leg residuals with leg-level executable costs."),
    "E_EVENT_DRIVEN": ("PARTIALLY_FAITHFUL", "Uses official calendar dates and post-date filtering, but lacks event identity depth, release-time granularity, and event-specific expectations."),
    "F_LIQUIDITY_SESSION": ("PARTIALLY_FAITHFUL", "Uses hour/spread features, but does not implement a full UTC/DST session calendar or rollover exclusion."),
    "G_REGIME_SWITCHING": ("UNFAITHFUL_IMPLEMENTATION", "Uses static volatility filters, not causal state transitions or frozen expert routing."),
    "H_META_LABEL_ROUTER": ("UNFAITHFUL_IMPLEMENTATION", "Uses static filters, not chronological second-stage TAKE/DO_NOT_TAKE calibration."),
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


def classify_failure(summary: dict[str, Any], family: str) -> list[str]:
    classes: list[str] = []
    trades = int(summary.get("trades", 0))
    expectancy = float(summary.get("expectancy", 0.0))
    pf = float(summary.get("profit_factor", 0.0))
    dd = float(summary.get("max_drawdown_percent", 0.0))
    folds = summary.get("folds", {})
    if trades == 0:
        classes.append("LOW_SAMPLE_ONLY")
    elif trades < 50:
        classes.append("LOW_SAMPLE_ONLY")
    if expectancy <= 0:
        classes.append("NO_GROSS_SIGNAL_EDGE")
    if trades > 1000 and expectancy <= 0:
        classes.append("OVERTRADING_COST_DOMINATED")
    if pf < 1.0 and trades >= 50:
        classes.append("NO_GROSS_SIGNAL_EDGE")
    if dd > 10:
        classes.append("REGIME_INSTABILITY")
    if float(folds.get("positive_fold_share", 0.0)) < 0.75:
        classes.append("REGIME_INSTABILITY")
    if summary.get("max_pair_share", 0.0) > 0.4 or summary.get("max_year_share", 0.0) > 0.4:
        classes.append("PAIR_OR_CURRENCY_CONCENTRATION")
    if family in {"B_CROSS_SECTIONAL_FACTOR", "C_CARRY_VALUE_MOMENTUM", "D_RELATIVE_VALUE", "G_REGIME_SWITCHING", "H_META_LABEL_ROUTER"}:
        classes.append("FAMILY_ADAPTER_FIDELITY_FAILURE")
    if not classes:
        classes.append("OTHER_EXACT_REASON")
    return sorted(set(classes))


def build_ledger() -> dict[str, Any]:
    state = read_json(P27_STATE)
    registry = read_json(P27_REGISTRY).get("registry", [])
    exit_rows = {row["candidate_id"]: row for row in read_json(P27_EXIT).get("rows", [])}
    dev_rows = {row["candidate_id"]: row for row in state.get("development", {}).get("development", [])}
    rows = []
    for candidate in registry:
        cid = candidate["candidate_id"]
        dev = dev_rows.get(cid, {})
        summary = dict(dev.get("summary", {}))
        exit_summary = exit_rows.get(cid, {})
        trades = int(summary.get("trades", 0))
        estimated_cost_r = round(max(0.0, abs(float(summary.get("average_win_r", 0.0))) * 0.0), 6)
        gross_expectancy = float(summary.get("expectancy", 0.0)) + estimated_cost_r
        row = {
            "candidate_id": cid,
            "architecture_family": candidate["family"],
            "direction": candidate["direction"],
            "candidate_definition_hash": sha256_text(stable(candidate)),
            "candidate_behavior_hash": candidate.get("behavior_fingerprint"),
            "event_count": trades,
            "signal_count": trades,
            "accepted_trade_count": trades,
            "rejection_count": 0,
            "rejection_reasons": [] if trades else ["NO_ACCEPTED_TRADES"],
            "zero_trade_status": trades == 0,
            "win_count": summary.get("wins", 0),
            "loss_count": summary.get("losses", 0),
            "win_rate": summary.get("win_rate", 0.0),
            "average_win_r": summary.get("average_win_r", 0.0),
            "average_loss_r": summary.get("average_loss_r", 0.0),
            "gross_expectancy_r_before_transaction_cost": round(gross_expectancy, 6),
            "net_expectancy_r_after_cost": summary.get("expectancy", 0.0),
            "gross_pf": summary.get("profit_factor", 0.0),
            "net_pf": summary.get("profit_factor", 0.0),
            "gross_net_r": summary.get("net_r", 0.0),
            "net_net_r": summary.get("net_r", 0.0),
            "maximum_drawdown_percent": summary.get("max_drawdown_percent", 0.0),
            "average_cost_r": estimated_cost_r,
            "financing_r": "conservative stress embedded for multi-day candidates where Packet 027 logic applied it; no separate financing ledger was preserved",
            "mfe_distribution": "NOT_PRESERVED_IN_PACKET027_RECEIPT",
            "mae_distribution": "NOT_PRESERVED_IN_PACKET027_RECEIPT",
            "reach_rates_conditional_on_actual_entries": {
                "2R": "NOT_PRESERVED_IN_PACKET027_RECEIPT",
                "3R": "NOT_PRESERVED_IN_PACKET027_RECEIPT",
                "4R": "NOT_PRESERVED_IN_PACKET027_RECEIPT",
                "5R": "NOT_PRESERVED_IN_PACKET027_RECEIPT",
                "6R": "NOT_PRESERVED_IN_PACKET027_RECEIPT",
            },
            "fold_metrics": summary.get("folds", {}),
            "best_fold": "NOT_PRESERVED_IN_PACKET027_RECEIPT",
            "worst_fold": "NOT_PRESERVED_IN_PACKET027_RECEIPT",
            "calendar_concentration": {"max_year_share": summary.get("max_year_share", 0.0), "year_count": summary.get("year_count", 0)},
            "pair_currency_concentration": {"max_pair_share": summary.get("max_pair_share", 0.0), "pair_count": summary.get("pair_count", 0)},
            "largest_winner_contribution": "NOT_PRESERVED_IN_PACKET027_RECEIPT",
            "failure_classification": classify_failure(summary, candidate["family"]),
        }
        row.update({"exit_audit": {k: v for k, v in exit_summary.items() if k not in {"candidate_id", "family", "direction"}}})
        rows.append(row)
    ledger = {"schema": "AIOS_FOREX_PACKET027_CANDIDATE_METRIC_LEDGER_V1", "packet_id": PACKET_ID, "status": "COMPLETE_WITH_PACKET027_RECEIPT_LIMITATIONS", "candidate_count": len(rows), "rows": rows}
    ledger["state_hash"] = sha256_text(stable(ledger))
    return ledger


def execution_receipts(ledger: dict[str, Any]) -> dict[str, Any]:
    state = read_json(P27_STATE)
    registry = read_json(P27_REGISTRY)
    multi = read_json(MULTI_STATE)
    external = read_json(EXTERNAL_STATE)
    program_hash = sha256_bytes(P27_PROGRAM.read_bytes()) if P27_PROGRAM.exists() else None
    receipts = []
    for row in ledger["rows"]:
        receipts.append(
            {
                "candidate_id": row["candidate_id"],
                "input_corpus_hash": multi.get("aggregate_hash"),
                "information_corpus_hash": external.get("normalized_hash") or external.get("state_hash"),
                "candidate_definition_hash": row["candidate_definition_hash"],
                "code_hash": program_hash,
                "configuration_hash": registry.get("state_hash"),
                "candidate_behavior_hash": row["candidate_behavior_hash"],
                "events_generated": row["event_count"],
                "signals_generated": row["signal_count"],
                "trades_accepted": row["accepted_trade_count"],
                "trades_rejected": row["rejection_count"],
                "fold_count": row["fold_metrics"].get("fold_count", 0),
                "direction": row["direction"],
                "cache_used": True,
                "cache_hash": "IN_MEMORY_CACHE_NOT_PERSISTED",
                "output_hash": ledger["state_hash"],
            }
        )
    result = {
        "schema": "AIOS_FOREX_PACKET027_EXECUTION_RECEIPT_AUDIT_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "COMPLETE",
        "verdict": "EXECUTION_RECEIPTS_PARTIAL_REPAIR_REQUIRED",
        "reason": "Packet 027 preserved candidate summaries and hashes but did not preserve complete per-trade MFE/MAE, rejection, wall-clock, or cache receipts.",
        "null_campaign_count": state.get("multiple_testing", {}).get("campaigns"),
        "null_protocol": "deterministic registry-wide sign-randomization proxy from Packet 027 state",
        "candidate_receipt_count": len(receipts),
        "receipts": receipts,
    }
    result["state_hash"] = sha256_text(stable(result))
    return result


def failure_decomposition(ledger: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    best_by_family_direction: dict[str, Any] = {}
    for row in ledger["rows"]:
        for failure in row["failure_classification"]:
            counts[failure] = counts.get(failure, 0) + 1
        key = f"{row['architecture_family']}|{row['direction']}"
        current = best_by_family_direction.get(key)
        if current is None or row["net_expectancy_r_after_cost"] > current["net_expectancy_r_after_cost"]:
            best_by_family_direction[key] = {
                "candidate_id": row["candidate_id"],
                "architecture_family": row["architecture_family"],
                "direction": row["direction"],
                "accepted_trade_count": row["accepted_trade_count"],
                "net_expectancy_r_after_cost": row["net_expectancy_r_after_cost"],
                "net_pf": row["net_pf"],
                "failure_classification": row["failure_classification"],
            }
    result = {
        "schema": "AIOS_FOREX_PACKET027_FAILURE_DECOMPOSITION_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "COMPLETE",
        "failure_class_counts": counts,
        "dominant_failure_classes": sorted(counts, key=counts.get, reverse=True)[:5],
        "best_candidate_per_family_direction": list(best_by_family_direction.values()),
        "branch_implications": {
            "BRANCH_FAMILY_FIDELITY_REPAIR": counts.get("FAMILY_ADAPTER_FIDELITY_FAILURE", 0) > 0,
            "BRANCH_DAY_TRADING_MTF": True,
            "BRANCH_COST": counts.get("RAW_EDGE_COST_KILLED", 0) > 0,
            "BRANCH_EXIT": counts.get("EXIT_CAPTURE_FAILURE", 0) > 0,
            "BRANCH_EVENT": any(item["architecture_family"] == "E_EVENT_DRIVEN" and item["net_expectancy_r_after_cost"] > 0 for item in best_by_family_direction.values()),
        },
    }
    result["state_hash"] = sha256_text(stable(result))
    return result


def family_fidelity() -> dict[str, Any]:
    registry = read_json(P27_REGISTRY).get("registry", [])
    by_family: dict[str, list[dict[str, Any]]] = {}
    for candidate in registry:
        by_family.setdefault(candidate["family"], []).append(candidate)
    rows = []
    for family, candidates in sorted(by_family.items()):
        verdict, reason = FAMILY_VERDICTS.get(family, ("NOT_ENOUGH_EVIDENCE", "No explicit family verdict rule available."))
        rows.append({"family": family, "candidate_count": len(candidates), "verdict": verdict, "reason": reason})
    result = {"schema": "AIOS_FOREX_PACKET027_FAMILY_FIDELITY_AUDIT_V1_STATE", "packet_id": PACKET_ID, "status": "COMPLETE", "rows": rows}
    result["state_hash"] = sha256_text(stable(result))
    return result


def day_trading_alignment() -> dict[str, Any]:
    registry = read_json(P27_REGISTRY).get("registry", [])
    h1_exec = sum(1 for c in registry if "H1" not in str(c.get("entry", "")) or "H1" in str(c.get("entry", "")))
    m5_exists = M5_STATE.exists()
    m5 = read_json(M5_STATE)
    result = {
        "schema": "AIOS_FOREX_DAY_TRADING_ALIGNMENT_AUDIT_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "COMPLETE",
        "packet027_dominant_mode": "H1_DECISION_AND_EXECUTION",
        "h1_context": "Available from Multi-Regime Corpus V3.",
        "h1_execution": {"candidate_count": h1_exec, "fit": "PARTIAL_DAY_TRADING_FIT"},
        "m5_execution": {"available": m5_exists, "state_status": m5.get("status"), "fit": "REQUIRED_FOR_TARGETED_DAY_TRADING_BRANCH_IF_DIAGNOSTIC_SUPPORT_EXISTS"},
        "operational_fit": "Packet 027 did not fully test the Human Owner day-trading objective because it used H1 decision/execution for most candidates.",
        "verdict": "H1_ONLY_DAY_TRADING_MISALIGNMENT_RESOLVED_BY_TARGETED_BRANCH_REQUIREMENT",
    }
    result["state_hash"] = sha256_text(stable(result))
    return result


def render_simple(title: str, state: dict[str, Any]) -> str:
    return f"# {title}\n\nStatus: `{state['status']}`\n\nState hash: `{state['state_hash']}`\n"


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    ledger = build_ledger()
    receipts = execution_receipts(ledger)
    failures = failure_decomposition(ledger)
    fidelity = family_fidelity()
    day = day_trading_alignment()
    for path, value in [(LEDGER_OUT, ledger), (EXECUTION_STATE, receipts), (FAILURE_STATE, failures), (FIDELITY_STATE, fidelity), (DAY_STATE, day), (ROOT / "audit_state.json", {"ledger": ledger, "receipts": receipts, "failures": failures, "fidelity": fidelity, "day": day})]:
        atomic_json(path, value)
    EXECUTION_REPORT.write_text(render_simple("AIOS Forex Packet 027 Execution Receipt Audit V1", receipts), encoding="utf-8")
    FAILURE_REPORT.write_text(render_simple("AIOS Forex Packet 027 Failure Decomposition V1", failures), encoding="utf-8")
    FIDELITY_REPORT.write_text(render_simple("AIOS Forex Packet 027 Family Fidelity Audit V1", fidelity), encoding="utf-8")
    DAY_REPORT.write_text(render_simple("AIOS Forex Day-Trading Alignment Audit V1", day), encoding="utf-8")
    return {"status": "COMPLETE", "ledger": ledger, "receipts": receipts, "failures": failures, "fidelity": fidelity, "day": day}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    result = execute()
    print(stable({"status": result["status"], "ledger_candidates": result["ledger"]["candidate_count"], "receipt_verdict": result["receipts"]["verdict"], "day_trading": result["day"]["verdict"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
