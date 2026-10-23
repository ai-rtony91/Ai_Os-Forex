"""Packet 021 External Information Corpus V3 freezer."""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine.forex_official_data_breakthrough_v1 import HUMAN_MANIFEST, NORMALIZED, PACKET_ID, STATE as ACQUISITION_STATE, atomic_json, sha256, stable

PACKET_ID = "PKT-EAST-FOREX-FULL-ATTACK-PROFITABILITY-022"
CORPUS_ID = "AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3"
ROOT = Path(".aios/runtime/forex_external_information_corpus_v3")
HUMAN_INBOX = Path(".aios/runtime/forex_official_data_human_inbox")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3_REPORT.md")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}


def load_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if NORMALIZED.exists():
        for path in sorted(NORMALIZED.glob("*.json")):
            records.extend(json.loads(path.read_text(encoding="utf-8")))
    return records


def validate_official_artifacts() -> dict[str, Any]:
    boe = HUMAN_INBOX / "CENTRAL_BANK_POLICY_HISTORY_BOE_IUDBEDR.csv"
    bls = HUMAN_INBOX / "OFFICIAL_MACRO_RELEASE_SCHEDULES_BLS_RELEASE_CALENDAR.ics"
    cftc_paths = sorted(HUMAN_INBOX.glob("CFTC_POSITIONING_HISTORY_DEACOT_*.zip"))
    artifacts: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    if boe.exists() and boe.stat().st_size > 0:
        header = boe.read_text(encoding="utf-8-sig", errors="replace").splitlines()[0] if boe.stat().st_size else ""
        valid = "Date" in header or "DATE" in header or "," in header
        artifacts.append({"source_id": "CENTRAL_BANK_POLICY_HISTORY", "path": boe.as_posix(), "bytes": boe.stat().st_size, "sha256": sha256(boe.read_bytes()), "validation": "PASS" if valid else "FAIL"})
        if not valid:
            failures.append({"source_id": "CENTRAL_BANK_POLICY_HISTORY", "reason": "CSV_HEADER_NOT_RECOGNIZED"})
    else:
        failures.append({"source_id": "CENTRAL_BANK_POLICY_HISTORY", "reason": "MISSING_OR_EMPTY"})

    cftc_expected_years = set(range(2005, 2027))
    cftc_years = set()
    for path in cftc_paths:
        try:
            year = int(path.stem.rsplit("_", 1)[-1])
        except ValueError:
            year = 0
        if path.exists() and path.stat().st_size > 0 and zipfile.is_zipfile(path):
            cftc_years.add(year)
            validation = "PASS"
        else:
            validation = "FAIL"
            failures.append({"source_id": "CFTC_POSITIONING_HISTORY", "reason": f"BAD_ZIP_{path.name}"})
        artifacts.append({"source_id": "CFTC_POSITIONING_HISTORY", "path": path.as_posix(), "bytes": path.stat().st_size if path.exists() else 0, "sha256": sha256(path.read_bytes()) if path.exists() else None, "validation": validation})
    missing_years = sorted(cftc_expected_years - cftc_years)
    if missing_years:
        failures.append({"source_id": "CFTC_POSITIONING_HISTORY", "reason": "MISSING_YEARS_" + "_".join(str(item) for item in missing_years)})

    if bls.exists() and bls.stat().st_size > 0:
        text = bls.read_text(encoding="utf-8-sig", errors="replace")
        lower = text[:5000].lower()
        valid = text.lstrip().startswith("BEGIN:VCALENDAR") and "END:VCALENDAR" in text and "<html" not in lower and "access denied" not in lower
        artifacts.append({"source_id": "OFFICIAL_MACRO_RELEASE_SCHEDULES", "path": bls.as_posix(), "bytes": bls.stat().st_size, "sha256": sha256(bls.read_bytes()), "validation": "PASS" if valid else "FAIL"})
        if not valid:
            failures.append({"source_id": "OFFICIAL_MACRO_RELEASE_SCHEDULES", "reason": "ICS_NOT_VALID_OR_HTML_DENIAL"})
    else:
        failures.append({"source_id": "OFFICIAL_MACRO_RELEASE_SCHEDULES", "reason": "MISSING_OR_EMPTY"})

    status = "PASS" if not failures and len(artifacts) == 24 else "FAIL"
    return {"status": status, "artifact_count": len(artifacts), "failures": failures, "artifacts": artifacts}


