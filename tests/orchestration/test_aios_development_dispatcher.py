from __future__ import annotations

import pytest

from automation.orchestration.runtime_queue.aios_development_dispatcher import build_dispatch_plan


def _queue(*items: dict) -> dict:
    return {"schema": "AIOS_RUNTIME_EXECUTION_QUEUE.v1", "items": list(items)}


def _item(item_id: str, **overrides: object) -> dict:
    item = {
        "id": item_id,
        "packet_id": item_id,
        "state": "QUEUED",
        "priority": "P2",
        "mode": "DRY_RUN",
        "approval_required": False,
        "approval_state": "NOT_REQUIRED",
        "attempt": 0,
        "max_attempts": 1,
        "depends_on": [],
        "allowed_paths": ["automation/orchestration/runtime_queue"],
        "forbidden_paths": ["RISK_POLICY.md"],
        "protected_action": False,
    }
    item.update(overrides)
    return item


def test_dispatcher_selects_priority_order_with_bounded_capacity() -> None:
    plan = build_dispatch_plan(_queue(_item("p2"), _item("p0", priority="P0")), worker_capacity=1)

    assert plan["status"] == "READY"
    assert [claim["id"] for claim in plan["claims"]] == ["p0"]
    deferred = next(item for item in plan["evaluated_items"] if item["id"] == "p2")
    assert deferred["blockers"] == ["WORKER_CAPACITY_EXHAUSTED"]


def test_dispatcher_requires_completed_dependencies() -> None:
    plan = build_dispatch_plan(_queue(_item("first", state="RUNNING"), _item("second", depends_on=["first"])))

    assert plan["claims"] == []
    second = next(item for item in plan["evaluated_items"] if item["id"] == "second")
    assert "DEPENDENCY_NOT_DONE:first" in second["blockers"]


def test_dispatcher_allows_dependency_after_done() -> None:
    plan = build_dispatch_plan(_queue(_item("first", state="DONE"), _item("second", depends_on=["first"])))

    assert [claim["id"] for claim in plan["claims"]] == ["second"]


@pytest.mark.parametrize(
    ("overrides", "blocker"),
    [
        ({"mode": "APPLY", "approval_required": True, "approval_state": "PENDING"}, "APPLY_APPROVAL_REQUIRED"),
        ({"protected_action": True}, "PROTECTED_ACTION"),
        ({"attempt": 2, "max_attempts": 2}, "RETRY_LIMIT_REACHED"),
    ],
)
def test_dispatcher_fails_closed_for_governed_blockers(overrides: dict, blocker: str) -> None:
    plan = build_dispatch_plan(_queue(_item("blocked", **overrides)))

    assert plan["status"] == "NO_DISPATCHABLE_WORK"
    assert blocker in plan["evaluated_items"][0]["blockers"]
    assert plan["safety"]["worker_launch"] is False


def test_dispatcher_allows_approved_apply_preview_without_executing() -> None:
    plan = build_dispatch_plan(
        _queue(_item("approved", mode="APPLY", approval_required=True, approval_state="APPROVED"))
    )

    assert plan["claims"][0]["claim_status"] == "READY_FOR_GOVERNED_CLAIM"
    assert plan["safety"]["queue_mutation"] is False


def test_dispatcher_rejects_invalid_queue_schema() -> None:
    plan = build_dispatch_plan({"schema": "wrong", "items": []})

    assert plan["status"] == "BLOCKED_INVALID_QUEUE_VIEW"


def test_dispatcher_rejects_negative_or_boolean_capacity() -> None:
    with pytest.raises(ValueError):
        build_dispatch_plan(_queue(), worker_capacity=-1)
    with pytest.raises(ValueError):
        build_dispatch_plan(_queue(), worker_capacity=True)


def test_dispatcher_cannot_claim_invalid_explicit_constraints() -> None:
    retry = build_dispatch_plan(_queue(_item("invalid", attempt=-1)))
    assert retry["claims"] == []
    assert "INVALID_RETRY_CONTRACT" in retry["evaluated_items"][0]["blockers"]
    dependency = build_dispatch_plan(_queue(_item("False", state="DONE"), _item("next", depends_on=[False])))
    assert dependency["claims"] == []
    assert "INVALID_DEPENDENCIES" in dependency["evaluated_items"][1]["blockers"]
