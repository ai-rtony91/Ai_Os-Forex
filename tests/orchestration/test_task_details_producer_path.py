"""Public synthetic records through real read-only producer/planner functions."""
from copy import deepcopy
import json

import pytest

from automation.orchestration import aios_candidate_packet_evidence_adapter as adapter
from automation.orchestration import aios_packet_queue_planner as planner
from automation.orchestration import aios_work_countdown_v1 as countdown
from automation.orchestration import aios_canonical_orchestration_spine_v1 as spine


def packet(tmp_path, **changes):
    value = {
        "packet_id": "PKT-LOCAL-DOCUMENT-CHECK",
        "title": "Check local document formatting",
        "status": "ready",
        "priority": "high",
        "risk_level": "low",
        "required_files": ["docs/local-format.md"],
        "blocked_files": [],
        "required_approvals": [],
        "validators": ["python -m pytest tests/test_local_format.py -q"],
        "dependencies": [],
        "conflicts": [],
        "safety_flags": [],
        # Synthetic test branch; no Git or worker operation is performed.
        "repository_state": {"worktree": str(tmp_path), "branch": "test/local-format"},
    }
    value.update(changes)
    return value


def adapter_plan(record):
    return planner.build_packet_queue_planner(
        adapter.build_candidate_packet_evidence({"packets": [record]})
    )


def assert_no_execution(result):
    assert result["commands_executed"] == []
    assert result["files_written"] == []
    assert result["workers_dispatched"] is False
    assert result["queues_mutated"] is False
    assert result["approvals_mutated"] is False


def test_adapter_preserves_details_and_real_planner_can_prepare_preview(tmp_path):
    record = packet(tmp_path)
    original = deepcopy(record)
    result = adapter_plan(record)
    assert result["codex_ready_packet_preview"]["packet_ready"] is True
    assert result["selected_packet"]["repository_state"] == record["repository_state"]
    assert record == original
    assert_no_execution(result)


@pytest.mark.parametrize("state", [None, {}, [], "bad", {"worktree": "relative", "branch": "x"},
                                  {"worktree": "/local", "branch": "unknown"},
                                  {"worktree": "/local", "branch": "has space"}])
def test_bad_details_are_retained_and_strict_planner_still_refuses(tmp_path, state):
    record = packet(tmp_path, repository_state=state)
    normalized = adapter.build_candidate_packet_evidence({"packets": [record]})
    assert normalized["candidate_packets"][0]["repository_state"] == state
    result = planner.build_packet_queue_planner(normalized)
    assert result["codex_ready_packet_preview"]["packet_ready"] is False
    assert_no_execution(result)


def test_valid_details_do_not_make_missing_checks_ready(tmp_path):
    result = adapter_plan(packet(tmp_path, validators=[]))
    assert result["codex_ready_packet_preview"]["reason_code"] == "validators_missing"
    assert result["codex_ready_packet_preview"]["packet_ready"] is False


def test_countdown_uses_packet_details_without_replacing_with_global_snapshot(tmp_path):
    record = packet(tmp_path)
    result = countdown.build_work_countdown(
        {"packets": [record], "authoritative_packet_inventory": True},
        repository_state={"worktree": "/different-folder", "branch": "different-branch"},
    )
    preview = result["queue_plan"]["codex_ready_packet_preview"]
    assert preview["packet_ready"] is True
    assert preview["repository_state"] == record["repository_state"]
    assert_no_execution(result["queue_plan"])


def test_inventory_reader_preserves_details_for_adapter_planner(tmp_path):
    record = packet(tmp_path, status="active")
    directory = tmp_path / "automation/orchestration/work_packets/active"
    directory.mkdir(parents=True)
    (directory / "local.json").write_text(json.dumps(record), encoding="utf-8")
    inventory = countdown.load_canonical_work_packet_inventory(tmp_path)
    loaded = inventory["records"][0]
    assert loaded["repository_state"] == record["repository_state"]
    # Inventory folder status stays active. This check does not make it ready.
    assert loaded["status"] == "active"
    result = adapter_plan({**loaded, "status": "ready"})
    assert result["codex_ready_packet_preview"]["packet_ready"] is True
    assert result["codex_ready_packet_preview"]["repository_state"] == record["repository_state"]
    assert_no_execution(result)


def spine_queue(record):
    catalog = spine.build_task_catalog([{**record, "folder_state": "active", "source_path": "packets/local.json"}])
    graph = spine.build_dependency_graph(catalog)
    return spine.build_queue_plan(catalog, graph)


def test_spine_preserves_task_scope_details_and_checks(tmp_path):
    record = packet(tmp_path)
    queue = spine_queue(record)
    selected = queue["selected_task"]
    assert selected["repository_state"] == record["repository_state"]
    assert selected["required_files"] == record["required_files"]
    assert selected["validators"] == record["validators"]
    preview = planner.build_packet_queue_planner([selected])["codex_ready_packet_preview"]
    assert preview["packet_ready"] is True
    assert queue["worker_dispatch_performed"] is False
    assert queue["queue_mutation_performed"] is False


@pytest.mark.parametrize("change", [{"safety_flags": ["secret path"]},
                                    {"conflicts": ["overlapping owner"]},
                                    {"blocked_files": ["docs/local-format.md"]}])
