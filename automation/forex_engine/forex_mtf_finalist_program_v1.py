"""Packet 032 finalist freeze / downstream gate controller.

This module freezes finalists only when the gross-edge surface has produced
search-correctable survivors.  It never opens PAPER, LIVE, funding, or
compounding without the upstream gates required by Packet 032.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


PACKET_ID = "PKT-EAST-FOREX-MTF-GROSS-EDGE-DISCOVERY-032"
SCHEMA = "AIOS_FOREX_MTF_FINALIST_PROGRAM.v1"
SURFACE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_MTF_GROSS_EDGE_SURFACE_V1_STATE.json")
LEDGER = Path("Reports/forex_delivery/AIOS_FOREX_MTF_HYPOTHESIS_LEDGER_V1.json")
REGISTRY = Path("Reports/forex_delivery/AIOS_FOREX_MTF_FINALIST_REGISTRY_V1.json")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_MTF_FINALIST_PROGRAM_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_MTF_FINALIST_PROGRAM_V1_REPORT.md")


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def run_finalist_program() -> dict[str, Any]:
    surface = read_json(SURFACE_STATE)
    ledger_doc = read_json(LEDGER)
    hypotheses = ledger_doc.get("hypotheses", [])
    survivors = [h for h in hypotheses if h.get("result") == "GROSS_SCREEN_SURVIVOR_PENDING_FULL_SEARCH_NULL"]
    finalists: list[dict[str, Any]] = []
    for direction in ("LONG", "SHORT"):
        directional = [h for h in survivors if h.get("direction") == direction]
        directional.sort(key=lambda h: (h.get("metrics", {}).get("gross_expectancy", 0), h.get("metrics", {}).get("gross_pf", 0)), reverse=True)
        for row in directional[:6]:
            finalists.append(
                {
                    "candidate_id": row["hypothesis_id"].replace("MTF032-H", "MTF032-FINALIST-"),
                    "source_hypothesis_id": row["hypothesis_id"],
                    "direction": direction,
                    "indicator_family": row["indicator_family"],
                    "context_timeframe": row["context_timeframe"],
                    "signal_timeframe": row["signal_timeframe"],
                    "execution_timeframe": row["execution_timeframe"],
                    "entry": "next completed executable candle after signal",
                    "initial_stop": "indicator-window realized range, frozen before outcome",
                    "exit_family": "NOT_OPENED_UNTIL_SEARCH_NULL_AND_COST_FRONTIER_PASS",
                    "cost_policy": "NOT_OPENED_UNTIL_GROSS_AND_SEARCH_CORRECTION_PASS",
                    "fingerprint": sha256_text(stable(row)),
                    "status": "FROZEN_FOR_NULL_ONLY_NOT_VALIDATION",
                }
            )
    registry = {
        "schema": "AIOS_FOREX_MTF_FINALIST_REGISTRY.v1",
        "packet_id": PACKET_ID,
        "status": "NO_FINALISTS" if not finalists else "FINALISTS_FROZEN_PENDING_FULL_SEARCH_NULL",
        "finalist_count": len(finalists),
        "max_long_finalists": 6,
        "max_short_finalists": 6,
        "validation_opened": False,
        "paper_opened": False,
        "live_opened": False,
        "registry_hash": sha256_text(stable(finalists)),
        "finalists": finalists,
    }
    atomic_json(REGISTRY, registry)
    state = {
        "schema": SCHEMA,
        "packet_id": PACKET_ID,
        "status": "NO_FINALISTS_TO_VALIDATE" if not finalists else "VALIDATION_BLOCKED_SEARCH_NULL_REQUIRED",
        "surface_status": surface.get("status"),
        "finalist_count": len(finalists),
        "bootstrap_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "forward_opened": False,
        "v12_opened": False,
        "paper_opened": False,
        "live_opened": False,
        "compounding_opened": False,
        "reason": "No gross-edge survivors reached the finalist gate." if not finalists else "Survivors require full search-family null correction before Validation.",
        "registry_hash": registry["registry_hash"],
    }
    atomic_json(STATE, state)
    lines = [
        "# AIOS Forex MTF Finalist Program V1",
        "",
        f"- Packet: {PACKET_ID}",
        f"- Status: {state['status']}",
        f"- Finalists: {len(finalists)}",
        f"- Registry hash: {registry['registry_hash']}",
        "- Validation/Holdout/Forward/V12/PAPER/LIVE/compounding opened: NO",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return state


if __name__ == "__main__":
    print(json.dumps(run_finalist_program(), indent=2, sort_keys=True))
