"""Offline, fail-closed delivery receipt instrumentation for governed AIOS work."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

TASK_SCHEMA = "AIOS_CODEX_TASK_TIMING_RECEIPT.v1"
GITHUB_SCHEMA = "AIOS_GITHUB_PR_VALIDATION_RECEIPT.v1"
EVENT_SCHEMA = "AIOS_ENGINEERING_VELOCITY_EVENT.v1"
PROVENANCE = "MEASURED_REPOSITORY_INSTRUMENTATION"
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$")
SENSITIVE_KEY = re.compile(r"(?:secret|password|credential|authorization|cookie|token|account.?id|broker.?order|raw.?payload)", re.I)
SENSITIVE_VALUE = re.compile(r"(?:sk-[A-Za-z0-9]{12,}|bearer\s+\S+|-----BEGIN .*PRIVATE KEY-----)", re.I)
PRIVATE_IDENTITY = re.compile(r"(?:account|credential|secret|token|cookie|authorization|broker.?order)", re.I)


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def _sanitize(value: Any, path: str = "receipt") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if SENSITIVE_KEY.search(str(key)):
                raise ValueError(f"sensitive field rejected: {path}.{key}")
            _sanitize(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value): _sanitize(child, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite value rejected: {path}")
    elif isinstance(value, str) and SENSITIVE_VALUE.search(value):
        raise ValueError(f"secret-like value rejected: {path}")


def _utc(value: str, label: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not value.endswith(("Z", "+00:00")):
        raise ValueError(f"{label} must be an explicit UTC timestamp")
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc: raise ValueError(f"invalid {label}") from exc
    parsed = parsed.astimezone(timezone.utc)
    return parsed, parsed.isoformat().replace("+00:00", "Z")


def _identity(value: str, label: str) -> str:
    if not isinstance(value, str) or not IDENTITY.fullmatch(value): raise ValueError(f"malformed {label}")
    if PRIVATE_IDENTITY.search(value): raise ValueError(f"private identifier rejected: {label}")
    return value


def _safe_packet(packet_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", _identity(packet_id, "packet_id"))


def _write_once(path: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    _sanitize(value); content = stable_json(value)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current != content: raise ValueError(f"conflicting receipt: {path.name}")
        return dict(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return dict(value)


def start_task_timing(runtime_dir: str | Path, *, task_id: str, packet_id: str, lane: str, branch: str,
                      starting_head: str, started_utc: str, process_identity_type: str = "CODEX_WORKER") -> dict[str, Any]:
    _, timestamp = _utc(started_utc, "started_utc")
    receipt = {"schema": TASK_SCHEMA, "task_id": _identity(task_id, "task_id"), "packet_id": _identity(packet_id, "packet_id"),
               "lane": _identity(lane, "lane"), "branch": _identity(branch, "branch"), "starting_head": _identity(starting_head, "starting_head"),
               "started_utc": timestamp, "process_identity_type": _identity(process_identity_type, "process_identity_type"),
               "provenance": PROVENANCE, "runtime_marker_only": True}
    return _write_once(Path(runtime_dir) / f"{_safe_packet(packet_id)}.json", receipt)


def _terminal(runtime_dir: str | Path, terminal_dir: str | Path, *, task_id: str, packet_id: str,
              status: str, terminal_utc: str, **fields: Any) -> dict[str, Any]:
    task_id, packet_id = _identity(task_id, "task_id"), _identity(packet_id, "packet_id")
    ended, ended_text = _utc(terminal_utc, "terminal timestamp")
    path = Path(terminal_dir) / f"{_safe_packet(packet_id)}--{re.sub('[^A-Za-z0-9_.-]', '-', task_id)}.json"
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        timestamp_key = "completed_utc" if status == "COMPLETE" else "blocked_utc"
        expected_fields = {**fields, "status": status, timestamp_key: ended_text}
        if any(existing.get(key) != value for key, value in expected_fields.items()):
            raise ValueError(f"conflicting receipt: {path.name}")
        return existing
    marker_path = Path(runtime_dir) / f"{_safe_packet(packet_id)}.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8")) if marker_path.is_file() else None
    if marker and (marker.get("task_id"), marker.get("packet_id")) != (task_id, packet_id): raise ValueError("start marker identity mismatch")
    started_text = marker.get("started_utc") if marker else None
    elapsed = None; measured = False; exclusion = "START_MARKER_UNAVAILABLE"
    if marker:
        started, started_text = _utc(started_text, "started_utc")
        if ended < started: raise ValueError("terminal timestamp is earlier than start")
        elapsed = (ended - started).total_seconds(); measured = True; exclusion = None
    receipt = {"schema": TASK_SCHEMA, "task_id": task_id, "packet_id": packet_id, "status": status,
               "lane": marker.get("lane") if marker else fields.pop("lane", None),
               "branch": marker.get("branch") if marker else fields.pop("branch", None),
               "starting_head": marker.get("starting_head") if marker else fields.pop("starting_head", None),
               "started_utc": started_text, ("completed_utc" if status == "COMPLETE" else "blocked_utc"): ended_text,
               "elapsed_seconds": elapsed, "elapsed_minutes": round(elapsed / 60, 6) if measured else None,
               "duration_measured": measured, "duration_exclusion_reason": exclusion, "provenance": PROVENANCE,
               **fields}
    validate_task_receipt(receipt)
    result = _write_once(path, receipt)
    if marker_path.exists(): marker_path.unlink()
    return result


def complete_task_timing(runtime_dir: str | Path, terminal_dir: str | Path, *, task_id: str, packet_id: str,
                         completed_utc: str, **fields: Any) -> dict[str, Any]:
    defaults = {"files_changed_count": 0, "lines_added": 0, "lines_deleted": 0, "tests_run": 0, "tests_passed": 0,
                "tests_failed": 0, "tests_skipped": 0, "validation_status": "UNAVAILABLE", "blockers_found": 0,
                "blockers_closed": 0, "commit_created": False, "commit_sha": None, "commit_message": None,
                "pr_created": False, "merged": False, "archived": False}
    defaults.update(fields)
    return _terminal(runtime_dir, terminal_dir, task_id=task_id, packet_id=packet_id, status="COMPLETE", terminal_utc=completed_utc, **defaults)


def block_task_timing(runtime_dir: str | Path, terminal_dir: str | Path, *, task_id: str, packet_id: str,
                      blocked_utc: str, blocker_reasons: Sequence[str], **fields: Any) -> dict[str, Any]:
    if not blocker_reasons: raise ValueError("blocker reasons required")
    return _terminal(runtime_dir, terminal_dir, task_id=task_id, packet_id=packet_id, status="BLOCKED", terminal_utc=blocked_utc,
                     blocker_reasons=list(blocker_reasons), completion_credit=False, merged=False, **fields)


def validate_task_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    _sanitize(receipt)
    if receipt.get("schema") != TASK_SCHEMA or receipt.get("status") not in {"COMPLETE", "BLOCKED"}: raise ValueError("invalid task receipt contract")
    for key in ("task_id", "packet_id"): _identity(str(receipt.get(key, "")), key)
    if receipt.get("duration_measured"):
        value = receipt.get("elapsed_seconds")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0: raise ValueError("invalid measured duration")
    elif receipt.get("elapsed_seconds") is not None: raise ValueError("unmeasured duration must be null")
    for key in ("files_changed_count", "lines_added", "lines_deleted", "tests_run", "tests_passed", "tests_failed", "tests_skipped", "blockers_found", "blockers_closed"):
        if key in receipt and (isinstance(receipt[key], bool) or not isinstance(receipt[key], int) or receipt[key] < 0):
            raise ValueError(f"{key} must be a non-negative integer")
    if receipt["status"] == "BLOCKED":
        if not receipt.get("blocker_reasons") or receipt.get("merged") is not False or receipt.get("completion_credit") is not False:
            raise ValueError("blocked receipt cannot receive completion or merge credit")
    return dict(receipt)


def normalize_codex_task_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    value = validate_task_receipt(receipt)
    value["measurement_status"] = "MEASURED" if value["duration_measured"] else "DELIVERY_MEASURED_DURATION_UNAVAILABLE"
    value["completion_credit"] = False
    return value


def normalize_github_event_receipt(payload: Mapping[str, Any], *, own_workflow_name: str = "AIOS Delivery Validation Receipts V1") -> dict[str, Any] | None:
    _sanitize(payload)
    repo = payload.get("repository", {}).get("full_name")
    if workflow := payload.get("workflow_run"):
        if workflow.get("name") == own_workflow_name: return None
        conclusion = workflow.get("conclusion")
        prs = sorted({int(p["number"]) for p in workflow.get("pull_requests", []) if isinstance(p, Mapping) and isinstance(p.get("number"), int)})
        value = {"schema": GITHUB_SCHEMA, "receipt_type": "WORKFLOW_VALIDATION", "repository": repo,
                "workflow_name": workflow.get("name"), "workflow_run_id": workflow.get("id"), "workflow_event": workflow.get("event"),
                "workflow_status": workflow.get("status"), "workflow_conclusion": conclusion, "head_sha": workflow.get("head_sha"),
                "head_branch": workflow.get("head_branch"), "associated_pr_numbers": prs, "run_created_at": workflow.get("created_at"),
                "run_started_at": workflow.get("run_started_at"), "run_updated_at": workflow.get("updated_at"),
                "validation_passed": conclusion == "success", "validation_available": conclusion is not None, "provenance": "GITHUB_EVENT_PAYLOAD"}
        for key in ("run_created_at", "run_started_at", "run_updated_at"):
            if value[key] is not None: _, value[key] = _utc(value[key], key)
        return value
    if pr := payload.get("pull_request"):
        value = {"schema": GITHUB_SCHEMA, "receipt_type": "PR_CLOSED", "repository": repo, "pr_number": pr.get("number"),
                "created_at": pr.get("created_at"), "closed_at": pr.get("closed_at"), "merged_at": pr.get("merged_at"),
                "merged": pr.get("merged") is True, "base_branch": pr.get("base", {}).get("ref"), "head_branch": pr.get("head", {}).get("ref"),
                "base_sha": pr.get("base", {}).get("sha"), "head_sha": pr.get("head", {}).get("sha"),
                "commit_count": pr.get("commits"), "provenance": "GITHUB_EVENT_PAYLOAD"}
        for key in ("created_at", "closed_at", "merged_at"):
            if value[key] is not None: _, value[key] = _utc(value[key], key)
        return value
    raise ValueError("unsupported GitHub event payload")


def rebuild_codex_delivery_metadata(receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    values = [normalize_codex_task_receipt(item) for item in receipts]
    return sorted(values, key=lambda x: (x["task_id"], x["packet_id"]))


def merge_codex_delivery_metadata(existing: Sequence[Mapping[str, Any]], receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Preserve historical rows while upserting one normalized instrumentation row."""
    normalized = normalize_codex_task_receipt(receipt)
    identity = (normalized["task_id"], normalized["packet_id"])
    result: list[dict[str, Any]] = []
    replaced = False
    for item in existing:
        value = dict(item)
        item_identity = (value.get("task_id"), value.get("packet_id"))
        if item_identity == identity:
            if stable_json(value) != stable_json(normalized):
                raise ValueError("conflicting canonical Codex delivery metadata")
            replaced = True
        result.append(value)
    if not replaced:
        result.append(normalized)
    return sorted(result, key=lambda value: (str(value.get("task_id", "")), str(value.get("packet_id", "")), stable_json(value)))


