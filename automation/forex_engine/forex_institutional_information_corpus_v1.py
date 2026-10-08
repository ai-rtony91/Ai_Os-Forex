"""Packet 016 institutional information corpus freezer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from automation.forex_engine.forex_institutional_data_breakthrough_v1 import (
    CORPUS_ID,
    FROZEN,
    MANIFESTS,
    MARKET_CORPUS_HASH,
    NORMALIZED,
    QUALITY,
    REPORT as ACQUISITION_REPORT,
    STATE as ACQUISITION_STATE,
    atomic_json,
    sha256,
    stable,
)

ROOT = Path(".aios/runtime/forex_institutional_information_corpus_v1")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_INSTITUTIONAL_INFORMATION_CORPUS_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_INSTITUTIONAL_INFORMATION_CORPUS_V1_REPORT.md")


def load_acquisition() -> dict[str, Any]:
    return json.loads(ACQUISITION_STATE.read_text(encoding="utf-8"))


def validate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    required = {
        "source_id",
        "series_id",
        "observation_time_utc",
        "publication_time_utc",
        "strategy_available_time_utc",
        "vintage_or_revision_status",
        "retrieval_time_utc",
        "source_artifact_hash",
        "normalization_code_hash",
    }
    violations = []
    seen = set()
    for index, record in enumerate(records):
        missing = sorted(required - set(record))
        key = (record.get("source_id"), record.get("series_id"), record.get("observation_time_utc"))
        if missing:
            violations.append({"index": index, "reason": "MISSING_REQUIRED_FIELDS", "fields": missing})
        if key in seen:
            violations.append({"index": index, "reason": "DUPLICATE_RECORD_KEY", "key": key})
        seen.add(key)
        if str(record.get("strategy_available_time_utc", "")) < str(record.get("publication_time_utc", "")):
            violations.append({"index": index, "reason": "AVAILABILITY_BEFORE_PUBLICATION"})
    return {"record_count": len(records), "duplicate_count": len(records) - len(seen), "violations": violations, "pass": not violations}


def execute() -> dict[str, Any]:
    acquisition = load_acquisition()
    ROOT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    artifact_hashes = []
    if NORMALIZED.exists():
        for path in sorted(NORMALIZED.glob("*.json")):
            rows = json.loads(path.read_text(encoding="utf-8"))
            records.extend(rows)
            artifact_hashes.append({"path": path.as_posix(), "sha256": sha256(path.read_bytes()), "records": len(rows)})
    quality = validate_records(records)
    status = "FROZEN_VALID" if records and quality["pass"] and acquisition["external_information_coverage_score"] >= 80 else "NOT_FROZEN_CAPABILITY_BELOW_PARITY"
    if acquisition["status"] == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED":
        status = "HUMAN_OFFICIAL_DATA_DROP_REQUIRED"
    manifest = {
        "schema": "AIOS_FOREX_INSTITUTIONAL_INFORMATION_CORPUS_V1",
        "corpus_id": CORPUS_ID,
        "status": status,
        "market_corpus_hash": MARKET_CORPUS_HASH,
        "acquisition_state_hash": sha256(ACQUISITION_STATE.read_bytes()),
        "acquisition_report_hash": sha256(ACQUISITION_REPORT.read_bytes()) if ACQUISITION_REPORT.exists() else None,
        "normalized_artifacts": artifact_hashes,
        "record_count": len(records),
        "quality": quality,
        "frozen": status == "FROZEN_VALID",
    }
    manifest["aggregate_hash"] = sha256(stable(manifest).encode("utf-8"))
    atomic_json(ROOT / "manifests" / "manifest.json", manifest)
    atomic_json(ROOT / "quality" / "point_in_time_quality.json", quality)
    if manifest["frozen"]:
        atomic_json(ROOT / "frozen" / "FROZEN.json", {"corpus_id": CORPUS_ID, "aggregate_hash": manifest["aggregate_hash"], "status": status})
    atomic_json(STATE, manifest)
    REPORT.write_text(render_report(manifest, acquisition), encoding="utf-8")
    return manifest


def render_report(state: dict[str, Any], acquisition: dict[str, Any]) -> str:
    return f"""# AIOS Forex Institutional Information Corpus V1

WHAT HAPPENED:
Packet 016 evaluated whether newly acquired official information was sufficient to freeze an institutional corpus.

IS IT SAFE:
YES. This is local file validation only; no broker, credential, LIVE, order, or funding action occurred.

WHAT DO I DO NEXT:
If status is `HUMAN_OFFICIAL_DATA_DROP_REQUIRED`, place only public official files in the manual inbox and resume Packet 016.

HOW CLOSE ARE WE:
Estimated readiness: {acquisition['external_information_coverage_score']}% for external-information coverage.

WHICH MODE SHOULD I USE:
HIGH after the public official files are available; INSTANT for status review.

TECHNICAL DETAILS:
- Corpus ID: `{CORPUS_ID}`
- Status: `{state['status']}`
- Frozen: {str(state['frozen']).lower()}
- Records: {state['record_count']}
- Quality PASS: {str(state['quality']['pass']).lower()}
- Aggregate hash: `{state['aggregate_hash']}`
- Acquisition status: `{acquisition['status']}`
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required")
    state = execute()
    print(stable({"status": state["status"], "records": state["record_count"], "frozen": state["frozen"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
