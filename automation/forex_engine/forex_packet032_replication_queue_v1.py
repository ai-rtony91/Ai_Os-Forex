"""Packet 033 replication queue from Packet 032 raw-positive diagnostics."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


PACKET_ID = "PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033"
SOURCE_PACKET = "PKT-EAST-FOREX-MTF-GROSS-EDGE-DISCOVERY-032"
P32_LEDGER = Path("Reports/forex_delivery/AIOS_FOREX_MTF_HYPOTHESIS_LEDGER_V1.json")
P32_STATE = Path("Reports/forex_delivery/AIOS_FOREX_MTF_GROSS_EDGE_SURFACE_V1_STATE.json")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_PACKET032_REPLICATION_QUEUE_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PACKET032_REPLICATION_QUEUE_V1_REPORT.md")


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def priority(row: dict[str, Any]) -> int:
    if row.get("indicator_family") == "MACD" and row.get("context_timeframe") == "M30":
        return 1
    metrics = row.get("metrics", {})
    if metrics.get("gross_expectancy", 0) > 0 and metrics.get("gross_pf", 0) > 1:
        return 2
    return 9


def build_queue() -> dict[str, Any]:
    ledger_bytes = P32_LEDGER.read_bytes()
    source_state = read_json(P32_STATE)
    ledger_doc = json.loads(ledger_bytes.decode("utf-8-sig"))
    positives = []
    for row in ledger_doc.get("hypotheses", []):
        metrics = row.get("metrics", {})
        if metrics.get("gross_expectancy", 0) > 0 and metrics.get("gross_pf", 0) > 1:
            positives.append(
                {
                    "queue_id": f"PKT033-REP-{len(positives)+1:04d}",
                    "source_packet": SOURCE_PACKET,
                    "packet032_hypothesis_id": row.get("hypothesis_id"),
                    "direction": row.get("direction"),
                    "timeframe": row.get("context_timeframe"),
                    "indicator_combination": row.get("indicator_family"),
                    "parameters": row.get("parameters"),
                    "trade_count": metrics.get("trades"),
                    "gross_expectancy": metrics.get("gross_expectancy"),
                    "gross_pf": metrics.get("gross_pf"),
                    "fold_distribution": {
                        "fold_count": metrics.get("fold_count"),
                        "positive_fold_share": metrics.get("positive_fold_share"),
                    },
                    "breadth_failure": metrics.get("pair_count", 0) < 4 or metrics.get("max_pair_share", 1) > 0.45,
                    "sample_failure": metrics.get("trades", 0) < 50,
                    "nearest_parameter_neighbors": [],
                    "replication_priority": priority(row),
                    "status": "QUEUED_FOR_FULL_REPLICATION",
                    "fingerprint": sha256_text(stable(row)),
                }
            )
    positives.sort(key=lambda r: (r["replication_priority"], r["timeframe"], r["direction"], r["packet032_hypothesis_id"]))
    macd_m30_long = [r for r in positives if r["indicator_combination"] == "MACD" and r["timeframe"] == "M30" and r["direction"] == "LONG"]
    macd_m30_short = [r for r in positives if r["indicator_combination"] == "MACD" and r["timeframe"] == "M30" and r["direction"] == "SHORT"]
    state = {
        "schema": "AIOS_FOREX_PACKET032_REPLICATION_QUEUE.v1",
        "packet_id": PACKET_ID,
        "source_packet": SOURCE_PACKET,
        "status": "PACKET032_REPLICATION_QUEUE_BUILT",
        "packet032_ledger_sha256": sha256_bytes(ledger_bytes),
        "packet032_surface_status": source_state.get("status"),
        "packet032_hypotheses": ledger_doc.get("hypothesis_count"),
        "queued_raw_positive_diagnostics": len(positives),
        "priority_1_count": sum(1 for r in positives if r["replication_priority"] == 1),
        "macd_m30_long_count": len(macd_m30_long),
        "macd_m30_short_count": len(macd_m30_short),
        "macd_m30_replication_neighborhood": {
            "macd_families": [[6, 13, 5], [8, 17, 9], [10, 21, 7], [12, 26, 9], [15, 30, 9], [19, 39, 9], [24, 52, 18]],
            "histogram_variants": ["line_signal_relation", "histogram_sign", "histogram_slope", "zero_line_state", "zero_line_pullback_continuation"],
        },
        "full_pair_replication_complete": False,
        "full_calendar_replication_complete": False,
        "queue_hash": sha256_text(stable(positives)),
        "queue": positives,
    }
    atomic_json(STATE, state)
    REPORT.write_text(
        "\n".join(
            [
                "# AIOS Forex Packet 032 Replication Queue V1",
                "",
                f"- Packet: {PACKET_ID}",
                f"- Status: {state['status']}",
                f"- Packet 032 hypotheses: {state['packet032_hypotheses']}",
                f"- Queued raw positives: {state['queued_raw_positive_diagnostics']}",
                f"- Priority 1 MACD/M30 items: {state['priority_1_count']}",
                f"- Queue hash: {state['queue_hash']}",
                "",
                "No Packet 032 result was promoted. Every item remains queued until full-pair/full-calendar replication executes.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return state


if __name__ == "__main__":
    print(json.dumps(build_queue(), indent=2, sort_keys=True))
