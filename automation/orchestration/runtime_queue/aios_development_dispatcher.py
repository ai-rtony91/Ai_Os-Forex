"""Deterministic, read-only dispatcher for the AI_OS development queue.

The dispatcher converts the normalized runtime queue view into a bounded claim
plan.  It deliberately does not mutate queue state, launch a worker, or grant
an approval; those actions remain behind their existing governed gates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "AIOS_DEVELOPMENT_DISPATCH_PLAN.v1"
QUEUE_SCHEMA = "AIOS_RUNTIME_EXECUTION_QUEUE.v1"
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _item_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("packet_id") or "")


def _blockers(item: dict[str, Any], states: dict[str, str]) -> list[str]:
    blockers: list[str] = []
    item_id = _item_id(item)
    if not item_id:
        blockers.append("MISSING_ITEM_ID")
    if item.get("state") != "QUEUED":
        blockers.append("NOT_QUEUED")
    if item.get("protected_action") is True:
        blockers.append("PROTECTED_ACTION")

    mode = str(item.get("mode", "DRY_RUN")).upper()
    approval_state = str(item.get("approval_state", "NOT_REQUIRED")).upper()
    if mode == "APPLY" and approval_state != "APPROVED":
        blockers.append("APPLY_APPROVAL_REQUIRED")
    elif item.get("approval_required") is True and approval_state != "APPROVED":
        blockers.append("APPROVAL_REQUIRED")

    try:
        counters = (item.get("attempt", 0), item.get("max_attempts", 1))
        if any(isinstance(value, bool) or not isinstance(value, (int, float, str)) for value in counters):
            raise ValueError("invalid_retry_contract")
        attempt, max_attempts = (int(value) for value in counters)
        if attempt < 0 or max_attempts < 1 or any(
            isinstance(value, float) and value != normalized
            for value, normalized in zip(counters, (attempt, max_attempts))
        ):
            raise ValueError("invalid_retry_contract")
    except (TypeError, ValueError, OverflowError):
        blockers.append("INVALID_RETRY_CONTRACT")
    else:
        if attempt >= max_attempts:
            blockers.append("RETRY_LIMIT_REACHED")

    dependencies = item.get("depends_on", [])
    if not isinstance(dependencies, list) or any(
        not isinstance(dependency, str) or not dependency.strip() for dependency in dependencies
    ):
        blockers.append("INVALID_DEPENDENCIES")
    else:
        for dependency in dependencies:
            if states.get(dependency) != "DONE":
                blockers.append(f"DEPENDENCY_NOT_DONE:{dependency}")

    return blockers


def build_dispatch_plan(queue_view: dict[str, Any], *, worker_capacity: int = 1) -> dict[str, Any]:
    """Return a deterministic preview of the next bounded dispatch claims."""
    if isinstance(worker_capacity, bool) or worker_capacity < 0:
        raise ValueError("worker_capacity must be a non-negative integer")

    items = queue_view.get("items", []) if isinstance(queue_view, dict) else []
    input_valid = queue_view.get("schema") == QUEUE_SCHEMA and isinstance(items, list)
    typed_items = [item for item in items if isinstance(item, dict)] if input_valid else []
    states = {_item_id(item): str(item.get("state", "")) for item in typed_items if _item_id(item)}

    evaluated: list[dict[str, Any]] = []
    for position, item in enumerate(typed_items):
        blockers = _blockers(item, states)
        evaluated.append(
            {
                "id": _item_id(item),
                "packet_id": item.get("packet_id"),
                "priority": item.get("priority", "P2"),
                "mode": item.get("mode", "DRY_RUN"),
                "allowed_paths": item.get("allowed_paths", []),
                "forbidden_paths": item.get("forbidden_paths", []),
                "eligible": not blockers,
                "blockers": blockers,
                "_position": position,
            }
        )

    eligible = [item for item in evaluated if item["eligible"]]
    eligible.sort(key=lambda item: (PRIORITY_ORDER.get(str(item["priority"]), 2), item["_position"], item["id"]))
    selected = eligible[:worker_capacity]
    selected_ids = {item["id"] for item in selected}

    for item in eligible[worker_capacity:]:
        item["blockers"] = ["WORKER_CAPACITY_EXHAUSTED"]
        item["eligible"] = False

    public_evaluated = [{key: value for key, value in item.items() if key != "_position"} for item in evaluated]
    claims = [
        {
            "id": item["id"],
            "packet_id": item["packet_id"],
            "mode": item["mode"],
            "allowed_paths": item["allowed_paths"],
            "forbidden_paths": item["forbidden_paths"],
            "claim_status": "READY_FOR_GOVERNED_CLAIM",
        }
        for item in selected
        if item["id"] in selected_ids
    ]

    status = "READY" if claims else "NO_DISPATCHABLE_WORK"
    if not input_valid:
        status = "BLOCKED_INVALID_QUEUE_VIEW"

    return {
        "schema": SCHEMA,
        "mode": "DRY_RUN_READ_ONLY",
        "status": status,
        "source_schema": queue_view.get("schema") if isinstance(queue_view, dict) else None,
        "worker_capacity": worker_capacity,
        "claims": claims,
        "evaluated_items": public_evaluated,
        "safety": {
            "queue_mutation": False,
            "worker_launch": False,
            "approval_mutation": False,
            "file_writes": False,
            "broker_or_live_trading": False,
        },
        "next_safe_action": (
            "Submit each preview claim to the existing governed assignment and approval gates."
            if claims
            else "Resolve the reported blockers; do not launch a worker."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview bounded AI_OS development dispatch claims.")
    parser.add_argument("queue_view", type=Path, help="Normalized runtime queue view JSON file.")
    parser.add_argument("--worker-capacity", type=int, default=1)
    args = parser.parse_args(argv)
    queue_view = json.loads(args.queue_view.read_text(encoding="utf-8"))
    plan = build_dispatch_plan(queue_view, worker_capacity=args.worker_capacity)
    print(json.dumps(plan, indent=2))
    return 0 if plan["status"] != "BLOCKED_INVALID_QUEUE_VIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
