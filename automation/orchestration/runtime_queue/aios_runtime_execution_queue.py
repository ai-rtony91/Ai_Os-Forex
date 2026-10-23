"""AI_OS canonical runtime execution queue — read-only normalizer (observe-only).

There is no single runtime execution queue on main: work is fragmented across the
relay inbox, the command queue, the dispatcher queue, the worker task queue, the
unified queue index, and more. This module defines ONE canonical contract
(AIOS_RUNTIME_EXECUTION_QUEUE.v1) and a READ-ONLY adapter that normalizes those
fragmented sources into a single queue view plus a source map. It is the keystone the
later relay/runtime wiring will read; it does not change relay, runtime, or any source.

Safety posture:
  * Observe-only. Reads source queue files. Optionally writes ONE report under
    Reports/runtime_queue/. It mutates NO source queue, enqueues nothing, dequeues
    nothing, dispatches nothing, executes nothing.
  * Protected-item aware. Any normalized item whose payload carries a protected/forbidden
    execution flag is marked protected_action=True so the validator can BLOCK it.
  * Fail-soft on read. A missing or malformed source is skipped and recorded; never fatal.

Pure standard library. No network. No mutation of any source queue.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


SCHEMA = "AIOS_RUNTIME_EXECUTION_QUEUE.v1"
DEFAULT_REPORT_SUBDIR = Path("Reports") / "runtime_queue"

CANONICAL_STATES = {"QUEUED", "RUNNING", "DONE", "ERROR", "BLOCKED", "DEFERRED"}
CANONICAL_PRIORITIES = {"P0", "P1", "P2", "P3"}
CANONICAL_MODES = {"DRY_RUN", "APPLY"}
CANONICAL_APPROVAL_STATES = {"NOT_REQUIRED", "PENDING", "APPROVED", "REJECTED"}

STATE_SYNONYMS = {
    "pending": "QUEUED", "queued": "QUEUED", "waiting": "QUEUED", "new": "QUEUED",
    "ready": "QUEUED", "open": "QUEUED", "todo": "QUEUED",
    "running": "RUNNING", "in_progress": "RUNNING", "active": "RUNNING", "claimed": "RUNNING",
    "done": "DONE", "complete": "DONE", "completed": "DONE", "success": "DONE", "succeeded": "DONE",
    "error": "ERROR", "failed": "ERROR", "failure": "ERROR",
    "blocked": "BLOCKED", "waiting_approval": "BLOCKED", "needs_approval": "BLOCKED",
    "wait_approval": "BLOCKED", "approval_required": "BLOCKED",
    "deferred": "DEFERRED", "paused": "DEFERRED", "hold": "DEFERRED", "on_hold": "DEFERRED",
    "stale": "DEFERRED", "expired": "DEFERRED", "skipped": "DEFERRED",
}

# An item whose payload mentions any of these is a protected/forbidden execution candidate.
PROTECTED_RE = re.compile(
    r"(?i)(git\s+merge|git\s+push|\bmerge\b|\bpush\b|\bcommit\b|broker|oanda|live[_\s-]?trad|"
    r"place_order|real_order|live_order|secret|credential|api[_-]?key|token|schtasks|"
    r"scheduler|register-service|new-service|webhook)"
)

# Known AI_OS queue fragments. Each: name, relative path, loader kind.
#   tasks_dir : a directory of per-item *.json / *.task.json files
#   list_file : a JSON file holding a list, or a dict with a list under a known key
#   index_file: an aggregate index (counts only, no items) -> read as informational
DEFAULT_SOURCES: list[dict[str, str]] = [
    {"name": "relay_inbox", "path": "relay/inbox", "loader": "tasks_dir"},
    {"name": "command_queue", "path": "automation/orchestration/command_queue/AIOS_COMMAND_QUEUE.json", "loader": "list_file"},
    {"name": "worker_task_queue", "path": "automation/operator/worker_queue/WORKER_TASK_QUEUE_V1.json", "loader": "list_file"},
    {"name": "unified_queue_index", "path": "telemetry/coordination_spine/UNIFIED_QUEUE_INDEX.json", "loader": "index_file"},
]

LIST_KEYS = ("items", "queue", "packets", "tasks", "entries", "commands")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Any:
    # utf-8-sig tolerates a leading BOM, which PowerShell-written AI_OS JSON commonly has.
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _extract_list(obj: Any) -> list:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in LIST_KEYS:
            if isinstance(obj.get(key), list):
                return obj[key]
    return []


def _first(raw: dict, *keys: str) -> Any:
    for k in keys:
        if raw.get(k) not in (None, ""):
            return raw[k]
    return None


def _string_list(value: Any) -> list[str]:
    """Return a deterministic string list without accepting scalar lookalikes."""
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item) for item in value if item not in (None, "")))


def _nonnegative_int(value: Any, default: int) -> int:
    """Normalize counters while rejecting booleans and negative values."""
    if isinstance(value, bool):
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized >= 0 else default


def _constraint_evidence(value: Any) -> Any:
    """Retain malformed source fields as finite JSON evidence, without changing input."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"invalid_number": str(value)}
    if isinstance(value, dict):
        return {str(key): _constraint_evidence(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_constraint_evidence(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return {"invalid_type": type(value).__name__, "representation": str(value)}

def _valid_counter(value: Any, minimum: int) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return False
    try:
        normalized = int(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return normalized >= minimum and (not isinstance(value, float) or value == normalized)

def _scheduling_errors(raw: dict) -> list[str]:
    errors: list[str] = []
    for key in ("depends_on", "dependencies"):
        if key in raw and (not isinstance(raw[key], list) or any(
            not isinstance(item, str) or not item.strip() for item in raw[key]
        )):
            errors.append(f"invalid_dependencies:{key}")
    for key in ("attempt", "attempt_count", "max_attempts"):
        if key in raw and not _valid_counter(raw[key], 1 if key == "max_attempts" else 0):
            errors.append(f"invalid_retry_counter:{key}")
    if (
        not any(error.startswith("invalid_dependencies:") for error in errors)
        and "depends_on" in raw and "dependencies" in raw
        and set(raw["depends_on"]) != set(raw["dependencies"])
    ):
        errors.append("invalid_dependencies:conflicting_aliases")
    if (
        not any(error in errors for error in ("invalid_retry_counter:attempt", "invalid_retry_counter:attempt_count"))
        and "attempt" in raw and "attempt_count" in raw
        and int(raw["attempt"]) != int(raw["attempt_count"])
    ):
        errors.append("invalid_retry_counter:attempt")
    return errors


def normalize_item(raw: Any, source: str, index: int) -> dict[str, object]:
    """Normalize one raw source record into a canonical queue item. Read-only."""
    raw = raw if isinstance(raw, dict) else {"value": raw}
    rid = _first(raw, "id", "packet_id", "task_id", "command_id", "name")
    synthetic = rid is None
    item_id = str(rid) if rid is not None else f"{source}#{index}"

    raw_state = _first(raw, "state", "status", "phase_state") or "QUEUED"
    norm_state = STATE_SYNONYMS.get(str(raw_state).strip().lower(), str(raw_state).strip().upper())

    kind = _first(raw, "kind", "type", "worker", "provider", "lane") or "unknown"
    allowed = _string_list(raw.get("allowed_paths"))
    created = _first(raw, "created_utc", "created_at", "created", "timestamp_utc")

    priority = str(_first(raw, "priority", "queue_priority") or "P2").strip().upper()
    if priority not in CANONICAL_PRIORITIES:
        priority = "P2"
    mode = str(_first(raw, "mode", "execution_mode") or "DRY_RUN").strip().upper()
    if mode not in CANONICAL_MODES:
        mode = "DRY_RUN"

    approval_required = bool(raw.get("approval_required")) or mode == "APPLY"
    default_approval = "PENDING" if approval_required else "NOT_REQUIRED"
    approval_state = str(raw.get("approval_state") or default_approval).strip().upper()
    if approval_state not in CANONICAL_APPROVAL_STATES:
        approval_state = default_approval

    errors = _scheduling_errors(raw)
    attempt = (
        None if any(error in errors for error in ("invalid_retry_counter:attempt", "invalid_retry_counter:attempt_count"))
        else _nonnegative_int(_first(raw, "attempt", "attempt_count"), 0)
    )
    max_attempts = (
        None if "invalid_retry_counter:max_attempts" in errors
        else max(1, _nonnegative_int(raw.get("max_attempts"), 1))
    )
    dependencies = (
        None if any(error.startswith("invalid_dependencies:") for error in errors)
        else _string_list(_first(raw, "depends_on", "dependencies"))
    )
    if errors:
        norm_state = "BLOCKED"
    forbidden_paths = _string_list(raw.get("forbidden_paths"))
    packet_id = _first(raw, "packet_id", "task_id", "command_id")
    branch = _first(raw, "branch", "target_branch")
    worktree = _first(raw, "worktree", "worktree_path")

    protected = bool(raw.get("protected_action")) or bool(PROTECTED_RE.search(json.dumps(raw, default=str)))

    return {
        "id": item_id,
        "synthetic_id": synthetic,
        "source": source,
        "kind": str(kind),
        "state": norm_state,
        "raw_state": str(raw_state),
        "priority": priority,
        "mode": mode,
        "depends_on": dependencies,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "approval_required": approval_required,
        "approval_state": approval_state,
        "packet_id": str(packet_id) if packet_id is not None else None,
        "branch": str(branch) if branch is not None else None,
        "worktree": str(worktree) if worktree is not None else None,
        "allowed_paths": allowed,
        "forbidden_paths": forbidden_paths,
        "protected_action": protected,
        "created_utc": str(created) if created is not None else None,
        **({
            "normalization_errors": errors,
            "source_scheduling_constraints": {
                key: _constraint_evidence(raw[key]) for key in (
                    "depends_on", "dependencies", "attempt", "attempt_count", "max_attempts"
                ) if key in raw
            },
        } if errors else {}),
    }


def _load_source_records(repo_root: Path, spec: dict) -> tuple[list, str]:
    """Return (raw_records, status). status in READ | MISSING | MALFORMED | INDEX."""
    path = repo_root / spec["path"]
    loader = spec["loader"]
    if not path.exists():
        return [], "MISSING"
    try:
        if loader == "tasks_dir":
            records = []
            for fp in sorted(path.glob("*.json")):
                try:
                    records.append(_read_json(fp))
                except (OSError, ValueError):
                    continue
            return records, "READ"
        if loader == "list_file":
            return _extract_list(_read_json(path)), "READ"
        if loader == "index_file":
            # aggregate counts only; do not synthesize items from an index
            return [], "INDEX"
    except (OSError, ValueError):
        return [], "MALFORMED"
    return [], "MISSING"


def build_queue_view(
    repo_root: Optional[Path] = None,
    *,
    sources: Optional[list[dict]] = None,
    now: Optional[str] = None,
) -> dict[str, object]:
    """Normalize the fragmented queue sources into one canonical view. Read-only."""
    repo_root = Path(repo_root) if repo_root else Path.cwd()
    sources = sources if sources is not None else DEFAULT_SOURCES
    now = now or _now()

    items: list[dict] = []
    by_id: dict[str, dict] = {}
    collisions: dict[str, set] = {}
    source_map: dict[str, int] = {}
    sources_read: list[str] = []
    sources_missing: list[str] = []
    sources_malformed: list[str] = []
    sources_index: list[str] = []

    for spec in sources:
        name = spec["name"]
        records, status = _load_source_records(repo_root, spec)
        if status == "MISSING":
            sources_missing.append(name); continue
        if status == "MALFORMED":
            sources_malformed.append(name); continue
        if status == "INDEX":
            sources_index.append(name); continue
        sources_read.append(name)
        count = 0
        for i, raw in enumerate(records):
            item = normalize_item(raw, name, i)
            count += 1
            iid = item["id"]
            if iid in by_id:
                collisions.setdefault(iid, {by_id[iid]["source"]}).add(name)
            else:
                by_id[iid] = item
                items.append(item)
        source_map[name] = count

    state_counts: dict[str, int] = {}
    for it in items:
        state_counts[it["state"]] = state_counts.get(it["state"], 0) + 1

    return {
        "schema": SCHEMA,
        "generated_at": now,
        "observe_only": True,
        "item_count": len(items),
        "items": items,
        "source_map": source_map,
        "sources_read": sources_read,
        "sources_missing": sources_missing,
        "sources_malformed": sources_malformed,
        "sources_index_only": sources_index,
        "id_collisions": [{"id": k, "sources": sorted(v)} for k, v in sorted(collisions.items())],
        "state_counts": state_counts,
        "protected_item_count": sum(1 for it in items if it["protected_action"]),
        "canonical_states": sorted(CANONICAL_STATES),
        "contract": {
            "purpose": "autonomous_development_workflow",
            "priority_order": ["P0", "P1", "P2", "P3"],
            "modes": sorted(CANONICAL_MODES),
            "approval_states": sorted(CANONICAL_APPROVAL_STATES),
            "apply_requires_approval": True,
            "dependency_semantics": "An item may run only after every depends_on item is DONE.",
            "retry_semantics": "attempt must remain below max_attempts before another claim.",
        },
        "safe_next_action": (
            "Read-only normalized view. Run the integrity validator before any later "
            "drain/wiring packet consumes it. This view enqueues, dispatches, and executes nothing."
        ),
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def write_report(view: dict, *, repo_root: Optional[Path] = None, output_dir: Optional[Path] = None) -> dict[str, object]:
    """Write the queue view JSON + a markdown summary under Reports/runtime_queue/ (allowed)."""
    if output_dir is not None:
        target = Path(output_dir)
    else:
        base = Path(repo_root) if repo_root else Path.cwd()
        target = base / DEFAULT_REPORT_SUBDIR
    json_path = target / "runtime_execution_queue_view.json"
    md_path = target / "runtime_execution_queue_view.md"
    _atomic_write_text(json_path, json.dumps(view, indent=2, sort_keys=True))
    _atomic_write_text(md_path, _render_md(view))
    return {"json_path": str(json_path), "md_path": str(md_path)}


def _render_md(view: dict) -> str:
    lines = [
        "# AI_OS Canonical Runtime Execution Queue (read-only view)",
        "",
        f"- generated_at: `{view['generated_at']}`",
        f"- item_count: `{view['item_count']}`",
        f"- protected_item_count: `{view['protected_item_count']}`",
        f"- sources_read: `{view['sources_read']}`",
        f"- sources_missing: `{view['sources_missing']}`",
        f"- id_collisions: `{len(view['id_collisions'])}`",
        "",
        "## State counts",
    ]
    for state, n in sorted(view["state_counts"].items()):
        lines.append(f"- `{state}`: {n}")
    lines += ["", "## Source map"]
    for src, n in sorted(view["source_map"].items()):
        lines.append(f"- `{src}`: {n} items")
    lines += ["", "_Observe-only normalized view. No source mutated. Nothing enqueued or executed._"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize fragmented AI_OS queues into one read-only view.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--report", action="store_true", help="write a report under Reports/runtime_queue/")
    args = parser.parse_args()
    view = build_queue_view(Path(args.repo_root))
    if args.report:
        view["_report"] = write_report(view, repo_root=Path(args.repo_root))
    print(json.dumps(view, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