def task_receipt_velocity_events(receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Derive only evidence explicitly present in a valid terminal receipt."""
    value = validate_task_receipt(receipt)
    task_id, packet_id = value["task_id"], value["packet_id"]
    common = {"schema": EVENT_SCHEMA, "task_id": task_id, "packet_id": packet_id,
              "lane": value.get("lane"), "branch": value.get("branch"), "provenance": PROVENANCE}
    events: list[dict[str, Any]] = []
    if value.get("started_utc"):
        events.append({**common, "event_id": f"TASK_STARTED|{task_id}|{packet_id}", "event_type": "TASK_STARTED",
                       "timestamp_utc": value["started_utc"]})
    terminal_type = "TASK_COMPLETED" if value["status"] == "COMPLETE" else "TASK_BLOCKED"
    terminal_time = value.get("completed_utc") or value.get("blocked_utc")
    terminal_event = {**common, "event_id": f"{terminal_type}|{task_id}|{packet_id}", "event_type": terminal_type,
                      "timestamp_utc": terminal_time}
    if value.get("elapsed_seconds") is not None: terminal_event["elapsed_seconds"] = value["elapsed_seconds"]
    events.append(terminal_event)
    if value.get("commit_created") is True and value.get("commit_sha"):
        events.append({**common, "event_id": f"COMMIT_CREATED|{task_id}|{packet_id}|{value['commit_sha']}",
                       "event_type": "COMMIT_CREATED", "timestamp_utc": terminal_time, "commit_sha": value["commit_sha"]})
    validation = str(value.get("validation_status") or "").upper()
    if validation in {"PASS", "PASSED", "SUCCESS"}:
        events.append({**common, "event_id": f"VALIDATION_PASSED|{task_id}|{packet_id}", "event_type": "VALIDATION_PASSED", "timestamp_utc": terminal_time})
    elif validation in {"FAIL", "FAILED", "FAILURE"}:
        events.append({**common, "event_id": f"VALIDATION_FAILED|{task_id}|{packet_id}", "event_type": "VALIDATION_FAILED", "timestamp_utc": terminal_time})
    return events


def rebuild_github_pr_delivery_metadata(receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in receipts:
        _sanitize(item)
        key = f"{item.get('receipt_type')}:{item.get('pr_number', item.get('workflow_run_id'))}"
        value = dict(item); old = unique.get(key)
        if old is not None and stable_json(old) != stable_json(value): raise ValueError(f"conflicting GitHub receipt: {key}")
        unique[key] = value
    prs = [v for v in unique.values() if v.get("receipt_type") == "PR_CLOSED"]
    workflows = [v for v in unique.values() if v.get("receipt_type") == "WORKFLOW_VALIDATION"]
    result = []
    for pr in sorted(prs, key=lambda x: int(x["pr_number"])):
        checks = [w for w in workflows if pr["pr_number"] in w.get("associated_pr_numbers", []) and w.get("head_sha") == pr.get("head_sha")]
        validated = any(w.get("validation_passed") is True for w in checks)
        result.append({**pr, "state": "MERGED" if pr.get("merged") else "CLOSED_UNMERGED", "validated": validated,
                       "validation_status": "SUCCESS" if validated else ("FAILED_OR_UNAVAILABLE" if checks else "UNAVAILABLE"),
                       "completion_credit": pr.get("merged") is True and bool(pr.get("head_sha")) and validated})
    return result


def append_velocity_event(path: str | Path, event: Mapping[str, Any]) -> bool:
    _sanitize(event)
    if event.get("schema") != EVENT_SCHEMA or not event.get("event_id"): raise ValueError("invalid velocity event")
    target = Path(path); lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    by_id = {json.loads(line).get("event_id"): json.loads(line) for line in lines if line.strip()}
    event_id = str(event["event_id"])
    if event_id in by_id:
        if stable_json(by_id[event_id]) != stable_json(dict(event)): raise ValueError("conflicting duplicate velocity event")
        return False
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text("\n".join(lines + [json.dumps(event, sort_keys=True, allow_nan=False)]) + "\n", encoding="utf-8")
    return True


def render_owner_report(state: Mapping[str, Any]) -> str:
    return f"""# AIOS Delivery Receipt Instrumentation V1

## Automatic measurement
Governed APPLY tasks record runtime-only starts and COMPLETE or BLOCKED terminal receipts. Duration is calculated only from matching UTC evidence; owner estimates are never substituted.

## Storage and ingestion
Start markers live at `{state['runtime_marker_path']}`. Terminal receipts rebuild `{state['codex_metadata_path']}` and the velocity event log. GitHub emits sanitized downloadable artifacts; artifacts cannot modify this repository and require bounded local ingestion.

## Completion credit and safety
A PR is credited only when merged evidence, a matching head SHA, and a successful validation receipt agree. Identical evidence is deduplicated; conflicts fail closed. First Withdrawable Dollar remains a separate milestone.

Current status: {state['status']}. No network, credential, broker, push, merge, or workflow repository-write authority is enabled.

## Limitations
GitHub artifacts must be downloaded and ingested locally. Missing task starts produce null duration. Missing validation or merge evidence receives no completion credit.
"""
