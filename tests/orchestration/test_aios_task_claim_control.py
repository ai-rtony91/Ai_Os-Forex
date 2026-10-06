from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[2] / "automation/orchestration/claims/aios_task_claim_control.py"
SPEC = importlib.util.spec_from_file_location("claim_control", MODULE)
claim_control = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = claim_control
SPEC.loader.exec_module(claim_control)


def claim(root: Path, task: str = "one", **updates):
    now = datetime.now(timezone.utc)
    value = {
        "schema_version": claim_control.SCHEMA_VERSION, "task_id": task, "packet_id": f"packet-{task}",
        "repository": "ai-rtony91/Ai_Os", "supervisor": "Anthony", "worker": f"worker-{task}",
        "worktree": str(root), "branch": f"task/{task}", "base_branch": "main", "base_sha": "a" * 40,
        "claimed_paths": [f"src/{task}"], "ports": [], "processes_or_services": [], "containers": [],
        "cache_dirs": [f".cache/{task}"], "temp_dirs": [f"tmp/{task}"], "log_dirs": [f"logs/{task}"],
        "env_files": [f"config/{task}.env"], "databases_or_schemas": [f"db_{task}"],
        "deployment_targets": [f"target-{task}"], "pull_request": f"pr-{task}", "state": "ACTIVE",
        "acquired_at": now.isoformat(), "heartbeat_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(), "cleanup_policy": "owned-only",
        "receipt_path": str(root / "receipts" / f"{task}.json"),
    }
    value.update(updates)
    return value


def controller(tmp_path):
    return claim_control.TaskClaimController(tmp_path / "active.json")


@pytest.mark.parametrize(
    "field,value,label",
    [("worktree", None, "worktree_path"), ("branch", "task/one", "branch"),
     ("ports", [8123], "port"), ("processes_or_services", ["svc"], "process_or_service"),
     ("containers", ["box"], "container"), ("cache_dirs", [".cache/shared"], "cache_dir"),
     ("temp_dirs", ["tmp/shared"], "temp_dir"), ("env_files", ["config/shared.env"], "env_file"),
     ("databases_or_schemas", ["shared"], "database_or_schema"),
     ("deployment_targets", ["shared"], "deployment_target")],
)
def test_duplicate_resources_blocked(tmp_path, field, value, label):
    first = claim(tmp_path)
    second = claim(tmp_path, "two")
    if field == "worktree":
        second["worktree"] = first["worktree"]
    else:
        first[field] = value
        second[field] = value
        if field not in {"cache_dirs", "temp_dirs", "env_files"}:
            second["worktree"] = str(tmp_path / "other")
            Path(second["worktree"]).mkdir()
    candidate = claim_control.normalize_claim(second)
    assert any(item.startswith(label) for item in claim_control.collisions(candidate, [first]))


def test_parent_child_and_windows_case_paths_collide(tmp_path):
    first = claim(tmp_path, claimed_paths=["Source/Feature"])
    second = claim(tmp_path, "two", claimed_paths=["source/feature/child"])
    found = claim_control.collisions(claim_control.normalize_claim(second), [first])
    assert "claimed_path:one" in found


def test_traversal_and_symlink_escape_rejected(tmp_path):
    with pytest.raises(claim_control.ClaimError, match="traversal"):
        claim_control.normalize_claim(claim(tmp_path, claimed_paths=["../escape"]))
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    original_resolve = claim_control.Path.resolve
    def fake_resolve(self, *args, **kwargs):
        if self.as_posix().casefold().endswith("/link/file.py"):
            return (outside / "file.py").resolve(strict=False)
        return original_resolve(self, *args, **kwargs)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(claim_control.Path, "resolve", fake_resolve)
    with pytest.raises(claim_control.ClaimError, match="escapes"):
        claim_control.normalize_claim(claim(tmp_path, claimed_paths=["link/file.py"]))
    monkeypatch.undo()


def test_disjoint_claims_are_accepted_atomically(tmp_path):
    ctl = controller(tmp_path)
    ctl.acquire(claim(tmp_path, "one"))
    other = tmp_path / "other"
    other.mkdir()
    ctl.acquire(claim(other, "two"))
    assert len(json.loads(ctl.board_path.read_text())["claims"]) == 2
    assert not ctl.board_path.with_suffix(".json.lock").exists()


