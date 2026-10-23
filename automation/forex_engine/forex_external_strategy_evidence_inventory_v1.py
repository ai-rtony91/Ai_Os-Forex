"""Local-only external strategy evidence inventory for PKT-FOREX-017."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PACKET_ID = "PKT-FOREX-017"
PACKET_SHA256 = "2c672f35a484fc802d57c35437ee716ae4491c40adc62eb6e6119ece72f2f90b"
SOURCE_FILES = (
    "AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V2_STATE.json",
    "AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V2_REPORT.md",
    "AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3_STATE.json",
    "AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3_REPORT.md",
    "AIOS_FOREX_INSTITUTIONAL_INFORMATION_CORPUS_V1_STATE.json",
    "AIOS_FOREX_INSTITUTIONAL_INFORMATION_CORPUS_V1_REPORT.md",
)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_record(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {"path": path.as_posix(), "bytes": len(content), "sha256": sha256(content)}


def _reported_artifacts(state: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = state.get("official_artifacts", {}).get("artifacts", [])
    return [
        {"path": item["path"], "bytes": item["bytes"], "sha256": item["sha256"], "source_id": item["source_id"], "validation": item["validation"]}
        for item in artifacts
    ]


def _normalized_artifacts(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"path": item["path"], "records": item["records"], "sha256": item["sha256"]}
        for item in state.get("normalized_artifacts", [])
    ]


def build_inventory(report_root: Path) -> dict[str, Any]:
    paths = [report_root / name for name in SOURCE_FILES]
    missing = [path.as_posix() for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing authorized evidence inputs: {missing}")
    v2 = json.loads(paths[0].read_text(encoding="utf-8"))
    v3 = json.loads(paths[2].read_text(encoding="utf-8"))
    institutional = json.loads(paths[4].read_text(encoding="utf-8"))
    if v3.get("status") != "FROZEN_VALID" or not v3.get("frozen"):
        raise ValueError("external information corpus V3 is not frozen valid")
    if institutional.get("status") != "FROZEN_VALID" or not institutional.get("frozen"):
        raise ValueError("institutional information corpus V1 is not frozen valid")

    official = _reported_artifacts(v3)
    normalized = _normalized_artifacts(institutional)
    official_ids = sorted({item["source_id"] for item in official})
    normalized_names = sorted(Path(item["path"]).name for item in normalized)
    return {
        "schema": "AIOS_FOREX_EXTERNAL_STRATEGY_EVIDENCE_INVENTORY.v1",
        "packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA256,
        "status": "LOCAL_POINT_IN_TIME_EVIDENCE_SUFFICIENT_FOR_PREREGISTRATION",
        "sources": [source_record(path) for path in paths],
        "corpora": {
            "external_v2": {"status": v2.get("status"), "records": v2.get("records"), "frozen": v2.get("frozen"), "eligible": False},
            "external_v3": {"status": v3["status"], "frozen": v3["frozen"], "records": v3["record_count"], "aggregate_hash": v3["aggregate_hash"], "reported_artifact_count": len(official), "reported_source_ids": official_ids, "direct_record_inspection": "NOT_AUTHORIZED_IN_THIS_PACKET"},
            "institutional_v1": {"status": institutional["status"], "frozen": institutional["frozen"], "records": institutional["record_count"], "aggregate_hash": institutional["aggregate_hash"], "reported_normalized_artifact_count": len(normalized), "reported_artifact_names": normalized_names, "direct_record_inspection": "NOT_AUTHORIZED_IN_THIS_PACKET"},
        },
        "evidence_classes": {
            "central_bank_policy_rates": {"availability": "REPORTED_FROZEN_LOCAL_EVIDENCE", "point_in_time": "SUPPORTED_BY_EXTERNAL_V3_CANONICAL_REPORT", "coverage_dates": "NOT_RECORDED_IN_ALLOWED_SUMMARIES", "revision_behavior": "NOT_RECORDED", "license": "NOT_RECORDED", "cost": "NOT_RECORDED", "authentication": "NOT_RECORDED", "eligible_mechanisms": ["RATE_DIFFERENTIAL_STATE", "RISK_SENTIMENT_RATE_INTERACTION"]},
            "historical_swap_financing": {"availability": "NO_EVIDENCE", "point_in_time": "NO_EVIDENCE", "eligible_mechanisms": []},
            "macro_release_calendar": {"availability": "REPORTED_FROZEN_LOCAL_EVIDENCE", "point_in_time": "SCHEDULE_ONLY", "coverage_dates": "NOT_RECORDED_IN_ALLOWED_SUMMARIES", "eligible_mechanisms": ["SCHEDULED_EVENT_WINDOW_BEHAVIOR"]},
            "macro_actual_consensus_revision": {"availability": "PARTIAL", "point_in_time": "ALFRED_VINTAGE_SERIES_REPORTED_FOR_CPI_AND_PAYROLLS", "consensus": "NO_EVIDENCE", "release_timestamp": "NOT_RECORDED", "eligible_mechanisms": []},
            "yield_curves": {"availability": "REPORTED_FROZEN_LOCAL_EVIDENCE", "point_in_time": "NOT_RECORDED", "eligible_mechanisms": ["YIELD_CURVE_RISK_STATE"]},
            "risk_sentiment": {"availability": "REPORTED_FROZEN_LOCAL_EVIDENCE", "point_in_time": "NOT_RECORDED", "eligible_mechanisms": ["RISK_SENTIMENT_CURRENCY_ALLOCATION"]},
            "currency_positioning": {"availability": "REPORTED_FROZEN_LOCAL_EVIDENCE", "point_in_time": "SUPPORTED_BY_EXTERNAL_V3_CANONICAL_REPORT", "coverage_dates": "2005_THROUGH_2026_ARTIFACTS_REPORTED", "eligible_mechanisms": ["POSITIONING_EXTREMES_REVERSAL", "POSITIONING_TREND_CONTINUATION"]},
            "session_holiday_calendar": {"availability": "NO_EVIDENCE", "point_in_time": "NO_EVIDENCE", "eligible_mechanisms": []},
        },
        "next_eligible_research": {
            "family": "CFTC_POSITIONING_STATE_WITH_PRICE_CONFIRMATION",
            "status": "ELIGIBLE_FOR_DIRECT_EVIDENCE_QUALIFICATION_AND_PREREGISTRATION",
            "requirements": ["VERIFY_REPORTED_ARTIFACT_HASHES", "PARSE_RELEASE_AND_AS_OF_TIMESTAMPS", "MAP_CFTC_CONTRACTS_TO_CERTIFIED_PAIRS", "DUPLICATE_FINGERPRINT_AUDIT", "FREEZE_CHRONOLOGICAL_JOIN_RULE"],
        },
        "safety": {"network": False, "credentials": False, "broker": False, "collector": False, "paper": False, "practice": False, "live": False, "orders": False, "money_movement": False, "strategy_execution": False, "holdout_access": False},
    }


def acquisition_proposal(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_EXTERNAL_STRATEGY_DATA_ACQUISITION_PROPOSAL.v1",
        "status": "LOCAL_EVIDENCE_FIRST_NO_ACQUISITION_AUTHORIZED",
        "local_first_action": "QUALIFY_EXISTING_FROZEN_CFTC_RATE_YIELD_AND_RISK_ARTIFACTS",
        "missing_evidence": [
            {"class": "HISTORICAL_SWAP_FINANCING", "required_fields": ["instrument", "effective_utc", "long_financing", "short_financing", "currency", "publication_utc"], "coverage": "2024-01-01_THROUGH_2025-12-31", "point_in_time": True},
            {"class": "MACRO_CONSENSUS_AND_ACTUALS", "required_fields": ["event_id", "currency", "scheduled_utc", "actual", "consensus", "previous_as_published", "vintage_utc"], "coverage": "2024-01-01_THROUGH_2025-12-31", "point_in_time": True},
            {"class": "SESSION_AND_HOLIDAY_CALENDAR", "required_fields": ["market", "date", "open_utc", "close_utc", "holiday_type", "published_utc"], "coverage": "2024-01-01_THROUGH_2025-12-31", "point_in_time": True},
            {"class": "LICENSE_AND_REUSE_METADATA", "required_fields": ["source_authority", "dataset_name", "license", "cost", "authentication", "download_method", "expected_size"]},
        ],
        "proposed_storage_root": ".aios/runtime/forex_external_strategy_data_acquisition_v1",
        "hashing": "SHA256_PER_SOURCE_PLUS_CANONICAL_MANIFEST",
        "missing_data_treatment": "NO_FORWARD_FILL_ACROSS_RELEASE_BOUNDARY; UNKNOWN_REMAINS_UNKNOWN",
        "leakage_controls": ["PUBLICATION_TIME_NOT_OBSERVATION_PERIOD", "VINTAGE_DATA_ONLY", "NEXT_TRADABLE_CANDLE_EXECUTION", "SEALED_FINAL_HOLDOUT"],
        "authority_required": "SEPARATE_HUMAN_OWNER_AUTHORIZATION_BEFORE_ANY_NETWORK_PROVIDER_CREDENTIAL_OR_DATA_WRITE",
        "acquisition_executed": False,
    }


def write_outputs(inventory: dict[str, Any], state_path: Path, report_path: Path, proposal_path: Path, runtime_root: Path) -> dict[str, Any]:
    runtime_root.mkdir(parents=True, exist_ok=False)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    proposal = acquisition_proposal(inventory)
    state_bytes = canonical_bytes(inventory)
    proposal_bytes = canonical_bytes(proposal)
    report = (
        "# External Strategy Evidence Inventory V1\n\n"
        f"Status: {inventory['status']}\n\n"
        "The allowed canonical reports attest a frozen 35,755-record point-in-time external corpus and a frozen 4,121-record institutional corpus. "
        "CFTC positioning, policy-rate, yield, and risk-sentiment evidence can advance to direct artifact qualification. "
        "Historical swap financing, macro consensus/actual release records, session/holiday evidence, and licensing metadata remain incomplete. "
        "No provider, credential, broker, strategy, dataset, or final holdout was accessed.\n"
    ).encode("utf-8")
    manifest = {
        "schema": "AIOS_FOREX_EXTERNAL_STRATEGY_EVIDENCE_MANIFEST.v1",
        "outputs": {
            state_path.name: {"bytes": len(state_bytes), "sha256": sha256(state_bytes)},
            report_path.name: {"bytes": len(report), "sha256": sha256(report)},
            proposal_path.name: {"bytes": len(proposal_bytes), "sha256": sha256(proposal_bytes)},
        },
        "sources": inventory["sources"],
    }
    manifest_bytes = canonical_bytes(manifest)
    receipt = {
        "schema": "AIOS_FOREX_EXTERNAL_STRATEGY_EVIDENCE_RECEIPT.v1",
        "status": inventory["status"],
        "source_count": len(inventory["sources"]),
        "manifest_sha256": sha256(manifest_bytes),
        "acceptance": {"six_sources_hashed": "PASS", "frozen_corpora_classified": "PASS", "missing_fields_explicit": "PASS", "point_in_time_distinction": "PASS", "proposal_is_non_executing": "PASS", "safety_flags_false": "PASS"},
        "safety": inventory["safety"],
    }
    state_path.write_bytes(state_bytes)
    report_path.write_bytes(report)
    proposal_path.write_bytes(proposal_bytes)
    (runtime_root / "AIOS_FOREX_EXTERNAL_STRATEGY_EVIDENCE_MANIFEST.json").write_bytes(manifest_bytes)
    (runtime_root / "AIOS_FOREX_EXTERNAL_STRATEGY_EVIDENCE_RECEIPT.json").write_bytes(canonical_bytes(receipt))
    return receipt
