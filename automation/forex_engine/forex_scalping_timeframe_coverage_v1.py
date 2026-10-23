"""Packet 033 expanded timeframe coverage classification."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from automation.forex_engine.forex_mtf_indicator_coverage_v1 import coverage_matrix as packet032_coverage


PACKET_ID = "PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033"
REQUESTED = ["S1", "S5", "S10", "S15", "S30", "S45", "M1", "M2", "M4", "M5", "M10", "M15", "M30", "H1", "H2", "H3", "H4", "H6", "H8", "H12", "D1", "W1", "MN1", "MO6"]
OANDA_NATIVE = {"S5", "S10", "S15", "S30", "M1", "M2", "M4", "M5", "M10", "M15", "M30", "H1", "H2", "H3", "H4", "H6", "H8", "H12", "D1", "W1", "MN1"}
STATE = Path("Reports/forex_delivery/AIOS_FOREX_SCALPING_TIMEFRAME_COVERAGE_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_SCALPING_TIMEFRAME_COVERAGE_V1_REPORT.md")
P32_COVERAGE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_MTF_TIMEFRAME_COVERAGE_V1_STATE.json")


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


def base_coverage_matrix() -> dict[str, Any]:
    if P32_COVERAGE_STATE.exists():
        data = json.loads(P32_COVERAGE_STATE.read_text(encoding="utf-8-sig"))
        if data.get("status") == "TIMEFRAME_COVERAGE_AUDITED" and isinstance(data.get("timeframes"), dict):
            return data["timeframes"]
    return packet032_coverage()


def classify_timeframes() -> dict[str, Any]:
    base = base_coverage_matrix()
    matrix: dict[str, Any] = {}
    for tf in REQUESTED:
        if tf in base and base[tf].get("eligible_for_development"):
            source = base[tf]
            status = "NATIVE_PROVIDER_GRANULARITY" if source.get("native_or_resampled") == "NATIVE" else "DERIVED_FROM_VALID_LOWER_TIMEFRAME"
            matrix[tf] = {
                "native_or_derived_status": status,
                "provider_native": tf in OANDA_NATIVE,
                "source": source.get("source_artifact"),
                "earliest_timestamp": source.get("earliest_timestamp"),
                "latest_timestamp": source.get("latest_timestamp"),
                "pair_count": source.get("pair_count", 0),
                "sample_count": source.get("record_count") or source.get("artifact_count") or "SEE_SOURCE_CORPUS",
                "bid_ask_availability": bool(source.get("bid_available") and source.get("ask_available")),
                "completed_bar_integrity": bool(source.get("completed_candle_guarantee")),
                "gap_rate": source.get("gap_rate", "SEE_SOURCE_CORPUS"),
                "duplicate_count": source.get("duplicate_count", "SEE_SOURCE_CORPUS"),
                "Development_eligible": True,
                "Validation_eligible": source.get("eligible_for_validation"),
                "Holdout_eligible": bool(source.get("eligible_for_sealed_holdout")),
                "Forward_only": False,
                "exact_exclusion_reason": "",
            }
            continue
        if tf in {"H2", "H3", "H6", "H8", "H12"} and base.get("H1", {}).get("eligible_for_development"):
            h1 = base["H1"]
            matrix[tf] = {
                "native_or_derived_status": "DERIVED_FROM_VALID_LOWER_TIMEFRAME",
                "provider_native": True,
                "source": "FROZEN_MULTI_REGIME_CORPUS_V3_H1_PRACTICE_INBOX",
                "earliest_timestamp": h1.get("earliest_timestamp"),
                "latest_timestamp": h1.get("latest_timestamp"),
                "pair_count": h1.get("pair_count", 0),
                "sample_count": "DERIVED_FROM_H1_COMPLETED_CANDLES",
                "bid_ask_availability": bool(h1.get("bid_available") and h1.get("ask_available")),
                "completed_bar_integrity": True,
                "gap_rate": "SEE_H1_SOURCE_CORPUS",
                "duplicate_count": "SEE_H1_SOURCE_CORPUS",
                "Development_eligible": True,
                "Validation_eligible": True,
                "Holdout_eligible": True,
                "Forward_only": False,
                "exact_exclusion_reason": "",
            }
            continue
        if tf == "M10" and base.get("M5", {}).get("eligible_for_development"):
            m5 = base["M5"]
            matrix[tf] = {
                "native_or_derived_status": "DERIVED_FROM_VALID_LOWER_TIMEFRAME",
                "provider_native": True,
                "source": "FROZEN_M5_CORPUS_V2",
                "earliest_timestamp": m5.get("earliest_timestamp"),
                "latest_timestamp": m5.get("latest_timestamp"),
                "pair_count": m5.get("pair_count", 0),
                "sample_count": "DERIVED_FROM_M5_COMPLETED_CANDLES",
                "bid_ask_availability": True,
                "completed_bar_integrity": True,
                "gap_rate": "SEE_M5_SOURCE_CORPUS",
                "duplicate_count": "SEE_M5_SOURCE_CORPUS",
                "Development_eligible": True,
                "Validation_eligible": "PROVISIONAL_CONSUMED_HISTORY_ONLY",
                "Holdout_eligible": False,
                "Forward_only": False,
                "exact_exclusion_reason": "",
            }
            continue
        if tf == "MO6" and base.get("MN1", {}).get("eligible_for_development"):
            mn1 = base["MN1"]
            matrix[tf] = {
                "native_or_derived_status": "DERIVED_FROM_VALID_LOWER_TIMEFRAME",
                "provider_native": False,
                "source": "SIX_COMPLETE_CONSECUTIVE_MN1_CANDLES_JAN_JUN_JUL_DEC",
                "earliest_timestamp": mn1.get("earliest_timestamp"),
                "latest_timestamp": mn1.get("latest_timestamp"),
                "pair_count": mn1.get("pair_count", 0),
                "sample_count": "DERIVED_FROM_COMPLETE_MONTHLY_CANDLES",
                "bid_ask_availability": True,
                "completed_bar_integrity": True,
                "gap_rate": "SEE_MN1_SOURCE_CORPUS",
                "duplicate_count": "SEE_MN1_SOURCE_CORPUS",
                "Development_eligible": True,
                "Validation_eligible": True,
                "Holdout_eligible": True,
                "Forward_only": False,
                "exact_exclusion_reason": "",
            }
            continue
        reason = "No current frozen local artifact at required granularity or valid lower timeframe for exact construction."
        if tf == "S1":
            reason = "OANDA candle granularity list does not include S1; no tick/S1 historical source is frozen locally."
        if tf == "S45":
            reason = "S45 is not provider-native and requires valid S5/S15 history; no such frozen local artifact exists."
        matrix[tf] = {
            "native_or_derived_status": "UNAVAILABLE_WITH_CURRENT_EVIDENCE",
            "provider_native": tf in OANDA_NATIVE,
            "source": "NONE",
            "earliest_timestamp": None,
            "latest_timestamp": None,
            "pair_count": 0,
            "sample_count": 0,
            "bid_ask_availability": False,
            "completed_bar_integrity": False,
            "gap_rate": None,
            "duplicate_count": None,
            "Development_eligible": False,
            "Validation_eligible": False,
            "Holdout_eligible": False,
            "Forward_only": tf == "S1",
            "exact_exclusion_reason": reason,
        }
    return matrix


def run() -> dict[str, Any]:
    matrix = classify_timeframes()
    unavailable = [tf for tf, row in matrix.items() if row["native_or_derived_status"] == "UNAVAILABLE_WITH_CURRENT_EVIDENCE"]
    state = {
        "schema": "AIOS_FOREX_SCALPING_TIMEFRAME_COVERAGE.v1",
        "packet_id": PACKET_ID,
        "status": "SCALPING_TIMEFRAMES_CLASSIFIED",
        "official_provider_capability_source": "OANDA v20 Instrument Definitions / CandlestickGranularity",
        "requested_timeframes": REQUESTED,
        "all_requested_timeframes_classified": True,
        "unavailable_timeframes": unavailable,
        "human_data_acquisition_required": bool(unavailable),
        "timeframes": matrix,
        "coverage_hash": sha256_text(stable(matrix)),
    }
    atomic_json(STATE, state)
    lines = ["# AIOS Forex Scalping Timeframe Coverage V1", "", f"- Status: {state['status']}", f"- Unavailable: {', '.join(unavailable) if unavailable else 'NONE'}", f"- Coverage hash: {state['coverage_hash']}", "", "| TF | Status | Provider native | Dev | Reason |", "|---|---|---:|---:|---|"]
    for tf in REQUESTED:
        row = matrix[tf]
        lines.append(f"| {tf} | {row['native_or_derived_status']} | {row['provider_native']} | {row['Development_eligible']} | {row['exact_exclusion_reason']} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return state


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
