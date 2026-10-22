"""Fail-closed, read-only resolution of queue items into execution packets.

This module is deliberately a decision component, not an executor.  It consumes
already-normalized queue and preflight evidence, reuses a canonical packet when
there is exactly one valid match, or delegates packet construction to the
repository-aligned packet builder.  It performs no I/O and mutates no inputs.
"""

from __future__ import annotations

import copy
import re
from pathlib import PurePosixPath
from typing import Any

from automation.orchestration.aios_codex_packet_builder import (
    build_repository_aligned_apply_packet,
)


SCHEMA = "AIOS_EXECUTION_PACKET_RESOLUTION.v1"
QUEUE_SCHEMA = "AIOS_RUNTIME_EXECUTION_QUEUE.v1"
PACKET_SCHEMA = "AIOS_REPOSITORY_ALIGNED_APPLY_PACKET.v1"
CANONICAL_COMPONENTS = {
    "packet_builder": "automation/orchestration/aios_codex_packet_builder.py",
    "execution_registry": "automation/orchestration/execution_registry/AIOS_EXECUTION_CLASSIFICATION_REGISTRY.json",
    "source_of_truth_resolver": "automation/orchestration/recommendations/Resolve-AiOsSourceOfTruth.ps1",
    "runtime_queue_contract": "automation/orchestration/runtime_queue/aios_runtime_execution_queue.py",
    "development_dispatcher": "automation/orchestration/runtime_queue/aios_development_dispatcher.py",
}
PLACEHOLDER_RE = re.compile(r"(?i)(@filename|\bTODO\b|\bTBD\b|path/to/file|\[REAL-FILENAME\]|\{[^{}]+\})")
PROTECTED_TERMS = re.compile(
    r"(?i)(broker|credential|secret|api[_ -]?key|live[_ -]?trad|real[_ -]?order|"
    r"webhook|git\s+(?:add|commit|push|merge)|scheduler|daemon|worker launch|queue mutation)"
)
IDENTITY_FIELDS = (
    "mission_id", "mission_name", "program_id", "program_name", "epic_id", "epic_name",
    "bucket_id", "bucket_name", "packet_id", "packet_name", "supervisor_identity", "zone",
    "worker_identity", "lane", "stop_point",
)


def _result(status: str, reason_code: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": status,
        "reason_code": reason_code,
        "packet": None,
        "canonical_components": dict(CANONICAL_COMPONENTS),
        "safety": {
            "executes_packets": False,
            "mutates_queues": False,
            "launches_workers": False,
            "reads_credentials": False,
            "broker_demo_or_live_actions": False,
            "file_writes": False,
        },
        **extra,
    }


