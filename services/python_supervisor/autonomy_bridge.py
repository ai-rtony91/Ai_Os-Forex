"""AI_OS Autonomy Bridge v1.

Connects local Relay evidence, Night Supervisor evidence, Morning Digest output,
and dashboard-readable state. This module is local-only, standard-library-only,
and evidence-only. It does not run shell commands, call the network, mutate Git,
read secrets, touch broker systems, or approve protected actions.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "AIOS_AUTONOMY_BRIDGE_STATE.v1"
OUTPUTS = {
    "bridge_state": Path("telemetry/night_supervisor/AUTONOMY_BRIDGE_STATE.json"),
    "morning_state": Path("telemetry/morning_digest/MORNING_DIGEST_STATE.json"),
    "morning_digest": Path("telemetry/morning_digest/MORNING_DIGEST_LATEST.md"),
}
BLOCKED_CAPABILITIES = [
    "live_trading",
    "broker_execution",
    "oanda_integration",
    "api_key_handling",
    "real_webhook_execution",
    "real_order_routing",
    "secret_handling",
    "worker_launch",
    "packet_mutation",
    "approval_mutation",
    "git_stage_commit_push",
]
FORBIDDEN_PATH_TERMS = (
    ".env",
    "secrets/",
    "credentials/",
    "private key",
    "broker",
    "oanda",
    "live webhook",
    "real order",
)
STATUS_ORDER = {"BLOCKED": 4, "NEEDS_APPROVAL": 3, "WARN": 2, "UNKNOWN": 1, "PASS": 0}
EXPLICIT_STATUS_MAP = {
    "BLOCKED": "BLOCKED",
    "UNSAFE_BLOCKED": "BLOCKED",
    "FAILED": "BLOCKED",
    "FAIL": "BLOCKED",
    "ERROR": "BLOCKED",
    "NEEDS_APPROVAL": "NEEDS_APPROVAL",
    "WAITING_APPROVAL": "NEEDS_APPROVAL",
    "WAITING_REVIEW": "NEEDS_APPROVAL",
    "APPROVAL_REQUIRED": "NEEDS_APPROVAL",
    "PENDING_APPROVAL": "NEEDS_APPROVAL",
    "WAITING": "NEEDS_APPROVAL",
    "WARN": "WARN",
    "WARNING": "WARN",
    "REVIEW": "WARN",
    "STALE": "WARN",
    "UNKNOWN": "UNKNOWN",
    "PASS": "PASS",
    "READY": "PASS",
    "COMPLETE": "PASS",
    "DONE": "PASS",
    "READY_FOR_NEXT_SAFE_ACTION": "PASS",
}
RISK_STATUS_MAP = {
    "BLOCKED": "BLOCKED",
    "BLOCKER": "BLOCKED",
    "HIGH": "NEEDS_APPROVAL",
    "MEDIUM": "NEEDS_APPROVAL",
    "LOW": "WARN",
}
BLOCKER_FALLBACK_TERMS = (
    "risk level: blocker",
    "risk level:** blocker",
    "live now",
    "real order",
    "buy order",
    "sell order",
    "place a buy",
    "place a sell",
    "broker execution",
    "live trading",
    "oanda",
    "api key",
    "secret",
    "credential",
    "webhook",
    "scheduler",
    "scheduled task",
    "schtasks",
    "protected action",
    "git add .",
    "force push",
    "reset --hard",
    "git clean",
)
APPROVAL_FALLBACK_TERMS = (
    "approval required",
    "needs approval",
    "waiting approval",
    "waiting_approval",
    "approval_required",
    "human approval",
    "human_review_required",
)
WARN_FALLBACK_TERMS = ("warn", "review", "stale", "unknown")
REFERENCE_PATH_TERMS = (
    "/archive/",
    "/examples/",
    "/templates/",
    "/example.",
    "example.",
    ".example.",
    ".sample.",
    ".schema.json",
)
STATIC_REFERENCE_PATHS = {
    "automation/orchestration/night_supervisor/night_supervisor_config.json",
    "automation/orchestration/night_supervisor/night_supervisor_report.schema.json",
    "automation/orchestration/night_supervisor/night_supervisor_safety_policy.json",
    "automation/orchestration/night_supervisor/readme.md",
    "relay/readme.md",
    "relay/handoffs/codex_bridge_loop_sequence.md",
}
PROJECTION_PATHS = {
    "relay/reports/alert_latest.md",
    "telemetry/morning_digest/morning_digest_latest.md",
    "telemetry/morning_digest/morning_digest_state.json",
    "telemetry/night_supervisor/autonomy_bridge_state.json",
}
HISTORICAL_PATH_TERMS = (
    "relay/approvals/approved/",
    "relay/done/",
    "relay/goals/processed/",
    "relay/handoffs/processed/",
    "relay/logs/",
    "relay/outbox/",
    "relay/reports/",
)
STALE_REVIEW_PATH_TERMS = (
    "relay/approvals/",
    "control/operation_glue/worker_packets/",
)
EVIDENCE_DATE_PATTERN = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")
ACTIVE_CLASSIFICATIONS = {
    "active_current",
    "active_approval_required",
    "active_blocker",
}
SAMPLE_OR_EXAMPLE_TERMS = (
    "sample",
    "example",
    ".example.",
    "_example",
    "sample_resume_proof",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_json_safely(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except FileNotFoundError:
        return {"source_path": str(path), "status": "UNKNOWN", "error": "File missing."}
    except json.JSONDecodeError as exc:
        return {"source_path": str(path), "status": "BLOCKED", "error": f"JSON parse failed: {exc}"}
    except OSError as exc:
        return {"source_path": str(path), "status": "UNKNOWN", "error": str(exc)}
    if isinstance(payload, dict):
        payload.setdefault("source_path", str(path))
        return payload
    return {"source_path": str(path), "status": "BLOCKED", "error": "JSON root is not an object."}


def load_latest_night_report(repo_root: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    report_dir = Path(repo_root).resolve() / "telemetry/night_supervisor/reports"
    if not report_dir.exists():
        return None, None
    reports = sorted(report_dir.glob("night_summary_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not reports:
        return None, None
    latest = reports[0]
    return load_json_safely(latest), repo_relative(latest, Path(repo_root).resolve())


def read_text_preview(path: Path, limit: int = 900) -> str:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""
    return " ".join(text.split())[:limit]


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def _iter_explicit_values(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "status",
        "state",
        "supervisor_status",
        "night_supervisor_status",
        "classification",
        "result",
    ):
        if item.get(key) is not None:
            values.append(_normalize_token(item.get(key)))
    for key in ("risk_level", "risk"):
        if item.get(key) is not None:
            values.append(_normalize_token(item.get(key)))
    for key in ("gate_flags", "flags"):
        raw_flags = item.get(key)
        if isinstance(raw_flags, list):
            values.extend(_normalize_token(flag) for flag in raw_flags)
        elif raw_flags is not None:
            values.append(_normalize_token(raw_flags))
    return values


def _status_category(status: str, path: str, text: str) -> str:
    if status == "BLOCKED":
        return "noise"
    if status == "NEEDS_APPROVAL":
        return "noise"
    if status == "WARN":
        return "noise"
    if status == "PASS":
        return "completed_record"
    if path.startswith("relay/"):
        return "historical_evidence"
    return "noise"


def _extract_evidence_dates(path: str, text: str) -> list[datetime.date]:
    dates: list[datetime.date] = []
    for raw_year, raw_month, raw_day in EVIDENCE_DATE_PATTERN.findall(f"{path} {text}"):
        try:
            dates.append(datetime(int(raw_year), int(raw_month), int(raw_day), tzinfo=timezone.utc).date())
        except ValueError:
            continue
    return dates


def _contains_stale_evidence_date(path: str, text: str) -> bool:
    today = datetime.now(timezone.utc).date()
    return any(evidence_date < today for evidence_date in _extract_evidence_dates(path, text))


def _is_reference_evidence(path: str) -> bool:
    return path in STATIC_REFERENCE_PATHS or any(term in path for term in REFERENCE_PATH_TERMS)


def _is_projection_evidence(path: str) -> bool:
    return path in PROJECTION_PATHS


def _is_sample_or_example(path: str, text: str) -> bool:
    haystack = f"{path} {text}"
    return any(term in haystack for term in SAMPLE_OR_EXAMPLE_TERMS)


def _has_current_unsafe_terms(path: str, text: str) -> bool:
    return "/error/" in path or any(term in text for term in BLOCKER_FALLBACK_TERMS)


def _is_historical_evidence(path: str, text: str) -> bool:
    if path.startswith("relay/approvals/"):
        if _contains_stale_evidence_date(path, text):
            return True
        if path.startswith("relay/approvals/g-"):
            return True
        return not _has_current_unsafe_terms(path, text)
    if any(term in path for term in HISTORICAL_PATH_TERMS):
        return True
    if any(term in path for term in STALE_REVIEW_PATH_TERMS):
        return _contains_stale_evidence_date(path, text)
    return False


def _max_status(*statuses: str) -> str:
    known = [status for status in statuses if status in STATUS_ORDER]
    if not known:
        return "UNKNOWN"
    return max(known, key=lambda status: STATUS_ORDER[status])


def _explicit_status(item: dict[str, Any]) -> str | None:
    status: str | None = None
    for value in _iter_explicit_values(item):
        if value in EXPLICIT_STATUS_MAP:
            status = _max_status(status or "PASS", EXPLICIT_STATUS_MAP[value])
        if value in RISK_STATUS_MAP:
            status = _max_status(status or "PASS", RISK_STATUS_MAP[value])
        if "APPROVAL" in value or "HUMAN_REVIEW" in value:
            status = _max_status(status or "PASS", "NEEDS_APPROVAL")
        if any(term in value for term in ("BLOCK", "UNSAFE", "PROTECTED_ACTION")):
            status = _max_status(status or "PASS", "BLOCKED")
    return status


def _fallback_status(path: str, text: str, raw_status: str) -> str:
    if "/error/" in path or any(term in text for term in BLOCKER_FALLBACK_TERMS):
        return "BLOCKED"
    if "approval" in path or any(term in text for term in APPROVAL_FALLBACK_TERMS):
        return "NEEDS_APPROVAL"
    if raw_status in {"PASS", "READY", "COMPLETE", "DONE"} or any(term in path for term in ("/done/", "/processed/")):
        return "PASS"
    if any(term in text for term in WARN_FALLBACK_TERMS):
        return "NEEDS_APPROVAL"
    return "NEEDS_APPROVAL"


def classify_item(item: dict[str, Any]) -> dict[str, str]:
    text = " ".join(str(value) for value in item.values()).lower()
    path = str(item.get("source_path", "")).lower().replace("\\", "/")
    raw_status = str(item.get("status") or item.get("state") or item.get("supervisor_status") or "").upper()

    if _is_sample_or_example(path, text):
        return {"status": "WARN", "category": "reference_evidence"}
    if _is_projection_evidence(path):
        return {"status": "WARN", "category": "reference_evidence"}
    if _is_reference_evidence(path):
        return {"status": "WARN", "category": "reference_evidence"}
    if _is_historical_evidence(path, text):
        return {"status": "WARN", "category": "historical_evidence"}

    explicit = _explicit_status(item)
    fallback = _fallback_status(path, text, _normalize_token(raw_status))
    status = _max_status(explicit or "PASS", fallback)
    category = _status_category(status, path, text)

    if "morning" in path:
        category = "noise"
    if "validator" in path:
        category = "noise"

    return {"status": status, "category": category}


def _item_from_path(path: Path, repo_root: Path) -> dict[str, Any]:
    rel = repo_relative(path, repo_root)
    payload = load_json_safely(path) if path.suffix.lower() == ".json" else {}
    text = json.dumps(payload, sort_keys=True) if payload else read_text_preview(path)
    classification = classify_item({"source_path": rel, "status": payload.get("status", ""), "text": text})
    title = path.stem.replace("_", " ").replace("-", " ").strip().title() or rel
    summary = payload.get("summary") or payload.get("plain_summary") or payload.get("next_safe_action") or text
    if not summary:
        summary = "Evidence found, but no readable summary was available."
    return {
        "title": str(title)[:90],
        "status": classification["status"],
        "category": classification["category"],
        "status_impact": classification["category"] in ACTIVE_CLASSIFICATIONS,
        "summary": str(summary)[:220],
        "source_path": rel,
        "next_safe_action": str(payload.get("next_safe_action") or "Review this evidence before protected action."),
    }


def _glue_approval_card_from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    source_path = str(item.get("source_path") or "")
    if not source_path.startswith("control/operation_glue/"):
        return None
    if item.get("status") not in {"NEEDS_APPROVAL", "BLOCKED"}:
        return None
    recommended_action = str(item.get("next_safe_action") or "Review Glue approval before execution.")
    title = str(item.get("title") or "Operation Glue Approval")
    return {
        "title": title,
        "file": source_path,
        "packet_id": str(item.get("id") or source_path or "UNKNOWN"),
        "requested_action": title,
        "status": str(item.get("status") or "NEEDS_APPROVAL"),
        "risk": str(item.get("risk_level") or "UNKNOWN"),
        "classification": "active_approval_required",
        "why_it_matters": "Human review is required before mutation or protected action.",
        "recommended_action": recommended_action,
        "source_path": source_path,
    }


def collect_source_files(repo_root: str | Path) -> list[Path]:
    root = Path(repo_root).resolve()
    candidates: list[Path] = []
    patterns = [
        ("relay", "**/*"),
        ("telemetry/night_supervisor", "**/*.json"),
        ("telemetry/supervisor_briefs", "*.json"),
        ("telemetry/morning_digest", "*.json"),
        ("control/operation_glue", "**/*.json"),
        ("telemetry/operation_glue", "**/*.json"),
        ("automation/orchestration/night_supervisor", "*.json"),
        ("automation/orchestration/night_supervisor", "*.md"),
    ]
    for folder, pattern in patterns:
        base = root / folder
        if not base.exists():
            continue
        for path in sorted(base.glob(pattern)):
            if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".md", ".txt"}:
                candidates.append(path)
    return sorted(dict.fromkeys(candidates), key=lambda value: repo_relative(value, root))


def build_repo_state(branch: str = "UNKNOWN", git_status: str = "") -> dict[str, Any]:
    changed: list[str] = []
    untracked: list[str] = []
    for raw_line in git_status.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("## "):
            continue
        path = line[3:].strip() if len(line) > 3 else line
        if line.startswith("?? "):
            untracked.append(path)
        else:
            changed.append(path)
    repo_dirty = bool(changed or untracked)
    return {
        "branch": branch or "UNKNOWN",
        "repo_dirty": repo_dirty,
        "changed_files": changed,
        "untracked_files": untracked,
        "status_summary": "Repo has local changed or untracked files." if repo_dirty else "Repo tree is clean.",
    }


def _legacy_dashboard_status(status: str) -> str:
    return {
        "READY": "PASS",
        "NEEDS_APPROVAL": "WARN",
        "BLOCKED": "BLOCKED",
    }.get(status, "UNKNOWN")


def _report_phase(report: dict[str, Any], phase_name: str) -> dict[str, Any] | None:
    for phase in report.get("phases") or []:
        if isinstance(phase, dict) and phase.get("phase") == phase_name:
            return phase
    return None


def _canonical_approval_cards(repo_root: Path, report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    phase = _report_phase(report, "approval_automation") or {}
    pending = ((phase.get("detail") or {}).get("pending_human_review") or [])
    active_cards: list[dict[str, Any]] = []
    noise_cards: list[dict[str, Any]] = []

    for raw in pending:
        if not isinstance(raw, dict):
            continue
        file_path = str(raw.get("file") or "")
        tier = str(raw.get("tier") or "UNKNOWN")
        name = Path(file_path).name
        record = load_json_safely(repo_root / "automation/orchestration/approval_inbox" / name)
        status = str(record.get("approval_status") or record.get("status") or "pending_or_unknown")
        card = {
            "title": name or "Approval Decision",
            "file": file_path,
            "packet_id": str(record.get("packet_id") or report.get("execution_result", {}).get("packet_id") or "UNKNOWN"),
            "requested_action": str(record.get("requested_action") or record.get("requested_mode") or "review approval evidence"),
            "status": status,
            "risk": str(record.get("risk_level") or tier),
            "classification": "ACTIVE_APPROVAL_REQUIRED",
            "why_it_matters": "Human review is required before mutation or protected action.",
            "recommended_action": "Approve, reject, or defer from the canonical approval inbox.",
            "source_path": file_path,
        }
        lowered = f"{name} {tier} {status}".lower()
        if "example" in lowered:
            card["classification"] = "SAMPLE_OR_EXAMPLE"
            card["why_it_matters"] = "Example approval records are not active decision work."
            card["recommended_action"] = "Keep visible as noise/detail only."
            noise_cards.append(card)
        elif status.lower() == "completed":
            card["classification"] = "COMPLETED_RECORD"
            card["why_it_matters"] = "Completed approval records are historical evidence."
            card["recommended_action"] = "Keep visible as completed evidence only."
            noise_cards.append(card)
        else:
            active_cards.append(card)

    return active_cards, noise_cards


def _active_current_from_report(report: dict[str, Any], report_path: str | None) -> dict[str, Any]:
    execution = report.get("execution_result") or {}
    safety = report.get("safety_confirmation") or {}
    return {
        "title": "Latest Night Supervisor Report",
        "status": str(report.get("supervisor_status") or "UNKNOWN"),
        "category": "ACTIVE_CURRENT",
        "status_impact": True,
        "summary": str(report.get("next_safe_action") or execution.get("next_safe_action") or "Review latest Night Supervisor report."),
        "source_path": report_path or str(report.get("source_path") or "telemetry/night_supervisor/reports"),
        "validator_status": str(execution.get("validator_status") or "UNKNOWN"),
        "qa_status": str(execution.get("qa_status") or "UNKNOWN"),
        "execution_result": str(execution.get("result_classification") or "UNKNOWN"),
        "forbidden_write_attempts": int(safety.get("forbidden_write_attempts") or 0),
    }


def _current_blockers_from_report(report: dict[str, Any], report_path: str | None) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    execution = report.get("execution_result") or {}
    safety = report.get("safety_confirmation") or {}
    report_status = _normalize_token(report.get("supervisor_status"))
    validator_status = _normalize_token(execution.get("validator_status"))
    qa_status = _normalize_token(execution.get("qa_status"))

    def add_blocker(title: str, summary: str) -> None:
        blockers.append(
            {
                "title": title,
                "status": "BLOCKED",
                "category": "ACTIVE_BLOCKER",
                "status_impact": True,
                "summary": summary,
                "source_path": report_path or "latest_night_report",
                "next_safe_action": "Stop and resolve this current blocker before continuation.",
            }
        )

    if report_status in {"BLOCKED", "FAILED", "FAIL", "ERROR", "UNSAFE_BLOCKED"}:
        add_blocker("Night Supervisor current status blocker", f"Latest Night Supervisor status is {report_status}.")
    if validator_status not in {"PASS", "READY", "COMPLETE", "DONE"}:
        add_blocker("Validator current blocker", f"Latest validator status is {validator_status or 'UNKNOWN'}.")
    if qa_status not in {"PASS", "READY", "COMPLETE", "DONE"}:
        add_blocker("QA current blocker", f"Latest QA status is {qa_status or 'UNKNOWN'}.")
    if int(safety.get("forbidden_write_attempts") or 0) > 0:
        add_blocker("Forbidden write current blocker", "Latest report recorded forbidden write attempts.")
    return blockers


def _stale_state_warnings(
    latest_report: dict[str, Any] | None,
    latest_report_path: str | None,
    previous_bridge_status: str | None,
    previous_bridge_generated_at: str | None,
) -> list[str]:
    warnings: list[str] = []
    if latest_report:
        report_status = str(latest_report.get("supervisor_status") or "UNKNOWN")
        if previous_bridge_status and previous_bridge_status != report_status:
            warnings.append(f"Prior bridge status was {previous_bridge_status} while latest report is {report_status}.")
        if previous_bridge_generated_at and str(previous_bridge_generated_at)[:10] != str(latest_report.get("generated_at") or "")[:10]:
            warnings.append("Prior bridge state date does not match the latest Night Supervisor report date.")
    else:
        warnings.append("No latest Night Supervisor report found; bridge status cannot be fully anchored.")
    if latest_report_path:
        warnings.append(f"Status anchored to {latest_report_path}.")
    return warnings


def build_dashboard_cards(bridge_state: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = {
        "wins": bridge_state["wins_count"],
        "blocked": bridge_state["blocked_count"],
        "approval_needed": bridge_state["approval_needed_count"],
        "worker_notes": bridge_state["worker_notes_count"],
    }
    return [
        {
            "title": "Night Supervisor Brief",
            "status": bridge_state["night_supervisor_status"],
            "summary": bridge_state["plain_summary"],
            "metrics": metrics,
            "next_action": bridge_state["next_safe_action"],
            "details_ref": bridge_state["morning_digest_path"],
        }
    ]


def build_bridge_state(repo_root: str | Path, branch: str = "UNKNOWN", git_status: str = "") -> dict[str, Any]:
    root = Path(repo_root).resolve()
    generated_at = utc_now()
    cycle_id = f"autonomy-bridge-{generated_at[:10]}"
    source_files = collect_source_files(root)
    items = [_item_from_path(path, root) for path in source_files]
    previous_bridge = load_json_safely(root / OUTPUTS["bridge_state"])
    latest_report, latest_report_path = load_latest_night_report(root)

    completed = [item for item in items if item["status"] == "PASS"]
    historical = [item for item in items if item["category"] == "historical_evidence"]
    samples = [item for item in items if item["category"] == "reference_evidence"]
    noise = [item for item in items if item["category"] == "noise"]
    worker_notes = [item for item in items if item["category"] in {"worker_output", "validator_output", "relay_input"}]
    repo_state = build_repo_state(branch, git_status)
    active_current = [_active_current_from_report(latest_report, latest_report_path)] if latest_report else []
    active_decision_cards, approval_noise = _canonical_approval_cards(root, latest_report or {})
    operation_glue_cards = [
        card
        for card in (_glue_approval_card_from_item(item) for item in items)
        if card is not None
    ]
    approval_cards_by_path: dict[str, dict[str, Any]] = {}
    for card in [*active_decision_cards, *operation_glue_cards]:
        approval_cards_by_path[str(card.get("source_path") or card.get("file") or "")] = card
    approval_cards = list(approval_cards_by_path.values())
    current_blockers = _current_blockers_from_report(latest_report or {}, latest_report_path) if latest_report else []
    noise_cards = [*approval_noise, *samples[:8], *noise[:8]]
    detail_only_blocked = [item for item in items if item["status"] == "BLOCKED" and item["category"] not in ACTIVE_CLASSIFICATIONS]

    if current_blockers:
        status = "BLOCKED"
    elif approval_cards:
        status = "NEEDS_APPROVAL"
    elif latest_report and _normalize_token(latest_report.get("supervisor_status")) == "READY":
        status = "READY"
    else:
        status = "UNKNOWN"
    legacy_status = _legacy_dashboard_status(status)

    source_count = len(items)
    plain_summary = (
        f"Bridge status {status}: {len(current_blockers)} active blockers, "
        f"{len(active_decision_cards)} active approval decisions, {source_count} detail evidence items seen."
    )
    must_see: list[str] = []
    must_see.extend(item["summary"] for item in current_blockers[:3])
    must_see.extend(card["recommended_action"] for card in approval_cards[:3])
    if not must_see:
        must_see.append("No current blockers found; review active decisions before APPLY.")

    stale_warnings = _stale_state_warnings(
        latest_report,
        latest_report_path,
        str(previous_bridge.get("night_supervisor_status") or previous_bridge.get("supervisor_status") or ""),
        str(previous_bridge.get("generated_at") or ""),
    )

    bridge_state: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "cycle_id": cycle_id,
        "source_paths": [repo_relative(path, root) for path in source_files],
        "bridge_status": status,
        "legacy_dashboard_status": legacy_status,
        "supervisor_status": status,
        "night_supervisor_status": status,
        "plain_summary": plain_summary,
        "must_see": must_see,
        "relay_items_seen": [item for item in items if item["source_path"].startswith("relay/")],
        "items_completed": completed,
        "items_blocked": current_blockers,
        "items_needing_approval": approval_cards,
        "active_current": active_current,
        "active_decision_cards": approval_cards,
        "current_blockers": current_blockers,
        "historical_evidence": historical,
        "sample_or_example": samples,
        "completed_records": completed,
        "noise_cards": noise_cards,
        "stale_state_warnings": stale_warnings,
        "detail_only_blocked": detail_only_blocked,
        "repo_state": repo_state,
        "wins_count": len(completed),
        "blocked_count": len(current_blockers),
        "approval_needed_count": len(approval_cards),
        "worker_notes_count": len(worker_notes),
        "next_safe_action": (
            "Resolve current blockers before continuation."
            if current_blockers
            else (
                "Anthony reviews active approval decision cards before any APPLY or protected action."
                if active_decision_cards
                else "Continue DRY_RUN or sandbox work; protected actions still require approval."
            )
        ),
        "dashboard_cards": [],
        "morning_digest_path": OUTPUTS["morning_digest"].as_posix(),
        "raw_evidence": [
            {
                "source_path": item["source_path"],
                "evidence_type": item["category"],
                "status": item["status"],
                "status_impact": bool(item.get("status_impact")),
            }
            for item in items
        ],
        "safety_flags": {
            "no_live_trading": True,
            "no_broker_execution": True,
            "no_oanda": True,
            "no_api_keys": True,
            "no_real_webhooks": True,
            "no_real_orders": True,
            "no_secrets": True,
            "no_commit": True,
            "no_push": True,
            "writes_within_allowed_paths_only": True,
        },
        "authority_boundary": {
            "evidence_only": True,
            "approval_authority": "Anthony Meza",
            "blocked_capabilities": BLOCKED_CAPABILITIES,
        },
    }
    bridge_state["dashboard_cards"] = build_dashboard_cards(bridge_state)
    return bridge_state


def build_markdown_digest(bridge_state: dict[str, Any]) -> str:
    date_key = str(bridge_state["generated_at"])[:10]
    repo = bridge_state["repo_state"]

    def bullet(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "- None found."

    def item_lines(items: list[dict[str, Any]]) -> list[str]:
        return [f"{item['title']}: {item['summary']} ({item['source_path']})" for item in items[:8]]

    changed = list(repo.get("changed_files", []))
    untracked = list(repo.get("untracked_files", []))
    lines = [
        f"# Morning Digest - {date_key}",
        "",
        "Status:",
        f"- {bridge_state['night_supervisor_status']}",
        "",
        "Plain summary:",
        f"- {bridge_state['plain_summary']}",
        "",
        "Must See:",
        bullet(list(bridge_state["must_see"])),
        "",
        "Completed Overnight:",
        bullet(item_lines(list(bridge_state["items_completed"]))),
        "",
        "Blocked:",
        bullet(item_lines(list(bridge_state["items_blocked"]))),
        "",
        "Approval Needed:",
        bullet(item_lines(list(bridge_state["items_needing_approval"]))),
        "",
        "Repo State:",
        f"- branch: {repo.get('branch', 'UNKNOWN')}",
        f"- clean/dirty: {'dirty' if repo.get('repo_dirty') else 'clean'}",
        f"- changed files: {', '.join(changed) if changed else 'None'}",
        f"- untracked files: {', '.join(untracked) if untracked else 'None'}",
        "",
        "Next Safe Action:",
        f"- {bridge_state['next_safe_action']}",
        "",
        "Raw Evidence:",
        bullet([item["source_path"] for item in bridge_state["raw_evidence"][:12]]),
        "",
        "Safety:",
        "- No live trading, broker execution, OANDA, API keys, real webhooks, real orders, secrets, commit, or push.",
    ]
    return "\n".join(lines) + "\n"


def planned_output_paths(repo_root: str | Path) -> list[str]:
    root = Path(repo_root).resolve()
    return [repo_relative(root / path, root) for path in OUTPUTS.values()]


def _blocked_output_path(path: Path) -> str | None:
    normalized = path.as_posix().lower()
    for term in FORBIDDEN_PATH_TERMS:
        if term in normalized:
            return term
    return None


def write_outputs(repo_root: str | Path, bridge_state: dict[str, Any], apply: bool = False) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    planned = [root / path for path in OUTPUTS.values()]
    blocked_terms = [term for path in planned if (term := _blocked_output_path(path))]
    if blocked_terms:
        return {
            "mode": "BLOCKED",
            "written": [],
            "planned": [repo_relative(path, root) for path in planned],
            "errors": [f"Forbidden output path term detected: {term}" for term in blocked_terms],
        }
    if not apply:
        return {
            "mode": "DRY_RUN",
            "written": [],
            "planned": [repo_relative(path, root) for path in planned],
            "errors": [],
        }

    written: list[str] = []
    errors: list[str] = []
    outputs = {
        OUTPUTS["bridge_state"]: bridge_state,
        OUTPUTS["morning_state"]: bridge_state,
        OUTPUTS["morning_digest"]: build_markdown_digest(bridge_state),
    }
    for rel_path, content in outputs.items():
        path = root / rel_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                path.write_text(content, encoding="utf-8", newline="\n")
            else:
                path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8", newline="\n")
            written.append(repo_relative(path, root))
        except OSError as exc:
            errors.append(f"{repo_relative(path, root)}: {exc}")
    return {
        "mode": "APPLY",
        "written": written,
        "planned": [repo_relative(path, root) for path in planned],
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build AI_OS Autonomy Bridge state.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--repo-branch", default="UNKNOWN", help="Branch captured by the runner.")
    parser.add_argument("--git-status", default="", help="git status --short --branch output captured by the runner.")
    parser.add_argument("--apply", action="store_true", help="Write telemetry outputs. Default is DRY_RUN preview.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON result.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = build_bridge_state(args.repo_root, branch=args.repo_branch, git_status=args.git_status)
    receipt = write_outputs(args.repo_root, state, apply=args.apply)
    result = {
        "schema": "AIOS_AUTONOMY_BRIDGE_RUN_RECEIPT.v1",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "status": "BLOCKED" if receipt["errors"] else state["night_supervisor_status"],
        "planned_output_paths": receipt["planned"],
        "written_output_paths": receipt["written"],
        "errors": receipt["errors"],
        "bridge_state": state,
    }
    print(json.dumps(result, indent=2 if args.pretty else None))
    return 1 if receipt["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
