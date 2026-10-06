"""Trace-backed M5 day-trading bridge for Packet 030."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine import forex_trace_control_validator_v1 as validator
from automation.forex_engine import forex_trace_evidence_contract_v1 as contract


PACKET_ID = "PKT-EAST-FOREX-TRACE-BACKED-FIDELITY-030"
ROOT = Path(".aios/runtime/forex_m5_day_trading_adapter_v2")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_DAY_TRADING_ADAPTER_V2_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_M5_DAY_TRADING_ADAPTER_V2_REPORT.md")
M5_STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_V2_STATE.json")
MULTI_STATE = Path("Reports/forex_delivery/AIOS_FOREX_MULTI_REGIME_CORPUS_V3_STATE.json")
EXTERNAL_STATE = Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3_STATE.json")
ADAPTER_ID = "m5_mtf_completed_bar_next_interval_adapter_v2"


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


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


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}


def adapter_code_hash() -> str:
    return contract.content_hash(Path(__file__))


def m5_spec() -> dict[str, Any]:
    return {
        "family_id": "M5_DAY_TRADING_MTF",
        "adapter_id": ADAPTER_ID,
        "adapter_code_hash": adapter_code_hash(),
        "expected_outcome": {"kind": "positive_edge", "minimum_trades": 1, "minimum_net_expectancy": 0.1},
    }


def make_m5_trace(control_id: str = "M5_MTF_POSITIVE_TRACE_CONTROL_V2") -> dict[str, Any]:
    decision = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    execution = decision + timedelta(minutes=5)
    exit_time = execution + timedelta(minutes=10)
    events = [
        contract.make_event(
            1,
            "RUN_START",
            family_id="M5_DAY_TRADING_MTF",
            adapter_id=ADAPTER_ID,
            candidate_or_control_id=control_id,
            instrument_or_portfolio_id="EUR_USD",
            direction="LONG",
            source_timestamp_utc="2026-01-05T09:55:00Z",
            source_available_timestamp_utc="2026-01-05T09:55:00Z",
            decision_timestamp_utc=contract.utc(decision),
            event_id=f"{control_id}_START",
            input_row_hash=contract.sha256_text("m5-start"),
        ),
        contract.make_event(
            2,
            "FEATURE_COMPUTED",
            family_id="M5_DAY_TRADING_MTF",
            adapter_id=ADAPTER_ID,
            candidate_or_control_id=control_id,
            instrument_or_portfolio_id="EUR_USD",
            direction="LONG",
            source_timestamp_utc="2026-01-05T00:00:00Z",
            source_available_timestamp_utc="2026-01-05T00:00:00Z",
            decision_timestamp_utc=contract.utc(decision),
            event_id=f"{control_id}_D1",
            input_row_hash=contract.sha256_text("d1"),
            feature_name="D1_CONTEXT_LAST_COMPLETED",
            feature_value=1.0,
            feature_available_timestamp_utc="2026-01-05T00:00:00Z",
        ),
        contract.make_event(
            3,
            "FEATURE_COMPUTED",
            family_id="M5_DAY_TRADING_MTF",
            adapter_id=ADAPTER_ID,
            candidate_or_control_id=control_id,
            instrument_or_portfolio_id="EUR_USD",
            direction="LONG",
            source_timestamp_utc="2026-01-05T08:00:00Z",
            source_available_timestamp_utc="2026-01-05T08:00:00Z",
            decision_timestamp_utc=contract.utc(decision),
            event_id=f"{control_id}_H4",
            input_row_hash=contract.sha256_text("h4"),
            feature_name="H4_CONTEXT_LAST_COMPLETED",
            feature_value=1.0,
            feature_available_timestamp_utc="2026-01-05T08:00:00Z",
        ),
        contract.make_event(
            4,
            "FEATURE_COMPUTED",
            family_id="M5_DAY_TRADING_MTF",
            adapter_id=ADAPTER_ID,
            candidate_or_control_id=control_id,
            instrument_or_portfolio_id="EUR_USD",
            direction="LONG",
            source_timestamp_utc="2026-01-05T09:00:00Z",
            source_available_timestamp_utc="2026-01-05T09:00:00Z",
            decision_timestamp_utc=contract.utc(decision),
            event_id=f"{control_id}_H1",
            input_row_hash=contract.sha256_text("h1"),
            feature_name="H1_CONTEXT_LAST_COMPLETED",
            feature_value=1.0,
            feature_available_timestamp_utc="2026-01-05T09:00:00Z",
        ),
        contract.make_event(
            5,
            "FEATURE_COMPUTED",
            family_id="M5_DAY_TRADING_MTF",
            adapter_id=ADAPTER_ID,
            candidate_or_control_id=control_id,
            instrument_or_portfolio_id="EUR_USD",
            direction="LONG",
            source_timestamp_utc="2026-01-05T09:55:00Z",
            source_available_timestamp_utc="2026-01-05T09:55:00Z",
            decision_timestamp_utc=contract.utc(decision),
            event_id=f"{control_id}_M5",
            input_row_hash=contract.sha256_text("m5"),
            feature_name="M5_SIGNAL_CANDLE_COMPLETED",
            feature_value=1.0,
            feature_available_timestamp_utc="2026-01-05T09:55:00Z",
        ),
        contract.make_event(
            6,
            "SIGNAL_EMITTED",
            family_id="M5_DAY_TRADING_MTF",
            adapter_id=ADAPTER_ID,
            candidate_or_control_id=control_id,
            instrument_or_portfolio_id="EUR_USD",
            direction="LONG",
            source_timestamp_utc="2026-01-05T09:55:00Z",
            source_available_timestamp_utc="2026-01-05T09:55:00Z",
            decision_timestamp_utc=contract.utc(decision),
            event_id=f"{control_id}_SIGNAL",
            input_row_hash=contract.sha256_text("signal"),
            signal_value=1.0,
            signal_action="TAKE",
        ),
        contract.make_event(
            7,
            "ENTRY_FILLED",
            family_id="M5_DAY_TRADING_MTF",
            adapter_id=ADAPTER_ID,
            candidate_or_control_id=control_id,
            instrument_or_portfolio_id="EUR_USD",
            direction="LONG",
            source_timestamp_utc="2026-01-05T09:55:00Z",
            source_available_timestamp_utc="2026-01-05T09:55:00Z",
            decision_timestamp_utc=contract.utc(decision),
            execution_timestamp_utc=contract.utc(execution),
            event_id=f"{control_id}_ENTRY",
            trade_id=f"{control_id}_TRADE_001",
            input_row_hash=contract.sha256_text("entry"),
            entry_side="ask",
            entry_bid=1.1000,
            entry_ask=1.1002,
            entry_fill=1.1002,
            stop_price=1.0992,
            target_or_exit_contract="m5_next_interval_time_exit",
            initial_risk=1.0,
            equity_before=10000.0,
        ),
        contract.make_event(
            8,
            "EXIT_FILLED",
            family_id="M5_DAY_TRADING_MTF",
            adapter_id=ADAPTER_ID,
            candidate_or_control_id=control_id,
            instrument_or_portfolio_id="EUR_USD",
            direction="LONG",
            source_timestamp_utc="2026-01-05T09:55:00Z",
            source_available_timestamp_utc="2026-01-05T09:55:00Z",
            decision_timestamp_utc=contract.utc(decision),
            execution_timestamp_utc=contract.utc(exit_time),
            event_id=f"{control_id}_EXIT",
            trade_id=f"{control_id}_TRADE_001",
            input_row_hash=contract.sha256_text("exit"),
            exit_side="bid",
            exit_bid=1.1015,
            exit_ask=1.1017,
            exit_fill=1.1015,
            gross_pnl=1.2,
            spread_cost=0.1,
            slippage_cost=0.0,
            financing_cost=0.0,
            net_pnl=1.1,
            initial_risk=1.0,
            realized_r=1.1,
            equity_before=10000.0,
            equity_after=10001.1,
        ),
        contract.make_event(
            9,
            "COST_APPLIED",
            family_id="M5_DAY_TRADING_MTF",
            adapter_id=ADAPTER_ID,
            candidate_or_control_id=control_id,
            instrument_or_portfolio_id="EUR_USD",
            direction="LONG",
            decision_timestamp_utc=contract.utc(decision),
            execution_timestamp_utc=contract.utc(exit_time),
            event_id=f"{control_id}_COST",
            trade_id=f"{control_id}_TRADE_001",
            spread_cost=0.1,
            slippage_cost=0.0,
            financing_cost=0.0,
        ),
        contract.make_event(10, "RUN_END", family_id="M5_DAY_TRADING_MTF", adapter_id=ADAPTER_ID, candidate_or_control_id=control_id, event_id=f"{control_id}_END"),
    ]
    reported = {
        "trade_count": 1,
        "wins": 1,
        "losses": 0,
        "gross_pnl": 1.2,
        "net_pnl": 1.1,
        "net_expectancy": 1.1,
        "profit_factor": 999.0,
        "net_r": 1.1,
        "max_drawdown": 0.0,
        "average_cost_r": 0.1,
    }
    m5_state = read_json(M5_STATE)
    multi_state = read_json(MULTI_STATE)
    external_state = read_json(EXTERNAL_STATE)
    return contract.make_trace(
        trace_run_id=f"{control_id}_RUN",
        run_kind="M5_POSITIVE_CONTROL",
        family_id="M5_DAY_TRADING_MTF",
        adapter_id=ADAPTER_ID,
        candidate_or_control_id=control_id,
        direction_scope="LONG",
        input_artifact_ids=["M5_CORPUS_V2", "MULTI_REGIME_CORPUS_V3", "EXTERNAL_INFORMATION_CORPUS_V3"],
        input_artifact_hashes={
            "M5_CORPUS_V2": m5_state.get("aggregate_corpus_fingerprint", "UNKNOWN"),
            "MULTI_REGIME_CORPUS_V3": multi_state.get("aggregate_hash", "UNKNOWN"),
            "EXTERNAL_INFORMATION_CORPUS_V3": external_state.get("normalized_hash") or external_state.get("state_hash", "UNKNOWN"),
        },
        adapter_code_hash=adapter_code_hash(),
        configuration_hash=contract.sha256_text(control_id),
        random_seed=30030,
        events=events,
        reported_metrics=reported,
    )


def validate_m5_trace(trace: dict[str, Any], rerun_trace: dict[str, Any] | None = None) -> dict[str, Any]:
    base = validator.validate_trace(trace, m5_spec(), rerun_trace)
    events = trace["events"]
    by_name = {event.get("feature_name"): event for event in events if event.get("event_type") == "FEATURE_COMPUTED"}
    entry = next(event for event in events if event["event_type"] == "ENTRY_FILLED")
    decision = validator.parse_time(entry["decision_timestamp_utc"])
    execution = validator.parse_time(entry["execution_timestamp_utc"])
    m5_source = validator.parse_time(by_name["M5_SIGNAL_CANDLE_COMPLETED"]["source_timestamp_utc"])
    extra = {
        "D1_COMPLETED_BEFORE_DECISION": validator.parse_time(by_name["D1_CONTEXT_LAST_COMPLETED"]["feature_available_timestamp_utc"]) <= decision,
        "H4_COMPLETED_BEFORE_DECISION": validator.parse_time(by_name["H4_CONTEXT_LAST_COMPLETED"]["feature_available_timestamp_utc"]) <= decision,
        "H1_COMPLETED_BEFORE_DECISION": validator.parse_time(by_name["H1_CONTEXT_LAST_COMPLETED"]["feature_available_timestamp_utc"]) <= decision,
        "M5_SIGNAL_CANDLE_COMPLETE": by_name["M5_SIGNAL_CANDLE_COMPLETED"]["feature_value"] == 1.0 and m5_source < decision,
        "NEXT_M5_ENTRY": execution == decision + timedelta(minutes=5),
        "M5_CORPUS_PRESENT": trace["input_artifact_hashes"].get("M5_CORPUS_V2") not in {"", "UNKNOWN", None},
    }
    base["criteria"].update(extra)
    base["overall_valid"] = all(base["criteria"].values())
    return base


def m5_mutation_rejected(mutation: str) -> bool:
    trace = make_m5_trace()
    if mutation == "partial_h1_context":
        trace["events"][3]["feature_available_timestamp_utc"] = "2026-01-05T10:30:00Z"
    elif mutation == "signal_candle_entry":
        trace["events"][6]["execution_timestamp_utc"] = "2026-01-05T10:00:00Z"
    elif mutation == "wrong_bid_ask":
        trace["events"][6]["entry_fill"] = trace["events"][6]["entry_bid"]
    elif mutation == "duplicate_m5_event":
        trace["events"][7]["event_id"] = trace["events"][6]["event_id"]
    elif mutation == "future_external_information":
        trace["events"][1]["source_available_timestamp_utc"] = "2026-01-05T10:30:00Z"
    else:
        raise ValueError(mutation)
    return not validate_m5_trace(trace, make_m5_trace())["overall_valid"]


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    trace = make_m5_trace()
    validation = validate_m5_trace(trace, make_m5_trace())
    mutations = {name: m5_mutation_rejected(name) for name in ["partial_h1_context", "signal_candle_entry", "wrong_bid_ask", "duplicate_m5_event", "future_external_information"]}
    state = {
        "schema": "AIOS_FOREX_M5_DAY_TRADING_ADAPTER_V2_STATE",
        "packet_id": PACKET_ID,
        "status": "M5_DAY_TRADING_BRIDGE_CERTIFIED" if validation["overall_valid"] and all(mutations.values()) else "M5_BRIDGE_REPAIR_REQUIRED",
        "positive_trace_chain_hash": trace["trace_chain_hash"],
        "validator_result": validation,
        "mutation_rejections": mutations,
        "historical_holdout_claimed": False,
        "forward_required_for_m5_profitability": True,
    }
    state["state_hash"] = contract.sha256_text(stable(state))
    atomic_json(STATE, state)
    atomic_json(ROOT / "m5_day_trading_adapter_v2_state.json", state)
    REPORT.write_text(
        "# AIOS Forex M5 Day-Trading Adapter V2\n\n"
        f"Status: `{state['status']}`\n\n"
        "The bridge uses observed M5 corpus evidence only for bridge validation; no untouched M5 historical holdout is claimed.\n",
        encoding="utf-8",
    )
    return state


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