def validate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    required = {"source_id", "series_id", "observation_time_utc", "publication_time_utc", "strategy_available_time_utc", "vintage_or_revision_status", "retrieval_time_utc", "raw_artifact_hash", "normalized_record_hash"}
    violations = []
    seen = set()
    for index, record in enumerate(records):
        missing = sorted(required - set(record))
        if missing:
            violations.append({"index": index, "reason": "MISSING_REQUIRED_FIELDS", "fields": missing})
        key = (record.get("source_id"), record.get("series_id"), record.get("observation_time_utc"))
        if key in seen:
            violations.append({"index": index, "reason": "DUPLICATE_RECORD_KEY", "key": list(key)})
        seen.add(key)
        try:
            publication = datetime.fromisoformat(str(record.get("publication_time_utc")))
            available = datetime.fromisoformat(str(record.get("strategy_available_time_utc")))
            observation = datetime.fromisoformat(str(record.get("observation_time_utc")))
            if available < publication:
                violations.append({"index": index, "reason": "AVAILABLE_BEFORE_PUBLICATION"})
            if publication < observation:
                violations.append({"index": index, "reason": "PUBLICATION_BEFORE_OBSERVATION"})
        except ValueError:
            violations.append({"index": index, "reason": "INVALID_TIMESTAMP"})
    return {"record_count": len(records), "duplicate_count": len(records) - len(seen), "violations": violations, "pass": not violations}


def execute() -> dict[str, Any]:
    for folder in ("raw", "normalized", "manifests", "quality", "frozen", "human_download_inbox"):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    acquisition = read_json(ACQUISITION_STATE)
    human = read_json(HUMAN_MANIFEST)
    records = load_records()
    quality = validate_records(records)
    official = validate_official_artifacts()
    score = int(acquisition.get("external_information_coverage_score", 0))
    pending_human = 0 if official["status"] == "PASS" else int(human.get("item_count", 0))
    status = "FROZEN_VALID" if score >= 85 and pending_human == 0 and quality["pass"] and records and official["status"] == "PASS" else "HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED"
    if not records and pending_human == 0:
        status = "EXTERNAL_INFORMATION_CAPABILITY_BLOCKED"
    manifest = {"schema": "AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3_STATE", "packet_id": "PKT-EAST-FOREX-POST-HUMAN-DATA-CONTINUATION-026", "corpus_id": CORPUS_ID, "status": status, "frozen": status == "FROZEN_VALID", "external_information_coverage_score": score, "record_count": len(records), "quality": quality, "official_artifacts": official, "pending_human_download_items": pending_human, "human_inbox": HUMAN_INBOX.as_posix(), "acquisition_state_hash": sha256(ACQUISITION_STATE.read_bytes()) if ACQUISITION_STATE.exists() else None, "safety": {"credentials_read": False, "broker_write": False, "live": False, "orders": False, "funding": False}}
    manifest["aggregate_hash"] = sha256(stable(manifest).encode("utf-8"))
    atomic_json(ROOT / "quality" / "point_in_time_quality.json", quality)
    atomic_json(ROOT / "manifests" / "manifest.json", manifest)
    if manifest["frozen"]:
        atomic_json(ROOT / "frozen" / "FROZEN.json", {"corpus_id": CORPUS_ID, "aggregate_hash": manifest["aggregate_hash"], "status": status})
    atomic_json(STATE, manifest)
    REPORT.write_text(render_report(manifest), encoding="utf-8")
    return manifest


def render_report(state: dict[str, Any]) -> str:
    return f"""# AIOS Forex External Information Corpus V3

WHAT HAPPENED:
Packet 021 validated point-in-time official information records and determined whether External Information Corpus V3 can freeze.

IS IT SAFE:
YES. This is local validation only; no credentials, LIVE calls, orders, or funding actions occurred.

WHAT DO I DO NEXT:
If status is `HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED`, complete the consolidated public official data download package and resume this same packet.

HOW CLOSE ARE WE:
Estimated readiness: {state['external_information_coverage_score']}% for external-information coverage.

WHICH MODE SHOULD I USE:
HIGH after the Human-only official downloads are complete.

TECHNICAL DETAILS:
- Corpus ID: `{CORPUS_ID}`
- Status: `{state['status']}`
- Frozen: {str(state['frozen']).lower()}
- Records: {state['record_count']}
- Official artifacts: {state['official_artifacts']['status']} ({state['official_artifacts']['artifact_count']} files)
- Pending Human download items: {state['pending_human_download_items']}
- Aggregate hash: `{state['aggregate_hash']}`
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = execute()
    print(stable({"status": state["status"], "frozen": state["frozen"], "records": state["record_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
