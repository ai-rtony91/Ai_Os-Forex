"""Governed Packet 033 R5 continuation controller and pre-data validators."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


PACKET_ID = "PKT-EAST-FOREX-PACKET033-R5-CONTINUATION-CONSTITUTION"
SCHEMA_VERSION = "AIOS_FOREX_PACKET033_R5_CONTINUATION.v1"
PREVIOUS_PRODUCTIVE_MINUTES = 0.4
TARGET_PRODUCTIVE_MINUTES = 60.0

TASKS: tuple[tuple[str, str], ...] = (
    ("T01", "PREFLIGHT_LOCK"),
    ("T02", "R3_REGRESSION"),
    ("T03", "R5_CONTROLLER_TIME_LEDGER"),
    ("T04", "PHYSICAL_ARTIFACT_VALIDATOR"),
    ("T05", "CORPUS_FREEZE_READINESS"),
    ("T06", "TIMEFRAME_MAPPING"),
    ("T07", "PACKET032_033_STATE_INTEGRITY"),
    ("T08", "TECHNIQUE_FIDELITY_READINESS"),
    ("T09", "COMPUTE_SHARD_PLANNER"),
    ("T10", "HYPOTHESIS_LEDGER_INTEGRITY"),
    ("T11", "GROSS_EDGE_GATE_TESTS"),
    ("T12", "M30_MACD_REPLICATION_READINESS"),
    ("T13", "FINALIST_FORWARD_V13_READINESS"),
    ("T14", "ACQUISITION_LOAD_PLAN"),
    ("T15", "CHANGED_DEPENDENCY_VALIDATION"),
)
TASK_IDS = tuple(item[0] for item in TASKS)
TERMINAL_TASK_STATUSES = frozenset({"COMPLETE", "LEGITIMATELY_INAPPLICABLE"})
ALLOWED_TASK_STATUSES = TERMINAL_TASK_STATUSES | frozenset({"WAITING_HUMAN", "BLOCKED"})
REQUESTED_TIMEFRAMES = (
    "S1", "S5", "S10", "S15", "S30", "S45",
    "M1", "M2", "M4", "M5", "M10", "M15", "M30",
    "H1", "H2", "H3", "H4", "H6", "H8", "H12",
    "D1", "W1", "MN1", "MO6",
)
GRANULARITY_SECONDS = {
    "S1": 1, "S5": 5, "S10": 10, "S15": 15, "S30": 30, "S45": 45,
    "M1": 60, "M2": 120, "M4": 240, "M5": 300, "M10": 600,
    "M15": 900, "M30": 1800, "H1": 3600, "H2": 7200, "H3": 10800,
    "H4": 14400, "H6": 21600, "H8": 28800, "H12": 43200,
    "D1": 86400, "W1": 604800,
}
SENSITIVE_MARKERS = ("authorization:", "bearer ", "api-fxtrade", "/orders", "accountid")


@dataclass(frozen=True)
class AuditResult:
    status: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence: Mapping[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "evidence": dict(self.evidence or {}),
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include an offset")
    return parsed.astimezone(timezone.utc)


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        json.loads(Path(temp_name).read_text(encoding="utf-8"))
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def empty_task_ledger() -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA_VERSION}.task-ledger",
        "packet_id": PACKET_ID,
        "append_only": True,
        "entries": [],
    }


def _entry_payload(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in entry.items() if key != "entry_hash"}


def verify_task_ledger(ledger: Mapping[str, Any]) -> AuditResult:
    errors: list[str] = []
    if ledger.get("packet_id") != PACKET_ID or ledger.get("append_only") is not True:
        errors.append("task ledger identity or append-only contract mismatch")
    previous_hash = "GENESIS"
    previous_end: datetime | None = None
    latest_status: dict[str, str] = {}
    for index, raw in enumerate(ledger.get("entries", []), start=1):
        entry = dict(raw)
        task_id = str(entry.get("task_id", ""))
        status = str(entry.get("status", ""))
        if entry.get("entry_id") != f"R5-{index:04d}":
            errors.append(f"entry {index}: non-sequential entry_id")
        if task_id not in TASK_IDS:
            errors.append(f"entry {index}: unknown task_id {task_id!r}")
        if status not in ALLOWED_TASK_STATUSES:
            errors.append(f"entry {index}: unsupported task status {status!r}")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or not item for item in evidence):
            errors.append(f"entry {index}: evidence must contain non-empty strings")
        if entry.get("previous_entry_hash") != previous_hash:
            errors.append(f"entry {index}: previous hash mismatch")
        try:
            expected_hash = sha256_text(stable(_entry_payload(entry)))
            if entry.get("entry_hash") != expected_hash:
                errors.append(f"entry {index}: entry hash mismatch")
        except (TypeError, ValueError):
            errors.append(f"entry {index}: entry payload is not canonical JSON")
        try:
            productive_seconds = float(entry.get("productive_seconds", -1))
        except (TypeError, ValueError):
            productive_seconds = -1.0
        if not math.isfinite(productive_seconds) or productive_seconds < 0:
            errors.append(f"entry {index}: productive time must be finite and non-negative")
        try:
            started = parse_utc(str(entry.get("started_at_utc", "")))
            ended = parse_utc(str(entry.get("ended_at_utc", "")))
            elapsed_seconds = (ended - started).total_seconds()
            if elapsed_seconds < 0:
                errors.append(f"entry {index}: task end precedes start")
            if productive_seconds > elapsed_seconds + 0.001:
                errors.append(f"entry {index}: productive time exceeds elapsed time")
            if previous_end is not None and started < previous_end:
                errors.append(f"entry {index}: task interval overlaps prior ledger entry")
            previous_end = ended
        except ValueError as exc:
            errors.append(f"entry {index}: invalid task timestamp: {exc}")
        if status in TERMINAL_TASK_STATUSES and task_id in TASK_IDS:
            task_index = TASK_IDS.index(task_id)
            missing_prerequisites = [
                prerequisite for prerequisite in TASK_IDS[:task_index]
                if latest_status.get(prerequisite) not in TERMINAL_TASK_STATUSES
            ]
            if missing_prerequisites:
                errors.append(f"entry {index}: terminal task is out of order")
        if status == "COMPLETE":
            if latest_status.get(task_id) == "COMPLETE":
                errors.append(f"entry {index}: duplicate unchanged completed task {task_id}")
        latest_status[task_id] = status
        previous_hash = str(entry.get("entry_hash", ""))
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        evidence={"entry_count": len(ledger.get("entries", [])), "tail_hash": previous_hash},
    )


def append_task_entry(
    ledger: Mapping[str, Any],
    *,
    task_id: str,
    status: str,
    productive_seconds: float,
    evidence: Sequence[str],
    started_at_utc: str,
    ended_at_utc: str,
) -> dict[str, Any]:
    if task_id not in TASK_IDS:
        raise ValueError(f"unknown task_id: {task_id}")
    if status not in ALLOWED_TASK_STATUSES:
        raise ValueError(f"unsupported task status: {status}")
    if not math.isfinite(float(productive_seconds)) or productive_seconds < 0:
        raise ValueError("productive_seconds must be finite and non-negative")
    if not evidence or any(not isinstance(item, str) or not item for item in evidence):
        raise ValueError("task evidence must contain non-empty strings")
    started = parse_utc(started_at_utc)
    ended = parse_utc(ended_at_utc)
    if ended < started:
        raise ValueError("task end cannot precede task start")
    if productive_seconds > (ended - started).total_seconds() + 0.001:
        raise ValueError("productive_seconds cannot exceed elapsed task time")
    copy = json.loads(stable(ledger))
    if copy.get("entries"):
        previous_end = parse_utc(str(copy["entries"][-1]["ended_at_utc"]))
        if started < previous_end:
            raise ValueError("task interval cannot overlap the prior ledger entry")
    validation = verify_task_ledger(copy)
    if not validation.passed:
        raise ValueError(f"existing ledger is invalid: {validation.errors}")
    prior_task_entries = [item for item in copy.get("entries", []) if item.get("task_id") == task_id]
    prior_task_status = prior_task_entries[-1]["status"] if prior_task_entries else "PENDING"
    if status == "COMPLETE" and prior_task_status == "COMPLETE":
        raise ValueError(f"completed task cannot be appended twice: {task_id}")
    previous_hash = copy["entries"][-1]["entry_hash"] if copy["entries"] else "GENESIS"
    entry: dict[str, Any] = {
        "entry_id": f"R5-{len(copy['entries']) + 1:04d}",
        "task_id": task_id,
        "status": status,
        "started_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "productive_seconds": round(float(productive_seconds), 3),
        "evidence": list(evidence),
        "evidence_hash": sha256_text(stable(list(evidence))),
        "previous_entry_hash": previous_hash,
        "prior_task_status": prior_task_status,
        "reopened_task_resolution": status == "COMPLETE" and prior_task_status in {"BLOCKED", "WAITING_HUMAN"},
    }
    entry["entry_hash"] = sha256_text(stable(entry))
    copy["entries"].append(entry)
    validation = verify_task_ledger(copy)
    if not validation.passed:
        raise ValueError(f"new ledger entry is invalid: {validation.errors}")
    return copy


def productive_time_state(ledger: Mapping[str, Any]) -> dict[str, Any]:
    validation = verify_task_ledger(ledger)
    if not validation.passed:
        raise ValueError(f"cannot total invalid task ledger: {validation.errors}")
    current_seconds = sum(float(item["productive_seconds"]) for item in ledger.get("entries", []))
    cumulative = PREVIOUS_PRODUCTIVE_MINUTES + current_seconds / 60.0
    remaining = max(0.0, TARGET_PRODUCTIVE_MINUTES - cumulative)
    return {
        "schema": f"{SCHEMA_VERSION}.productive-time",
        "packet_id": PACKET_ID,
        "previously_proven_minutes": PREVIOUS_PRODUCTIVE_MINUTES,
        "r5_productive_seconds": round(current_seconds, 3),
        "productive_minutes_cumulative": round(cumulative, 3),
        "productive_minutes_remaining": round(remaining, 3),
        "one_hour_requirement_status": "SATISFIED" if remaining == 0 else "PAUSED_NOT_SATISFIED",
        "task_ledger_tail_hash": validation.evidence["tail_hash"],
    }


def task_statuses(ledger: Mapping[str, Any]) -> dict[str, str]:
    statuses = {task_id: "PENDING" for task_id in TASK_IDS}
    for entry in ledger.get("entries", []):
        statuses[str(entry["task_id"])] = str(entry["status"])
    return statuses


def first_incomplete_task(ledger: Mapping[str, Any]) -> str:
    statuses = task_statuses(ledger)
    return next((task_id for task_id in TASK_IDS if statuses[task_id] not in TERMINAL_TASK_STATUSES), "P01")


def build_checkpoint(
    ledger: Mapping[str, Any],
    *,
    current_lock: str,
    human_artifacts_present: bool,
    token_budget_pause: bool = False,
) -> dict[str, Any]:
    time_state = productive_time_state(ledger)
    incomplete = first_incomplete_task(ledger)
    pre_data_complete = incomplete == "P01"
    if token_budget_pause:
        status = "CODEX_TOKEN_BUDGET_PAUSE"
    elif pre_data_complete and not human_artifacts_present:
        status = "WAITING_HUMAN_SCALPING_ARTIFACTS"
    else:
        status = "CONTINUE_NEXT_AUTHORIZED_UNIT"
    return {
        "schema": f"{SCHEMA_VERSION}.checkpoint",
        "packet_id": PACKET_ID,
        "updated_at_utc": utc_now(),
        "status": status,
        "task_statuses": task_statuses(ledger),
        "last_completed_task": next(
            (str(item["task_id"]) for item in reversed(ledger.get("entries", [])) if item.get("status") == "COMPLETE"),
            "NONE",
        ),
        "first_incomplete_task": incomplete,
        "current_lock": current_lock,
        "human_artifacts_present": human_artifacts_present,
        "same_packet_resume_required": status != "COMPLETE",
        **time_state,
    }


def _safe_relative(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ValueError(f"artifact path escapes root: {relative}")
    return candidate


def _contains_sensitive_marker(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            _contains_sensitive_marker(str(key)) or _contains_sensitive_marker(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_sensitive_marker(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in SENSITIVE_MARKERS)
    return False


def validate_physical_artifacts(root: Path, manifest: Mapping[str, Any]) -> AuditResult:
    errors: list[str] = []
    warnings: list[str] = []
    scope = manifest.get("scope")
    if not isinstance(scope, dict):
        errors.append("manifest scope is missing")
        scope = {}
    expected_scope_fingerprint = sha256_text(stable(scope))
    if manifest.get("scope_fingerprint") != expected_scope_fingerprint:
        errors.append("scope fingerprint mismatch")
    series_rows = manifest.get("series")
    if not isinstance(series_rows, list) or not series_rows:
        errors.append("manifest series membership is empty")
        series_rows = []
    if "series_count" in manifest and manifest.get("series_count") != len(series_rows):
        errors.append("manifest series_count does not match membership")
    expected_series_ids = set(scope.get("series_ids", [])) if isinstance(scope, Mapping) else set()
    declared_gaps = manifest.get("allowed_gaps", {})
    if not isinstance(declared_gaps, Mapping):
        errors.append("allowed_gaps must be keyed by series identity")
        declared_gaps = {}
    seen_ids: set[str] = set()
    aggregate_rows: list[dict[str, Any]] = []
    for index, raw in enumerate(series_rows, start=1):
        if not isinstance(raw, dict):
            errors.append(f"series {index}: membership row is not an object")
            continue
        series_id = str(raw.get("series_id", ""))
        if not series_id or series_id in seen_ids:
            errors.append(f"series {index}: missing or duplicate series identity")
        seen_ids.add(series_id)
        expected_series_id = ".".join(str(raw.get(field, "")) for field in ("instrument", "granularity", "price"))
        if series_id != expected_series_id:
            errors.append(f"series {series_id}: series identity does not match instrument/granularity/price")
        for field, scope_field in (("instrument", "instruments"), ("granularity", "granularities")):
            declared = scope.get(scope_field, []) if isinstance(scope, Mapping) else []
            if declared and raw.get(field) not in declared:
                errors.append(f"series {series_id}: {field} is outside manifest scope")
        if isinstance(scope, Mapping) and scope.get("price") and raw.get("price") != scope.get("price"):
            errors.append(f"series {series_id}: price is outside manifest scope")
        try:
            path = _safe_relative(root, str(raw.get("relative_path", "")))
        except ValueError as exc:
            errors.append(f"series {series_id}: {exc}")
            continue
        if not path.is_file():
            errors.append(f"series {series_id}: artifact missing")
            continue
        actual_hash = sha256_file(path)
        if raw.get("sha256") != actual_hash:
            errors.append(f"series {series_id}: artifact hash mismatch")
        try:
            document = read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"series {series_id}: invalid JSON artifact: {exc}")
            continue
        if not isinstance(document, Mapping):
            errors.append(f"series {series_id}: artifact root must be an object")
            continue
        for field in ("instrument", "granularity", "price"):
            if document.get(field) != raw.get(field):
                errors.append(f"series {series_id}: {field} identity mismatch")
        if _contains_sensitive_marker(raw) or _contains_sensitive_marker(document):
            errors.append(f"series {series_id}: secret, LIVE, account, or order indicator")
        candles = document.get("candles")
        if not isinstance(candles, list) or not candles:
            errors.append(f"series {series_id}: candle list is empty")
            continue
        timestamps: list[datetime] = []
        for candle_index, candle in enumerate(candles, start=1):
            try:
                timestamp = parse_utc(str(candle["time"]))
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"series {series_id}: candle {candle_index} timestamp invalid: {exc}")
                continue
            timestamps.append(timestamp)
            if candle.get("complete") is not True:
                errors.append(f"series {series_id}: candle {candle_index} is incomplete")
            price = str(raw.get("price", ""))
            expected_keys = {"M": "mid", "B": "bid", "A": "ask"}
            required_components = [expected_keys[key] for key in price if key in expected_keys]
            if not required_components or any(component not in candle for component in required_components):
                errors.append(f"series {series_id}: candle {candle_index} price components missing")
            component_closes: dict[str, float] = {}
            for component in required_components:
                quote = candle.get(component)
                if not isinstance(quote, Mapping) or not all(key in quote for key in ("o", "h", "l", "c")):
                    errors.append(f"series {series_id}: candle {candle_index} {component} OHLC invalid")
                    continue
                try:
                    open_price, high, low, close = (float(quote[key]) for key in ("o", "h", "l", "c"))
                except (TypeError, ValueError):
                    errors.append(f"series {series_id}: candle {candle_index} {component} OHLC non-numeric")
                    continue
                if not all(math.isfinite(item) for item in (open_price, high, low, close)):
                    errors.append(f"series {series_id}: candle {candle_index} {component} OHLC non-finite")
                    continue
                if low > min(open_price, close) or high < max(open_price, close) or low > high:
                    errors.append(f"series {series_id}: candle {candle_index} {component} OHLC inconsistent")
                component_closes[component] = close
            if "bid" in component_closes and "ask" in component_closes and component_closes["bid"] > component_closes["ask"]:
                errors.append(f"series {series_id}: candle {candle_index} bid exceeds ask")
            if "mid" in component_closes and {"bid", "ask"}.issubset(component_closes):
                if not component_closes["bid"] <= component_closes["mid"] <= component_closes["ask"]:
                    errors.append(f"series {series_id}: candle {candle_index} mid outside bid/ask")
        if timestamps:
            if timestamps != sorted(timestamps):
                errors.append(f"series {series_id}: chronology is not sorted")
            if len(timestamps) != len(set(timestamps)):
                errors.append(f"series {series_id}: duplicate candle timestamps")
            try:
                from_utc = parse_utc(str(raw["from_utc"]))
                to_utc = parse_utc(str(raw["to_utc"]))
                if any(item < from_utc or item >= to_utc for item in timestamps):
                    errors.append(f"series {series_id}: candle outside [FromUtc, ToUtc)")
            except (KeyError, ValueError) as exc:
                errors.append(f"series {series_id}: invalid bounds: {exc}")
            seconds = GRANULARITY_SECONDS.get(str(raw.get("granularity")))
            if seconds:
                unexplained_gaps = 0
                allowed = declared_gaps.get(series_id, [])
                if not isinstance(allowed, list):
                    errors.append(f"series {series_id}: allowed gap entries must be a list")
                    allowed = []
                for left, right in zip(timestamps, timestamps[1:]):
                    if int((right - left).total_seconds()) == seconds:
                        continue
                    match = next((
                        gap for gap in allowed
                        if isinstance(gap, Mapping)
                        and gap.get("after_utc") == left.isoformat().replace("+00:00", "Z")
                        and gap.get("before_utc") == right.isoformat().replace("+00:00", "Z")
                        and gap.get("reason") in {"MARKET_CLOSED", "PROVIDER_CONFIRMED_GAP"}
                    ), None)
                    if match is None:
                        unexplained_gaps += 1
                    else:
                        warnings.append(f"series {series_id}: declared {match['reason']} gap")
                if unexplained_gaps:
                    errors.append(f"series {series_id}: {unexplained_gaps} unexplained chronological gaps")
            else:
                warnings.append(f"series {series_id}: calendar granularity gap check deferred")
        aggregate_rows.append({"series_id": series_id, "sha256": actual_hash, "row_count": len(candles)})
    if expected_series_ids and expected_series_ids != seen_ids:
        errors.append("manifest membership does not match scope series_ids")
    aggregate_hash = sha256_text(stable(sorted(aggregate_rows, key=lambda item: item["series_id"])))
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        warnings=tuple(warnings),
        evidence={"series_count": len(series_rows), "aggregate_hash": aggregate_hash},
    )


def corpus_freeze_plan(
    root: Path,
    manifest: Mapping[str, Any],
    source_mapping: Mapping[str, Mapping[str, Any]],
) -> AuditResult:
    artifact_result = validate_physical_artifacts(root, manifest)
    errors = list(artifact_result.errors)
    timeframe_result = validate_timeframe_mapping(source_mapping)
    errors.extend(timeframe_result.errors)
    for timeframe in REQUESTED_TIMEFRAMES:
        mapping = source_mapping.get(timeframe)
        if not isinstance(mapping, Mapping):
            errors.append(f"{timeframe}: canonical source mapping missing")
            continue
        source_kind = mapping.get("source_kind")
        if source_kind not in {"NATIVE", "DERIVED"}:
            errors.append(f"{timeframe}: source_kind must be NATIVE or DERIVED")
        if source_kind == "DERIVED" and not mapping.get("source_timeframes"):
            errors.append(f"{timeframe}: derived mapping has no sources")
    mapping_hash = sha256_text(stable(source_mapping))
    aggregate_hash = sha256_text(stable({
        "artifact_hash": artifact_result.evidence.get("aggregate_hash"),
        "mapping_hash": mapping_hash,
    }))
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        warnings=artifact_result.warnings,
        evidence={"aggregate_hash": aggregate_hash, "mapping_hash": mapping_hash},
    )


def validate_timeframe_mapping(mapping: Mapping[str, Mapping[str, Any]]) -> AuditResult:
    errors: list[str] = []
    missing = [timeframe for timeframe in REQUESTED_TIMEFRAMES if timeframe not in mapping]
    unexpected = sorted(set(mapping) - set(REQUESTED_TIMEFRAMES))
    if missing:
        errors.append(f"missing timeframes: {','.join(missing)}")
    if unexpected:
        errors.append(f"unexpected timeframes: {','.join(unexpected)}")
    s1 = mapping.get("S1", {})
    if s1.get("source_kind") == "DERIVED" and "S5" in s1.get("source_timeframes", []):
        errors.append("S1 cannot be derived from S5")
    s45 = mapping.get("S45", {})
    if s45.get("source_kind") == "DERIVED":
        base_seconds = s45.get("source_seconds")
        if not isinstance(base_seconds, int) or base_seconds <= 0 or 45 % base_seconds:
            errors.append("S45 requires a granular aligned source")
        if s45.get("alignment_seconds") != 45:
            errors.append("S45 alignment must be 45 seconds")
    mo6 = mapping.get("MO6", {})
    if mo6.get("source_kind") == "DERIVED":
        if mo6.get("source_timeframes") != ["MN1"] or mo6.get("complete_source_candles") != 6:
            errors.append("MO6 requires six complete MN1 candles")
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        evidence={"requested_count": len(REQUESTED_TIMEFRAMES), "mapping_hash": sha256_text(stable(mapping))},
    )


def audit_timeframe_coverage_state(state: Mapping[str, Any]) -> AuditResult:
    errors: list[str] = []
    requested = tuple(state.get("requested_timeframes", []))
    matrix = state.get("timeframes", {})
    if set(requested) != set(REQUESTED_TIMEFRAMES) or len(requested) != len(REQUESTED_TIMEFRAMES):
        errors.append("requested timeframe contract does not contain the exact 24 unique timeframes")
    if not isinstance(matrix, Mapping) or set(matrix) != set(REQUESTED_TIMEFRAMES):
        errors.append("coverage matrix does not classify the exact requested timeframe set")
        matrix = {}
    if state.get("all_requested_timeframes_classified") is not True:
        errors.append("all-requested-timeframes classification is not asserted")
    s1 = matrix.get("S1", {})
    if s1.get("source") not in {"NONE", "TICK_OR_NATIVE_S1"}:
        errors.append("S1 has an unauthorized derived source")
    s45 = matrix.get("S45", {})
    if s45.get("native_or_derived_status") != "UNAVAILABLE_WITH_CURRENT_EVIDENCE":
        source = str(s45.get("source", ""))
        if not any(token in source for token in ("S1", "S5", "S15")):
            errors.append("S45 lacks a valid granular source")
    mo6 = matrix.get("MO6", {})
    if mo6.get("native_or_derived_status") != "UNAVAILABLE_WITH_CURRENT_EVIDENCE":
        if "SIX_COMPLETE_CONSECUTIVE_MN1_CANDLES" not in str(mo6.get("source", "")):
            errors.append("MO6 is not mapped from six complete consecutive MN1 candles")
    for timeframe, row in matrix.items():
        if row.get("Development_eligible") and row.get("completed_bar_integrity") is not True:
            errors.append(f"{timeframe}: Development eligibility lacks completed-bar integrity")
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        evidence={
            "requested_count": len(requested),
            "unavailable_count": len(state.get("unavailable_timeframes", [])),
            "coverage_hash": state.get("coverage_hash"),
        },
    )


def audit_packet_integrity(
    packet032_state: Mapping[str, Any],
    packet033_state: Mapping[str, Any],
    inventory_state: Mapping[str, Any],
) -> AuditResult:
    errors: list[str] = []
    expected = {
        "packet032_hypotheses": 912,
        "queued_raw_positive_diagnostics": 263,
        "macd_m30_long_count": 2,
        "macd_m30_short_count": 1,
    }
    for field, value in expected.items():
        if packet032_state.get(field) != value:
            errors.append(f"Packet 032/033 queue {field} expected {value}")
    queue = packet032_state.get("queue", [])
    queue_ids = [item.get("queue_id") for item in queue if isinstance(item, Mapping)]
    if len(queue) != 263 or len(queue_ids) != len(set(queue_ids)):
        errors.append("replication queue must contain 263 unique IDs")
    if packet032_state.get("queue_hash") != sha256_text(stable(queue)):
        errors.append("replication queue hash mismatch")
    if inventory_state.get("technique_count") != 82:
        errors.append("mechanical technique inventory must contain 82 techniques")
    if packet033_state.get("queued_packet032_positive_diagnostics") != 263:
        errors.append("Packet 033 state does not reconcile the 263-item queue")
    if packet033_state.get("macd_m30_long_queued") != 2 or packet033_state.get("macd_m30_short_queued") != 1:
        errors.append("Packet 033 state M30 MACD clue counts do not reconcile")
    finalist_status = packet033_state.get("finalist_status")
    no_finalist_state = (
        finalist_status is None
        or finalist_status == "NONE_EARNED"
        or str(finalist_status).startswith("NO_FINALIST")
    )
    if not no_finalist_state:
        errors.append("five-trade clues appear to have been promoted")
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        evidence={
            "hypotheses": packet032_state.get("packet032_hypotheses"),
            "queue_count": len(queue),
            "technique_count": inventory_state.get("technique_count"),
        },
    )


def validate_technique_fidelity(techniques: Sequence[Mapping[str, Any]]) -> AuditResult:
    errors: list[str] = []
    if len(techniques) != 82:
        errors.append(f"expected 82 techniques, found {len(techniques)}")
    ids = [str(item.get("technique_id", "")) for item in techniques]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        errors.append("technique IDs must be present and unique")
    for technique in techniques:
        technique_id = str(technique.get("technique_id", "UNKNOWN"))
        directions = set(technique.get("directions", []))
        if not directions or not directions.issubset({"LONG", "SHORT"}):
            errors.append(f"{technique_id}: invalid direction contract")
        if not technique.get("objective_entry_rules") or not technique.get("objective_exit_rules"):
            errors.append(f"{technique_id}: objective entry/exit rules missing")
        if not technique.get("controls") or not technique.get("fingerprint"):
            errors.append(f"{technique_id}: controls or fingerprint missing")
        if technique.get("requires_order_flow") and technique.get("order_flow_data_eligible") is not True:
            errors.append(f"{technique_id}: order-flow technique lacks eligible data")
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        evidence={"technique_count": len(techniques), "fidelity_hash": sha256_text(stable(techniques))},
    )


def audit_technique_inventory_state(
    inventory: Mapping[str, Any],
    fidelity: Mapping[str, Any],
) -> AuditResult:
    errors: list[str] = []
    families = inventory.get("families", [])
    if inventory.get("family_count") != 12 or len(families) != 12:
        errors.append("technique inventory must contain 12 families")
    techniques = [
        technique
        for family in families
        if isinstance(family, Mapping)
        for technique in family.get("techniques", [])
    ]
    if inventory.get("technique_count") != 82 or len(techniques) != 82:
        errors.append("technique inventory must contain 82 techniques")
    if len(techniques) != len(set(techniques)):
        errors.append("technique inventory contains duplicate IDs")
    for family in families:
        family_id = str(family.get("family_id", "UNKNOWN"))
        if family.get("mechanical_definition_required") is not True:
            errors.append(f"family {family_id}: mechanical definition is not required")
        if family.get("long_short_separate") is not True:
            errors.append(f"family {family_id}: LONG/SHORT separation missing")
        fingerprint = str(family.get("behavior_fingerprint", ""))
        if len(fingerprint) != 64:
            errors.append(f"family {family_id}: behavior fingerprint invalid")
        if family.get("data_requirement") == "ORDER_BOOK_OR_TRADE_TAPE" and not str(family.get("status", "")).startswith("INELIGIBLE"):
            errors.append(f"family {family_id}: order-flow family improperly eligible")
    if inventory.get("inventory_hash") != sha256_text(stable(families)):
        errors.append("technique inventory hash mismatch")
    required_fidelity = {
        "mechanical": True,
        "causal_completed_bar_only": True,
        "subjective_chart_drawing": False,
        "order_book_claims": False,
        "centralized_volume_claims": False,
    }
    for field, expected in required_fidelity.items():
        if fidelity.get(field) is not expected:
            errors.append(f"fidelity field {field} expected {expected}")
    if len(str(fidelity.get("code_fingerprint", ""))) != 64:
        errors.append("technique primitive code fingerprint invalid")
    contracts = fidelity.get("technique_contracts", [])
    if not isinstance(contracts, list) or len(contracts) != 82:
        errors.append("fidelity state must contain 82 per-technique contracts")
        contracts = []
    contract_ids = [contract.get("technique_id") for contract in contracts if isinstance(contract, Mapping)]
    if len(contract_ids) != len(set(contract_ids)) or set(contract_ids) != set(techniques):
        errors.append("per-technique contracts do not match the 82-item inventory")
    for contract in contracts:
        technique_id = str(contract.get("technique_id", "UNKNOWN"))
        if contract.get("directions") != ["LONG", "SHORT"]:
            errors.append(f"{technique_id}: objective LONG/SHORT contract missing")
        if not contract.get("objective_entry_rules") or not contract.get("objective_exit_rules"):
            errors.append(f"{technique_id}: objective rules missing")
        if not contract.get("controls") or not contract.get("data_requirement"):
            errors.append(f"{technique_id}: controls or data requirement missing")
        if len(str(contract.get("fingerprint", ""))) != 64:
            errors.append(f"{technique_id}: contract fingerprint invalid")
        if contract.get("data_requirement") == "ORDER_BOOK_OR_TRADE_TAPE" and contract.get("data_eligible") is not False:
            errors.append(f"{technique_id}: order-flow data eligibility must fail closed")
    if contracts and fidelity.get("contract_registry_hash") != sha256_text(stable(contracts)):
        errors.append("technique contract registry hash mismatch")
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        evidence={
            "family_count": len(families),
            "technique_count": len(techniques),
            "inventory_hash": inventory.get("inventory_hash"),
            "code_fingerprint": fidelity.get("code_fingerprint"),
            "contract_count": len(contracts),
        },
    )


def plan_compute_shards(
    timeframes: Iterable[str],
    technique_ids: Iterable[str],
    directions: Iterable[str],
    pair_tiers: Iterable[str],
    *,
    completed: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    completed = completed or {}
    combinations = sorted({
        (timeframe, technique, direction, pair_tier)
        for timeframe in timeframes
        for technique in technique_ids
        for direction in directions
        for pair_tier in pair_tiers
    })
    shards: list[dict[str, Any]] = []
    for timeframe, technique, direction, pair_tier in combinations:
        identity = {
            "timeframe": timeframe,
            "technique_id": technique,
            "direction": direction,
            "pair_tier": pair_tier,
        }
        shard_hash = sha256_text(stable(identity))
        shard_id = f"SHARD-{shard_hash[:16]}"
        shards.append({
            **identity,
            "shard_id": shard_id,
            "shard_hash": shard_hash,
            "writer": "SINGLE_PACKET033_R5_WRITER",
            "status": "REUSE_COMPLETE" if completed.get(shard_id) == shard_hash else "PENDING",
        })
    return {
        "requested_combination_count": len(combinations),
        "planned_shard_count": len(shards),
        "silent_sample_reduction": False,
        "single_writer": True,
        "shards": shards,
        "progress_hash": sha256_text(stable(shards)),
    }


def validate_hypothesis_ledger(ledger: Mapping[str, Any]) -> AuditResult:
    errors: list[str] = []
    hypotheses = ledger.get("hypotheses", [])
    ids = [item.get("hypothesis_id") for item in hypotheses if isinstance(item, Mapping)]
    if len(ids) != len(set(ids)) or any(not item for item in ids):
        errors.append("hypothesis IDs must be present and unique")
    effective_trials = ledger.get("effective_trial_count")
    if not isinstance(effective_trials, int) or effective_trials < len(hypotheses):
        errors.append("effective trial count cannot be smaller than the ledger")
    negative_count = sum(
        1 for item in hypotheses
        if item.get("status") in {"NEGATIVE", "FAILED", "REJECTED", "NO_EDGE"}
    )
    if ledger.get("negative_results_preserved") is not True:
        errors.append("negative-result preservation is not asserted")
    if ledger.get("append_only") is not True:
        errors.append("hypothesis ledger is not append-only")
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        evidence={"hypothesis_count": len(hypotheses), "negative_count": negative_count},
    )


def audit_packet033_hypothesis_ledger(ledger: Mapping[str, Any]) -> AuditResult:
    errors: list[str] = []
    entries = ledger.get("entries", [])
    if not isinstance(entries, list):
        errors.append("entries must be a list")
        entries = []
    ids = [entry.get("hypothesis_id") for entry in entries if isinstance(entry, Mapping)]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        errors.append("Packet 033 hypothesis IDs must be present and unique")
    total_attempted = int(ledger.get("total_attempted", -1))
    effective_trials = int(ledger.get("effective_trials", -1))
    if total_attempted < 0 or effective_trials < total_attempted:
        errors.append("effective trial accounting is smaller than attempted trials")
    if ledger.get("hidden_trials_possible") is not False:
        errors.append("hidden-trial path is not fail-closed")
    executed_entries = [
        entry for entry in entries
        if "QUEUED" not in str(entry.get("result", "")) and "NOT_EXECUTED" not in str(entry.get("result", ""))
    ]
    if len(executed_entries) != total_attempted:
        errors.append("attempted-trial count does not reconcile executed entries")
    if ledger.get("ledger_hash") != sha256_text(stable(entries)):
        errors.append("Packet 033 hypothesis ledger hash mismatch")
    stage_attempts = sum(
        int(stage.get("attempted", 0))
        for name in ("screen", "full_replication", "interactions")
        if isinstance((stage := ledger.get(name, {})), Mapping)
    )
    if stage_attempts != total_attempted:
        errors.append("stage attempt counts do not reconcile total_attempted")
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        evidence={
            "entry_count": len(entries),
            "total_attempted": total_attempted,
            "effective_trials": effective_trials,
            "ledger_hash": ledger.get("ledger_hash"),
        },
    )


def evaluate_gross_edge_gate(metrics: Mapping[str, Any]) -> AuditResult:
    requirements = {
        "sample_size": (int(metrics.get("sample_size", 0)), 50),
        "fold_count": (int(metrics.get("fold_count", 0)), 3),
        "positive_fold_share": (float(metrics.get("positive_fold_share", 0.0)), 2 / 3),
        "pair_count": (int(metrics.get("pair_count", 0)), 4),
        "parameter_neighbor_pass_count": (int(metrics.get("parameter_neighbor_pass_count", 0)), 2),
    }
    errors = [f"{name} below gate" for name, (actual, minimum) in requirements.items() if actual < minimum]
    if float(metrics.get("max_pair_share", 1.0)) > 0.45:
        errors.append("pair dominance exceeds gate")
    if float(metrics.get("gross_expectancy", 0.0)) <= 0 or float(metrics.get("gross_profit_factor", 0.0)) <= 1:
        errors.append("gross edge is not positive")
    if metrics.get("direction") not in {"LONG", "SHORT"}:
        errors.append("direction isolation missing")
    if metrics.get("multiple_testing_route") not in {"REQUIRED", "PASS"}:
        errors.append("multiple-testing route missing")
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        evidence={"direction": metrics.get("direction"), "gate_fingerprint": sha256_text(stable(metrics))},
    )


def audit_m30_macd_readiness(queue_state: Mapping[str, Any]) -> AuditResult:
    errors: list[str] = []
    if queue_state.get("macd_m30_long_count") != 2:
        errors.append("M30 MACD LONG clue count must remain 2")
    if queue_state.get("macd_m30_short_count") != 1:
        errors.append("M30 MACD SHORT clue count must remain 1")
    neighborhood = queue_state.get("macd_m30_replication_neighborhood", {})
    if not neighborhood.get("macd_families") or not neighborhood.get("histogram_variants"):
        errors.append("M30 MACD neighboring parameter registry is incomplete")
    queue = queue_state.get("queue", [])
    m30 = [item for item in queue if item.get("indicator_combination") == "MACD" and item.get("timeframe") == "M30"]
    if any(int(item.get("trade_count", 0)) >= 50 for item in m30):
        errors.append("M30 clue set no longer matches the five-trade readiness premise")
    if any(item.get("status") != "QUEUED_FOR_FULL_REPLICATION" for item in m30):
        errors.append("M30 clues were promoted before replication")
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        evidence={"m30_macd_queue_count": len(m30)},
    )


def finalist_forward_v13_readiness(state: Mapping[str, Any]) -> AuditResult:
    errors: list[str] = []
    gross_ready = state.get("long_gross_edge") is True and state.get("short_gross_edge") is True
    if not gross_ready:
        invented = [name for name in ("forward_opened", "v13_opened", "paper_opened") if state.get(name) is True]
        if invented:
            errors.append(f"downstream evidence opened without bidirectional gross edge: {','.join(invented)}")
    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(errors),
        evidence={"gross_ready": gross_ready, "route": "FORWARD" if gross_ready else "WAIT_FOR_EARNED_CANDIDATE"},
    )


def acquisition_load_plan(
    *,
    instruments: Sequence[str],
    granularities: Sequence[str],
    estimated_candles_per_series: int | Mapping[str, int],
    candles_per_request: int,
    output_root: str = ".aios/runtime/forex_scalping_history_human_inbox_v1",
    from_utc: str = "2024-01-01T00:00:00Z",
    to_utc: str = "2026-08-30T00:00:00Z",
    minimum_request_interval_seconds: float = 0.5,
) -> dict[str, Any]:
    if candles_per_request <= 0:
        raise ValueError("request size must be positive")
    if not math.isfinite(minimum_request_interval_seconds) or minimum_request_interval_seconds <= 0:
        raise ValueError("request pacing interval must be finite and positive")
    if parse_utc(to_utc) <= parse_utc(from_utc):
        raise ValueError("acquisition ToUtc must be after FromUtc")
    unique_instruments = sorted(set(instruments))
    unique_granularities = sorted(set(granularities))
    if not unique_instruments or not unique_granularities:
        raise ValueError("acquisition requires at least one instrument and granularity")
    if any(re.fullmatch(r"[A-Z]{3}_[A-Z]{3}", item) is None for item in unique_instruments):
        raise ValueError("instrument must use canonical AAA_BBB format")
    if any(item not in GRANULARITY_SECONDS for item in unique_granularities):
        raise ValueError("unsupported acquisition granularity")
    series_count = len(unique_instruments) * len(unique_granularities)
    if isinstance(estimated_candles_per_series, Mapping):
        candle_estimates = {item: int(estimated_candles_per_series.get(item, 0)) for item in unique_granularities}
    else:
        candle_estimates = {item: int(estimated_candles_per_series) for item in unique_granularities}
    if any(value <= 0 for value in candle_estimates.values()):
        raise ValueError("every granularity requires a positive candle estimate")
    requests_by_granularity = {
        item: len(unique_instruments) * ((count + candles_per_request - 1) // candles_per_request)
        for item, count in candle_estimates.items()
    }
    request_count = sum(requests_by_granularity.values())
    def ps_quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    instrument_expression = "@(" + ",".join(ps_quote(item) for item in unique_instruments) + ")"
    granularity_expression = "@(" + ",".join(ps_quote(item) for item in unique_granularities) + ")"
    command = (
        "& '.\\scripts\\forex_delivery\\Acquire-AiOsOandaPracticeScalpingHistory.HUMAN_ONLY.ps1' "
        f"-OutputRoot {ps_quote(output_root)} -Instruments {instrument_expression} "
        f"-Granularities {granularity_expression} -FromUtc {ps_quote(from_utc)} -ToUtc {ps_quote(to_utc)}"
    )
    return {
        "practice_get_only": True,
        "orders_allowed": False,
        "live_host_allowed": False,
        "secret_persistence_allowed": False,
        "series_count": series_count,
        "estimated_request_count": request_count,
        "estimated_requests_by_granularity": requests_by_granularity,
        "estimated_candles_per_series_by_granularity": candle_estimates,
        "candles_per_request": candles_per_request,
        "pacing_policy": "SINGLE_IN_FLIGHT_FIXED_MINIMUM_INTERVAL",
        "minimum_request_interval_seconds": minimum_request_interval_seconds,
        "estimated_minimum_request_duration_seconds": math.ceil(request_count * minimum_request_interval_seconds),
        "checkpoint_every_requests": 1,
        "resume_from_first_incomplete_series": True,
        "estimated_raw_bytes": len(unique_instruments) * sum(candle_estimates.values()) * 420,
        "estimate_class": "UPPER_BOUND_WITH_FX_MARKET_OPEN_RATIO",
        "from_utc": from_utc,
        "to_utc": to_utc,
        "to_boundary_semantics": "EXCLUSIVE",
        "plan_command": command + " -WhatIfOnly",
        "acquisition_command": command,
    }


def estimate_candles_by_granularity(
    from_utc: str,
    to_utc: str,
    granularities: Sequence[str],
    *,
    market_open_ratio: float = 5 / 7,
) -> dict[str, int]:
    if not 0 < market_open_ratio <= 1:
        raise ValueError("market_open_ratio must be in (0, 1]")
    elapsed_seconds = (parse_utc(to_utc) - parse_utc(from_utc)).total_seconds()
    if elapsed_seconds <= 0:
        raise ValueError("estimate interval must be positive")
    estimates: dict[str, int] = {}
    for granularity in sorted(set(granularities)):
        seconds = GRANULARITY_SECONDS.get(granularity)
        if seconds is None:
            raise ValueError(f"unsupported fixed-duration granularity: {granularity}")
        estimates[granularity] = max(1, math.ceil(elapsed_seconds * market_open_ratio / seconds))
    return estimates


def repository_pre_data_audits(repo_root: Path) -> dict[str, Any]:
    reports = repo_root / "Reports" / "forex_delivery"
    queue_state = read_json(reports / "AIOS_FOREX_PACKET032_REPLICATION_QUEUE_V1_STATE.json")
    packet033_state = read_json(reports / "AIOS_FOREX_ALL_TIMEFRAME_SCALPING_SEARCH_V1_STATE.json")
    inventory_state = read_json(reports / "AIOS_FOREX_SCALPING_TECHNIQUE_INVENTORY_V1_STATE.json")
    fidelity_state = read_json(reports / "AIOS_FOREX_SCALPING_TECHNIQUE_FIDELITY_V1_STATE.json")
    coverage_state = read_json(reports / "AIOS_FOREX_SCALPING_TIMEFRAME_COVERAGE_V1_STATE.json")
    hypothesis_ledger = read_json(reports / "AIOS_FOREX_ALL_TIMEFRAME_SCALPING_HYPOTHESIS_LEDGER_V1.json")
    results = {
        "T06_TIMEFRAME_MAPPING": audit_timeframe_coverage_state(coverage_state),
        "T07_PACKET_STATE_INTEGRITY": audit_packet_integrity(queue_state, packet033_state, inventory_state),
        "T08_TECHNIQUE_FIDELITY": audit_technique_inventory_state(inventory_state, fidelity_state),
        "T10_HYPOTHESIS_LEDGER": audit_packet033_hypothesis_ledger(hypothesis_ledger),
        "T12_M30_MACD_READINESS": audit_m30_macd_readiness(queue_state),
        "T13_FINALIST_FORWARD_V13": finalist_forward_v13_readiness(packet033_state),
    }
    return {name: result.as_dict() for name, result in results.items()}


def build_stop_proof(
    checkpoint: Mapping[str, Any],
    audits: Mapping[str, Mapping[str, Any]],
    *,
    active_compute_shard_count: int,
    compute_shard_evidence: str,
) -> dict[str, Any]:
    if active_compute_shard_count < 0 or not compute_shard_evidence:
        raise ValueError("compute shard stop-proof evidence is required")
    statuses = checkpoint.get("task_statuses", {})
    remaining_tasks = [task_id for task_id in TASK_IDS if statuses.get(task_id) not in TERMINAL_TASK_STATUSES]
    failed_audits = [name for name, result in audits.items() if result.get("status") != "PASS"]
    independent_count = len(remaining_tasks) + len(failed_audits) + active_compute_shard_count
    alternate_actions = [f"CONTINUE_{task_id}" for task_id in remaining_tasks[:1]]
    unlocked_phases = [checkpoint.get("first_incomplete_task")] if remaining_tasks else []
    pre_terminal = "PASS" if independent_count == 0 else "FAIL_CONTINUE"
    return {
        "remaining_authorized_work_count": independent_count,
        "independent_codex_resolvable_work_count": independent_count,
        "alternate_safe_actions": alternate_actions,
        "unlocked_next_phase_count": len(unlocked_phases),
        "unlocked_next_phases": unlocked_phases,
        "repairable_p0_p1_count": len(failed_audits),
        "active_compute_shard_count": active_compute_shard_count,
        "compute_shard_evidence": compute_shard_evidence,
        "report_only_stop": False,
        "phase_completion_only_stop": False,
        "pre_terminal_audit_status": pre_terminal,
        "stop_allowed": pre_terminal == "PASS",
    }


def build_r5_state(
    ledger: Mapping[str, Any],
    *,
    current_lock: str,
    human_artifacts_present: bool,
    audits: Mapping[str, Mapping[str, Any]],
    acquisition_plan: Mapping[str, Any],
) -> dict[str, Any]:
    checkpoint = build_checkpoint(
        ledger,
        current_lock=current_lock,
        human_artifacts_present=human_artifacts_present,
    )
    stop_proof = build_stop_proof(
        checkpoint,
        audits,
        active_compute_shard_count=0,
        compute_shard_evidence="PRE_DATA_SHARD_PLANNER_VALIDATED_NO_SHARDS_LAUNCHED",
    )
    state = {
        "schema": SCHEMA_VERSION,
        "packet_id": PACKET_ID,
        "updated_at_utc": utc_now(),
        "status": checkpoint["status"],
        "checkpoint": checkpoint,
        "audits": dict(audits),
        "acquisition_plan": dict(acquisition_plan),
        "human_artifact_status": "PRESENT" if human_artifacts_present else "ABSENT_WAITING_HUMAN",
        "long_gross_edge": "NOT_PROVEN",
        "short_gross_edge": "NOT_PROVEN",
        "full_cost_net_edge": "NOT_OPENED",
        "stop_proof": stop_proof,
        "safety": {
            "broker_mutation": False,
            "practice_order": False,
            "live_request": False,
            "live_order": False,
            "secret_output": False,
            "money_movement": False,
            "commit": False,
            "push": False,
        },
        "state_hash": "",
    }
    state["state_hash"] = sha256_text(stable({key: value for key, value in state.items() if key != "state_hash"}))
    return state


def build_attack_state(
    prior: Mapping[str, Any],
    r5_state: Mapping[str, Any],
) -> dict[str, Any]:
    updated = json.loads(stable(prior))
    checkpoint = r5_state["checkpoint"]
    updated.update({
        "schema": "AIOS_FOREX_ATTACK_TO_FINISH.v11",
        "packet_id": "PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033",
        "status": r5_state["status"],
        "updated_by_packet": PACKET_ID,
        "r5_checkpoint": {
            "last_completed_task": checkpoint["last_completed_task"],
            "first_incomplete_task": checkpoint["first_incomplete_task"],
            "productive_minutes_cumulative": checkpoint["productive_minutes_cumulative"],
            "productive_minutes_remaining": checkpoint["productive_minutes_remaining"],
            "one_hour_requirement_status": checkpoint["one_hour_requirement_status"],
            "task_ledger_tail_hash": checkpoint["task_ledger_tail_hash"],
        },
        "remaining_authorized_work_count": r5_state["stop_proof"]["remaining_authorized_work_count"],
        "independent_codex_resolvable_work_count": r5_state["stop_proof"]["independent_codex_resolvable_work_count"],
        "alternate_safe_actions": r5_state["stop_proof"]["alternate_safe_actions"],
        "pre_terminal_audit_status": r5_state["stop_proof"]["pre_terminal_audit_status"],
        "same_packet_resume_command": "Resume PKT-EAST-FOREX-PACKET033-R5-CONTINUATION-CONSTITUTION from first_incomplete_task.",
        "stop_point": checkpoint["first_incomplete_task"],
    })
    return updated


def write_authoritative_r5_outputs(
    repo_root: Path,
    ledger: Mapping[str, Any],
    *,
    current_lock: str,
) -> dict[str, Any]:
    reports = repo_root / "Reports" / "forex_delivery"
    human_root = repo_root / ".aios" / "runtime" / "forex_scalping_history_human_inbox_v1"
    audits = repository_pre_data_audits(repo_root)
    handoff = read_json(reports / "AIOS_FOREX_SCALPING_HISTORY_HUMAN_HANDOFF_V1_STATE.json")
    estimated_candles = estimate_candles_by_granularity(
        handoff["overall_from_utc"],
        handoff["overall_to_utc"],
        handoff["requested_granularities"],
    )
    plan = acquisition_load_plan(
        instruments=handoff["instruments"],
        granularities=handoff["requested_granularities"],
        estimated_candles_per_series=estimated_candles,
        candles_per_request=int(handoff["candles_per_request"]),
        output_root=handoff["output_root"],
        from_utc=handoff["overall_from_utc"],
        to_utc=handoff["overall_to_utc"],
    )
    state = build_r5_state(
        ledger,
        current_lock=current_lock,
        human_artifacts_present=human_root.is_dir(),
        audits=audits,
        acquisition_plan=plan,
    )
    atomic_json(reports / "AIOS_FOREX_PACKET033_R5_STATE.json", state)
    checkpoint = state["checkpoint"]
    report = "\n".join([
        "# AIOS Forex Packet 033 R5 Continuation",
        "",
        f"- Status: {state['status']}",
        f"- Last completed task: {checkpoint['last_completed_task']}",
        f"- First incomplete task: {checkpoint['first_incomplete_task']}",
        f"- Productive minutes cumulative: {checkpoint['productive_minutes_cumulative']}",
        f"- Productive minutes remaining: {checkpoint['productive_minutes_remaining']}",
        f"- Human artifacts: {state['human_artifact_status']}",
        f"- LONG gross edge: {state['long_gross_edge']}",
        f"- SHORT gross edge: {state['short_gross_edge']}",
        f"- Pre-terminal audit: {state['stop_proof']['pre_terminal_audit_status']}",
        "- Broker mutation, orders, LIVE requests, secret output, commit, and push: NO",
        "",
    ])
    atomic_text(reports / "AIOS_FOREX_PACKET033_R5_REPORT.md", report)
    prior_attack = read_json(reports / "AIOS_FOREX_ATTACK_TO_FINISH_V11_STATE.json")
    attack = build_attack_state(prior_attack, state)
    atomic_json(reports / "AIOS_FOREX_ATTACK_TO_FINISH_V11_STATE.json", attack)
    atomic_text(
        reports / "AIOS_FOREX_ATTACK_TO_FINISH_V11_REPORT.md",
        "\n".join([
            "# AIOS Forex Attack To Finish V11",
            "",
            f"- Status: {attack['status']}",
            f"- Updated by: {PACKET_ID}",
            f"- First incomplete task: {checkpoint['first_incomplete_task']}",
            f"- Remaining authorized work: {attack['remaining_authorized_work_count']}",
            f"- Pre-terminal audit: {attack['pre_terminal_audit_status']}",
            "- Human data branch remains waiting; independent R5 work routes first.",
            "",
        ]),
    )
    return state


def write_checkpoint_bundle(
    output_root: Path,
    ledger: Mapping[str, Any],
    *,
    current_lock: str,
    human_artifacts_present: bool,
) -> dict[str, Any]:
    checkpoint = build_checkpoint(
        ledger,
        current_lock=current_lock,
        human_artifacts_present=human_artifacts_present,
    )
    time_state = productive_time_state(ledger)
    atomic_json(output_root / "AIOS_FOREX_PACKET033_R5_TASK_LEDGER.json", ledger)
    atomic_json(output_root / "AIOS_FOREX_PACKET033_R5_PRODUCTIVE_TIME_LEDGER.json", time_state)
    atomic_json(output_root / "AIOS_FOREX_PACKET033_R5_CHECKPOINT_STATE.json", checkpoint)
    return checkpoint


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("Reports/forex_delivery"))
    parser.add_argument("--task-ledger", type=Path)
    parser.add_argument("--record-task", choices=TASK_IDS)
    parser.add_argument("--status", default="COMPLETE")
    parser.add_argument("--productive-seconds", type=float, default=0.0)
    parser.add_argument("--started-at-utc")
    parser.add_argument("--ended-at-utc")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--current-lock", default="NONE")
    parser.add_argument("--human-artifact-root", type=Path, default=Path(".aios/runtime/forex_scalping_history_human_inbox_v1"))
    parser.add_argument("--write-authoritative-state", action="store_true")
    parser.add_argument("--verify-ledger", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    ledger_path = args.task_ledger or args.output_root / "AIOS_FOREX_PACKET033_R5_TASK_LEDGER.json"
    ledger = read_json(ledger_path) if ledger_path.exists() else empty_task_ledger()
    if args.verify_ledger:
        result = verify_task_ledger(ledger)
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        return 0 if result.passed else 1
    if args.record_task:
        ended = args.ended_at_utc or utc_now()
        started = args.started_at_utc or ended
        ledger = append_task_entry(
            ledger,
            task_id=args.record_task,
            status=args.status,
            productive_seconds=args.productive_seconds,
            evidence=args.evidence,
            started_at_utc=started,
            ended_at_utc=ended,
        )
    checkpoint = write_checkpoint_bundle(
        args.output_root,
        ledger,
        current_lock=args.current_lock,
        human_artifacts_present=args.human_artifact_root.is_dir(),
    )
    output: Mapping[str, Any] = checkpoint
    if args.write_authoritative_state:
        output = write_authoritative_r5_outputs(
            args.repo_root.resolve(),
            ledger,
            current_lock=args.current_lock,
        )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