def test_only_one_repository_integration_claim(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    first = claim(tmp_path, state="INTEGRATING")
    second = claim_control.normalize_claim(claim(other, "two", state="INTEGRATING"))
    assert "repository_integration:one" in claim_control.collisions(second, [first])


def test_base_drift_returns_task_to_active(tmp_path):
    ctl = controller(tmp_path)
    ctl.acquire(claim(tmp_path))
    ctl.transition("one", "VERIFYING")
    assert ctl.transition("one", "INTEGRATING", base_drift=True)["state"] == "ACTIVE"


@pytest.mark.parametrize("key,value,error", [("worktree", "other", "wrong worktree"), ("branch", "wrong", "wrong branch")])
def test_execution_guard_rejects_wrong_identity(tmp_path, key, value, error):
    ctl = controller(tmp_path)
    ctl.acquire(claim(tmp_path))
    kwargs = dict(repository="ai-rtony91/Ai_Os", worktree=tmp_path, branch="task/one", head_is_descendant=True, changed_paths=["src/one/file.py"])
    if key == "worktree":
        kwargs[key] = tmp_path / value
        kwargs[key].mkdir()
    else:
        kwargs[key] = value
    with pytest.raises(claim_control.ClaimError, match=error):
        ctl.guard("one", **kwargs)


def test_execution_guard_rejects_unauthorized_source_path(tmp_path):
    ctl = controller(tmp_path)
    ctl.acquire(claim(tmp_path))
    with pytest.raises(claim_control.ClaimError, match="outside claimed"):
        ctl.guard("one", repository="ai-rtony91/Ai_Os", worktree=tmp_path, branch="task/one", head_is_descendant=True, changed_paths=["unowned/file.py"])


def test_interrupted_atomic_write_preserves_board(tmp_path, monkeypatch):
    path = tmp_path / "board.json"
    path.write_text('{"claims": []}\n')
    monkeypatch.setattr(claim_control.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("interrupt")))
    with pytest.raises(OSError):
        claim_control._atomic_write(path, {"claims": [{"task_id": "new"}]})
    assert json.loads(path.read_text()) == {"claims": []}


def test_stale_claim_fails_closed(tmp_path):
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    stale = claim(tmp_path, acquired_at=old.isoformat(), heartbeat_at=old.isoformat(), expires_at=(old + timedelta(hours=1)).isoformat())
    other = tmp_path / "other"
    other.mkdir()
    candidate = claim_control.normalize_claim(claim(other, "two"))
    assert "stale_claim:one" in claim_control.collisions(candidate, [stale])


def test_cleanup_is_owned_only_idempotent_and_receipt_is_single(tmp_path):
    ctl = controller(tmp_path)
    ctl.acquire(claim(tmp_path))
    ctl.transition("one", "VERIFYING")
    ctl.transition("one", "INTEGRATING")
    ctl.transition("one", "RELEASING")
    with pytest.raises(claim_control.ClaimError, match="not owned"):
        ctl.release("one", owned_resources={"containers": ["another"]})
    called = []
    receipt = ctl.release("one", owned_resources={"containers": []}, cleanup=lambda field, value: called.append((field, value)))
    assert ctl.release("one") == receipt
    assert called == []
    assert json.loads(receipt.read_text())["state"] == "COMPLETE_RECEIPT"
    assert json.loads(ctl.board_path.read_text())["claims"] == []


def test_exact_staged_allowlist():
    claim_control.verify_exact_allowlist(["automation/orchestration/x.py", "tests/orchestration/test_x.py"], ["automation/orchestration", "tests/orchestration"])
    with pytest.raises(claim_control.ClaimError, match="unexpected"):
        claim_control.verify_exact_allowlist(["apps/dashboard/x.py"], ["automation/orchestration"])


def test_module_introduces_no_activation_or_protected_integration():
    source = MODULE.read_text(encoding="utf-8").casefold()
    forbidden = ("subprocess", "schedule.", "daemon", "oanda", "broker", "order submission", "credential", "deploy(")
    assert not any(token in source for token in forbidden)
