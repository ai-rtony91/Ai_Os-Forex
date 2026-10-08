"""Packet 032 timeframe coverage and resampling audit.

Reads frozen local corpus metadata and small deterministic samples.  Reports
only sanitized coverage facts and hashes; it does not mutate frozen corpora.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


PACKET_ID = "PKT-EAST-FOREX-MTF-GROSS-EDGE-DISCOVERY-032"
SCHEMA = "AIOS_FOREX_MTF_TIMEFRAME_COVERAGE.v1"
M5_STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_V2_STATE.json")
MULTI_STATE = Path("Reports/forex_delivery/AIOS_FOREX_MULTI_REGIME_CORPUS_V3_STATE.json")
PRACTICE_H1_ROOT = Path(".aios/runtime/forex_practice_history_human_inbox")
M5_ROOT = Path(".aios/runtime/forex_m5_immutable_corpus_v2")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_MTF_TIMEFRAME_COVERAGE_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_MTF_TIMEFRAME_COVERAGE_V1_REPORT.md")
TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
DERIVED_FROM_M5 = {"M15": 15, "M30": 30}
DERIVED_FROM_H1 = {"H4": 240, "D1": 1440, "W1": 10080, "MN1": 43200}


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


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def resolve_m5_artifact(path_text: str) -> Path:
    raw = Path(path_text)
    candidates = [raw, M5_ROOT / raw, M5_ROOT / raw.name]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[1]


def first_jsonl_row(path: Path) -> dict[str, Any] | None:
    opener = gzip.open if path.suffix == ".gz" else open
    try:
        with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[arg-type]
            for line in handle:
                if line.strip():
                    return json.loads(line)
    except OSError:
        return None
    return None


def h1_files() -> list[Path]:
    return sorted(PRACTICE_H1_ROOT.glob("*.H1.json"))


def inspect_h1_file(path: Path) -> dict[str, Any]:
    data = read_json(path)
    candles = [c for c in data.get("candles", []) if c.get("complete") is True]
    if not candles:
        return {}
    first = str(candles[0].get("time"))
    last = str(candles[-1].get("time"))
    sample = candles[min(len(candles) - 1, 3)]
    return {
        "records": len(candles),
        "first": first,
        "last": last,
        "bid": "bid" in sample,
        "ask": "ask" in sample,
        "mid": "mid" in sample,
    }


def coverage_matrix() -> dict[str, Any]:
    m5_state = read_json(M5_STATE)
    multi_state = read_json(MULTI_STATE)
    artifacts = m5_state.get("artifacts", [])
    resolved_existing = 0
    sample_row: dict[str, Any] | None = None
    m5_pairs = sorted({str(a.get("instrument")) for a in artifacts if a.get("instrument")})
    for artifact in artifacts[: max(1, min(80, len(artifacts)))]:
        path_text = artifact.get("path")
        if not path_text:
            continue
        path = resolve_m5_artifact(str(path_text))
        if path.exists():
            resolved_existing += 1
            sample_row = sample_row or first_jsonl_row(path)
    h1_stats = [inspect_h1_file(path) for path in h1_files()]
    h1_stats = [item for item in h1_stats if item]
    h1_pairs = [path.name.replace(".H1.json", "") for path in h1_files()]
    h1_first = min((item["first"] for item in h1_stats), default=None)
    h1_last = max((item["last"] for item in h1_stats), default=None)
    h1_records = sum(item["records"] for item in h1_stats)

    m5_first = m5_state.get("start_utc")
    m5_last = m5_state.get("end_utc")
    m5_bid = bool(sample_row and "bid" in sample_row)
    m5_ask = bool(sample_row and "ask" in sample_row)
    m5_mid = bool(sample_row and "mid" in sample_row)
    matrix: dict[str, Any] = {}
    matrix["M1"] = {
        "native_or_resampled": "UNAVAILABLE",
        "source_artifact": "NONE",
        "eligible_for_development": False,
        "reason": "No genuine validated M1 corpus located; Packet 032 forbids synthesis.",
    }
    matrix["M5"] = {
        "native_or_resampled": "NATIVE",
        "source_artifact": "FROZEN_M5_CORPUS_V2",
        "earliest_timestamp": m5_first,
        "latest_timestamp": m5_last,
        "pair_count": len(m5_pairs),
        "artifact_count": len(artifacts),
        "sampled_artifacts_resolved": resolved_existing,
        "bid_available": m5_bid,
        "ask_available": m5_ask,
        "mid_available": m5_mid,
        "completed_candle_guarantee": m5_state.get("status") == "FROZEN_VALID",
        "gap_rate": "SEE_CORPUS_QUALITY_RECONCILIATION",
        "duplicate_count": "SEE_CORPUS_QUALITY_RECONCILIATION",
        "eligible_for_development": m5_state.get("status") == "FROZEN_VALID",
        "eligible_for_validation": "PROVISIONAL_CONSUMED_HISTORY_ONLY",
        "eligible_for_sealed_holdout": False,
        "eligible_only_for_forward": False,
    }
    for tf, minutes in DERIVED_FROM_M5.items():
        matrix[tf] = {
            "native_or_resampled": "DETERMINISTIC_RESAMPLE_FROM_M5",
            "source_artifact": "FROZEN_M5_CORPUS_V2",
            "resample_minutes": minutes,
            "earliest_timestamp": m5_first,
            "latest_timestamp": m5_last,
            "pair_count": len(m5_pairs),
            "bid_available": m5_bid,
            "ask_available": m5_ask,
            "mid_available": m5_mid,
            "completed_candle_guarantee": m5_state.get("status") == "FROZEN_VALID",
            "eligible_for_development": m5_state.get("status") == "FROZEN_VALID",
            "eligible_for_validation": "PROVISIONAL_CONSUMED_HISTORY_ONLY",
            "eligible_for_sealed_holdout": False,
        }
    matrix["H1"] = {
        "native_or_resampled": "NATIVE",
        "source_artifact": "FROZEN_MULTI_REGIME_CORPUS_V3_H1_PRACTICE_INBOX",
        "earliest_timestamp": h1_first,
        "latest_timestamp": h1_last,
        "pair_count": len(h1_pairs),
        "record_count": h1_records,
        "bid_available": any(item["bid"] for item in h1_stats),
        "ask_available": any(item["ask"] for item in h1_stats),
        "mid_available": any(item["mid"] for item in h1_stats),
        "completed_candle_guarantee": multi_state.get("status") == "FROZEN_VALID",
        "eligible_for_development": bool(h1_stats) and multi_state.get("status") == "FROZEN_VALID",
        "eligible_for_validation": True,
        "eligible_for_sealed_holdout": True,
    }
    for tf, minutes in DERIVED_FROM_H1.items():
        matrix[tf] = {
            "native_or_resampled": "DETERMINISTIC_RESAMPLE_FROM_H1",
            "source_artifact": "FROZEN_MULTI_REGIME_CORPUS_V3_H1_PRACTICE_INBOX",
            "resample_minutes": minutes,
            "earliest_timestamp": h1_first,
            "latest_timestamp": h1_last,
            "pair_count": len(h1_pairs),
            "bid_available": matrix["H1"]["bid_available"],
            "ask_available": matrix["H1"]["ask_available"],
            "mid_available": matrix["H1"]["mid_available"],
            "completed_candle_guarantee": multi_state.get("status") == "FROZEN_VALID",
            "eligible_for_development": bool(h1_stats) and multi_state.get("status") == "FROZEN_VALID",
            "eligible_for_validation": True,
            "eligible_for_sealed_holdout": True,
        }
    for tf in TIMEFRAMES:
        matrix.setdefault(tf, {"native_or_resampled": "UNRESOLVED", "eligible_for_development": False})
    return matrix


def run() -> dict[str, Any]:
    matrix = coverage_matrix()
    state = {
        "schema": SCHEMA,
        "packet_id": PACKET_ID,
        "status": "TIMEFRAME_COVERAGE_AUDITED",
        "timeframes": matrix,
        "coverage_hash": sha256_text(stable(matrix)),
        "broker_or_live_api_work": "NO",
    }
    atomic_json(STATE, state)
    lines = [
        "# AIOS Forex MTF Timeframe Coverage V1",
        "",
        f"- Packet: {PACKET_ID}",
        f"- Status: {state['status']}",
        f"- Coverage hash: {state['coverage_hash']}",
        "- Broker/API/live work: NO",
        "",
        "| Timeframe | Availability | Source | Pair count | Development | Sealed Holdout |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for tf in TIMEFRAMES:
        row = matrix[tf]
        lines.append(
            f"| {tf} | {row.get('native_or_resampled')} | {row.get('source_artifact', 'NONE')} | "
            f"{row.get('pair_count', 0)} | {row.get('eligible_for_development', False)} | "
            f"{row.get('eligible_for_sealed_holdout', False)} |"
        )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return state


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
