from __future__ import annotations

import argparse
from copy import deepcopy
import json
from typing import Any


SCHEMA = "AIOS_CANDIDATE_PACKET_EVIDENCE_ADAPTER.v1"

FOREX_MILESTONE = (
    "AIOS self-building machine -> first proof target: industrial-grade forex bot builder "
    "-> no broker/live/secrets until gates prove safety"
)

NOISE_PATH_PREFIXES = (
    "reports/",
    "control/review_bridge/",
    "automation/orchestration/work_packets/preview/",
)

UNSAFE_PATH_TERMS = (
    "broker",
    "live",
    "secret",
    "credential",
    "order",
    "webhook",
)

DEFAULT_VALIDATOR = (
    "python -m pytest -p no:cacheprovider "
    "tests/orchestration/test_aios_persistent_runtime_supervisor.py "
    "tests/orchestration/test_aios_packet_queue_planner.py "
    "tests/orchestration/test_aios_cycle_ledger.py "
    "tests/orchestration/test_aios_candidate_packet_evidence_adapter.py -q"
)


def _safety() -> dict[str, bool]:
    return {
        "preview_only": True,
        "evidence_only": True,
        "command_execution": False,
        "filesystem_writes": False,
        "reports_written": False,
        "network_access": False,
        "worker_dispatch": False,
        "queue_mutation": False,
        "approval_mutation": False,
        "scheduler_activation": False,
        "daemon_activation": False,
        "broker": False,
        "live_trading": False,
        "credentials": False,
        "real_orders": False,
        "real_webhooks": False,
        "git_add": False,
        "git_commit": False,
        "git_push": False,
        "git_merge": False,
    }


def _as_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [part.strip() for part in value.replace("\r", "\n").replace(",", "\n").splitlines() if part.strip()]
    if value in (None, "", {}, []):
        return []
    return [value]


def _as_text_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_items(value) if str(item).strip()]


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _normalized_path(value: Any) -> str:
    normalized = _text(value).replace("\\", "/").strip().lower()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _path_from_record(record: dict[str, Any]) -> str:
    for key in ("path", "source_path", "preview_path", "file", "file_path"):
        value = _text(record.get(key))
        if value:
            return value
    return ""


def _is_generated_backlog_path(path: str) -> bool:
    normalized = _normalized_path(path)
    return any(normalized.startswith(prefix) for prefix in NOISE_PATH_PREFIXES)


def _is_promoted(record: dict[str, Any]) -> bool:
    for key in ("promoted", "promote", "promote_to_candidate", "candidate_promoted", "explicitly_promoted"):
        if record.get(key) is True:
            return True
        if isinstance(record.get(key), str) and record[key].strip().lower() in {"true", "yes", "promoted"}:
            return True
    return False


def _alignment(safety_flags: list[str] | None = None) -> dict[str, Any]:
    flags = safety_flags or []
    blocked = sorted(
        {
            term
            for term in UNSAFE_PATH_TERMS
            if any(term in flag.lower() for flag in flags)
        }
    )
    return {
        "milestone": FOREX_MILESTONE,
        "proof_target": "industrial-grade forex bot builder",
        "control_plane_role": "candidate packet evidence normalization",
        "aligned": not blocked,
        "blocked_boundaries": blocked,
        "requires_future_gates_before_execution": True,
    }