def _has_placeholder(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_placeholder(key) or _has_placeholder(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_has_placeholder(item) for item in value)
    return isinstance(value, str) and bool(PLACEHOLDER_RE.search(value))


def _valid_scope(paths: Any, forbidden: Any) -> tuple[bool, list[str]]:
    if not isinstance(paths, list) or not paths:
        return False, ["allowed_paths_missing"]
    denied = set(forbidden) if isinstance(forbidden, list) else set()
    defects: list[str] = []
    for raw in paths:
        path = str(raw).replace("\\", "/").strip()
        parts = PurePosixPath(path).parts
        if not path or path.startswith("/") or re.match(r"^[A-Za-z]:", path) or ".." in parts:
            defects.append(f"invalid_path:{raw}")
        if path in denied:
            defects.append(f"forbidden_path:{raw}")
    return not defects, defects


def _dependency_blockers(item: dict[str, Any], repository_state: dict[str, Any]) -> list[str]:
    states = repository_state.get("dependency_states", {})
    dependencies = item.get("depends_on", [])
    if not isinstance(dependencies, list):
        return ["invalid_dependencies"]
    return [f"dependency_not_done:{dependency}" for dependency in dependencies if states.get(str(dependency)) != "DONE"]


def resolve_execution_packet(
    queue_item: dict[str, Any] | None,
    repository_state: dict[str, Any] | None,
    *,
    existing_packets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a deterministic packet resolution without performing any action."""
    item = copy.deepcopy(queue_item) if isinstance(queue_item, dict) else {}
    state = copy.deepcopy(repository_state) if isinstance(repository_state, dict) else {}
    packets = copy.deepcopy(existing_packets) if isinstance(existing_packets, list) else []

    if item.get("queue_schema", QUEUE_SCHEMA) != QUEUE_SCHEMA:
        return _result("BLOCKED", "invalid_queue_contract")
    if _has_placeholder(item):
        return _result("BLOCKED", "placeholder_detected")
    protected_surface = " ".join(
        [str(item.get("mission", "")), str(item.get("action_id", "")), *map(str, item.get("allowed_paths", []))]
    )
    if item.get("protected_action") is True or PROTECTED_TERMS.search(protected_surface):
        return _result("BLOCKED", "protected_action")
    if state.get("status_lines"):
        return _result("BLOCKED", "repository_dirty", dirty_files=list(state["status_lines"]))
    if not str(state.get("worktree", "")).strip() or not str(state.get("branch", "")).strip():
        return _result("BLOCKED", "repository_state_missing")

    scope_valid, scope_defects = _valid_scope(item.get("allowed_paths"), item.get("forbidden_paths"))
    if not scope_valid:
        return _result("BLOCKED", "invalid_scope", scope_defects=scope_defects)
    dependency_blockers = _dependency_blockers(item, state)
    if dependency_blockers:
        return _result("BLOCKED", "dependencies_failed", blockers=dependency_blockers)
    try:
        attempt, maximum = int(item.get("attempt", 0)), int(item.get("max_attempts", 1))
    except (TypeError, ValueError):
        return _result("BLOCKED", "invalid_retry_contract")
    if attempt >= maximum:
        return _result("BLOCKED", "retries_exhausted")
    if str(item.get("mode", "")).upper() != "APPLY" or str(item.get("approval_state", "")).upper() != "APPROVED":
        return _result("BLOCKED", "apply_approval_required")
    if not str(item.get("approval_authority", "")).strip():
        return _result("BLOCKED", "approval_authority_missing")
    if not str(item.get("commit_message", "")).strip():
        return _result("BLOCKED", "commit_message_missing")
    if not str(item.get("pr_authority", "")).strip():
        return _result("BLOCKED", "pr_authority_missing")

    packet_id = str(item.get("packet_id", "")).strip()
    identity = item.get("packet_identity", {})
    missing = [field for field in IDENTITY_FIELDS if not str(identity.get(field, "")).strip()]
    if missing:
        return _result("BLOCKED", "identity_fields_missing", missing_identity_fields=missing)
    if str(identity.get("packet_id")) != packet_id:
        return _result("BLOCKED", "packet_identity_mismatch")

    validators = item.get("validators", [])
    packet = build_repository_aligned_apply_packet(
        repository_state=state,
        packet_identity=identity,
        mission=str(item.get("mission", "")),
        allowed_paths=item["allowed_paths"],
        forbidden_paths=item.get("forbidden_paths"),
        validators=validators if isinstance(validators, list) else [],
        approval_authority=str(item.get("approval_authority", "")).strip(),
    )
    if not packet.get("packet_ready"):
        return _result("BLOCKED", str(packet.get("reason_code", "packet_builder_blocked")), builder_result=packet)
    packet["commit_message"] = str(item["commit_message"]).strip()
    packet["pr_authority"] = str(item["pr_authority"]).strip()
    packet["codex_prompt_text"] = packet["codex_prompt_text"].replace(
        "\nSTOP POINT:",
        f"\nEXACT COMMIT MESSAGE: {packet['commit_message']}\nPR AUTHORITY: {packet['pr_authority']}\n\nSTOP POINT:",
    )

    matches = [existing for existing in packets if str(existing.get("packet_id", "")).strip() == packet_id]
    if len(matches) > 1:
        return _result("BLOCKED", "duplicate_canonical_packets", duplicate_count=len(matches))
    if len(matches) == 1:
        existing = matches[0]
        if existing.get("schema") != PACKET_SCHEMA or existing.get("packet_ready") is not True:
            return _result("BLOCKED", "existing_packet_invalid")
        # Rebuild from the current canonical inputs before reuse.  This preserves
        # builder-owned instrumentation paths while rejecting stale or tampered
        # identity, scope, validator, authority, state, and prompt content.
        if existing != packet:
            return _result("BLOCKED", "existing_packet_canonical_mismatch")
        return _result("REUSED", "existing_packet_reused", packet=existing)

    return _result("CREATED", "packet_candidate_created", packet=packet)
