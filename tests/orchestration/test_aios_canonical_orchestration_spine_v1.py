import json
from pathlib import Path

import pytest
from automation.orchestration.aios_canonical_orchestration_spine_v1 import (
    build_dependency_graph, build_orchestration_spine, build_queue_plan,
    build_task_catalog, discover_canonical_components, render_orchestration_report, stable_json,
)

ROOT = Path(__file__).parents[2]


def record(task_id, title, status="active", **extra):
    return {"packet_id": task_id, "title": title, "folder_state": status,
            "source_path": f"packets/{task_id}.json", "required_files": [f"x/{task_id}"], **extra}


def test_components_and_missing_fail_closed(tmp_path):
    assert discover_canonical_components(ROOT)["status"] == "CANONICAL_READY"
    assert discover_canonical_components(tmp_path)["status"] == "BLOCKED_CANONICAL_COMPONENT_MISSING"
    with pytest.raises(FileNotFoundError, match="BLOCKED_CANONICAL_COMPONENT_MISSING"):
        build_orchestration_spine(tmp_path)


def test_aliases_duplicates_and_ownership():
    catalog = build_task_catalog([record("A", "One"), record("A", "Alias"), record("B", "One")])
    assert [x["classification"] for x in catalog] == ["ACTIVE", "ALIAS", "DUPLICATE"]
    assert all(x["controller_owner"] for x in catalog)
    assert sum(x["classification"] not in {"ALIAS", "DUPLICATE"} for x in catalog) == 1


def test_selection_filters_status_dependencies_cycles_and_approval():
    catalog = build_task_catalog([
        record("DONE", "Done", "complete"), record("BLOCK", "Blocked", "blocked"),
        record("READY", "Ready"), record("WAIT", "Wait", dependencies=["MISSING"]),
        record("APPROVE", "Approve", required_approvals=["Human Owner approval"]),
    ])
    graph = build_dependency_graph(catalog); queue = build_queue_plan(catalog, graph)
    assert graph["next_executable_task"] == "READY"
    assert queue["selected_task"]["packet_id"] == "READY"
    assert not queue["queue_mutation_performed"] and not queue["worker_dispatch_performed"]
    cyclic = build_task_catalog([record("A", "A", dependencies=["B"]), record("B", "B", dependencies=["A"])])
    assert build_dependency_graph(cyclic)["cyclic_dependencies"] == ["A", "B"]


def test_spine_queue_preserves_supplied_repository_state():
    catalog = build_task_catalog([record("READY", "Ready")])
    graph = build_dependency_graph(catalog)
    state = {"worktree": "/owned/spine", "branch": "lane/spine"}
    queue = build_queue_plan(catalog, graph, repository_state=state)
    assert queue["selected_task"]["repository_state"] == state


def test_state_is_safe_deterministic_and_schema_valid():
    state = build_orchestration_spine(ROOT, "2026-07-28T00:00:00Z")
    assert stable_json(state) == stable_json(json.loads(stable_json(state)))
    assert state["economic_anchor"]["primary_operator_milestone"] != state["economic_anchor"]["repository_live_trade_milestone"]
    assert state["economic_anchor"]["engineering_hours_status"] in {"VERIFIED", "NOT_VERIFIED"}
    assert all(value is False for value in state["protected_actions"].values())
    assert state["queue_plan"]["queue_mutation_performed"] is False
    assert state["queue_plan"]["worker_dispatch_performed"] is False
    schema = json.loads((ROOT / "schemas/orchestration/aios_canonical_orchestration_spine_v1.schema.json").read_text())
    assert schema["properties"]["schema"]["const"] == state["schema"]
    report = render_orchestration_report(state)
    assert report.startswith("# 🧭 AI_OS CANONICAL ORCHESTRATION SPINE")
    assert "## ▶️ NEXT VERIFIED TASK" in report and "## 💵 FIRST-DOLLAR ANCHOR" in report
    assert "Classification coverage is not repository" in report


def test_runtime_does_not_invoke_network_relay_or_git(monkeypatch):
    import socket, subprocess
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network used"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("git/worker invoked"))
    state = build_orchestration_spine(ROOT, "2026-07-28T00:00:00Z")
    assert state["permissions"]["relay_invocation"] is False
