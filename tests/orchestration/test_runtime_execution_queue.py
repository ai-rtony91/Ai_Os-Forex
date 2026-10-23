"""Tests for the canonical runtime execution queue adapter + integrity validator."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QUEUE = REPO_ROOT / "automation" / "orchestration" / "runtime_queue" / "aios_runtime_execution_queue.py"
VALIDATOR = REPO_ROOT / "automation" / "validators" / "aios_runtime_execution_queue_validator.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _q():
    return _load("aios_runtime_execution_queue", QUEUE)


def _v():
    return _load("aios_runtime_execution_queue_validator", VALIDATOR)


def _seed(root: Path):
    # relay inbox: dir of per-task json
    inbox = root / "relay" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "t1.task.json").write_text(json.dumps({"id": "t1", "status": "pending", "worker": "west"}), encoding="utf-8")
    (inbox / "t2.task.json").write_text(json.dumps({"id": "t2", "status": "running", "kind": "build"}), encoding="utf-8")
    # command queue: list file
    cq = root / "automation" / "orchestration" / "command_queue"
    cq.mkdir(parents=True)
    (cq / "AIOS_COMMAND_QUEUE.json").write_text(json.dumps({"items": [{"id": "c1", "state": "done"}]}), encoding="utf-8")
    # worker task queue: bare list
    wq = root / "automation" / "operator" / "worker_queue"
    wq.mkdir(parents=True)
    (wq / "WORKER_TASK_QUEUE_V1.json").write_text(json.dumps([{"id": "w1", "state": "waiting"}]), encoding="utf-8")


def test_normalizes_and_dedupes_across_sources(tmp_path):
    q = _q()
    _seed(tmp_path)
    view = q.build_queue_view(tmp_path)
    assert view["schema"] == "AIOS_RUNTIME_EXECUTION_QUEUE.v1"
    assert view["item_count"] == 4
    ids = {it["id"] for it in view["items"]}
    assert ids == {"t1", "t2", "c1", "w1"}
    # state synonyms normalized
    states = {it["id"]: it["state"] for it in view["items"]}
    assert states["t1"] == "QUEUED" and states["t2"] == "RUNNING"
    assert states["c1"] == "DONE" and states["w1"] == "QUEUED"
    assert set(view["sources_read"]) == {"relay_inbox", "command_queue", "worker_task_queue"}


def test_stale_state_normalized_to_deferred(tmp_path):
    q, v = _q(), _v()
    cq = tmp_path / "automation" / "orchestration" / "command_queue"
    cq.mkdir(parents=True)
    # PowerShell-written JSON with a BOM and a real AI_OS "STALE" state
    cq.joinpath("AIOS_COMMAND_QUEUE.json").write_text(
        "﻿" + json.dumps({"items": [{"id": "cmd1", "state": "STALE"}]}), encoding="utf-8")
    view = q.build_queue_view(tmp_path)
    assert view["item_count"] == 1
    assert view["items"][0]["state"] == "DEFERRED"
    assert view["items"][0]["raw_state"] == "STALE"
    # validator passes: STALE is a known parked state, not an integrity violation
    assert v.validate_queue_view(view)["status"] == "PASS"


def test_id_collision_recorded_across_sources(tmp_path):
    q = _q()
    _seed(tmp_path)
    # add a command-queue item that collides with relay t1
    cq = tmp_path / "automation" / "orchestration" / "command_queue" / "AIOS_COMMAND_QUEUE.json"
    cq.write_text(json.dumps({"items": [{"id": "t1", "state": "done"}]}), encoding="utf-8")
    view = q.build_queue_view(tmp_path)
    assert any(c["id"] == "t1" for c in view["id_collisions"])
    coll = next(c for c in view["id_collisions"] if c["id"] == "t1")
    assert "relay_inbox" in coll["sources"] and "command_queue" in coll["sources"]


def test_protected_item_flagged(tmp_path):
    q = _q()
    _seed(tmp_path)
    inbox = tmp_path / "relay" / "inbox"
    (inbox / "danger.task.json").write_text(json.dumps({"id": "d1", "state": "pending", "provider_command": "git push origin main"}), encoding="utf-8")
    view = q.build_queue_view(tmp_path)
    d1 = next(it for it in view["items"] if it["id"] == "d1")
    assert d1["protected_action"] is True
    assert view["protected_item_count"] >= 1


def test_autonomous_development_fields_are_normalized(tmp_path):
    q = _q()
    inbox = tmp_path / "relay" / "inbox"
    inbox.mkdir(parents=True)
    inbox.joinpath("build.task.json").write_text(json.dumps({
        "id": "build-2",
        "packet_id": "PKT-BUILD-2",
        "status": "pending",
        "priority": "p1",
        "mode": "dry_run",
        "depends_on": ["build-1", "build-1"],
        "attempt_count": 1,
        "max_attempts": 3,
        "branch": "feature/build-2",
        "worktree": "/workspace/build-2",
        "allowed_paths": ["src/"],
        "forbidden_paths": ["RISK_POLICY.md"],
    }), encoding="utf-8")

    view = q.build_queue_view(tmp_path)
    item = view["items"][0]
    assert item["priority"] == "P1"
    assert item["mode"] == "DRY_RUN"
    assert item["depends_on"] == ["build-1"]
    assert item["attempt"] == 1 and item["max_attempts"] == 3
    assert item["approval_state"] == "NOT_REQUIRED"
    assert item["packet_id"] == "PKT-BUILD-2"
    assert view["contract"]["purpose"] == "autonomous_development_workflow"


def test_validator_blocks_apply_without_explicit_approval(tmp_path):
    q, v = _q(), _v()
    inbox = tmp_path / "relay" / "inbox"
    inbox.mkdir(parents=True)
    inbox.joinpath("apply.task.json").write_text(json.dumps({
        "id": "apply-1", "mode": "APPLY", "approval_state": "PENDING"
    }), encoding="utf-8")

    result = v.validate_queue_view(q.build_queue_view(tmp_path))
    assert result["status"] == "BLOCK"
    assert "RQV-006-APPLY-APPROVAL" in result["blocking_findings"]


def test_validator_blocks_invalid_retry_or_self_dependency():
    q, v = _q(), _v()
    item = q.normalize_item({"id": "bad"}, "test", 0)
    item["depends_on"] = ["bad"]
    item["attempt"] = 2
    item["max_attempts"] = 1
    view = {
        "schema": q.SCHEMA,
        "contract": {"purpose": "autonomous_development_workflow"},
        "items": [item],
        "id_collisions": [],
    }

    result = v.validate_queue_view(view)
    assert result["status"] == "BLOCK"
    assert "RQV-005-AUTONOMY-CONTRACT" in result["blocking_findings"]


def test_missing_and_malformed_sources_are_failsoft(tmp_path):
    q = _q()
    # only a malformed command queue, nothing else
    cq = tmp_path / "automation" / "orchestration" / "command_queue"
    cq.mkdir(parents=True)
    (cq / "AIOS_COMMAND_QUEUE.json").write_text("{ not json", encoding="utf-8")
    view = q.build_queue_view(tmp_path)
    assert view["item_count"] == 0
    assert "command_queue" in view["sources_malformed"]
    assert "relay_inbox" in view["sources_missing"]


def test_adapter_mutates_no_source(tmp_path):
    q = _q()
    _seed(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    q.build_queue_view(tmp_path)
    after = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert before == after  # observe-only: no source file changed


def test_validator_pass_on_clean_queue(tmp_path):
    q, v = _q(), _v()
    _seed(tmp_path)
    view = q.build_queue_view(tmp_path)
    res = v.validate_queue_view(view)
    assert res["status"] == "PASS"
    assert res["approves_protected_action"] is False


def test_validator_blocks_protected_item(tmp_path):
    q, v = _q(), _v()
    _seed(tmp_path)
    (tmp_path / "relay" / "inbox" / "danger.task.json").write_text(
        json.dumps({"id": "d1", "state": "pending", "provider_command": "place_order live"}), encoding="utf-8")
    view = q.build_queue_view(tmp_path)
    res = v.validate_queue_view(view)
    assert res["status"] == "BLOCK"
    assert "RQV-003-NO-PROTECTED-ITEM" in res["blocking_findings"]


def test_validator_blocks_unknown_state():
    v = _v()
    view = {"schema": "AIOS_RUNTIME_EXECUTION_QUEUE.v1",
            "items": [{"id": "x", "state": "WEIRD", "protected_action": False, "synthetic_id": False}],
            "id_collisions": []}
    res = v.validate_queue_view(view)
    assert res["status"] == "BLOCK"
    assert "RQV-002-CANONICAL-STATES" in res["blocking_findings"]


def test_validator_blocks_malformed_view():
    v = _v()
    res = v.validate_queue_view({"not": "a view"})
    assert res["status"] == "BLOCK"
    assert "RQV-000-VIEW-SHAPE" in res["blocking_findings"]


def test_write_report_only_under_reports(tmp_path):
    q = _q()
    _seed(tmp_path)
    view = q.build_queue_view(tmp_path)
    out = q.write_report(view, output_dir=tmp_path / "Reports" / "runtime_queue")
    assert Path(out["json_path"]).exists() and Path(out["md_path"]).exists()
    leftovers = [p.name for p in (tmp_path / "Reports" / "runtime_queue").iterdir() if p.name.startswith(".") or p.name.endswith(".tmp")]
    assert leftovers == []


def test_source_normalization_preserves_invalid_scheduling_constraints_as_blocked():
    q, v = _q(), _v()
    for changes in ({"depends_on": "PRIOR"}, {"attempt": -1}, {"max_attempts": 0}):
        item = q.normalize_item({"id": "bad", "state": "QUEUED", **changes}, "owned", 0)
        assert item["state"] == "BLOCKED"
        assert item["source_scheduling_constraints"] == changes
        result = v.validate_queue_view({"schema": q.SCHEMA, "contract": {"purpose": "autonomous_development_workflow"}, "items": [item], "id_collisions": []})
        assert result["status"] == "BLOCK"