def test_spine_does_not_drop_restrictions_before_selection(tmp_path, change):
    queue = spine_queue(packet(tmp_path, **change))
    assert queue["selected_task"] is None


def test_spine_missing_checks_remain_not_ready(tmp_path):
    queue = spine_queue(packet(tmp_path, validators=[]))
    result = planner.build_packet_queue_planner([queue["selected_task"]])
    assert result["codex_ready_packet_preview"]["packet_ready"] is False


def test_missing_details_are_not_filled_from_process_or_global_state(tmp_path):
    record = packet(tmp_path)
    record.pop("repository_state")
    result = countdown.build_work_countdown(
        {"packets": [record], "authoritative_packet_inventory": True},
        repository_state={"worktree": str(tmp_path), "branch": "test/global-only"},
    )
    assert result["queue_plan"]["codex_ready_packet_preview"]["packet_ready"] is False


@pytest.mark.parametrize("state", [None, "invalid-state", {"worktree": "/local", "branch": "unknown"}])
def test_inventory_route_retains_bad_details_for_strict_refusal(tmp_path, state):
    record = packet(tmp_path, status="active", repository_state=state)
    directory = tmp_path / "automation/orchestration/work_packets/active"
    directory.mkdir(parents=True)
    (directory / "local.json").write_text(json.dumps(record), encoding="utf-8")
    loaded = countdown.load_canonical_work_packet_inventory(tmp_path)["records"][0]
    assert loaded["repository_state"] == state
    result = adapter_plan({**loaded, "status": "ready"})
    assert result["codex_ready_packet_preview"]["packet_ready"] is False


@pytest.mark.parametrize("state", [None, "invalid-state", {"worktree": "/local", "branch": "unknown"}])
def test_spine_route_retains_bad_details_for_strict_refusal(tmp_path, state):
    queue = spine_queue(packet(tmp_path, repository_state=state))
    assert queue["selected_task"]["repository_state"] == state
    result = planner.build_packet_queue_planner([queue["selected_task"]])
    assert result["codex_ready_packet_preview"]["packet_ready"] is False


def full_spine(tmp_path, records):
    for relative in spine.REQUIRED_COMPONENTS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# public synthetic component\n", encoding="utf-8")
    directory = tmp_path / "automation/orchestration/work_packets/active"
    directory.mkdir(parents=True, exist_ok=True)
    for index, record in enumerate(records):
        (directory / f"packet-{index}.json").write_text(json.dumps(record), encoding="utf-8")
    return spine.build_orchestration_spine(tmp_path)


@pytest.mark.parametrize("change", [
    {"safety_flags": ["secret path"]},
    {"conflicts": ["overlapping owner"]},
    {"blocked_files": ["docs/local-format.md"]},
    {"validators": []},
    {"repository_state": None},
    {"repository_state": {"worktree": "relative", "branch": "test/local-format"}},
])
def test_full_spine_never_advertises_planner_refusal_as_ready(tmp_path, change):
    state = full_spine(tmp_path, [packet(tmp_path, **change)])
    assert state["status"] == "BLOCKED"
    assert state["next_verified_task"] is None
    assert state["economic_anchor"]["next_verified_task"] is None
    assert state["dependency_graph"]["next_executable_task"] is None
    assert state["dependency_graph"]["ready_nodes"] == []
    assert state["queue_plan"]["ready_queue"] == []
    assert "PKT-LOCAL-DOCUMENT-CHECK" in state["queue_plan"]["blocked_queue"]
    assert "NONE_VERIFIED" in spine.render_orchestration_report(state)
    assert all(value is False for value in state["protected_actions"].values())


def test_full_spine_selects_safe_task_instead_of_rejected_first_id(tmp_path):
    rejected = packet(tmp_path, packet_id="A-REJECTED", title="Rejected task",
                      conflicts=["overlapping owner"])
    ready = packet(tmp_path, packet_id="Z-READY", title="Ready task",
                   required_files=["docs/other-local-format.md"])
    state = full_spine(tmp_path, [rejected, ready])
    assert state["status"] == "READY"
    assert state["next_verified_task"] == "Z-READY"
    assert state["economic_anchor"]["next_verified_task"] == "Z-READY"
    assert state["dependency_graph"]["next_executable_task"] == "Z-READY"
    assert state["dependency_graph"]["ready_nodes"] == ["Z-READY"]
    assert state["queue_plan"]["ready_queue"] == ["Z-READY"]
    assert "A-REJECTED" in state["queue_plan"]["blocked_queue"]


def test_full_spine_uses_actual_planner_priority_for_next_task(tmp_path):
    low = packet(tmp_path, packet_id="A-LOW", title="Low priority task", priority="low")
    high = packet(tmp_path, packet_id="Z-HIGH", title="High priority task",
                  priority="high", required_files=["docs/other-local-format.md"])
    state = full_spine(tmp_path, [low, high])
    assert state["queue_plan"]["selected_task"]["packet_id"] == "Z-HIGH"
    assert state["next_verified_task"] == "Z-HIGH"
    assert state["dependency_graph"]["next_executable_task"] == "Z-HIGH"
