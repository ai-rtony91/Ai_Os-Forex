#!/usr/bin/env python3
"""Canonical, local-only acquisition for the AIOS dashboard measurement pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "AIOS_DASHBOARD_PROJECTION_V1"
MAX_SOURCE_BYTES = 5 * 1024 * 1024
REPO_ROOT = Path(__file__).resolve().parents[2]

CANONICAL_SOURCES = (
    "automation/orchestration/campaign_registry/AIOS_STRATEGIC_CAMPAIGN_REGISTRY.json",
    "Reports/orchestration/AIOS_CODEX_TASK_DELIVERY_METADATA_V1.json",
    "Reports/orchestration/AIOS_GITHUB_PR_DELIVERY_METADATA_V1.json",
    "Reports/orchestration/AIOS_ENGINEERING_VELOCITY_EVENT_LOG_V1.jsonl",
    "Reports/forex_delivery/AIOS_FOREX_P1_SUPERVISED_PAPER_EVIDENCE_LEDGER_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_PROFIT_TRACK_P1_STRATEGY_EVIDENCE_V1_STATE.json",
)


class DuplicateKeyError(ValueError):
    """Raised when canonical JSON contains an ambiguous duplicate key."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def load_json_strict(path: Path) -> Any:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(REPO_ROOT.resolve()) or path.is_symlink():
        raise ValueError("unsafe source path")
    if resolved.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("source exceeds size limit")
    return json.loads(resolved.read_text(encoding="utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)


def _count_records(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("records", "items", "campaigns", "events", "trades", "packets"):
            if isinstance(value.get(key), list):
                return len(value[key])
        return 1
    return 0


def acquire_sources(root: Path = REPO_ROOT) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    blockers: list[str] = []
    for relative in CANONICAL_SOURCES:
        path = root / relative
        record: dict[str, Any] = {
            "source_id": relative,
            "authority": "CANONICAL_READ_ONLY",
            "parse_state": "MISSING",
            "record_count": 0,
            "freshness_state": "UNKNOWN",
            "warnings": [],
            "blockers": [],
        }
        try:
            raw = path.read_bytes()
            if relative.endswith(".jsonl"):
                parsed = [json.loads(line, object_pairs_hook=_pairs, parse_constant=_reject_constant) for line in raw.decode().splitlines() if line.strip()]
            else:
                parsed = load_json_strict(path)
            record.update(
                fingerprint_sha256=sha256_bytes(raw),
                parse_state="VALID",
                record_count=_count_records(parsed),
                freshness_state="LOCAL_SNAPSHOT",
                schema_version=(parsed.get("schema_version") or parsed.get("version") or "UNDECLARED") if isinstance(parsed, dict) else "UNDECLARED",
            )
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            message = f"{relative}: {type(exc).__name__}"
            record["blockers"].append(message)
            blockers.append(message)
        records.append(record)
    acquisition = {"phase": "A", "schema_version": SCHEMA_VERSION, "sources": records, "blockers": blockers}
    acquisition["receipt_sha256"] = sha256_bytes(canonical_bytes(acquisition))
    return acquisition


NORMALIZED_STATUSES = frozenset({
    "NOT_STARTED", "IN_PROGRESS", "BLOCKED", "IMPLEMENTED_UNVALIDATED",
    "VALIDATED_UNMERGED", "MERGED_UNDEPLOYED", "DEPLOYED_UNVERIFIED",
    "VERIFIED_COMPLETE", "EXCLUDED", "DEPRECATED", "UNKNOWN",
})


def normalize_requirements(requirements: list[dict[str, Any]], acquisition: dict[str, Any]) -> dict[str, Any]:
    """Produce conservative independent dimensions; ambiguity blocks the denominator."""
    if acquisition.get("receipt_sha256") != sha256_bytes(canonical_bytes({k: v for k, v in acquisition.items() if k != "receipt_sha256"})):
        raise ValueError("A receipt mismatch")
    seen: set[str] = set()
    blockers = list(acquisition.get("blockers", []))
    normalized = []
    for item in requirements:
        identifier = str(item.get("id", "")).strip()
        weight = item.get("weight")
        status = item.get("status", "UNKNOWN")
        if not identifier or identifier in seen:
            blockers.append("duplicate or missing requirement id")
        seen.add(identifier)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0:
            blockers.append(f"invalid weight: {identifier or 'UNKNOWN'}")
            weight = 0
        if status not in NORMALIZED_STATUSES:
            status = "UNKNOWN"
        normalized.append({"id": identifier, "weight": weight, "status": status})
    total = sum(item["weight"] for item in normalized)

    def credit(statuses: set[str]) -> float:
        return round(100 * sum(i["weight"] for i in normalized if i["status"] in statuses) / total, 2) if total else 0.0

    dimensions = {
        "inventory_coverage_pct": 100.0 if normalized and not blockers else 0.0,
        "engineering_implementation_pct": credit({"IMPLEMENTED_UNVALIDATED", "VALIDATED_UNMERGED", "MERGED_UNDEPLOYED", "DEPLOYED_UNVERIFIED", "VERIFIED_COMPLETE"}),
        "validation_pct": credit({"VALIDATED_UNMERGED", "MERGED_UNDEPLOYED", "DEPLOYED_UNVERIFIED", "VERIFIED_COMPLETE"}),
        "main_branch_integration_pct": credit({"MERGED_UNDEPLOYED", "DEPLOYED_UNVERIFIED", "VERIFIED_COMPLETE"}),
        "deployment_runtime_pct": credit({"DEPLOYED_UNVERIFIED", "VERIFIED_COMPLETE"}),
        "forex_evidence_readiness_pct": credit({"VERIFIED_COMPLETE"}),
        "overall_verified_completion_pct": credit({"VERIFIED_COMPLETE"}) if normalized and not blockers else None,
    }
    result = {"phase": "B", "a_receipt_sha256": acquisition["receipt_sha256"], "requirements": normalized, "dimensions": dimensions,
              "overall_status": "MEASURABLE" if dimensions["overall_verified_completion_pct"] is not None else "PARTIAL_INVENTORY", "blockers": blockers}
    result["receipt_sha256"] = sha256_bytes(canonical_bytes(result))
    return result


ACTION_CLASSES = (
    "SAFE_GENERATED_DATA_REPAIR", "SOURCE_CODE_TASK_REQUIRED", "OWNER_EVIDENCE_REQUIRED",
    "EXTERNAL_RUNTIME_EVIDENCE_REQUIRED", "BLOCKED_BY_OPEN_PR", "REMOTE_METADATA_UNAVAILABLE",
)


def reconcile(acquisition: dict[str, Any], measurement: dict[str, Any]) -> dict[str, Any]:
    """Reconcile generated data only; return actions rather than mutating source evidence."""
    expected_a = sha256_bytes(canonical_bytes({k: v for k, v in acquisition.items() if k != "receipt_sha256"}))
    expected_b = sha256_bytes(canonical_bytes({k: v for k, v in measurement.items() if k != "receipt_sha256"}))
    if acquisition.get("receipt_sha256") != expected_a or measurement.get("receipt_sha256") != expected_b:
        raise ValueError("phase receipt mismatch")
    blockers = sorted(set(acquisition.get("blockers", []) + measurement.get("blockers", [])))
    actions = []
    if blockers:
        actions.append({"class": "SOURCE_CODE_TASK_REQUIRED", "priority": 1, "reason": "canonical inventory is incomplete or ambiguous"})
    if not any(source["source_id"].endswith("GITHUB_PR_DELIVERY_METADATA_V1.json") and source["parse_state"] == "VALID" for source in acquisition["sources"]):
        actions.append({"class": "REMOTE_METADATA_UNAVAILABLE", "priority": 2, "reason": "local PR snapshot unavailable"})
    result = {
        "phase": "C", "a_receipt_sha256": acquisition["receipt_sha256"], "b_receipt_sha256": measurement["receipt_sha256"],
        "dimensions": measurement["dimensions"], "forecast_confidence": "LOW" if blockers else "BOUNDED",
        "critical_path": blockers[:10], "actions": actions, "blockers": blockers,
    }
    result["receipt_sha256"] = sha256_bytes(canonical_bytes(result))
    return result


def acquire_lock(lock_path: Path) -> int | None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return None
    os.write(descriptor, canonical_bytes({"pid": os.getpid(), "created_unix": int(time.time())}))
    os.fsync(descriptor)
    return descriptor


def release_lock(descriptor: int, lock_path: Path) -> None:
    os.close(descriptor)
    lock_path.unlink(missing_ok=True)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as stream:
        stream.write(canonical_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name != "nt":
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


RUNTIME_ROOT = REPO_ROOT / ".aios/runtime/dashboard_measurement"
PROJECTION_PATH = RUNTIME_ROOT / "AIOS_DASHBOARD_PROJECTION_V1.json"
RECEIPT_PATH = RUNTIME_ROOT / "AIOS_DASHBOARD_RUN_RECEIPT_V1.json"
LOCK_PATH = RUNTIME_ROOT / "AIOS_DASHBOARD_PIPELINE_V1.lock"


def _repository_identity() -> dict[str, str]:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True).stdout.strip()
    return {"branch": git("branch", "--show-current"), "head": git("rev-parse", "HEAD")}


def run_once() -> dict[str, Any]:
    descriptor = acquire_lock(LOCK_PATH)
    if descriptor is None:
        return {"status": "BUSY"}
    started = time.monotonic()
    try:
        run_id = f"AIOS-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:12]}"
        staging = RUNTIME_ROOT / "staging" / run_id
        repository = _repository_identity()
        a = acquire_sources(); atomic_json(staging / "A_ACQUISITION.json", a)
        b = normalize_requirements([], a); atomic_json(staging / "B_MEASUREMENT.json", b)
        c = reconcile(a, b); atomic_json(staging / "C_RECONCILIATION.json", c)
        projection = {
            "schema_version": SCHEMA_VERSION, "run_identity": run_id, "repository": repository,
            "projection_state": "PARTIAL" if b["overall_status"] == "PARTIAL_INVENTORY" else "SNAPSHOT",
            "last_verified_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "dimensions": b["dimensions"],
            "overall_status": b["overall_status"], "verified_pnl": {"verified": False, "mode": "NONE", "label": "NOT VERIFIED - 0 qualifying closed records", "qualifying_record_count": 0, "cumulative_realized_pnl": None, "points": []},
            "source_health": {"sources": a["sources"], "automation": "RUN_ONCE"},
            "receipts": {"A": a["receipt_sha256"], "B": b["receipt_sha256"], "C": c["receipt_sha256"]},
            "blockers": c["blockers"], "actions": c["actions"],
        }
        projection["receipts"]["D"] = sha256_bytes(canonical_bytes(projection))
        atomic_json(staging / "D_PROJECTION.json", projection)
        encoded = canonical_bytes(projection)
        if len(encoded) > 250 * 1024:
            raise ValueError("projection exceeds 250 KB")
        previous = json.loads(PROJECTION_PATH.read_text()) if PROJECTION_PATH.exists() else None
        mode = "NO_CHANGE" if previous and previous.get("receipts", {}).get("A") == projection["receipts"]["A"] else ("INCREMENTAL" if previous else "FULL")
        if mode != "NO_CHANGE": atomic_json(PROJECTION_PATH, projection)
        receipt = {"status": "OK", "run_identity": run_id, "run_mode": mode, "source_branch": repository["branch"], "source_sha": repository["head"], "receipts": projection["receipts"], "projection_sha256": sha256_bytes(encoded), "total_duration_ms": round((time.monotonic() - started) * 1000, 3)}
        atomic_json(RECEIPT_PATH, receipt)
        return receipt
    finally:
        release_lock(descriptor, LOCK_PATH)


def verify_projection() -> dict[str, Any]:
    if not PROJECTION_PATH.is_file(): return {"status": "UNAVAILABLE"}
    raw = PROJECTION_PATH.read_bytes()
    data = json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_pairs)
    if len(raw) > 250 * 1024 or not {"schema_version", "run_identity", "dimensions", "verified_pnl", "receipts"}.issubset(data):
        raise ValueError("invalid projection")
    return {"status": "VERIFIED", "projection_sha256": sha256_bytes(raw), "run_identity": data["run_identity"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run-once", "status", "verify", "watch")); parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.command == "run-once": result = run_once()
    elif args.command == "status": result = json.loads(RECEIPT_PATH.read_text()) if RECEIPT_PATH.exists() else {"status": "UNAVAILABLE"}
    elif args.command == "verify": result = verify_projection()
    else:
        if os.environ.get("AIOS_DASHBOARD_AUTOMATION_ENABLED") != "true" or args.interval_seconds < 60: parser.error("watch requires AIOS_DASHBOARD_AUTOMATION_ENABLED=true and interval >= 60")
        failures = 0
        while failures < 3:
            result = run_once(); failures = 0 if result.get("status") == "OK" else failures + 1; time.sleep(args.interval_seconds)
    print(json.dumps(result, sort_keys=True)); return 0 if result.get("status") not in {"BUSY", "UNAVAILABLE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