def _unsafe_path_flags(record: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    paths.extend(_as_text_list(record.get("required_files")))
    paths.extend(_as_text_list(record.get("blocked_files")))
    path = _path_from_record(record)
    if path:
        paths.append(path)

    flags: list[str] = []
    for path_item in paths:
        normalized = _normalized_path(path_item)
        for term in UNSAFE_PATH_TERMS:
            if term in normalized:
                flag = f"unsafe_path:{term}:{path_item}"
                if flag not in flags:
                    flags.append(flag)
    return flags


def _candidate_id(record: dict[str, Any], index: int) -> str:
    packet_id = _text(record.get("packet_id") or record.get("id"))
    if packet_id:
        return packet_id
    title = _text(record.get("title"))
    if title:
        return "PKT-" + "".join(ch if ch.isalnum() else "-" for ch in title.upper()).strip("-")
    return f"PKT-AIOS-CANDIDATE-{index + 1}"


def _normalized_candidate(record: dict[str, Any], index: int) -> dict[str, Any]:
    existing_flags = _as_text_list(record.get("safety_flags"))
    safety_flags = [*existing_flags, *_unsafe_path_flags(record)]
    seen_flags: list[str] = []
    for flag in safety_flags:
        if flag not in seen_flags:
            seen_flags.append(flag)

    return {
        "packet_id": _candidate_id(record, index),
        "title": _text(record.get("title"), "Untitled AIOS candidate packet"),
        "lane": _text(record.get("lane"), "candidate-packet-evidence"),
        "priority": record.get("priority", "medium"),
        "milestone_value": record.get("milestone_value", "medium"),
        "risk_level": _text(record.get("risk_level"), "low"),
        "status": _text(record.get("status"), "candidate"),
        "required_files": _as_text_list(record.get("required_files")),
        "blocked_files": _as_text_list(record.get("blocked_files")),
        "required_approvals": _as_text_list(record.get("required_approvals")),
        "validators": _as_text_list(record.get("validators")),
        "repository_state": deepcopy(record.get("repository_state")),
        "dependencies": _as_items(record.get("dependencies")),
        "conflicts": _as_text_list(record.get("conflicts")),
        "safety_flags": seen_flags,
        "forex_builder_alignment": _alignment(seen_flags),
    }


def _default_candidate() -> dict[str, Any]:
    return {
        "packet_id": "PKT-AIOS-SELFROUTE-CANDIDATE-EVIDENCE-INTEGRATION",
        "title": "Connect candidate packet evidence adapter into self-route",
        "lane": "connect-candidate-evidence-to-selfroute",
        "priority": "high",
        "milestone_value": "high",
        "risk_level": "low",
        "status": "candidate",
        "required_files": [
            "automation/orchestration/runtime/Invoke-AiOsRuntimeSelfRoute.ps1",
            "tests/orchestration/test_aios_persistent_runtime_supervisor.py",
        ],
        "blocked_files": [],
        "required_approvals": [],
        "validators": [DEFAULT_VALIDATOR],
        "dependencies": [],
        "conflicts": [],
        "safety_flags": [],
        "forex_builder_alignment": _alignment([]),
    }


def _goal_requires_self_build(evidence: Any) -> bool:
    if evidence in (None, "", [], {}):
        return True
    text = json.dumps(evidence, sort_keys=True).lower() if isinstance(evidence, (dict, list)) else str(evidence).lower()
    if "disable_default_candidate" in text:
        return False
    return any(term in text for term in ("aios", "self-build", "self building", "self-building", "forex"))


def _record_from_path(path: str, source_type: str) -> dict[str, Any]:
    return {
        "path": path,
        "source_type": source_type,
    }


def _raw_records(evidence: Any) -> list[dict[str, Any]]:
    if isinstance(evidence, list):
        return [item for item in evidence if isinstance(item, dict)]
    if not isinstance(evidence, dict):
        return []

    records: list[dict[str, Any]] = []
    for key in (
        "candidates",
        "candidate_packets",
        "manual_candidates",
        "manual_candidate_specs",
        "proposed_packets",
        "proposed_packet_records",
        "packets",
        "records",
    ):
        for item in _as_items(evidence.get(key)):
            if isinstance(item, dict):
                records.append(item)

    for item in _as_items(evidence.get("work_packet_preview_paths")):
        records.append(_record_from_path(str(item), "work_packet_preview_path"))
    for item in _as_items(evidence.get("work_packet_previews")):
        if isinstance(item, dict):
            records.append(item)
        else:
            records.append(_record_from_path(str(item), "work_packet_preview_path"))

    repo_status = evidence.get("repo_status")
    if isinstance(repo_status, dict):
        for item in _as_items(repo_status.get("untracked_paths")):
            records.append(_record_from_path(str(item), "repo_status_untracked_path"))

    if not records and any(key in evidence for key in ("packet_id", "title", "path", "source_path")):
        records.append(evidence)

    return records


def _archive_noise(path: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": path,
        "classification": "archive_noise",
        "reason": "generated_backlog_path_not_promoted",
        "promoted": _is_promoted(record),
    }


def build_candidate_packet_evidence(raw_evidence: Any | None = None) -> dict[str, Any]:
    records = _raw_records(raw_evidence)
    candidates: list[dict[str, Any]] = []
    archive_noise: list[dict[str, Any]] = []

    for index, record in enumerate(records):
        path = _path_from_record(record)
        generated_noise = bool(path and _is_generated_backlog_path(path))
        promoted = _is_promoted(record)
        candidate_like = promoted or bool(record.get("packet_id") or record.get("title") or record.get("required_files"))

        if generated_noise and not promoted:
            archive_noise.append(_archive_noise(path, record))
            continue
        if not candidate_like:
            if path:
                archive_noise.append(
                    {
                        "path": path,
                        "classification": "reference_noise",
                        "reason": "path_only_record_not_promoted",
                        "promoted": promoted,
                    }
                )
            continue
        candidates.append(_normalized_candidate(record, index))

    if not candidates and _goal_requires_self_build(raw_evidence):
        candidates.append(_default_candidate())

    return {
        "schema": SCHEMA,
        "candidate_packets": candidates,
        "candidates": candidates,
        "archive_noise": archive_noise,
        "default_candidate_used": bool(candidates and candidates[0]["packet_id"] == _default_candidate()["packet_id"]),
        "today_goal_alignment": _alignment([]),
        "commands_executed": [],
        "files_written": [],
        "workers_dispatched": False,
        "queues_mutated": False,
        "approvals_mutated": False,
        "safety": _safety(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize AIOS candidate packet evidence.")
    parser.add_argument("--evidence", default="{}", help="JSON candidate evidence.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        evidence = json.loads(args.evidence)
    except json.JSONDecodeError:
        evidence = {}
    result = build_candidate_packet_evidence(evidence)
    print(json.dumps(result, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
