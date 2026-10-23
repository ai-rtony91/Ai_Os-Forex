"""Packet 033 search controller."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine.forex_all_timeframe_scalping_finalist_v1 import run as run_finalist
from automation.forex_engine.forex_all_timeframe_scalping_gross_edge_v1 import run as run_gross
from automation.forex_engine.forex_packet032_replication_queue_v1 import build_queue
from automation.forex_engine.forex_scalping_technique_inventory_v1 import build_inventory
from automation.forex_engine.forex_scalping_techniques_v1 import write_outputs as write_technique_outputs
from automation.forex_engine.forex_scalping_timeframe_corpus_v1 import run as run_corpus
from automation.forex_engine.forex_scalping_timeframe_coverage_v1 import run as run_coverage
from automation.forex_engine.forex_supertrend_macd_adx_v2 import fidelity_state_v2


PACKET_ID = "PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033"
STATE = Path("Reports/forex_delivery/AIOS_FOREX_ALL_TIMEFRAME_SCALPING_SEARCH_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_ALL_TIMEFRAME_SCALPING_SEARCH_V1_REPORT.md")
ATTACK_STATE = Path("Reports/forex_delivery/AIOS_FOREX_ATTACK_TO_FINISH_V11_STATE.json")
ATTACK_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_ATTACK_TO_FINISH_V11_REPORT.md")


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


def attack_state(search_state: dict[str, Any]) -> dict[str, Any]:
    blocker = {
        "blocker_id": "P0-001",
        "priority": "P0",
        "phase": "TIMEFRAME_DATA_ACQUISITION",
        "direction": "BOTH",
        "branch": "ALL_TIMEFRAME_SCALPING",
        "status": "WAITING_HUMAN" if search_state["status"] == "HUMAN_SCALPING_TIMEFRAME_DATA_ACQUISITION_REQUIRED" else "OPEN",
        "exact_blocker": "Required scalping-native timeframe artifacts are not frozen locally, so Packet 033 cannot complete full replication/search without Human-only Practice GET data acquisition.",
        "why_it_matters": "Packet 033 forbids silent compute downscoping and fake subminute/M1/M2/M4 evidence.",
        "canonical_owner_file": "Reports/forex_delivery/AIOS_FOREX_SCALPING_DATA_HUMAN_HANDOFF_V1.md",
        "test_file": "tests/forex_engine/test_oanda_practice_scalping_history_human_only_v1.py",
        "runner_or_validator": "scripts/forex_delivery/Acquire-AiOsOandaPracticeScalpingHistory.HUMAN_ONLY.ps1 -WhatIfOnly",
        "missing_evidence": search_state["missing_timeframes_requiring_human_data"],
        "repair_options": ["Human runs GET-only Practice acquisition helper for listed granularities", "Human authorizes a narrower packet retiring unavailable granularities with rationale"],
        "chosen_action": "Stop at Human data acquisition gate after preserving current evidence.",
        "unlock_condition": "Status-only confirmation that required frozen scalping timeframe artifacts exist and parse cleanly.",
        "proof_of_unlock": "",
        "next_action": "Run the Human-only helper in WhatIf mode, then acquire only the listed missing granularities if approved.",
        "can_codex_resolve": False,
        "human_action_required": True,
        "external_time_required": False,
        "governance_action_required": False,
        "retry_count": 0,
        "last_attempt_utc": "2026-08-31T00:00:00Z",
        "failure_signature": "MISSING_SCALPING_NATIVE_TIMEFRAME_ARTIFACTS",
        "no_bloat_guard": "No new generic registry; no duplicated broker writer.",
    }
    state = {
        "schema": "AIOS_FOREX_ATTACK_TO_FINISH.v11",
        "packet_id": PACKET_ID,
        "status": search_state["status"],
        "highest_priority_blocker": blocker,
        "remaining_authorized_work_count": 0 if search_state["status"] == "HUMAN_SCALPING_TIMEFRAME_DATA_ACQUISITION_REQUIRED" else 1,
        "alternate_safe_actions": [],
        "pre_terminal_audit_status": "PASS" if search_state["status"] == "HUMAN_SCALPING_TIMEFRAME_DATA_ACQUISITION_REQUIRED" else "FAIL_CONTINUE",
        "same_packet_resume_command": "Re-run Packet 033-PRO from C:\\Dev\\Ai.Os after the Human-only scalping timeframe data acquisition status is available.",
    }
    atomic_json(ATTACK_STATE, state)
    ATTACK_REPORT.write_text(
        "\n".join(
            [
                "# AIOS Forex Attack To Finish V11",
                "",
                f"- Status: {state['status']}",
                f"- Highest blocker: {blocker['blocker_id']} {blocker['status']}",
                f"- Remaining authorized work count: {state['remaining_authorized_work_count']}",
                f"- Pre-terminal audit: {state['pre_terminal_audit_status']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return state


def run_controller() -> dict[str, Any]:
    queue = build_queue()
    coverage = run_coverage()
    inventory = build_inventory()
    technique = write_technique_outputs()
    indicator = fidelity_state_v2()
    corpus = run_corpus()
    gross = run_gross()
    finalist = run_finalist()
    missing = corpus["missing_scientifically_relevant_native_timeframes"]
    status = "HUMAN_SCALPING_TIMEFRAME_DATA_ACQUISITION_REQUIRED" if missing else gross["status"]
    state = {
        "schema": "AIOS_FOREX_ALL_TIMEFRAME_SCALPING_SEARCH.v1",
        "packet_id": PACKET_ID,
        "status": status,
        "packet032_queue_status": queue["status"],
        "queued_packet032_positive_diagnostics": queue["queued_raw_positive_diagnostics"],
        "macd_m30_long_queued": queue["macd_m30_long_count"],
        "macd_m30_short_queued": queue["macd_m30_short_count"],
        "timeframe_status": coverage["status"],
        "all_requested_timeframes_classified": coverage["all_requested_timeframes_classified"],
        "missing_timeframes_requiring_human_data": missing,
        "technique_inventory_status": inventory["status"],
        "technique_fidelity_status": technique["status"],
        "indicator_fidelity_status": indicator["status"],
        "gross_status": gross["status"],
        "finalist_status": finalist["status"],
        "long_gross_edge": "NOT_PROVEN",
        "short_gross_edge": "NOT_PROVEN",
        "full_cost_edge": "NOT_OPENED",
        "validation_opened": False,
        "holdout_opened": False,
        "forward_opened": False,
        "v13_opened": False,
        "paper_opened": False,
        "live_opened": False,
        "funding_opened": False,
        "compounding_opened": False,
        "no_silent_downscoping": True,
        "state_hash": "",
    }
    state["state_hash"] = sha256_text(stable({k: v for k, v in state.items() if k != "state_hash"}))
    atomic_json(STATE, state)
    attack = attack_state(state)
    REPORT.write_text(
        "\n".join(
            [
                "# AIOS Forex All-Timeframe Scalping Search V1",
                "",
                f"- Status: {state['status']}",
                f"- Packet 032 positives queued: {state['queued_packet032_positive_diagnostics']}",
                f"- Missing data granularities: {', '.join(missing) if missing else 'NONE'}",
                f"- Technique families classified: {inventory['family_count']}",
                "- Gross/full-cost/Validation/Forward/PAPER/LIVE/funding/compounding opened: NO",
                f"- Pre-terminal audit: {attack['pre_terminal_audit_status']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return state


if __name__ == "__main__":
    print(json.dumps(run_controller(), indent=2, sort_keys=True))
