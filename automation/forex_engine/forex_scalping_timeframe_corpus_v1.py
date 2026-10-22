"""Packet 033 scalping timeframe corpus freeze status."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from automation.forex_engine.forex_scalping_timeframe_coverage_v1 import classify_timeframes


PACKET_ID = "PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033"
STATE = Path("Reports/forex_delivery/AIOS_FOREX_SCALPING_TIMEFRAME_CORPUS_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_SCALPING_TIMEFRAME_CORPUS_V1_REPORT.md")
HANDOFF = Path("Reports/forex_delivery/AIOS_FOREX_SCALPING_DATA_HUMAN_HANDOFF_V1.md")
HANDOFF_STATE = Path("Reports/forex_delivery/AIOS_FOREX_SCALPING_DATA_HUMAN_HANDOFF_V1_STATE.json")


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


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


def run() -> dict[str, Any]:
    matrix = classify_timeframes()
    unavailable = [tf for tf, row in matrix.items() if row["native_or_derived_status"] == "UNAVAILABLE_WITH_CURRENT_EVIDENCE"]
    acquisition_needed = [tf for tf in unavailable if tf in {"S5", "S10", "S15", "S30", "M1", "M2", "M4"}]
    state = {
        "schema": "AIOS_FOREX_SCALPING_TIMEFRAME_CORPUS.v1",
        "packet_id": PACKET_ID,
        "status": "HUMAN_SCALPING_TIMEFRAME_DATA_ACQUISITION_REQUIRED" if acquisition_needed else "SCALPING_TIMEFRAME_CORPUS_CURRENT_EVIDENCE_SUFFICIENT",
        "frozen_current_evidence_timeframes": [tf for tf, row in matrix.items() if row["Development_eligible"]],
        "missing_scientifically_relevant_native_timeframes": acquisition_needed,
        "corpus_mutation_performed": False,
        "broker_or_live_api_work": "NO",
        "corpus_hash": sha256_text(stable(matrix)),
    }
    handoff_state = {
        "schema": "AIOS_FOREX_SCALPING_DATA_HUMAN_HANDOFF.v1",
        "packet_id": PACKET_ID,
        "status": state["status"],
        "human_action_required": bool(acquisition_needed),
        "requested_granularities": acquisition_needed,
        "practice_host_only": True,
        "get_only": True,
        "live_host_allowed": False,
        "orders_allowed": False,
        "secret_persistence_allowed": False,
    }
    atomic_json(STATE, state)
    atomic_json(HANDOFF_STATE, handoff_state)
    REPORT.write_text(f"# AIOS Forex Scalping Timeframe Corpus V1\n\n- Status: {state['status']}\n- Corpus mutation performed: NO\n", encoding="utf-8")
    HANDOFF.write_text(
        "# AIOS Forex Scalping Data Human Handoff V1\n\n"
        f"- Status: {state['status']}\n"
        f"- Human action required: {bool(acquisition_needed)}\n"
        f"- Requested granularities: {', '.join(acquisition_needed) if acquisition_needed else 'NONE'}\n"
        "- Use the HUMAN_ONLY helper in WhatIf mode first.\n"
        "- Practice host only. GET-only. No orders. No LIVE host. No secret persistence.\n",
        encoding="utf-8",
    )
    return state


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
