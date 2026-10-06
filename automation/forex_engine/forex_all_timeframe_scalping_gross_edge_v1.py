"""Packet 033 scalping gross-edge checkpoint.

This module does not rerun Packet 032's 912 hypotheses under new IDs.  It
records the replication queue, classifies current data constraints, and blocks
full replication/search until the missing scalping timeframe evidence is either
provided or explicitly retired by evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from automation.forex_engine.forex_packet032_replication_queue_v1 import build_queue
from automation.forex_engine.forex_scalping_timeframe_corpus_v1 import run as run_corpus
from automation.forex_engine.forex_scalping_timeframe_coverage_v1 import classify_timeframes


PACKET_ID = "PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033"
STATE = Path("Reports/forex_delivery/AIOS_FOREX_ALL_TIMEFRAME_SCALPING_GROSS_EDGE_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_ALL_TIMEFRAME_SCALPING_GROSS_EDGE_V1_REPORT.md")
LEDGER = Path("Reports/forex_delivery/AIOS_FOREX_ALL_TIMEFRAME_SCALPING_HYPOTHESIS_LEDGER_V1.json")


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
    queue = build_queue()
    corpus = run_corpus()
    coverage = classify_timeframes()
    missing_required = corpus["missing_scientifically_relevant_native_timeframes"]
    ledger_entries = []
    for item in queue["queue"]:
        ledger_entries.append(
            {
                "hypothesis_id": f"PKT033-{item['queue_id']}",
                "source_packet": item["source_packet"],
                "replication_or_novel": "REPLICATION",
                "technique_family": "PACKET032_SUPERTREND_MACD_ADX_REPLICATION",
                "indicator_family": item["indicator_combination"],
                "parameters": item["parameters"],
                "direction": item["direction"],
                "regime_timeframe": item["timeframe"],
                "context_timeframe": item["timeframe"],
                "signal_timeframe": item["timeframe"],
                "execution_timeframe": item["timeframe"],
                "pair_universe": "BLOCKED_PENDING_FULL_REPLICATION_COVERAGE",
                "session_event_scope": "ALL_AVAILABLE_AFTER_DATA_GATE",
                "entry_rule": "SOURCE_PACKET032_CAUSAL_SIGNAL",
                "exit_rule": "SOURCE_PACKET032_FIXED_HORIZON_GROSS_DIAGNOSTIC",
                "cost_policy": "NOT_OPENED_UNTIL_GROSS_REPLICATION_PASS",
                "data_hashes": {"packet032_ledger_sha256": queue["packet032_ledger_sha256"]},
                "created_utc": "2026-08-31T00:00:00Z",
                "execution_shard": "REPLICATION_QUEUE_ONLY",
                "result": "QUEUED_NOT_EXECUTED_DATA_GATE",
                "behavior_fingerprint": item["fingerprint"],
            }
        )
    ledger = {
        "schema": "AIOS_FOREX_ALL_TIMEFRAME_SCALPING_HYPOTHESIS_LEDGER.v1",
        "packet_id": PACKET_ID,
        "screen": {"attempted": 0, "status": "NOT_OPENED_DATA_GATE"},
        "full_replication": {"attempted": 0, "queued": queue["queued_raw_positive_diagnostics"], "status": "PACKET032_REPLICATION_INCOMPLETE"},
        "interactions": {"attempted": 0, "status": "NOT_OPENED_DATA_GATE"},
        "total_attempted": 0,
        "effective_trials": 0,
        "hidden_trials_possible": False,
        "entries": ledger_entries,
        "ledger_hash": sha256_text(stable(ledger_entries)),
    }
    atomic_json(LEDGER, ledger)
    state = {
        "schema": "AIOS_FOREX_ALL_TIMEFRAME_SCALPING_GROSS_EDGE.v1",
        "packet_id": PACKET_ID,
        "status": "HUMAN_SCALPING_TIMEFRAME_DATA_ACQUISITION_REQUIRED" if missing_required else "PACKET032_REPLICATION_INCOMPLETE",
        "packet032_replication_queue_total": queue["queued_raw_positive_diagnostics"],
        "replication_completed": 0,
        "macd_m30_long_queued": queue["macd_m30_long_count"],
        "macd_m30_short_queued": queue["macd_m30_short_count"],
        "all_requested_timeframes_classified": True,
        "all_eligible_timeframes_tested": False,
        "all_scalping_families_classified": False,
        "full_pair_replication_complete": False,
        "full_calendar_replication_complete": False,
        "full_parameter_family_complete": False,
        "search_family_exhausted": False,
        "scored_first_pass_subset": False,
        "missing_timeframes_requiring_human_data": missing_required,
        "long_gross_edge": "NOT_PROVEN",
        "short_gross_edge": "NOT_PROVEN",
        "full_cost_edge": "NOT_OPENED",
        "validation_opened": False,
        "forward_opened": False,
        "paper_opened": False,
        "live_opened": False,
        "compounding_opened": False,
        "hypothesis_ledger_hash": ledger["ledger_hash"],
        "coverage_hash": sha256_text(stable(coverage)),
    }
    atomic_json(STATE, state)
    REPORT.write_text(
        "\n".join(
            [
                "# AIOS Forex All-Timeframe Scalping Gross Edge V1",
                "",
                f"- Status: {state['status']}",
                f"- Packet 032 raw positives queued: {state['packet032_replication_queue_total']}",
                f"- Full replications completed: {state['replication_completed']}",
                f"- Missing required data: {', '.join(missing_required) if missing_required else 'NONE'}",
                "- Search-family exhausted: false",
                "- Gross/full-cost/Validation/PAPER/LIVE/compounding: not opened",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return state


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
