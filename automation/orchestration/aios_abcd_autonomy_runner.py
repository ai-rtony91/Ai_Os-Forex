"""Bounded connector for one approved packet through the canonical ABCD lifecycle.

The connector composes existing decision/publication/claim owners. It executes
at most one supplied task; a returned next task is only a preview.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from automation.orchestration.claims.aios_task_claim_control import (
    ClaimError,
    RELEASE_SCHEMA,
    TaskClaimController,
    _atomic_write,
    _claim_contract,
    _cleanup_plan,
    _exclusive_lock,
    _norm_path,
    _read_board,
    _select_claim,
    normalize_claim,
    verify_exact_allowlist,
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


@dataclass(frozen=True)
class RequirementReadRequest:
    """Exact immutable inputs the existing publication reader must validate."""

    task_id: str
    packet_id: str
    request_sha256: str
    claim_sha256: str
    acquired_at: str


@dataclass(frozen=True)
class AcceptedRequirement:
    """Process-local adapter result, never an independently writable proof.

    Constructing this class establishes nothing. Only a source-qualified adapter
    to the existing publication owner may return it after independently checking
    acceptance, validators, source/freshness and this exact request/claim attempt.
    None means reader-verified absence; unknown/conflicting evidence must raise.
    N06 supplies no native implementation or native identity qualification.
    Fixture readers qualify only component behavior and earn no productive credit.
    """

    request: RequirementReadRequest


def _json_digest(value: Any) -> str:
    def check(item: Any) -> None:
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ClaimError("invalid acceptance request object keys")
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif item is not None and type(item) not in {str, int, float, bool}:
            raise ClaimError("invalid acceptance request value")

    try:
        check(value)
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ClaimError("invalid acceptance request serialization") from exc
    return hashlib.sha256(encoded).hexdigest()


def _acceptance_request(item: dict[str, Any], queue_item: Any, raw_claim: Any) -> RequirementReadRequest:
    task_id, packet_id = item.get("id"), item.get("packet_id")
    if type(task_id) is not str or not task_id.strip() or type(packet_id) is not str or not packet_id.strip():
        raise ClaimError("invalid acceptance task identity")
    if type(queue_item) is not dict or type(raw_claim) is not dict:
        raise ClaimError("task connector input missing")
    if "release_intent" in raw_claim:
        raise ClaimError("caller-supplied release progress is not acceptance authority")
    claim = normalize_claim(raw_claim)
    if claim["task_id"] != task_id or claim["packet_id"] != packet_id or queue_item.get("packet_id") != packet_id:
        raise ClaimError("acceptance task and claim identity differ")
    dependencies = item.get("depends_on", [])
    if (type(dependencies) is not list or any(type(dep) is not str or not dep.strip() for dep in dependencies)
            or len(set(dependencies)) != len(dependencies) or queue_item.get("depends_on", []) != dependencies):
        raise ClaimError("dispatcher and resolver dependency contracts differ")
    for field, default in (("attempt", 0), ("max_attempts", 1)):
        if (type(item.get(field, default)) is not int or item.get(field, default) < 0
                or type(queue_item.get(field, default)) is not int
                or item.get(field, default) != queue_item.get(field, default)):
            raise ClaimError("dispatcher and resolver attempt contracts differ")
    # Only the dispatch node's lifecycle state is excluded. Unrelated arrivals
    # are not part of this task's identity; all other node/request inputs bind.
    request = {"dispatch_item": {key: value for key, value in item.items() if key != "state"},
               "queue_item": queue_item}
    return RequirementReadRequest(task_id, packet_id, _json_digest(request),
                                  _claim_contract(claim), claim["acquired_at"])


def _public_error_name(error: Exception) -> str:
    """Return a fixed public category; custom class names may contain private text."""
    for kind, label in ((OSError, "OSError"), (KeyError, "KeyError"),
                        (TypeError, "TypeError"), (ValueError, "ValueError"),
                        (RuntimeError, "RuntimeError"), (ClaimError, "ClaimError")):
        if type(error) is kind:
            return label
    return "Exception"


def _read_acceptance(reader: Callable, request: RequirementReadRequest) -> bool:
    try:
        result = reader(request)
    except Exception as exc:
        raise ClaimError("existing publication reader failed") from exc
    if result is None:
        return False
    if type(result) is not AcceptedRequirement or type(result.request) is not RequirementReadRequest or result.request != request:
        raise ClaimError("existing publication reader returned mismatched or malformed acceptance")
    return True


def _validate_saved_release_claim(selected: Any, expected_claim: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(selected, Mapping):
        raise ClaimError("saved release claim is not an object")
    normalized = normalize_claim(selected)
    expected = normalize_claim(expected_claim)
    intent = normalized.get("release_intent")
    if (normalized.get("state") != "RELEASING" or _claim_contract(normalized) != _claim_contract(expected)
            or not isinstance(intent, Mapping) or intent.get("schema") != RELEASE_SCHEMA
            or intent.get("claim_sha256") != _claim_contract(normalized)):
        raise ClaimError("saved release intent is not bound to the exact RELEASING claim")
    return normalized


def _read_saved_release_claim(claim_controller: TaskClaimController, task_id: str,
                              expected_claim: Mapping[str, Any]) -> dict[str, Any]:
    reader = getattr(claim_controller, "read_release_claim", None)
    if callable(reader):
        return _validate_saved_release_claim(reader(task_id, expected_claim=expected_claim), expected_claim)
    board_path = getattr(claim_controller, "board_path", None)
    if board_path is None:
        raise ClaimError("release intent readback is unavailable")
    with _exclusive_lock(board_path):
        board = _read_board(board_path)
        selected = _select_claim(board, task_id, expected_claim)
        return _validate_saved_release_claim(selected, expected_claim)


def _ensure_release_intent(claim_controller: TaskClaimController, task_id: str,
                           expected_claim: Mapping[str, Any], *,
                           owned_resources: Mapping[str, Sequence[Any]] | None,
                           cleanup: Callable[[str, Any], None] | None,
                           cleanup_idempotent: bool,
                           reconcile_cleanup: Callable[[str, Any], str] | None) -> dict[str, Any]:
    """Persist the controller's release intent before a checkpoint can stop.

    A real controller may expose this small prepare operation. The fallback
    uses the same claim owner lock and release-intent shape as its release
    method, then reads the saved claim back before returning.
    """
    prepare = getattr(claim_controller, "prepare_release_intent", None)
    if callable(prepare):
        prepare(task_id, expected_claim=expected_claim, owned_resources=owned_resources,
                cleanup=cleanup, cleanup_idempotent=cleanup_idempotent,
                reconcile_cleanup=reconcile_cleanup)
        return _read_saved_release_claim(claim_controller, task_id, expected_claim)
    with _exclusive_lock(claim_controller.board_path):
        board = _read_board(claim_controller.board_path)
        claim = _select_claim(board, task_id, expected_claim)
        if claim is None:
            raise ClaimError("active task claim not found")
        if claim.get("state") != "RELEASING":
            raise ClaimError("task must be RELEASING before release intent")
        if "release_intent" not in claim:
            if type(cleanup_idempotent) is not bool:
                raise ClaimError("cleanup idempotency must be explicit Boolean")
            if cleanup is not None and not callable(cleanup):
                raise ClaimError("cleanup callback is invalid")
            if reconcile_cleanup is not None and not callable(reconcile_cleanup):
                raise ClaimError("cleanup reconciliation callback is invalid")
            normalized = normalize_claim(claim)
            mode = "idempotent" if cleanup_idempotent else "reconcile" if reconcile_cleanup else "once"
            plan = _cleanup_plan(normalized, owned_resources if owned_resources is not None else {})
            if plan and cleanup is None:
                raise ClaimError("owned cleanup requires an explicit callback")
            claim["release_intent"] = {
                "schema": RELEASE_SCHEMA,
                "claim_sha256": _claim_contract(normalized),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "receipt_path": normalized["receipt_path"],
                "cleanup_mode": mode,
                "resources": [{**item, "status": "NOT_STARTED"} for item in plan],
            }
            _atomic_write(claim_controller.board_path, board)
        saved = _read_board(claim_controller.board_path)
        selected = _select_claim(saved, task_id, expected_claim)
        return _validate_saved_release_claim(selected, expected_claim)


def _terminal_release(claim_controller: TaskClaimController, task_id: str, raw_claim: Mapping[str, Any]) -> Path | None:
    # Read through the existing claim owner's lock and validators. A receipt
    # written before board replacement is not terminal while ownership remains.
    with _exclusive_lock(claim_controller.board_path):
        board = _read_board(claim_controller.board_path)
        active = _select_claim(board, task_id, raw_claim)
        receipt = claim_controller._receipt_for_task(task_id, expected_claim=raw_claim, board=board)
        return receipt if active is None else None


def _dependency_view(queue_view, queue_items, claims, claim_controller, reader):
    if type(queue_view) is not dict or not isinstance(queue_items, Mapping) or not isinstance(claims, Mapping):
        raise ClaimError("invalid acceptance connector inputs")
    items = queue_view.get("items")
    if queue_view.get("schema") != "AIOS_RUNTIME_EXECUTION_QUEUE.v1" or type(items) is not list:
        raise ClaimError("invalid acceptance queue view")
    view = {"schema": queue_view["schema"], "items": []}
    states, pending, accepted = {}, {}, set()
    for item in items:
        if type(item) is not dict:
            raise ClaimError("invalid acceptance queue item")
        task_id = item.get("id")
        if type(task_id) is not str or task_id in states:
            raise ClaimError("duplicate or invalid acceptance task identity")
        request = _acceptance_request(item, queue_items.get(task_id), claims.get(task_id))
        current = copy.deepcopy(item)
        if _read_acceptance(reader, request):
            accepted.add(task_id)
            if _terminal_release(claim_controller, task_id, claims[task_id]) is not None:
                current["state"] = "DONE"
            else:
                current["state"] = "QUEUED"
                pending[task_id] = current
        elif current.get("state") == "DONE":
            current["state"] = "UNVERIFIED"
        states[task_id] = current.get("state")
        view["items"].append(current)
    for item in view["items"]:
        if item["id"] in accepted and any(states.get(dep) != "DONE" for dep in item.get("depends_on", [])):
            raise ClaimError("accepted task has unresolved dependency ownership")
    return view, states, pending


def _next_task(queue_view: Mapping[str, Any], completed_task: str) -> dict[str, Any] | None:
    remaining = [
        item for item in queue_view.get("items", [])
        if isinstance(item, dict) and (str(item.get("id") or item.get("packet_id")) != completed_task
                                      or item.get("state") == "DONE")
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
    acceptance_reader: Callable[[RequirementReadRequest], AcceptedRequirement | None] | None = None,
    legacy_independent_tasks: bool = False,
    packet_profile_reader: Callable | None = None,
    campaign_admission_reader: Callable | None = None,
    changed_paths: Sequence[str] = (),
    cleanup_resources: Mapping[str, Sequence[str]] | None = None,
    cleanup: Callable[[str, Any], None] | None = None,
    cleanup_idempotent: bool = False,
    reconcile_cleanup: Callable[[str, Any], str] | None = None,
    checkpoint_after_acceptance: Callable[[RequirementReadRequest], bool] | None = None,
) -> AutonomyRunResult:
    """Run one task using a qualified existing-owner reader, or explicit legacy mode.

    The injected reader is trusted executable adapter code, not supplied evidence
    JSON. Its caller must qualify the real publication/source/identity checks
    before native use. This component does not provide that WP06 qualification.
    Legacy compatibility accepts independent tasks only and never supplies a
    dependency acceptance fact. Neither execute COMPLETE nor release is proof.
    """
    receipt_backed = acceptance_reader is not None
    if type(legacy_independent_tasks) is not bool or receipt_backed == legacy_independent_tasks:
        return AutonomyRunResult("BLOCKED", "select a publication reader or explicit independent-task compatibility")
    if checkpoint_after_acceptance is not None and (not receipt_backed or not callable(checkpoint_after_acceptance)):
        return AutonomyRunResult("BLOCKED", "accepted checkpoint requires a publication reader and callable host control")
    release_options = {"owned_resources": cleanup_resources, "cleanup": cleanup,
                       "cleanup_idempotent": cleanup_idempotent, "reconcile_cleanup": reconcile_cleanup}
    decision_view = queue_view
    decision_state = copy.deepcopy(repository_state)
    try:
        if receipt_backed:
            if not callable(acceptance_reader):
                raise ClaimError("existing publication reader is not callable")
            queue_view, queue_items, claims = copy.deepcopy((queue_view, queue_items, claims))
            decision_view, states, pending = _dependency_view(queue_view, queue_items, claims, claim_controller, acceptance_reader)
            decision_state["dependency_states"] = states
            if pending:
                pending_view = {"schema": decision_view["schema"], "items": [
                    {**item, "state": "QUEUED" if item["id"] in pending else
                     "DONE" if item.get("state") == "DONE" else "BLOCKED"}
                    for item in decision_view["items"]
                ]}
                plan = build_dispatch_plan(pending_view, worker_capacity=1)
                if not plan["claims"]:
                    raise ClaimError("accepted task requires owned lifecycle reconciliation")
                task_id = plan["claims"][0]["id"]
                receipt = claim_controller.reconcile_release(task_id, expected_claim=claims[task_id], **release_options)
                if receipt is None:
                    raise ClaimError("accepted task lacks terminal release; preserve owned lifecycle")
                return AutonomyRunResult("RELEASE_RECONCILED", "owned release reconciled; reread acceptance before dispatch", task_id, receipt_path=receipt)
        elif (any(item.get("depends_on") for item in queue_view.get("items", []) if isinstance(item, dict))
              or any(item.get("depends_on") for item in queue_items.values())):
            raise ClaimError("independent-task compatibility cannot accept dependencies")
    except ClaimError as exc:
        return AutonomyRunResult("BLOCKED", str(exc))

    plan = build_dispatch_plan(decision_view, worker_capacity=1)
    if not plan["claims"]:
        return AutonomyRunResult("BLOCKED", "no dispatchable task")

    task_id = str(plan["claims"][0]["id"])
    queue_item = queue_items.get(task_id)
    raw_claim = claims.get(task_id)
    if queue_item is None or raw_claim is None:
        return AutonomyRunResult("BLOCKED", "task connector input missing", task_id=task_id)

    profile_options = {}
    if packet_profile_reader is not None or campaign_admission_reader is not None:
        try:
            if not callable(packet_profile_reader) or not callable(campaign_admission_reader):
                raise TypeError("campaign requires both qualified profile and admission readers")
            node = next(item for item in queue_view["items"] if item.get("id") == task_id)
            request = _acceptance_request(node, queue_item, raw_claim)
            selection = (request.task_id, request.packet_id, request.request_sha256, request.claim_sha256, request.acquired_at)
            try:
                profile = packet_profile_reader(request)
            except Exception as exc:
                raise ClaimError("campaign profile callback failed") from exc
            normalized = normalize_claim(raw_claim)
            if (normalized["branch"] != decision_state.get("branch")
                    or Path(normalized["worktree"]) != Path(decision_state.get("worktree", "")).resolve()):
                raise ValueError("campaign claim and current repository identity differ")
            verify_exact_allowlist([_norm_path(path, Path(raw_claim["worktree"])) for path in queue_item["allowed_paths"]], normalized["claimed_paths"])
            profile_options = {"campaign_profile": profile, "campaign_admission_reader": campaign_admission_reader,
                               "campaign_selection": selection}
        except (ClaimError, ValueError, TypeError, OSError, KeyError, StopIteration) as exc:
            return AutonomyRunResult("BLOCKED", "campaign profile reader failed", task_id=task_id)
    resolved = resolve_execution_packet(queue_item, decision_state, **profile_options)
    if resolved["status"] not in {"CREATED", "REUSED"}:
        return AutonomyRunResult("BLOCKED", str(resolved["reason_code"]), task_id=task_id)
    packet = resolved["packet"]

    if raw_claim.get("task_id") != task_id or raw_claim.get("packet_id") != packet.get("packet_id"):
        return AutonomyRunResult("BLOCKED", "selected task and claim identity differ", task_id=task_id, packet=packet)
    try:
        receipt = claim_controller.reconcile_release(task_id, expected_claim=raw_claim, **release_options)
        if receipt is not None:
            return AutonomyRunResult("RELEASE_RECONCILED", "owned release reconciled; requirement acceptance requires its existing reader", task_id, packet, receipt)
        acquired = claim_controller.acquire(raw_claim)
        if acquired["state"] != "ACTIVE":
            return AutonomyRunResult("BLOCKED", "existing attempt requires lifecycle reconciliation", task_id=task_id, packet=packet)
        claim_controller.guard(
            task_id, repository=str(raw_claim["repository"]), worktree=Path(str(raw_claim["worktree"])),
            branch=str(raw_claim["branch"]), head_is_descendant=bool(repository_state.get("head_is_descendant", True)),
            changed_paths=changed_paths, expected_claim=acquired,
        )
    except ClaimError as exc:
        return AutonomyRunResult("BLOCKED", str(exc), task_id=task_id, packet=packet)

    execution = dict(execute(packet))
    if execution.get("status") != "COMPLETE":
        claim_controller.transition(task_id, "VERIFYING", expected_claim=acquired)
        claim_controller.transition(task_id, "ACTIVE", expected_claim=acquired)
        return AutonomyRunResult("VALIDATION_FAILED", str(execution.get("reason", "validation failed")), task_id, packet)

    claim_controller.transition(task_id, "VERIFYING", expected_claim=acquired)
    if execution.get("base_drift") is True:
        claim_controller.transition(task_id, "INTEGRATING", base_drift=True, expected_claim=acquired)
        return AutonomyRunResult("BASE_DRIFT", "base drift detected", task_id, packet)

    claim_controller.transition(task_id, "INTEGRATING", expected_claim=acquired)
    claim_controller.transition(task_id, "RELEASING", expected_claim=acquired)
    try:
        if checkpoint_after_acceptance is not None:
            node = next(item for item in queue_view["items"] if item["id"] == task_id)
            request = _acceptance_request(node, queue_item, raw_claim)
            if not _read_acceptance(acceptance_reader, request):
                _ensure_release_intent(
                    claim_controller, task_id, acquired,
                    owned_resources=cleanup_resources, cleanup=cleanup,
                    cleanup_idempotent=cleanup_idempotent,
                    reconcile_cleanup=reconcile_cleanup,
                )
                return AutonomyRunResult("AWAITING_ACCEPTANCE", "accepted checkpoint requires original requirement acceptance", task_id, packet)
            _ensure_release_intent(
                claim_controller, task_id, acquired,
                owned_resources=cleanup_resources, cleanup=cleanup,
                cleanup_idempotent=cleanup_idempotent,
                reconcile_cleanup=reconcile_cleanup,
            )
            try:
                checkpoint = checkpoint_after_acceptance(request)
            except Exception as error:
                raise ClaimError("accepted checkpoint host control failed") from error
            if type(checkpoint) is not bool:
                raise ClaimError("accepted checkpoint decision must be Boolean")
            if checkpoint:
                return AutonomyRunResult("ACCEPTED_CHECKPOINT", "original requirement accepted; terminal release remains pending", task_id, packet)
        receipt = claim_controller.release(task_id, expected_claim=acquired, **release_options)
        if receipt_backed:
            decision_view, states, _ = _dependency_view(queue_view, queue_items, claims, claim_controller, acceptance_reader)
            if states[task_id] != "DONE":
                return AutonomyRunResult("AWAITING_ACCEPTANCE", "terminal release exists; requirement acceptance is unverified", task_id, packet, receipt)
    except ClaimError as exc:
        return AutonomyRunResult("BLOCKED", str(exc), task_id=task_id, packet=packet)

    return AutonomyRunResult("COMPLETE", "task completed", task_id, packet, receipt,
                             _next_task(decision_view, task_id))


@dataclass(frozen=True)
class AutonomyWorkflowResult:
    status: str
    reason: str
    results: tuple[AutonomyRunResult, ...] = ()


def run_abcd_workflow(*, read_current_inputs: Callable, claim_controller: TaskClaimController,
                      execute: Callable, acceptance_reader: Callable, max_tasks: int,
                      max_elapsed_seconds: float, stop_requested: Callable,
                      monotonic: Callable | None = None, **single_task_options) -> AutonomyWorkflowResult:
    """Finite caller for the existing one-task owner; never a scheduler or grant.

    Host-owned callbacks supply current task inputs, per-job execution permission
    and the qualified acceptance reader. They must bound each synchronous worker
    call; this wrapper can stop another launch, not interrupt a hanging callback.
    Results and previews alone never grant permission or campaign completion.
    """
    import math
    import time

    results = []
    allowed = {"changed_paths", "cleanup_resources", "cleanup", "cleanup_idempotent",
               "reconcile_cleanup", "packet_profile_reader", "campaign_admission_reader",
               "checkpoint_after_acceptance"}
    def number(value):
        try:
            return type(value) in (int, float) and math.isfinite(value)
        except (OverflowError, TypeError, ValueError):
            return False
    if (type(max_tasks) is not int or not 1 <= max_tasks <= 5
            or not number(max_elapsed_seconds) or max_elapsed_seconds <= 0
            or not all(callable(item) for item in (read_current_inputs, execute, acceptance_reader, stop_requested))
            or set(single_task_options) - allowed
            or (single_task_options.get("checkpoint_after_acceptance") is not None
                and not callable(single_task_options["checkpoint_after_acceptance"]))
            or monotonic is not None and not callable(monotonic)):
        return AutonomyWorkflowResult("BLOCKED", "invalid workflow controls")
    clock = monotonic if monotonic is not None else time.monotonic
    previous = None
    def sample():
        nonlocal previous
        value = clock()
        if not number(value) or value < 0 or previous is not None and value < previous:
            raise ClaimError("invalid or regressed workflow clock")
        previous = value
        return value
    seen_tasks, seen_packets = set(), set()
    try:
        start = sample()
        def control():
            stopped = stop_requested()
            if type(stopped) is not bool or stopped:
                raise ClaimError("workflow stop requested or unknown")
            if sample() - start >= max_elapsed_seconds:
                raise ClaimError("workflow deadline reached")
        for _ in range(max_tasks):
            control()
            inputs = read_current_inputs()
            if type(inputs) not in (tuple, list) or len(inputs) != 4:
                raise ClaimError("current task inputs unavailable")
            view, state, queue_items, claims = copy.deepcopy(tuple(inputs))
            if type(queue_items) is not dict:
                raise ClaimError("current task mapping unavailable")
            def guarded_execute(packet):
                control()
                packet_id = packet.get("packet_id")
                selected = [task for task, item in queue_items.items()
                            if type(item) is dict and item.get("packet_id") == packet_id]
                if (type(packet_id) is not str or len(selected) != 1
                        or type(selected[0]) is not str or not selected[0]
                        or selected[0] in seen_tasks or packet_id in seen_packets):
                    return {"status": "BLOCKED", "reason": "duplicate or ambiguous workflow task"}
                # Record before the callback: unknown outcomes may never replay.
                seen_tasks.add(selected[0]); seen_packets.add(packet_id)
                return execute(packet)
            result = run_one_abcd_task(view, state, queue_items, claims,
                claim_controller=claim_controller, execute=guarded_execute,
                acceptance_reader=acceptance_reader, **single_task_options)
            results.append(result)
            if result.status != "COMPLETE":
                return AutonomyWorkflowResult(result.status, result.reason, tuple(results))
            # Always reload the existing owners. next_task remains a preview;
            # accepted work does not authorize the next task's execution.
        return AutonomyWorkflowResult("TASK_LIMIT", "finite workflow task limit reached", tuple(results))
    except Exception as error:
        return AutonomyWorkflowResult("BLOCKED", _public_error_name(error), tuple(results))
