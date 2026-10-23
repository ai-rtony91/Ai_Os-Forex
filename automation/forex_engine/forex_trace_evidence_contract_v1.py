"""Trace evidence contract for Packet 030.

The trace producer records facts only. It does not emit pass/fail verdicts or
certifications. Independent validators derive all control outcomes.
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


PACKET_ID = "PKT-EAST-FOREX-TRACE-BACKED-FIDELITY-030"
TRACE_SCHEMA = "AIOS_FOREX_TRACE_EVIDENCE_CONTRACT_V1"
EXECUTION_CORE_ID = "aios.execution.bidask.next_interval.stop_first.v1"
COST_CORE_ID = "aios.cost.single_charge.spread_slippage_financing.v1"
METRIC_CORE_ID = "aios.metric.recompute.r_expectancy_pf_dd.v1"
STATE = Path("Reports/forex_delivery/AIOS_FOREX_TRACE_EVIDENCE_CONTRACT_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_TRACE_EVIDENCE_CONTRACT_V1_REPORT.md")
ROOT = Path(".aios/runtime/forex_trace_backed_family_controls_v2")
PRODUCER_FORBIDDEN_KEYS = {
    "pass",
    "passed",
    "verdict",
    "certified",
    "chronology_pass",
    "leakage_pass",
    "path_identity_pass",
    "cost_path_pass",
    "metric_path_pass",
    "direction_isolation_pass",
    "deterministic_pass",
}


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def content_hash(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def utc(value: str | datetime) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return value


def no_forbidden_producer_keys(value: Any) -> bool:
    found: list[str] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if str(key).lower() in PRODUCER_FORBIDDEN_KEYS:
                    found.append(str(key))
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return not found


def make_event(sequence_number: int, event_type: str, **fields: Any) -> dict[str, Any]:
    event = {"sequence_number": sequence_number, "event_type": event_type}
    event.update({key: value for key, value in fields.items() if value is not None})
    if not no_forbidden_producer_keys(event):
        raise ValueError("trace producer attempted to emit a forbidden verdict-like field")
    return event


def chain_events(events: list[dict[str, Any]]) -> str:
    previous = "0" * 64
    for event in events:
        event["previous_event_hash"] = previous
        current_payload = stable({key: value for key, value in event.items() if key != "event_hash"})
        current = sha256_text(current_payload)
        event["event_hash"] = current
        previous = current
    return previous


def make_trace(
    *,
    trace_run_id: str,
    run_kind: str,
    family_id: str,
    adapter_id: str,
    candidate_or_control_id: str,
    direction_scope: str,
    input_artifact_ids: list[str],
    input_artifact_hashes: dict[str, str],
    adapter_code_hash: str,
    configuration_hash: str,
    random_seed: int,
    events: list[dict[str, Any]],
    reported_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ordered = sorted(events, key=lambda event: int(event["sequence_number"]))
    if [event["sequence_number"] for event in ordered] != list(range(1, len(ordered) + 1)):
        raise ValueError("trace events must be contiguous and ordered")
    trace_chain_hash = chain_events(ordered)
    trace = {
        "trace_schema": TRACE_SCHEMA,
        "trace_run_id": trace_run_id,
        "run_kind": run_kind,
        "family_id": family_id,
        "adapter_id": adapter_id,
        "candidate_or_control_id": candidate_or_control_id,
        "direction_scope": direction_scope,
        "input_artifact_ids": input_artifact_ids,
        "input_artifact_hashes": input_artifact_hashes,
        "adapter_code_hash": adapter_code_hash,
        "execution_core_id": EXECUTION_CORE_ID,
        "execution_core_hash": sha256_text(EXECUTION_CORE_ID),
        "cost_core_id": COST_CORE_ID,
        "cost_core_hash": sha256_text(COST_CORE_ID),
        "metric_core_id": METRIC_CORE_ID,
        "metric_core_hash": sha256_text(METRIC_CORE_ID),
        "configuration_hash": configuration_hash,
        "random_seed": random_seed,
        "started_utc": "2026-01-01T00:00:00Z",
        "completed_utc": "2026-01-01T00:00:01Z",
        "trace_event_count": len(ordered),
        "events": ordered,
        "reported_metrics": reported_metrics or {},
        "trace_chain_hash": trace_chain_hash,
    }
    if not no_forbidden_producer_keys(trace):
        raise ValueError("trace producer attempted to emit a forbidden verdict-like field")
    return trace


def contract_state() -> dict[str, Any]:
    state = {
        "schema": "AIOS_FOREX_TRACE_EVIDENCE_CONTRACT_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "TRACE_CONTRACT_DEFINED",
        "trace_schema": TRACE_SCHEMA,
        "producer_forbidden_keys": sorted(PRODUCER_FORBIDDEN_KEYS),
        "execution_core_id": EXECUTION_CORE_ID,
        "cost_core_id": COST_CORE_ID,
        "metric_core_id": METRIC_CORE_ID,
        "producer_writes_verdict": False,
        "hash_chain": "event_hash covers ordered event content and previous_event_hash",
    }
    state["state_hash"] = sha256_text(stable(state))
    return state


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    state = contract_state()
    atomic_json(STATE, state)
    atomic_json(ROOT / "trace_contract_state.json", state)
    REPORT.write_text(
        "# AIOS Forex Trace Evidence Contract V1\n\n"
        f"Status: `{state['status']}`\n\n"
        "The trace producer records facts only. It rejects verdict-like fields before serialization.\n",
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
