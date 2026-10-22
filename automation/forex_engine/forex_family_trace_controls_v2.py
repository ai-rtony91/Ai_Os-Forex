"""Trace-backed Family A-H controls for Packet 030."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine import forex_family_adapter_repair_v3 as adapters
from automation.forex_engine import forex_trace_control_validator_v1 as validator
from automation.forex_engine import forex_trace_evidence_contract_v1 as contract


PACKET_ID = "PKT-EAST-FOREX-TRACE-BACKED-FIDELITY-030"
ROOT = Path(".aios/runtime/forex_trace_backed_family_controls_v2")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_TRACE_BACKED_FAMILY_CONTROLS_V2_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_TRACE_BACKED_FAMILY_CONTROLS_V2_REPORT.md")


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


def validate_control_pair(family_id: str) -> dict[str, Any]:
    positive_spec = adapters.positive_spec(family_id)
    positive_validator_spec = positive_spec.__dict__ | {"adapter_code_hash": adapters.adapter_code_hash()}
    positive_trace = adapters.run_family_adapter(positive_spec)
    positive_rerun = adapters.run_family_adapter(positive_spec)
    positive_result = validator.validate_trace(positive_trace, positive_validator_spec, positive_rerun)
    negative_rows = []
    for suffix in ("INVALID_SHORTCUT", "LEAKAGE_SHORTCUT"):
        negative_spec = adapters.negative_spec(family_id, suffix=suffix)
        negative_validator_spec = negative_spec.__dict__ | {"adapter_code_hash": adapters.adapter_code_hash()}
        negative_trace = adapters.run_family_adapter(negative_spec)
        negative_result = validator.validate_trace(negative_trace, negative_validator_spec, adapters.run_family_adapter(negative_spec))
        negative_rows.append(
            {
                "control_id": negative_spec.control_id,
                "trace_chain_hash": negative_trace["trace_chain_hash"],
                "validator_result": negative_result,
            }
        )
    family_valid = positive_result["overall_valid"] and all(row["validator_result"]["overall_valid"] for row in negative_rows)
    return {
        "family_id": family_id,
        "adapter_id": positive_spec.adapter_id,
        "positive_control": {
            "control_id": positive_spec.control_id,
            "trace_chain_hash": positive_trace["trace_chain_hash"],
            "validator_result": positive_result,
        },
        "negative_controls": negative_rows,
        "trace_backed_control_valid": family_valid,
    }


def execute_controls() -> dict[str, Any]:
    rows = [validate_control_pair(family_id) for family_id in adapters.FAMILIES]
    state = {
        "schema": "AIOS_FOREX_TRACE_BACKED_FAMILY_CONTROLS_V2_STATE",
        "packet_id": PACKET_ID,
        "status": "TRACE_BACKED_FAMILY_CONTROLS_CERTIFIED"
        if all(row["trace_backed_control_valid"] for row in rows)
        else "TRACE_CONTROL_REPAIR_REQUIRED",
        "family_count": len(rows),
        "families_valid": sum(1 for row in rows if row["trace_backed_control_valid"]),
        "families_repair_required": [row["family_id"] for row in rows if not row["trace_backed_control_valid"]],
        "producer_no_verdict_fields": all(
            row["positive_control"]["validator_result"]["criteria"]["PRODUCER_NO_VERDICT_FIELDS"]
            and all(negative["validator_result"]["criteria"]["PRODUCER_NO_VERDICT_FIELDS"] for negative in row["negative_controls"])
            for row in rows
        ),
        "rows": rows,
    }
    state["state_hash"] = contract.sha256_text(stable(state))
    return state


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    state = execute_controls()
    atomic_json(STATE, state)
    atomic_json(ROOT / "family_trace_controls_v2_state.json", state)
    REPORT.write_text(
        "# AIOS Forex Trace-Backed Family Controls V2\n\n"
        f"Status: `{state['status']}`\n\n"
        f"Families valid: `{state['families_valid']}` / `{state['family_count']}`\n\n"
        "The status is derived from independent validator results over raw traces.\n",
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
