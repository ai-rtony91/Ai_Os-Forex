from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from automation.orchestration.aios_abcd_autonomy_runner import run_one_abcd_task
from automation.orchestration.claims.aios_task_claim_control import SCHEMA_VERSION, TaskClaimController


def _identity(task: str) -> dict[str, str]:
    return {
        "mission_id": "MISSION-AIOS", "mission_name": "AIOS completion",
        "program_id": "PROGRAM-ORCH", "program_name": "Orchestration",
        "epic_id": "EPIC-ABCD", "epic_name": "ABCD lifecycle",
        "bucket_id": "BUCKET-RUNTIME", "bucket_name": "Runtime queue",
        "packet_id": task, "packet_name": "ABCD connector",
        "supervisor_identity": "Anthony", "zone": "EAST", "worker_identity": "EAST_OCC_01",
        "lane": "abcd-connector", "stop_point": "Return one result and stop.",
    }


def _item(task: str) -> dict:
    return {
        "queue_schema": "AIOS_RUNTIME_EXECUTION_QUEUE.v1", "packet_id": task,
        "packet_identity": _identity(task), "mode": "APPLY", "approval_state": "APPROVED",
        "approval_authority": "Anthony approved bounded local apply.",
        "commit_message": "test: exercise connector", "pr_authority": "One reviewed PR; do not merge.",
        "mission": "Exercise the bounded ABCD connector.",
        "allowed_paths": ["src/one"], "forbidden_paths": ["RISK_POLICY.md"],
        "validators": ["pytest focused"], "depends_on": [], "attempt": 0, "max_attempts": 1,
        "protected_action": False,
    }


def _claim(root: Path, task: str = "one", **updates: object) -> dict:
    now = datetime.now(timezone.utc)
    value = {
        "schema_version": SCHEMA_VERSION, "task_id": task, "packet_id": task,
        "repository": "ai-rtony91/Ai_Os", "supervisor": "Anthony", "worker": f"worker-{task}",
        "worktree": str(root), "branch": f"task/{task}", "base_branch": "main", "base_sha": "a" * 40,
        "claimed_paths": ["src/one"], "ports": [], "processes_or_services": [], "containers": [],
        "cache_dirs": [f".cache/{task}"], "temp_dirs": [f"tmp/{task}"], "log_dirs": [f"logs/{task}"],
        "env_files": [f"config/{task}.env"], "databases_or_schemas": [], "deployment_targets": [],
        "pull_request": "", "state": "ACTIVE", "acquired_at": now.isoformat(),
        "heartbeat_at": now.isoformat(), "expires_at": (now + timedelta(hours=1)).isoformat(),
        "cleanup_policy": "owned-only", "receipt_path": str(root / "receipts" / f"{task}.json"),
    }
    value.update(updates)
    return value


def _inputs(tmp_path: Path, *, two: bool = False):
    items = [{"id": "one", "packet_id": "one", "state": "QUEUED", "priority": "P0", "mode": "APPLY",
              "approval_required": True, "approval_state": "APPROVED", "attempt": 0, "max_attempts": 1,
              "depends_on": [], "allowed_paths": ["src/one"], "forbidden_paths": [], "protected_action": False}]
    if two:
        items.append({**items[0], "id": "two", "packet_id": "two", "priority": "P1"})
    queue = {"schema": "AIOS_RUNTIME_EXECUTION_QUEUE.v1", "items": items}
    state = {"worktree": str(tmp_path), "branch": "task/one", "status_lines": [],
             "dependency_states": {}, "head_is_descendant": True}
    queue_items = {name: _item(name) for name in ("one", "two")}
    claims = {name: _claim(tmp_path, name) for name in ("one", "two")}
    return queue, state, queue_items, claims


def test_complete_success_path(tmp_path: Path) -> None:
    args = _inputs(tmp_path)
    result = run_one_abcd_task(*args, claim_controller=TaskClaimController(tmp_path / "board.json"),
                               execute=lambda _: {"status": "COMPLETE"}, changed_paths=["src/one/file.py"])
    assert result.status == "COMPLETE"
    assert result.receipt_path and result.receipt_path.exists()


def test_validation_failed_returns_claim_to_active(tmp_path: Path) -> None:
    args = _inputs(tmp_path); controller = TaskClaimController(tmp_path / "board.json")
    result = run_one_abcd_task(*args, claim_controller=controller,
                               execute=lambda _: {"status": "FAILED", "reason": "validator failed"})
    assert result.status == "VALIDATION_FAILED"
    assert controller.guard("one", repository="ai-rtony91/Ai_Os", worktree=tmp_path,
                            branch="task/one", head_is_descendant=True, changed_paths=[])["state"] == "ACTIVE"


def test_base_drift_returns_claim_to_active(tmp_path: Path) -> None:
    args = _inputs(tmp_path); controller = TaskClaimController(tmp_path / "board.json")
    result = run_one_abcd_task(*args, claim_controller=controller,
                               execute=lambda _: {"status": "COMPLETE", "base_drift": True})
    assert result.status == "BASE_DRIFT"
    assert controller.guard("one", repository="ai-rtony91/Ai_Os", worktree=tmp_path,
                            branch="task/one", head_is_descendant=True, changed_paths=[])["state"] == "ACTIVE"


def test_collision_reports_complete_canonical_reason(tmp_path: Path) -> None:
    args = _inputs(tmp_path); controller = TaskClaimController(tmp_path / "board.json")
    controller.acquire(_claim(tmp_path, "owner", branch="task/one"))
    result = run_one_abcd_task(*args, claim_controller=controller, execute=lambda _: {"status": "COMPLETE"})
    assert result.reason == "claim blocked: branch:owner, claimed_path:owner, worktree_path:owner"


def test_one_task_execution_limit(tmp_path: Path) -> None:
    args = _inputs(tmp_path, two=True); executed = []
    result = run_one_abcd_task(*args, claim_controller=TaskClaimController(tmp_path / "board.json"),
                               execute=lambda packet: executed.append(packet["packet_id"]) or {"status": "COMPLETE"})
    assert executed == ["one"]
    assert result.status == "COMPLETE"


def test_cleanup_ownership_isolation(tmp_path: Path) -> None:
    args = _inputs(tmp_path); cleaned = []
    result = run_one_abcd_task(*args, claim_controller=TaskClaimController(tmp_path / "board.json"),
                               execute=lambda _: {"status": "COMPLETE"},
                               cleanup_resources={"containers": ["not-owned"]},
                               cleanup=lambda field, value: cleaned.append((field, value)))
    assert result.status == "BLOCKED"
    assert result.reason == "cleanup requested for resource not owned by task"
    assert cleaned == []


def test_next_eligible_task_is_returned_but_not_executed(tmp_path: Path) -> None:
    args = _inputs(tmp_path, two=True); executed = []
    result = run_one_abcd_task(*args, claim_controller=TaskClaimController(tmp_path / "board.json"),
                               execute=lambda packet: executed.append(packet["packet_id"]) or {"status": "COMPLETE"})
    assert result.next_task and result.next_task["id"] == "two"
    assert executed == ["one"]
