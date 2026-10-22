import json
from pathlib import Path

import pytest

from automation.orchestration.aios_compound_work_braid_v1 import (
    WorkBraidError, build_compound_work_braid, collapse_duplicates,
    continuation_packet, dependency_graph, form_braids, form_cables,
    make_checkpoint, normalize_strand, reconcile_prs, stable_json,
    validate_resume, validate_state,
)
from automation.orchestration.platform import OrchestrationPlatform


def strand(identifier, **overrides):
    item = {"strand_id": identifier, "title": identifier, "status": "open", "component": "orchestration", "required_paths": [f"x/{identifier}.py"], "validators": ["pytest"]}
    item.update(overrides)
    return item


def test_normalization_and_serialization_are_stable():
    assert normalize_strand(strand("B")) == normalize_strand(strand("B"))
    assert stable_json({"b": 1, "a": 2}) == '{"a":2,"b":1}\n'


def test_duplicate_collapse_and_supersession():
    items = collapse_duplicates([strand("A", title="same"), strand("B", title="same"), strand("C", superseded_by="A")])
    assert [i["normalized_status"] for i in items] == ["OPEN_ACTIONABLE", "DUPLICATE", "SUPERSEDED"]


def test_pr_reconciliation_representation():
    values = reconcile_prs({"1337": {"state": "MERGED"}, "1342": {"state": "OPEN", "classification": "PARTIALLY_REUSABLE"}})
    assert [x["classification"] for x in values] == ["MERGED_OR_ALREADY_PRESENT", "PARTIALLY_REUSABLE", "REMOTE_METADATA_UNAVAILABLE"]


def test_graph_rejects_cycle_and_missing_dependency():
    with pytest.raises(WorkBraidError, match="DEPENDENCY_CYCLE"):
        dependency_graph([normalize_strand(strand("A", dependencies=["B"])), normalize_strand(strand("B", dependencies=["A"]))])
    with pytest.raises(WorkBraidError, match="MISSING_DEPENDENCY"):
        dependency_graph([normalize_strand(strand("A", dependencies=["missing"]))])


def test_graph_preserves_order_and_selects_critical_path():
    items = [normalize_strand(strand("A")), normalize_strand(strand("B", dependencies=["A"]))]
    graph = dependency_graph(items)
    assert graph["edges"] == [{"from": "A", "to": "B"}]
    assert graph["critical_path"][0] == "B"


def test_gates_are_isolated_from_actionable_braids():
    inputs = [strand("external", external_dependency="remote"), strand("owner", owner_decision_required=True), strand("protected", protected_action_required=True)]
    normalized = [normalize_strand(item) for item in inputs]
    assert {i["normalized_status"] for i in normalized} == {"BLOCKED_EXTERNAL", "OWNER_DECISION_REQUIRED"}
    assert form_braids(normalized) == []


def test_braid_and_cable_compatibility_and_conflicting_writes():
    compatible = [normalize_strand(strand("A")), normalize_strand(strand("B"))]
    braids = form_braids(compatible)
    assert len(braids) == 2
    cables = form_cables(braids)
    assert len(cables) == 1
    conflicting = form_braids([normalize_strand(strand("C", root_cause="other", required_paths=["x/A.py"]))])
    assert len(form_cables(braids + conflicting)) == 2


def test_scoring_is_deterministic():
    braids = form_braids([normalize_strand(strand("A")), normalize_strand(strand("B"))])
    assert form_cables(braids) == form_cables(reversed(braids))


def test_checkpoint_resume_drift_and_retry_limit():
    state = {"dependency_graph": {"graph_hash": "g"}, "selected_cable": {"cable_id": "c"}}
    fingerprint = {"head": "h", "branch": "b", "allowed_path_hashes": {}, "repository_root": "/r", "worktree_fingerprint": "f", "worktree_status": ""}
    checkpoint = make_checkpoint(state, fingerprint, completed_stages=["preflight"])
    validate_resume(checkpoint, fingerprint, "g")
    assert checkpoint["remaining_stages"][0] == "state_discovery"
    with pytest.raises(WorkBraidError, match="REPOSITORY_DRIFT"):
        validate_resume(checkpoint, {**fingerprint, "head": "changed"}, "g")
    with pytest.raises(WorkBraidError, match="REPAIR_BUDGET"):
        make_checkpoint(state, fingerprint, repair_pass_count=4)


def test_platform_reuses_controller_and_has_no_protected_authority(tmp_path):
    for folder in ("active", "blocked", "complete"):
        (tmp_path / "automation/orchestration/work_packets" / folder).mkdir(parents=True, exist_ok=True)
    # repository_fingerprint requires a real git repository.
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "seed").write_text("seed")
    subprocess.run(["git", "add", "seed"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=tmp_path, check=True, capture_output=True)
    result = OrchestrationPlatform(tmp_path).compound_work_braid(source_strands=[strand("A")])
    assert result["queue_mutation_performed"] is False
    assert not any(result["protected_actions"].values())


def test_continuation_is_complete_and_has_no_unresolved_placeholders():
    state = {"selected_cable": None}
    fingerprint = {"repository_root": "/repo", "branch": "work"}
    prompt = continuation_packet(state, fingerprint)
    assert prompt.startswith("CODEX-ONLY PROMPT\n")
    for field in ("AI_OS EXECUTION TOKEN", "IDENTITY MARKER", "SUPERVISOR IDENTITY", "PACKET ID", "MODE", "ZONE", "WORKER IDENTITY", "LANE", "WORKTREE", "BRANCH", "ALLOWED PATHS", "FORBIDDEN PATHS", "APPROVAL AUTHORITY", "VALIDATOR CHAIN", "STOP POINT", "MISSION", "PREFLIGHT", "FINAL REPORT FORMAT"):
        assert field in prompt
    assert "{" not in prompt and "TODO" not in prompt and "TBD" not in prompt


def test_real_build_is_deterministic_except_repository_fingerprint():
    root = Path(__file__).resolve().parents[2]
    first = build_compound_work_braid(root, source_strands=[strand("A")])
    second = build_compound_work_braid(root, source_strands=[strand("A")])
    assert first == second
    assert first["packet_execution_performed"] is False
    assert validate_state(first)["status"] == "PASS"
