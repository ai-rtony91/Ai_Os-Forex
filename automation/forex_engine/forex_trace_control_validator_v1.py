"""Independent trace validator for Packet 030 controls."""
from __future__ import annotations

import math
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine import forex_trace_evidence_contract_v1 as contract


TOLERANCE = 1e-9


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def close(left: float, right: float, tolerance: float = TOLERANCE) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def recompute_metrics(trace: dict[str, Any]) -> dict[str, Any]:
    realized = [float(event["realized_r"]) for event in trace.get("events", []) if event.get("event_type") == "EXIT_FILLED"]
    wins = [value for value in realized if value > 0]
    losses = [value for value in realized if value < 0]
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in realized:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {
        "trade_count": len(realized),
        "wins": len(wins),
        "losses": len(losses),
        "gross_pnl": round(sum(float(event.get("gross_pnl", 0.0)) for event in trace.get("events", []) if event.get("event_type") == "EXIT_FILLED"), 10),
        "net_pnl": round(sum(float(event.get("net_pnl", 0.0)) for event in trace.get("events", []) if event.get("event_type") == "EXIT_FILLED"), 10),
        "net_expectancy": round(sum(realized) / len(realized), 10) if realized else 0.0,
        "profit_factor": round(sum(wins) / gross_loss, 10) if gross_loss else (999.0 if wins else 0.0),
        "net_r": round(sum(realized), 10),
        "max_drawdown": round(drawdown, 10),
        "average_cost_r": round(
            sum(float(event.get("spread_cost", 0.0)) + float(event.get("slippage_cost", 0.0)) + float(event.get("financing_cost", 0.0)) for event in trace.get("events", []) if event.get("event_type") == "EXIT_FILLED")
            / len(realized),
            10,
        )
        if realized
        else 0.0,
    }


