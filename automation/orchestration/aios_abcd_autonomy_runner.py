"""Bounded connector for one approved packet through the canonical ABCD lifecycle.

The connector composes the existing dispatcher, packet resolver, and task-claim
controller.  It intentionally executes at most one supplied task and returns a
preview of the next eligible task without starting it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from automation.orchestration.claims.aios_task_claim_control import (
    ClaimError,
    TaskClaimController,
)
from automation.orchestration.runtime_queue.aios_development_dispatcher import (
    build_dispatch_plan,
)
from automation.orchestration.runtime_queue.aios_execution_packet_resolver import (
    resolve_execution_packet,
)


@dataclass(frozen=True)
class AutonomyRunResult:
    status: str
    reason: str
    task_id: str | None = None
    packet: dict[str, Any] | None = None
    receipt_path: Path | None = None
    next_task: dict[str, Any] | None = None


def _next_task(queue_view: Mapping[str, Any], completed_task: str) -> dict[str, Any] | None:
    remaining = [
        item for item in queue_view.get("items", [])
        if isinstance(item, dict) and str(item.get("id") or item.get("packet_id")) != completed_task
    ]
    plan = build_dispatch_plan({"schema": queue_view.get("schema"), "items": remaining}, worker_capacity=1)
    return plan["claims"][0] if plan["claims"] else None


def run_one_abcd_task(
    queue_view: dict[str, Any],
    repository_state: dict[str, Any],
    queue_items: Mapping[str, dict[str, Any]],
    claims: Mapping[str, dict[str, Any]],
    *,
    claim_controller: TaskClaimController,
    execute: Callable[[dict[str, Any]], Mapping[str, Any]],
    changed_paths: Sequence[str] = (),
    cleanup_resources: Mapping[str, Sequence[str]] | None = None,
    cleanup: Callable[[str, str], None] | None = None,
) -> AutonomyRunResult:
    """Resolve, claim, execute, validate, and release one eligible queue task."""
    plan = build_dispatch_plan(queue_view, worker_capacity=1)
    if not plan["claims"]:
        return AutonomyRunResult("BLOCKED", "no dispatchable task")

    task_id = str(plan["claims"][0]["id"])
    queue_item = queue_items.get(task_id)
    raw_claim = claims.get(task_id)
    if queue_item is None or raw_claim is None:
        return AutonomyRunResult("BLOCKED", "task connector input missing", task_id=task_id)

    resolved = resolve_execution_packet(queue_item, repository_state)
    if resolved["status"] not in {"CREATED", "REUSED"}:
        return AutonomyRunResult("BLOCKED", str(resolved["reason_code"]), task_id=task_id)
    packet = resolved["packet"]

    try:
        claim_controller.acquire(raw_claim)
        claim_controller.guard(
            task_id,
            repository=str(raw_claim["repository"]),
            worktree=Path(str(raw_claim["worktree"])),
            branch=str(raw_claim["branch"]),
            head_is_descendant=bool(repository_state.get("head_is_descendant", True)),
            changed_paths=changed_paths,
        )
    except ClaimError as exc:
        return AutonomyRunResult("BLOCKED", str(exc), task_id=task_id, packet=packet)

    execution = dict(execute(packet))
    if execution.get("status") != "COMPLETE":
        claim_controller.transition(task_id, "VERIFYING")
        claim_controller.transition(task_id, "ACTIVE")
        return AutonomyRunResult("VALIDATION_FAILED", str(execution.get("reason", "validation failed")), task_id, packet)

    claim_controller.transition(task_id, "VERIFYING")
    if execution.get("base_drift") is True:
        claim_controller.transition(task_id, "INTEGRATING", base_drift=True)
        return AutonomyRunResult("BASE_DRIFT", "base drift detected", task_id, packet)

    claim_controller.transition(task_id, "INTEGRATING")
    claim_controller.transition(task_id, "RELEASING")
    try:
        receipt = claim_controller.release(
            task_id, owned_resources=cleanup_resources, cleanup=cleanup
        )
    except ClaimError as exc:
        return AutonomyRunResult("BLOCKED", str(exc), task_id=task_id, packet=packet)

    return AutonomyRunResult(
        "COMPLETE", "task completed", task_id, packet, receipt,
        _next_task(queue_view, task_id),
    )
