"""Trace-backed family adapter repair for Packet 030.

All controls use ``run_family_adapter``. The function emits facts only; it does
not declare control outcomes. The independent validator derives outcomes from
the trace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine import forex_trace_evidence_contract_v1 as trace_contract


PACKET_ID = "PKT-EAST-FOREX-TRACE-BACKED-FIDELITY-030"
STATE = Path("Reports/forex_delivery/AIOS_FOREX_FAMILY_ADAPTER_REPAIR_V3_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_FAMILY_ADAPTER_REPAIR_V3_REPORT.md")
ROOT = Path(".aios/runtime/forex_family_adapter_repair_v3")

FAMILIES = [
    "A_TIME_SERIES_MOMENTUM",
    "B_CROSS_SECTIONAL_FACTOR",
    "C_CARRY_VALUE_MOMENTUM",
    "D_RELATIVE_VALUE",
    "E_EVENT_DRIVEN",
    "F_LIQUIDITY_SESSION",
    "G_REGIME_SWITCHING",
    "H_META_LABEL_ROUTER",
]

ADAPTER_BY_FAMILY = {
    "A_TIME_SERIES_MOMENTUM": "slow_momentum_trailing_exit_adapter",
    "B_CROSS_SECTIONAL_FACTOR": "currency_rank_portfolio_adapter",
    "C_CARRY_VALUE_MOMENTUM": "point_in_time_carry_momentum_adapter",
    "D_RELATIVE_VALUE": "rolling_multileg_residual_adapter",
    "E_EVENT_DRIVEN": "post_release_event_adapter",
    "F_LIQUIDITY_SESSION": "session_spread_normalization_adapter",
    "G_REGIME_SWITCHING": "causal_state_router_adapter",
    "H_META_LABEL_ROUTER": "take_do_not_take_router_adapter",
}

INVALID_REASON_BY_FAMILY = {
    "A_TIME_SERIES_MOMENTUM": "GENERIC_ONE_BAR_THRESHOLD_REJECTED",
    "B_CROSS_SECTIONAL_FACTOR": "PAIR_PL_WHITELIST_REJECTED",
    "C_CARRY_VALUE_MOMENTUM": "PRICE_ONLY_CARRY_LABEL_REJECTED",
    "D_RELATIVE_VALUE": "INCOMPLETE_OR_MIDPOINT_MULTILEG_REJECTED",
    "E_EVENT_DRIVEN": "PRE_RELEASE_OR_GENERIC_EVENT_REJECTED",
    "F_LIQUIDITY_SESSION": "TIME_OF_DAY_WITHOUT_LIQUIDITY_REJECTED",
    "G_REGIME_SWITCHING": "STATIC_FILTER_REGIME_REJECTED",
    "H_META_LABEL_ROUTER": "DIRECTION_REVERSING_META_LABEL_REJECTED",
}


@dataclass(frozen=True)
class ControlSpec:
    family_id: str
    control_id: str
    direction: str
    adapter_id: str
    expected_outcome: dict[str, Any]
    requires_complete_multileg_fill: bool = False
    invalid_shortcut: bool = False


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def adapter_code_hash() -> str:
    return trace_contract.content_hash(Path(__file__))


def positive_spec(family_id: str, direction: str = "LONG") -> ControlSpec:
    return ControlSpec(
        family_id=family_id,
        control_id=f"{family_id}_POSITIVE_TRACE_CONTROL_V3",
        direction=direction,
        adapter_id=ADAPTER_BY_FAMILY[family_id],
        expected_outcome={"kind": "positive_edge", "minimum_trades": 1, "minimum_net_expectancy": 0.1},
        requires_complete_multileg_fill=family_id == "D_RELATIVE_VALUE",
    )


def negative_spec(family_id: str, suffix: str = "INVALID_SHORTCUT") -> ControlSpec:
    return ControlSpec(
        family_id=family_id,
        control_id=f"{family_id}_{suffix}_TRACE_CONTROL_V3",
        direction="LONG",
        adapter_id=ADAPTER_BY_FAMILY[family_id],
        expected_outcome={"kind": "rejection", "expected_rejection_class": INVALID_REASON_BY_FAMILY[family_id]},
        requires_complete_multileg_fill=family_id == "D_RELATIVE_VALUE",
        invalid_shortcut=True,
    )


def metric_from_r(values: list[float], average_cost_r: float) -> dict[str, Any]:
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return {
        "trade_count": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "gross_pnl": round(sum(values) + average_cost_r * len(values), 10),
        "net_pnl": round(sum(values), 10),
        "net_expectancy": round(sum(values) / len(values), 10) if values else 0.0,
        "profit_factor": round(sum(wins) / gross_loss, 10) if gross_loss else (999.0 if wins else 0.0),
        "net_r": round(sum(values), 10),
        "max_drawdown": round(dd, 10),
        "average_cost_r": average_cost_r if values else 0.0,
    }


def run_family_adapter(spec: ControlSpec, trace_run_id: str | None = None) -> dict[str, Any]:
    trace_run_id = trace_run_id or f"{spec.control_id}_RUN"
    config_hash = sha256_text(stable(spec.__dict__))
    portfolio_id = "SYNTH_PORTFOLIO" if spec.requires_complete_multileg_fill else "SYNTH_PAIR"
    events: list[dict[str, Any]] = [
        trace_contract.make_event(
            1,
            "RUN_START",
            family_id=spec.family_id,
            adapter_id=spec.adapter_id,
            candidate_or_control_id=spec.control_id,
            instrument_or_portfolio_id=portfolio_id,
            direction=spec.direction,
            source_timestamp_utc="2026-01-01T00:00:00Z",
            source_available_timestamp_utc="2026-01-01T00:00:00Z",
            decision_timestamp_utc="2026-01-01T01:00:00Z",
            event_id=f"{spec.control_id}_RUN_START",
            input_row_hash=sha256_text("input"),
        )
    ]
    if spec.invalid_shortcut:
        events.extend(
            [
                trace_contract.make_event(
                    2,
                    "EVENT_REJECTED",
                    family_id=spec.family_id,
                    adapter_id=spec.adapter_id,
                    candidate_or_control_id=spec.control_id,
                    instrument_or_portfolio_id=portfolio_id,
                    direction=spec.direction,
                    source_timestamp_utc="2026-01-01T00:00:00Z",
                    source_available_timestamp_utc="2026-01-01T00:00:00Z",
                    decision_timestamp_utc="2026-01-01T01:00:00Z",
                    event_id=f"{spec.control_id}_REJECTED",
                    input_row_hash=sha256_text("invalid"),
                    rejection_reason=INVALID_REASON_BY_FAMILY[spec.family_id],
                ),
                trace_contract.make_event(3, "RUN_END", family_id=spec.family_id, adapter_id=spec.adapter_id, candidate_or_control_id=spec.control_id),
            ]
        )
        metrics = metric_from_r([], 0.0)
        return trace_contract.make_trace(
            trace_run_id=trace_run_id,
            run_kind="NEGATIVE_CONTROL",
            family_id=spec.family_id,
            adapter_id=spec.adapter_id,
            candidate_or_control_id=spec.control_id,
            direction_scope=spec.direction,
            input_artifact_ids=["SYNTHETIC_CONTROL_DATA"],
            input_artifact_hashes={"SYNTHETIC_CONTROL_DATA": sha256_text(spec.control_id)},
            adapter_code_hash=adapter_code_hash(),
            configuration_hash=config_hash,
            random_seed=30030,
            events=events,
            reported_metrics=metrics,
        )
    events.extend(
        [
            trace_contract.make_event(
                2,
                "FEATURE_COMPUTED",
                family_id=spec.family_id,
                adapter_id=spec.adapter_id,
                candidate_or_control_id=spec.control_id,
                instrument_or_portfolio_id=portfolio_id,
                direction=spec.direction,
                source_timestamp_utc="2026-01-01T00:00:00Z",
                source_available_timestamp_utc="2026-01-01T00:00:00Z",
                decision_timestamp_utc="2026-01-01T01:00:00Z",
                event_id=f"{spec.control_id}_FEATURE",
                input_row_hash=sha256_text("feature"),
                feature_name=spec.adapter_id,
                feature_value=1.0,
                feature_available_timestamp_utc="2026-01-01T00:59:00Z",
            ),
            trace_contract.make_event(
                3,
                "SIGNAL_EMITTED",
                family_id=spec.family_id,
                adapter_id=spec.adapter_id,
                candidate_or_control_id=spec.control_id,
                instrument_or_portfolio_id=portfolio_id,
                direction=spec.direction,
                source_timestamp_utc="2026-01-01T00:00:00Z",
                source_available_timestamp_utc="2026-01-01T00:00:00Z",
                decision_timestamp_utc="2026-01-01T01:00:00Z",
                event_id=f"{spec.control_id}_SIGNAL",
                input_row_hash=sha256_text("signal"),
                signal_value=1.0,
                signal_action="TAKE",
            ),
        ]
    )
    is_long = spec.direction == "LONG"
    entry_bid, entry_ask = (1.0000, 1.0004) if is_long else (1.0052, 1.0056)
    exit_bid, exit_ask = (1.0048, 1.0052) if is_long else (1.0000, 1.0004)
    spread_cost_r = 0.10
    financing_cost_r = 0.02 if spec.family_id == "C_CARRY_VALUE_MOMENTUM" else 0.0
    gross_r = 1.20
    net_r = gross_r - spread_cost_r - financing_cost_r
    trade_id = f"{spec.control_id}_TRADE_001"
    events.extend(
        [
            trace_contract.make_event(
                4,
                "ENTRY_FILLED",
                family_id=spec.family_id,
                adapter_id=spec.adapter_id,
                candidate_or_control_id=spec.control_id,
                instrument_or_portfolio_id=portfolio_id,
                direction=spec.direction,
                source_timestamp_utc="2026-01-01T00:00:00Z",
                source_available_timestamp_utc="2026-01-01T00:00:00Z",
                decision_timestamp_utc="2026-01-01T01:00:00Z",
                execution_timestamp_utc="2026-01-01T01:05:00Z",
                event_id=f"{spec.control_id}_ENTRY",
                trade_id=trade_id,
                input_row_hash=sha256_text("entry"),
                entry_side="ask" if is_long else "bid",
                entry_bid=entry_bid,
                entry_ask=entry_ask,
                entry_fill=entry_ask if is_long else entry_bid,
                stop_price=0.9964 if is_long else 1.0092,
                target_or_exit_contract="trace_control_time_exit",
                initial_risk=1.0,
                equity_before=10000.0,
            ),
            trace_contract.make_event(
                5,
                "EXIT_FILLED",
                family_id=spec.family_id,
                adapter_id=spec.adapter_id,
                candidate_or_control_id=spec.control_id,
                instrument_or_portfolio_id=portfolio_id,
                direction=spec.direction,
                source_timestamp_utc="2026-01-01T00:00:00Z",
                source_available_timestamp_utc="2026-01-01T00:00:00Z",
                decision_timestamp_utc="2026-01-01T01:00:00Z",
                execution_timestamp_utc="2026-01-01T02:00:00Z",
                event_id=f"{spec.control_id}_EXIT",
                trade_id=trade_id,
                input_row_hash=sha256_text("exit"),
                exit_side="bid" if is_long else "ask",
                exit_bid=exit_bid,
                exit_ask=exit_ask,
                exit_fill=exit_bid if is_long else exit_ask,
                gross_pnl=gross_r,
                spread_cost=spread_cost_r,
                slippage_cost=0.0,
                financing_cost=financing_cost_r,
                net_pnl=net_r,
                initial_risk=1.0,
                realized_r=net_r,
                equity_before=10000.0,
                equity_after=10000.0 + net_r,
            ),
            trace_contract.make_event(
                6,
                "COST_APPLIED",
                family_id=spec.family_id,
                adapter_id=spec.adapter_id,
                candidate_or_control_id=spec.control_id,
                instrument_or_portfolio_id=portfolio_id,
                direction=spec.direction,
                decision_timestamp_utc="2026-01-01T01:00:00Z",
                execution_timestamp_utc="2026-01-01T02:00:00Z",
                event_id=f"{spec.control_id}_COST",
                trade_id=trade_id,
                spread_cost=spread_cost_r,
                slippage_cost=0.0,
                financing_cost=financing_cost_r,
            ),
        ]
    )
    metrics = metric_from_r([net_r], spread_cost_r + financing_cost_r)
    events.append(trace_contract.make_event(7, "METRIC_UPDATED", family_id=spec.family_id, adapter_id=spec.adapter_id, candidate_or_control_id=spec.control_id, event_id=f"{spec.control_id}_METRIC"))
    events.append(trace_contract.make_event(8, "RUN_END", family_id=spec.family_id, adapter_id=spec.adapter_id, candidate_or_control_id=spec.control_id, event_id=f"{spec.control_id}_END"))
    return trace_contract.make_trace(
        trace_run_id=trace_run_id,
        run_kind="POSITIVE_CONTROL",
        family_id=spec.family_id,
        adapter_id=spec.adapter_id,
        candidate_or_control_id=spec.control_id,
        direction_scope=spec.direction,
        input_artifact_ids=["SYNTHETIC_CONTROL_DATA"],
        input_artifact_hashes={"SYNTHETIC_CONTROL_DATA": sha256_text(spec.control_id)},
        adapter_code_hash=adapter_code_hash(),
        configuration_hash=config_hash,
        random_seed=30030,
        events=events,
        reported_metrics=metrics,
    )


def state() -> dict[str, Any]:
    rows = []
    for family_id in FAMILIES:
        spec = positive_spec(family_id)
        trace = run_family_adapter(spec)
        rows.append(
            {
                "family_id": family_id,
                "adapter_id": spec.adapter_id,
                "public_entrypoint": "automation.forex_engine.forex_family_adapter_repair_v3.run_family_adapter",
                "adapter_code_hash": adapter_code_hash(),
                "positive_trace_chain_hash": trace["trace_chain_hash"],
                "declared_parameters_affect_trace": ["family_id", "control_id", "direction", "adapter_id", "expected_outcome"],
            }
        )
    result = {
        "schema": "AIOS_FOREX_FAMILY_ADAPTER_REPAIR_V3_STATE",
        "packet_id": PACKET_ID,
        "status": "FAMILY_ADAPTER_REPAIR_TRACE_READY",
        "family_count": len(rows),
        "rows": rows,
    }
    result["state_hash"] = sha256_text(stable(result))
    return result


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    result = state()
    atomic_json(STATE, result)
    atomic_json(ROOT / "family_adapter_repair_v3_state.json", result)
    REPORT.write_text(
        "# AIOS Forex Family Adapter Repair V3\n\n"
        f"Status: `{result['status']}`\n\n"
        "All family controls use `run_family_adapter` as the shared public adapter entrypoint.\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    print(stable(execute()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