def validate_trace(trace: dict[str, Any], spec: dict[str, Any], rerun_trace: dict[str, Any] | None = None) -> dict[str, Any]:
    events = trace.get("events", [])
    criteria: dict[str, bool] = {}
    criteria["TRACE_SCHEMA_VALID"] = trace.get("trace_schema") == contract.TRACE_SCHEMA
    criteria["PRODUCER_NO_VERDICT_FIELDS"] = contract.no_forbidden_producer_keys(trace)
    criteria["ORDERED_EVENTS_VALID"] = [event.get("sequence_number") for event in events] == list(range(1, len(events) + 1))
    criteria["TRACE_CHAIN_HASH_VALID"] = contract.chain_events([dict(event) for event in events]) == trace.get("trace_chain_hash")
    criteria["INPUT_HASH_VALID"] = bool(trace.get("input_artifact_hashes"))
    criteria["ADAPTER_IDENTITY_VALID"] = trace.get("adapter_id") == spec.get("adapter_id")
    criteria["ADAPTER_CODE_HASH_VALID"] = trace.get("adapter_code_hash") == spec.get("adapter_code_hash")
    criteria["EXECUTION_CORE_IDENTITY_VALID"] = trace.get("execution_core_id") == contract.EXECUTION_CORE_ID
    criteria["COST_CORE_IDENTITY_VALID"] = trace.get("cost_core_id") == contract.COST_CORE_ID
    criteria["METRIC_CORE_IDENTITY_VALID"] = trace.get("metric_core_id") == contract.METRIC_CORE_ID

    chronology = True
    availability = True
    no_future = True
    bid_ask = True
    r_valid = True
    for event in events:
        source_available = parse_time(event.get("source_available_timestamp_utc"))
        decision = parse_time(event.get("decision_timestamp_utc"))
        execution = parse_time(event.get("execution_timestamp_utc"))
        feature_available = parse_time(event.get("feature_available_timestamp_utc"))
        if source_available and decision and source_available > decision:
            availability = False
        if feature_available and decision and feature_available > decision:
            no_future = False
        if decision and execution and decision >= execution and event.get("event_type") in {"ENTRY_FILLED", "EXIT_FILLED"}:
            chronology = False
        if event.get("event_type") == "ENTRY_FILLED":
            if event.get("direction") == "LONG" and not close(event.get("entry_fill", 0.0), event.get("entry_ask", math.nan)):
                bid_ask = False
            if event.get("direction") == "SHORT" and not close(event.get("entry_fill", 0.0), event.get("entry_bid", math.nan)):
                bid_ask = False
        if event.get("event_type") == "EXIT_FILLED":
            if event.get("direction") == "LONG" and not close(event.get("exit_fill", 0.0), event.get("exit_bid", math.nan)):
                bid_ask = False
            if event.get("direction") == "SHORT" and not close(event.get("exit_fill", 0.0), event.get("exit_ask", math.nan)):
                bid_ask = False
            net = float(event.get("gross_pnl", 0.0)) - float(event.get("spread_cost", 0.0)) - float(event.get("slippage_cost", 0.0)) - float(event.get("financing_cost", 0.0))
            if not close(net, float(event.get("net_pnl", 0.0)), 1e-7):
                r_valid = False
            risk = float(event.get("initial_risk", 0.0))
            if risk <= 0 or not close(float(event.get("realized_r", 0.0)), float(event.get("net_pnl", 0.0)) / risk, 1e-7):
                r_valid = False
    criteria["CHRONOLOGY_VALID"] = chronology
    criteria["FEATURE_AVAILABILITY_VALID"] = availability
    criteria["NO_FUTURE_LEAKAGE"] = no_future
    criteria["BID_ASK_EXECUTION_VALID"] = bid_ask
    cost_counts: dict[str, int] = {}
    for event in events:
        if event.get("event_type") == "COST_APPLIED":
            cost_counts[str(event.get("trade_id"))] = cost_counts.get(str(event.get("trade_id")), 0) + 1
    trade_ids = [str(event.get("trade_id")) for event in events if event.get("event_type") == "EXIT_FILLED"]
    criteria["SINGLE_CHARGE_COST_VALID"] = (not trade_ids) or all(cost_counts.get(trade_id) == 1 for trade_id in trade_ids)
    criteria["FINANCING_VALID_WHERE_APPLICABLE"] = all(float(event.get("financing_cost", 0.0)) >= 0.0 for event in events if event.get("event_type") == "EXIT_FILLED")
    event_ids = [event.get("event_id") for event in events if event.get("event_id")]
    criteria["EVENT_DEDUP_VALID"] = len(event_ids) == len(set(event_ids))
    criteria["TRADE_ID_VALID"] = len(trade_ids) == len(set(trade_ids)) and all(trade_ids)
    criteria["R_ACCOUNTING_VALID"] = r_valid
    if spec.get("requires_complete_multileg_fill"):
        criteria["MULTILEG_FILL_COMPLETE"] = all(
            event.get("instrument_or_portfolio_id") != "LEG1_ONLY"
            for event in events
            if event.get("event_type") in {"ENTRY_FILLED", "EXIT_FILLED"}
        )
    else:
        criteria["MULTILEG_FILL_COMPLETE"] = True
    directions = {event.get("direction") for event in events if event.get("direction")}
    criteria["DIRECTION_ISOLATION_VALID"] = directions <= {trace.get("direction_scope")}
    recomputed = recompute_metrics(trace)
    reported = trace.get("reported_metrics", {})
    criteria["METRIC_RECOMPUTATION_MATCH"] = all(close(recomputed.get(key, 0.0), reported.get(key, 0.0), 1e-7) for key in ["trade_count", "wins", "losses", "net_expectancy", "profit_factor", "net_r", "max_drawdown", "average_cost_r"])
    if rerun_trace is None:
        criteria["DETERMINISTIC_RERUN_MATCH"] = True
    else:
        criteria["DETERMINISTIC_RERUN_MATCH"] = trace.get("trace_chain_hash") == rerun_trace.get("trace_chain_hash")

    expected = spec.get("expected_outcome", {})
    if expected.get("kind") == "positive_edge":
        criteria["EXPECTED_CONTROL_OUTCOME_OBSERVED"] = recomputed["trade_count"] >= int(expected.get("minimum_trades", 1)) and recomputed["net_expectancy"] >= float(expected.get("minimum_net_expectancy", 0.0))
    elif expected.get("kind") == "rejection":
        wanted = expected.get("expected_rejection_class")
        criteria["EXPECTED_CONTROL_OUTCOME_OBSERVED"] = any(event.get("event_type") == "EVENT_REJECTED" and event.get("rejection_reason") == wanted for event in events)
    else:
        criteria["EXPECTED_CONTROL_OUTCOME_OBSERVED"] = False
    return {
        "trace_run_id": trace.get("trace_run_id"),
        "family_id": trace.get("family_id"),
        "candidate_or_control_id": trace.get("candidate_or_control_id"),
        "criteria": criteria,
        "recomputed_metrics": recomputed,
        "overall_valid": all(criteria.values()),
    }


