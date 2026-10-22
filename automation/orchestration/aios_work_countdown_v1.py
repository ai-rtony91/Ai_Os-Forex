"""Deterministic, read-only AIOS engineering work countdown."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from automation.orchestration.aios_candidate_packet_evidence_adapter import (
    build_candidate_packet_evidence,
)
from automation.orchestration.aios_packet_queue_planner import build_packet_queue_planner
from automation.forex_engine.first_withdrawable_dollar_v1 import build_first_withdrawable_dollar

SCHEMA = "AIOS_WORK_COUNTDOWN.v1"
INVENTORY_SCHEMA = "AIOS_CANONICAL_WORK_PACKET_INVENTORY.v1"
MODE = "READ_ONLY"
CALCULATION_SCOPE = "CANONICAL_EXPLICIT_WORK_PACKETS"
FOLDER_STATES = ("active", "blocked", "complete")
COMPLETED = {"merged", "complete", "completed", "done", "closed"}
ACTIVE = {"active", "in_progress", "executing", "selected"}
BLOCKED = {"blocked", "deferred", "hold", "paused", "waiting_approval", "waiting_for_approval"}
READY = {"", "candidate", "open", "pending", "queued", "ready", "proposed", "waiting"}
KNOWN_STATUSES = COMPLETED | ACTIVE | BLOCKED | READY
MARKDOWN_PACKET_ID = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?PACKET[ _-]?ID(?:\*\*)?\s*:\s*`?([^`\s]+)", re.I | re.M)
MARKDOWN_STATUS = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?STATUS(?:\*\*)?\s*:\s*`?([^`\r\n]+)", re.I | re.M)


def _normalized_status(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _protected_actions() -> dict[str, bool]:
    return {key: False for key in (
        "worker_dispatch", "queue_mutation", "scheduler_creation", "daemon_creation",
        "broker_access", "credential_access", "order_placement", "money_movement",
        "git_stage", "git_commit", "git_push", "pr_create", "git_merge",
    )}


def _provider_state() -> dict[str, str]:
    return {
        "provider": "automation/forex_engine/first_withdrawable_dollar_v1.py",
        "provider_status": "EXTERNAL_PENDING_VERIFICATION",
        "verification_source": "GitHub",
        "verification_state": "WAITING_FOR_REMOTE_EVIDENCE",
    }


def _record(path: Path, root: Path, folder_state: str, payload: Mapping[str, Any], source_format: str) -> dict[str, Any]:
    packet_status = _normalized_status(payload.get("status"))
    packet_id = str(payload.get("packet_id") or "").strip()
    return {
        "packet_id": packet_id,
        "title": str(payload.get("title") or packet_id).strip(),
        "status": folder_state,
        "folder_state": folder_state,
        "packet_status": packet_status,
        "source_format": source_format,
        "source_path": path.relative_to(root).as_posix(),
        "priority": payload.get("priority", "normal"),
        "milestone_value": payload.get("milestone_value", 0),
        "risk_level": payload.get("risk_level", "low"),
        "required_files": list(payload.get("required_files") or payload.get("related_files") or []),
        "blocked_files": list(payload.get("blocked_files") or []),
        "required_approvals": list(payload.get("required_approvals") or []),
        "validators": list(payload.get("validators") or ([payload["validator"]] if payload.get("validator") else [])),
        "dependencies": list(payload.get("dependencies") or payload.get("blocked_by") or []),
        "conflicts": list(payload.get("conflicts") or []),
        "safety_flags": list(payload.get("safety_flags") or []),
        "engineering_stage": str(payload.get("engineering_stage") or payload.get("stage") or folder_state).strip(),
    }


def load_canonical_work_packet_inventory(repo_root: str | Path) -> dict[str, Any]:
    """Read canonical packet folders without mutating packet evidence."""
    root = Path(repo_root).resolve()
    packet_root = root / "automation" / "orchestration" / "work_packets"
    records: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    parse_failures: list[dict[str, str]] = []
    missing_ids: list[str] = []
    mismatches: list[dict[str, str]] = []
    scanned: list[dict[str, Any]] = []
    files: list[Path] = []

    for folder_state in FOLDER_STATES:
        folder = packet_root / folder_state
        scanned.append({"folder": folder.relative_to(root).as_posix(), "exists": folder.is_dir()})
        if folder.is_dir():
            files.extend(path for path in folder.iterdir() if path.is_file() and path.name != ".gitkeep")

    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        folder_state = path.parent.name
        relative = path.relative_to(root).as_posix()
        if folder_state not in FOLDER_STATES:
            parse_failures.append({"source_path": relative, "reason": "unknown_source_folder"})
            continue
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("packet JSON must be an object")
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                parse_failures.append({"source_path": relative, "reason": str(exc)})
                continue
            item = _record(path, root, folder_state, payload, "json")
        elif path.suffix.lower() in {".md", ".markdown"}:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                parse_failures.append({"source_path": relative, "reason": str(exc)})
                continue
            id_match = MARKDOWN_PACKET_ID.search(text)
            status_match = MARKDOWN_STATUS.search(text)
            if not id_match:
                excluded.append({"record_identity": relative, "source_path": relative, "reason": "legacy_markdown_missing_explicit_packet_id"})
                missing_ids.append(relative)
                continue
            payload = {
                "packet_id": id_match.group(1).strip(),
                "title": path.stem,
                "status": status_match.group(1).strip() if status_match else "",
            }
            item = _record(path, root, folder_state, payload, "markdown_legacy")
        else:
            excluded.append({"record_identity": relative, "source_path": relative, "reason": "unsupported_reference_format"})
            continue
        records.append(item)
        packet_status = item["packet_status"]
        if packet_status and packet_status != folder_state:
            mismatches.append({
                "packet_id": item["packet_id"], "source_path": relative,
                "folder_state": folder_state, "packet_status": packet_status,
            })

    id_counts = Counter(item["packet_id"] for item in records if item["packet_id"])
    duplicates = sorted(packet_id for packet_id, count in id_counts.items() if count > 1)
    machine_missing_ids = [item["source_path"] for item in records if not item["packet_id"]]
    missing_ids.extend(machine_missing_ids)
    blockers: list[str] = []
    if duplicates:
        blockers.append("duplicate_explicit_packet_ids")
    if parse_failures:
        blockers.append("packet_parse_failures")
    if machine_missing_ids:
        blockers.append("machine_readable_packet_ids_missing")
    warnings = ["folder_status_mismatch" for _ in mismatches]
    warnings.extend("excluded_legacy_record" for _ in excluded)
    if blockers:
        status = "BLOCKED"
    elif not records and not excluded:
        status = "EMPTY"
    elif excluded:
        status = "PARTIAL"
    else:
        status = "AUTHORITATIVE_SCOPED"
    return {
        "schema": INVENTORY_SCHEMA,
        "mode": MODE,
        "inventory_source": packet_root.relative_to(root).as_posix(),
        "inventory_scope": [f"{packet_root.relative_to(root).as_posix()}/{state}" for state in FOLDER_STATES],
        "inventory_status": status,
        "scanned_folders": scanned,
        "files_scanned": len(files),
        "explicit_packet_count": len(records),
        "active_packet_count": sum(item["folder_state"] == "active" for item in records),
        "blocked_packet_count": sum(item["folder_state"] == "blocked" for item in records),
        "complete_packet_count": sum(item["folder_state"] == "complete" for item in records),
        "records": records,
        "excluded_legacy_records": excluded,
        "duplicate_packet_ids": duplicates,
        "parse_failures": parse_failures,
        "missing_packet_ids": sorted(set(missing_ids)),
        "folder_status_mismatches": mismatches,
        "data_quality_warnings": warnings,
        "data_quality_blockers": blockers,
        "source_files_modified": False,
    }


def _explicit_inventory(evidence: Any) -> dict[str, Any] | None:
    if isinstance(evidence, Mapping) and evidence.get("schema") == INVENTORY_SCHEMA:
        return dict(evidence)
    return None


def _legacy_packets(evidence: Any) -> tuple[list[dict[str, Any]], bool]:
    if isinstance(evidence, list):
        return [dict(item) for item in evidence if isinstance(item, Mapping)], False
    if not isinstance(evidence, Mapping):
        return [], False
    authoritative = evidence.get("authoritative_packet_inventory") is True
    for key in ("packets", "candidate_packets", "candidates"):
        if isinstance(evidence.get(key), list):
            return [dict(item) for item in evidence[key] if isinstance(item, Mapping)], authoritative
    return [], authoritative


def _task(packet: Mapping[str, Any]) -> dict[str, Any]:
    return {"packet_id": str(packet.get("packet_id") or ""), "title": str(packet.get("title") or ""), "status": _normalized_status(packet.get("status"))}


def build_work_countdown(
    candidate_packet_evidence: Any = None,
    *, repo_root: str | Path | None = None,
    repository_state: Mapping[str, Any] | None = None,
    validator_state: Mapping[str, Any] | None = None,
    pr_state: Mapping[str, Any] | None = None,
    campaign_registry_context: Mapping[str, Any] | None = None,
    first_withdrawable_dollar_state: Mapping[str, Any] | None = None,
    engineering_velocity_forecast: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    inventory = _explicit_inventory(candidate_packet_evidence)
    if inventory is None and candidate_packet_evidence is None and repo_root is not None:
        inventory = load_canonical_work_packet_inventory(repo_root)

    if inventory is not None:
        packets = [dict(item) for item in inventory.get("records", []) if isinstance(item, Mapping)]
        authoritative = inventory.get("inventory_status") in {"AUTHORITATIVE_SCOPED", "PARTIAL"}
        inventory_status = str(inventory.get("inventory_status") or "BLOCKED")
    else:
        packets, authoritative = _legacy_packets(candidate_packet_evidence)
        inventory_status = "EXPLICIT_TEST_EVIDENCE" if authoritative else "UNSUPPLIED"

    ids = [str(item.get("packet_id") or "").strip() for item in packets]
    duplicates = sorted(set((inventory or {}).get("duplicate_packet_ids", [])) | {value for value, count in Counter(ids).items() if value and count > 1})
    invalid = [item for item in packets if not str(item.get("packet_id") or "").strip() or _normalized_status(item.get("status")) not in KNOWN_STATUSES]
    completed = sorted((_task(item) for item in packets if _normalized_status(item.get("status")) in COMPLETED), key=lambda item: item["packet_id"])
    active = sorted((_task(item) for item in packets if _normalized_status(item.get("status")) in ACTIVE), key=lambda item: item["packet_id"])
    blocked = sorted((_task(item) for item in packets if _normalized_status(item.get("status")) in BLOCKED), key=lambda item: item["packet_id"])
    ready = [item for item in packets if _normalized_status(item.get("status")) in READY]
    normalized = build_candidate_packet_evidence({"packets": ready, "disable_default_candidate": True})
    queue_plan = build_packet_queue_planner(normalized)

    inventory_blocked = inventory_status == "BLOCKED"
    data_quality = "BLOCKED" if inventory_blocked or duplicates or invalid else ("VALID" if authoritative and packets else "INCOMPLETE")
    evidence_status = "COMPLETE" if authoritative and packets else "INCOMPLETE"
    total = len(set(ids)) if data_quality == "VALID" else None
    completed_count = len(completed) if total is not None else None
    remaining = total - completed_count if total is not None else None
    percentage = round(completed_count * 100.0 / total, 2) if total else None
    selected = queue_plan.get("selected_packet")
    if data_quality == "BLOCKED":
        next_task: Any = "REPAIR_CANONICAL_PACKET_INVENTORY" if inventory is not None else "REPAIR_INVALID_PACKET_EVIDENCE"
    elif inventory_status == "EMPTY":
        next_task = "CREATE_OR_REGISTER_CANONICAL_WORK_PACKET"
    elif not authoritative:
        next_task = "SUPPLY_CANONICAL_PACKET_INVENTORY"
    else:
        next_task = _task(selected) if isinstance(selected, Mapping) else None

    provider = _provider_state()
    fwd_state = build_first_withdrawable_dollar(first_withdrawable_dollar_state) if first_withdrawable_dollar_state is not None else dict(provider)
    next_blocker = fwd_state.get("next_verified_blocker") or fwd_state.get("blocker") or "FIRST_WITHDRAWABLE_DOLLAR_PROVIDER_PENDING_VERIFICATION"
    dependency_graph = {
        "canonical_work_packet_inventory": "AUTHORITY",
        "work_packets_active": "AUTHORITY",
        "work_packets_blocked": "AUTHORITY",
        "work_packets_complete": "AUTHORITY",
        "unified_queue_index_projection": "READ_ONLY_PROJECTION",
        "campaign_registry_planning_context": "PLANNING_CONTEXT",
        "work_countdown_output": "READ_ONLY_PROJECTION",
        "first_withdrawable_dollar_external_provider": "EVIDENCE_PROJECTION" if first_withdrawable_dollar_state is not None else "EXTERNAL_PENDING",
    }
    limitation = None
    if inventory_status == "PARTIAL":
        limitation = "Scoped percentage covers explicit canonical packet IDs only; it is not whole-repository completion."
    elif data_quality != "VALID":
        limitation = "No safe canonical packet denominator is available."
    stages = sorted({str(item.get("engineering_stage") or "UNCLASSIFIED") for item in packets if _normalized_status(item.get("status")) not in COMPLETED}) if total is not None else None
    return {
        "schema": SCHEMA, "mode": MODE, "evidence_status": evidence_status,
        "data_quality_status": data_quality, "inventory_status": inventory_status,
        "calculation_scope": CALCULATION_SCOPE, "evidence_limitation": limitation,
        "canonical_work_packet_inventory": inventory,
        "total_packet_count": total, "completed_packet_count": completed_count,
        "remaining_packet_count": remaining, "completion_percentage": percentage,
        "completed_tasks": completed, "current_task": active[0] if active else None,
        "active_tasks": active, "next_task": next_task, "blocked_tasks": blocked,
        "engineering_stages_remaining": stages,
        "external_wait_state": {"waiting": True, "items": [provider], "excluded_from_engineering_stages": True},
        "dependency_graph": dependency_graph, "queue_plan": queue_plan,
        "repository_state": dict(repository_state or {}), "validator_state": dict(validator_state or {}),
        "pr_state": dict(pr_state or {}), "campaign_registry_planning_context": dict(campaign_registry_context or {}),
        "first_withdrawable_dollar_state": fwd_state, "next_verified_blocker": next_blocker,
        "hours_completed": fwd_state.get("hours_completed"),
        "hours_remaining_low": fwd_state.get("hours_remaining_low"),
        "hours_remaining_best": fwd_state.get("hours_remaining_best"),
        "hours_remaining_high": fwd_state.get("hours_remaining_high"),
        "weeks_remaining_50h_low": fwd_state.get("weeks_remaining_50h_low"),
        "weeks_remaining_50h_best": fwd_state.get("weeks_remaining_50h_best"),
        "weeks_remaining_50h_high": fwd_state.get("weeks_remaining_50h_high"),
        "derived_completion_percentage": fwd_state.get("derived_completion_percentage"),
        "confidence": fwd_state.get("confidence"), "confidence_basis": fwd_state.get("confidence_basis"),
        "credited_packet_count": fwd_state.get("credited_packet_count"), "uncredited_packet_count": fwd_state.get("uncredited_packet_count"),
        "owner_intervention_required": fwd_state.get("owner_action_required", True),
        "owner_view": {"status": data_quality, "inventory_status": inventory_status, "current_task": active[0] if active else None, "next_task": next_task, "next_verified_blocker": next_blocker},
        "protected_actions": _protected_actions(),
        "engineering_velocity_forecast": dict(engineering_velocity_forecast or {}),
    }


def stable_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root")
    parser.add_argument("--evidence", help="Explicit packet evidence JSON")
    parser.add_argument(
        "--first-withdrawable-dollar-evidence",
        help="Explicit First Withdrawable Dollar execution-receipt evidence JSON",
    )
    parser.add_argument(
        "--first-withdrawable-dollar-evidence-file",
        type=Path,
        help="Path to First Withdrawable Dollar execution-receipt evidence JSON",
    )
    parser.add_argument("--output", help="Optional output JSON path")
    args = parser.parse_args(argv)
    evidence = json.loads(args.evidence) if args.evidence is not None else None
    if (
        args.first_withdrawable_dollar_evidence is not None
        and args.first_withdrawable_dollar_evidence_file is not None
    ):
        parser.error(
            "use only one of --first-withdrawable-dollar-evidence and "
            "--first-withdrawable-dollar-evidence-file"
        )
    if args.first_withdrawable_dollar_evidence_file is not None:
        first_dollar_evidence = json.loads(
            args.first_withdrawable_dollar_evidence_file.read_text(encoding="utf-8")
        )
    elif args.first_withdrawable_dollar_evidence is not None:
        first_dollar_evidence = json.loads(args.first_withdrawable_dollar_evidence)
    else:
        first_dollar_evidence = None
    result = build_work_countdown(
        evidence,
        repo_root=args.repo_root,
        first_withdrawable_dollar_state=first_dollar_evidence,
    )
    rendered = stable_json(result)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
