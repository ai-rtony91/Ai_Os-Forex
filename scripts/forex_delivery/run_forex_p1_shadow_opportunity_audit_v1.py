#!/usr/bin/env python3
"""Run the isolated P1 money-following and Supertrend shadow audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_p1_shadow_opportunity_audit_v1 import (  # noqa: E402
    PACKET_ID,
    build_audit_state,
    merge_audit_states,
    stable_json,
)

AUTHORIZED_OUTPUT_ROOT = Path(r"C:\Dev\AIOS_TMP\P1_NEXT")
DEFAULT_HISTORY = ROOT / ".aios/runtime/forex_market_history/EUR_USD_latest.json"
DEFAULT_CAMPAIGN_STATE = ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_30_TRADE_CAMPAIGN_V1_STATE.json"
OUTPUTS = {
    "state": "AIOS_FOREX_SHADOW_OPPORTUNITY_AUDIT_STATE.json",
    "report": "AIOS_FOREX_SHADOW_OPPORTUNITY_AUDIT_REPORT.md",
    "ledger": "AIOS_FOREX_SHADOW_REJECTED_CANDIDATES.jsonl",
    "gates": "AIOS_FOREX_REJECTION_GATE_PERFORMANCE.json",
    "scorecard_json": "AIOS_FOREX_MONEY_FOLLOWING_SCORECARD.json",
    "scorecard_md": "AIOS_FOREX_MONEY_FOLLOWING_SCORECARD.md",
    "supertrend": "AIOS_FOREX_SUPERTREND_SHADOW_STATE.json",
    "ab_report": "AIOS_FOREX_PRODUCTION_VS_SHADOW_AB_REPORT.md",
}


def load_json(path: Path) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _authorized_root(path: Path) -> Path:
    resolved = path.resolve()
    if resolved != AUTHORIZED_OUTPUT_ROOT.resolve():
        raise ValueError("unauthorized_output_root")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _fmt(value: Any) -> str:
    if value is None:
        return "INSUFFICIENT_EVIDENCE"
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return str(value)


def _recommended_experiment(state: Mapping[str, Any]) -> str:
    if state["sample_confidence"] in {"VERY_LOW", "LOW"}:
        config = state["configuration"]
        return (
            "Continue the unchanged paired production-control/"
            f"{config['supertrend_strategy_name']} ATR {config['supertrend_atr_length']}, "
            f"multiplier {config['supertrend_multiplier']} shadow observation "
            "until at least 30 rejected candidates resolve; make no threshold change."
        )
    gate = state.get("most_expensive_rejection_gate")
    if gate:
        return (
            f"Run a future PAPER-only A/B packet for {gate}, changing one boundary only while "
            "retaining the current production control; do not promote from this audit."
        )
    return "Continue the unchanged control because no specific positive-edge rejection gate is supported."


def render_audit_report(state: Mapping[str, Any]) -> str:
    shadow = state["shadow_metrics"]
    production = state["production_control_metrics"]
    supertrend = state["supertrend_aligned_metrics"]
    current = state.get("current_observation") or {}
    lineage = current.get("lineage", {})
    roots = state.get("no_signal_root_causes", {})
    gates = state.get("gate_performance", {})
    config = state["configuration"]
    gate_lines = [
        f"- {key}: {value['total_rejections']} rejects; {value['shadow_wins']} winners; expectancy {_fmt(value['shadow_expectancy_r'])}R"
        for key, value in sorted(gates.items())
    ] or ["- NONE"]
    return "\n".join([
        "# AIOS Forex Shadow Opportunity Audit Report", "",
        "## Evidence boundary", "",
        f"- PACKET_ID: {state['packet_id']}",
        f"- SOURCE_PROVENANCE: {state['source_provenance']}",
        f"- SOURCE_HISTORY_SHA256: {state['source_history_sha256']}",
        f"- UNIQUE_SOURCE_HISTORY_WINDOWS: {state.get('source_history_window_count', len(state.get('source_history_windows', [])))}",
        f"- COMPLETED_M5_CONTROL_CYCLES: {state['cycles_analyzed']}",
        "- PRODUCTION: existing rules replayed unchanged against each completed prefix.",
        "- SHADOW — NOT EXECUTED: canonical long geometry evaluated only after each decision.",
        f"- SUPERTREND — DIAGNOSTIC ONLY: {config['supertrend_strategy_name']}; "
        f"ATR {config['supertrend_atr_length']}, multiplier {config['supertrend_multiplier']}; "
        "no production feedback.",
        "- Historical pricing ask was unavailable, so candidate entry uses the canonical signal entry reference.", "",
        "## Current production decision", "",
        f"- PRODUCTION_SIGNAL: {_fmt(lineage.get('production_signal'))}",
        f"- PRODUCTION_DECISION: {_fmt(lineage.get('production_decision'))}",
        f"- FIRST_FAILED_GATE: {_fmt(lineage.get('first_failed_gate'))}",
        f"- REJECTION_REASON: {_fmt(lineage.get('rejection_reason'))}",
        f"- ACTUAL_VALUE: {_fmt(lineage.get('actual_value'))}",
        f"- REQUIRED_VALUE: {_fmt(lineage.get('required_value'))}",
        f"- DISTANCE_TO_PASS: {_fmt(lineage.get('distance_to_pass'))}", "",
        "## Why SIGNAL:NONE", "",
        f"The measured root-cause counts are `{json.dumps(roots, sort_keys=True)}`. Production first "
        "checks volatility, then requires the three-candle close change to reach half the average "
        "candle range. Downtrends produce NO_SIGNAL; ranging regimes produce REGIME_REJECTED; "
        "abnormally low or high range percent produces RISK_REJECTED.", "",
        "## Rejection gates", "", *gate_lines, "",
        "## Money-following results", "",
        f"- SHADOW_CANDIDATES: {shadow['sample_size']}",
        f"- SHADOW_RESOLVED: {shadow['resolved']}",
        f"- SHADOW_UNRESOLVED: {shadow['unresolved']}",
        f"- SHADOW_AMBIGUOUS: {shadow['ambiguous']}",
        f"- SHADOW_WINS: {shadow['wins']}",
        f"- SHADOW_LOSSES: {shadow['losses']}",
        f"- SHADOW_EXPECTANCY_R: {_fmt(shadow['expectancy_r'])}",
        f"- SHADOW_PROFIT_FACTOR: {_fmt(shadow['profit_factor'])}",
        f"- SHADOW_MAX_DRAWDOWN_R: {_fmt(shadow['max_drawdown_r'])}",
        f"- SHADOW_MEAN_MFE_R: {_fmt(shadow['mean_mfe_r'])}",
        f"- SHADOW_MEAN_MAE_R: {_fmt(shadow['mean_mae_r'])}",
        f"- OPPORTUNITY_CAPTURE_RATE: {_fmt(state['opportunity_capture_rate'])}",
        f"- CANDIDATE_LEVEL_REGRET_R: {_fmt(state['candidate_level_regret_r'])}",
        f"- PORTFOLIO_FEASIBLE_REGRET_R: {_fmt(state['portfolio_feasible_regret_r'])}", "",
        "## Supertrend evidence", "",
        f"- SUPERTREND_ALIGNED_REJECTED: {state['supertrend_aligned_rejected']}",
        f"- SUPERTREND_ALIGNED_RESOLVED: {supertrend['resolved']}",
        f"- SUPERTREND_ALIGNED_WINS: {supertrend['wins']}",
        f"- SUPERTREND_ALIGNED_LOSSES: {supertrend['losses']}",
        f"- SUPERTREND_ALIGNED_EXPECTANCY_R: {_fmt(supertrend['expectancy_r'])}",
        f"- SUPERTREND_ALIGNED_PROFIT_FACTOR: {_fmt(supertrend['profit_factor'])}",
        f"- SUPERTREND_ALIGNED_MAX_DRAWDOWN_R: {_fmt(supertrend['max_drawdown_r'])}", "",
        "## Production-control comparison", "",
        f"- CONTROL_ACCEPTED_CANDIDATES: {production['sample_size']}",
        f"- CONTROL_WINS_LOSSES: {production['wins']} / {production['losses']}",
        f"- CONTROL_EXPECTANCY_R: {_fmt(production['expectancy_r'])}",
        f"- CONTROL_PROFIT_FACTOR: {_fmt(production['profit_factor'])}",
        f"- ACTUAL_CAMPAIGN_COMPLETED_TRADES: {state['production_actual_campaign_evidence']['completed_trades']}",
        "- Control replay candidates are not added to the production ledger and are not qualifying trades.", "",
        "## Evidence conclusion", "",
        f"- OVER_FILTERING_STATUS: {state['over_filtering_status']}",
        f"- MONEY_FOLLOWING_STATUS: {state['money_following_status']}",
        f"- SAMPLE_CONFIDENCE: {state['sample_confidence']} ({state['sample_confidence_rule']})",
        f"- RECOMMENDED_NEXT_EXPERIMENT: {_recommended_experiment(state)}", "",
        "No production threshold, risk rule, freshness rule, signal rule, broker state, PAPER P/L, "
        "or qualifying-trade count was changed.", "",
    ])


def render_scorecard(state: Mapping[str, Any]) -> str:
    card = state["scorecard"]
    lines = ["# AIOS Forex Money-Following Scorecard", ""]
    for key in (
        "opportunity_capture_rate", "candidate_level_regret_r", "portfolio_feasible_regret_r",
        "false_rejection_rate", "most_common_rejection_gate", "most_expensive_rejection_gate",
        "over_filtering_status", "money_following_status", "sample_confidence",
    ):
        lines.append(f"- {key.upper()}: {_fmt(card[key])}")
    lines.extend(["", "PRODUCTION, SHADOW — NOT EXECUTED, and SUPERTREND — DIAGNOSTIC ONLY remain separate.", ""])
    return "\n".join(lines)


def render_ab_report(state: Mapping[str, Any]) -> str:
    groups = (
        ("PRODUCTION CONTROL", state["production_control_metrics"]),
        ("SHADOW — NOT EXECUTED", state["shadow_metrics"]),
        ("SUPERTREND — DIAGNOSTIC ONLY", state["supertrend_aligned_metrics"]),
    )
    lines = ["# AIOS Forex Production vs Shadow A/B Report", ""]
    for label, metrics in groups:
        lines.extend([
            f"## {label}", "",
            f"- SAMPLE_SIZE: {metrics['sample_size']}",
            f"- RESOLVED: {metrics['resolved']}",
            f"- WINS: {metrics['wins']}",
            f"- LOSSES: {metrics['losses']}",
            f"- WIN_RATE: {_fmt(metrics['win_rate'])}",
            f"- EXPECTANCY_R: {_fmt(metrics['expectancy_r'])}",
            f"- PROFIT_FACTOR: {_fmt(metrics['profit_factor'])}",
            f"- MAX_DRAWDOWN_R: {_fmt(metrics['max_drawdown_r'])}",
            f"- MEAN_MFE_R: {_fmt(metrics['mean_mfe_r'])}",
            f"- MEAN_MAE_R: {_fmt(metrics['mean_mae_r'])}",
            f"- PAPER_OR_HYPOTHETICAL_PNL: {_fmt(metrics['hypothetical_pnl'])}", "",
        ])
    lines.extend([
        "## Portfolio-feasible alternative", "",
        f"- TOTAL_R: {_fmt(state['portfolio_feasible_alternative_replay']['total_r'])}",
        f"- SELECTED: {state['portfolio_feasible_alternative_replay']['selected_candidates']}",
        f"- SKIPPED_OVERLAPS: {state['portfolio_feasible_alternative_replay']['skipped_overlapping_candidates']}",
        f"- REGRET_VS_CONTROL_R: {_fmt(state['portfolio_feasible_regret_r'])}", "",
    ])
    return "\n".join(lines)


def _ledger_events(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    events = []
    for cycle in state["cycle_records"]:
        candidate = cycle.get("shadow_candidate")
        if not candidate:
            continue
        observed = {
            "event_type": "SHADOW_CANDIDATE_OBSERVED",
            "candidate_id": candidate["shadow_candidate_id"],
            "observed_utc": candidate["observed_utc"],
            "candidate": {key: value for key, value in candidate.items() if key != "counterfactual"},
        }
        observed["event_id"] = hashlib_sha(observed)
        events.append(observed)
        counterfactual = candidate["counterfactual"]
        if counterfactual["result"] != "UNRESOLVED":
            resolved = {
                "event_type": "SHADOW_CANDIDATE_RESOLUTION",
                "candidate_id": candidate["shadow_candidate_id"],
                "observed_utc": candidate["observed_utc"],
                "counterfactual": counterfactual,
            }
            resolved["event_id"] = hashlib_sha(resolved)
            events.append(resolved)
    return events


def hashlib_sha(value: Mapping[str, Any]) -> str:
    import hashlib
    return hashlib.sha256(stable_json(value).encode()).hexdigest()


def _append_ledger(path: Path, state: Mapping[str, Any]) -> None:
    known: set[str] = set()
    if path.exists():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or not isinstance(value.get("event_id"), str):
                raise ValueError(f"invalid_existing_shadow_ledger_line_{number}")
            known.add(value["event_id"])
    new_events = [event for event in _ledger_events(state) if event["event_id"] not in known]
    if new_events:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            for event in new_events:
                handle.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")
    elif not path.exists():
        path.write_text("", encoding="utf-8")


def write_outputs(state: Mapping[str, Any], output_root: Path) -> None:
    root = _authorized_root(output_root)
    paths = {key: root / name for key, name in OUTPUTS.items()}
    paths["state"].write_text(stable_json(state), encoding="utf-8")
    paths["report"].write_text(render_audit_report(state), encoding="utf-8")
    _append_ledger(paths["ledger"], state)
    paths["gates"].write_text(stable_json({
        "version": state["version"], "packet_id": state["packet_id"],
        "source_history_sha256": state["source_history_sha256"],
        "gate_performance": state["gate_performance"],
        "near_threshold_performance": state["near_threshold_performance"],
    }), encoding="utf-8")
    paths["scorecard_json"].write_text(stable_json({
        "version": state["version"], "packet_id": state["packet_id"], **state["scorecard"]
    }), encoding="utf-8")
    paths["scorecard_md"].write_text(render_scorecard(state), encoding="utf-8")
    current = state.get("current_observation") or {}
    paths["supertrend"].write_text(stable_json({
        "version": state["version"], "packet_id": state["packet_id"],
        "current": current.get("supertrend"),
        "disagreement_counts": state["supertrend_disagreement_counts"],
        "aligned_metrics": state["supertrend_aligned_metrics"],
        "production_feedback_allowed": False,
        "executed": False,
    }), encoding="utf-8")
    paths["ab_report"].write_text(render_ab_report(state), encoding="utf-8")


def run_offline(history_path: Path, campaign_state_path: Path, output_root: Path) -> dict[str, Any]:
    history = load_json(history_path)
    campaign = load_json(campaign_state_path) if campaign_state_path.exists() else {}
    root = _authorized_root(output_root)
    existing_path = root / OUTPUTS["state"]
    previous = load_json(existing_path) if existing_path.exists() else None
    state = merge_audit_states(
        previous, build_audit_state(history, campaign_state=campaign), campaign_state=campaign
    )
    write_outputs(state, output_root)
    return state


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="P1 shadow money-following audit; never executes trades.")
    sub = result.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    audit.add_argument("--campaign-state", type=Path, default=DEFAULT_CAMPAIGN_STATE)
    audit.add_argument("--output-root", type=Path, default=AUTHORIZED_OUTPUT_ROOT)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    state = run_offline(args.history, args.campaign_state, args.output_root)
    print(stable_json({
        "status": "PASS", "packet_id": PACKET_ID,
        "cycles_analyzed": state["cycles_analyzed"],
        "shadow_candidates": state["shadow_candidates"],
        "shadow_resolved": state["shadow_metrics"]["resolved"],
        "money_following_status": state["money_following_status"],
        "production_changed": False,
    }), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