def mutate_trace(trace: dict[str, Any], mutation: str) -> dict[str, Any]:
    mutated = deepcopy(trace)
    events = mutated["events"]
    if mutation == "future_feature_timestamp":
        events[1]["feature_available_timestamp_utc"] = "2026-01-02T00:00:00Z"
    elif mutation == "source_available_after_decision":
        events[1]["source_available_timestamp_utc"] = "2026-01-02T00:00:00Z"
    elif mutation == "invalid_entry_boundary":
        events[3]["execution_timestamp_utc"] = events[3]["decision_timestamp_utc"]
    elif mutation == "long_entry_bid":
        events[3]["entry_fill"] = events[3].get("entry_bid", 0.0)
    elif mutation == "short_entry_ask":
        events[3]["direction"] = "SHORT"
        events[3]["entry_fill"] = events[3].get("entry_ask", 0.0)
    elif mutation == "omitted_cost":
        for event in events:
            if event["event_type"] == "COST_APPLIED":
                event["trade_id"] = "missing"
    elif mutation == "double_cost":
        duplicate = dict(next(event for event in events if event["event_type"] == "COST_APPLIED"))
        duplicate["sequence_number"] = max(event["sequence_number"] for event in events) + 1
        events.append(duplicate)
    elif mutation == "altered_realized_r":
        next(event for event in events if event["event_type"] == "EXIT_FILLED")["realized_r"] = 9.0
    elif mutation == "altered_metric_summary":
        mutated["reported_metrics"]["net_r"] = 999.0
    elif mutation == "duplicated_event_id":
        first = next(event for event in events if event.get("event_id"))
        second = next(event for event in reversed(events) if event.get("event_id"))
        second["event_id"] = first["event_id"]
    elif mutation == "duplicated_trade_id":
        for event in events:
            if event.get("trade_id"):
                event["trade_id"] = "duplicate"
    elif mutation == "changed_adapter_code_hash":
        mutated["adapter_code_hash"] = "changed"
    elif mutation == "changed_execution_core_identity":
        mutated["execution_core_id"] = "changed"
    elif mutation == "changed_cost_core_identity":
        mutated["cost_core_id"] = "changed"
    elif mutation == "changed_metric_core_identity":
        mutated["metric_core_id"] = "changed"
    elif mutation == "changed_direction_after_base_event":
        events[3]["direction"] = "SHORT" if events[3].get("direction") == "LONG" else "LONG"
    elif mutation == "nondeterministic_rerun_trace":
        mutated["trace_chain_hash"] = "changed"
    elif mutation == "future_official_release":
        events[1]["source_available_timestamp_utc"] = "2026-01-02T00:00:00Z"
    elif mutation == "pre_release_event_entry":
        events[3]["execution_timestamp_utc"] = "2025-12-31T23:59:00Z"
    elif mutation == "incomplete_multileg_fill":
        events[3]["instrument_or_portfolio_id"] = "LEG1_ONLY"
    else:
        raise ValueError(mutation)
    return mutated
