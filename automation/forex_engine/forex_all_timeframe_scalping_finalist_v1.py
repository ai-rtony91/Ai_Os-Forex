"""Packet 033 finalist gate."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


PACKET_ID = "PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033"
GROSS_STATE = Path("Reports/forex_delivery/AIOS_FOREX_ALL_TIMEFRAME_SCALPING_GROSS_EDGE_V1_STATE.json")
REGISTRY = Path("Reports/forex_delivery/AIOS_FOREX_ALL_TIMEFRAME_SCALPING_FINALIST_REGISTRY_V1.json")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_ALL_TIMEFRAME_SCALPING_FINALIST_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_ALL_TIMEFRAME_SCALPING_FINALIST_V1_REPORT.md")


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


def run() -> dict[str, Any]:
    gross = read_json(GROSS_STATE)
    finalists: list[dict[str, Any]] = []
    registry = {
        "schema": "AIOS_FOREX_ALL_TIMEFRAME_SCALPING_FINALIST_REGISTRY.v1",
        "packet_id": PACKET_ID,
        "status": "NO_FINALISTS",
        "finalist_count": 0,
        "finalists": finalists,
        "reason": "No gross-edge replication/full-cost/search-correction passer exists.",
    }
    state = {
        "schema": "AIOS_FOREX_ALL_TIMEFRAME_SCALPING_FINALIST.v1",
        "packet_id": PACKET_ID,
        "status": "NO_FINALISTS_TO_VALIDATE",
        "gross_status": gross.get("status"),
        "validation_opened": False,
        "forward_opened": False,
        "paper_opened": False,
        "live_opened": False,
        "compounding_opened": False,
    }
    atomic_json(REGISTRY, registry)
    atomic_json(STATE, state)
    REPORT.write_text("# AIOS Forex All-Timeframe Scalping Finalist V1\n\n- Status: NO_FINALISTS_TO_VALIDATE\n- Downstream gates opened: NO\n", encoding="utf-8")
    return state


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
