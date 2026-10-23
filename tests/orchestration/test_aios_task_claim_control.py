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

@pytest.mark.parametrize("operation", ["transition", "release", "reconcile_release"])
def test_auth003_ir01_same_claim_lifecycle_refused_during_dispatch(tmp_path, operation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    fixture = _auth003_owned(tmp_path, containers=["owned-box"])
    started, finish = Event(), Event()
    calls, cleanup = [], []
    owner = claim_control.TaskClaimController(fixture["controller"].board_path)
    def action():
        started.set()
        assert finish.wait(timeout=5)
        calls.append("ran")
        return "owned-action"
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_auth003_dispatch, fixture, action)
        try:
            assert started.wait(timeout=5)
            before = owner.board_path.read_bytes()
            with pytest.raises(claim_control.ClaimError, match="dispatch"):
                if operation == "transition":
                    owner.transition("one", "BLOCKED", expected_claim=fixture["claim"])
                else:
                    method = getattr(owner, operation)
                    method("one", expected_claim=fixture["claim"], owned_resources={"containers": ["owned-box"]},
                           cleanup=lambda *args: cleanup.append(args))
            assert owner.board_path.read_bytes() == before and cleanup == []
            assert json.loads(before)["claims"][0]["state"] == "ACTIVE"
        finally:
            finish.set()
        assert future.result(timeout=10) == "owned-action"
    assert calls == ["ran"]
    # Once dispatch has returned, ordinary lifecycle/cleanup may proceed.
    for state in ("VERIFYING", "INTEGRATING", "RELEASING"):
        owner.transition("one", state, expected_claim=fixture["claim"])
    receipt = owner.release("one", expected_claim=fixture["claim"], owned_resources={"containers": ["owned-box"]},
                            cleanup=lambda *args: cleanup.append(args))
    assert receipt.exists() and cleanup == [("containers", "owned-box")]
    with pytest.raises(claim_control.ClaimError):
        _auth003_dispatch(fixture, lambda: pytest.fail("released dispatch replayed"), owner=owner)


def test_auth003_ir01_release_wins_before_dispatch(tmp_path):
    fixture = _auth003_owned(tmp_path, containers=["owned-box"])
    reads, cleanup, calls = [], [], []
    def reader():
        reads.append(True)
        if len(reads) == 2:
            for state in ("VERIFYING", "INTEGRATING", "RELEASING"):
                fixture["controller"].transition("one", state, expected_claim=fixture["claim"])
            fixture["controller"].release(
                "one", expected_claim=fixture["claim"], owned_resources={"containers": ["owned-box"]},
                cleanup=lambda *args: cleanup.append(args))
        return fixture["material"]
    with pytest.raises(claim_control.ClaimError, match="not active"):
        _auth003_dispatch(fixture, lambda: calls.append(True), reader=reader)
    assert not calls and cleanup == [("containers", "owned-box")]
    before = Path(fixture["claim"]["receipt_path"]).read_bytes()
    with pytest.raises(claim_control.ClaimError):
        _auth003_dispatch(fixture, lambda: calls.append(True),
                          owner=claim_control.TaskClaimController(fixture["controller"].board_path))
    assert Path(fixture["claim"]["receipt_path"]).read_bytes() == before and not calls
    assert len(json.loads(fixture["controller"].board_path.read_text())["execution_intents"]) == 1


@pytest.mark.parametrize("defect", ["missing", "malformed", "foreign", "unknown_state"])
def test_auth003_ir01_invalid_dispatch_lease_blocks_action_and_lifecycle(tmp_path, defect):
    fixture = _auth003_owned(tmp_path)
    marker = claim_control._dispatch_lock_file(fixture["controller"].board_path, fixture["claim"])
    reads, calls = [], []
    def reader():
        reads.append(True)
        if len(reads) == 2:
            if defect == "missing":
                marker.unlink()
            elif defect == "malformed":
                marker.write_bytes(b'{"schema":')
            else:
                saved = json.loads(marker.read_text())
                saved["board_path" if defect == "foreign" else "state"] = "foreign" if defect == "foreign" else "UNKNOWN"
                marker.write_text(json.dumps(saved))
        return fixture["material"]
    with pytest.raises(claim_control.ClaimError, match="dispatch"):
        _auth003_dispatch(fixture, lambda: calls.append(True), reader=reader)
    consumed = json.loads(fixture["controller"].board_path.read_text())["execution_intents"]
    assert not calls and len(consumed) == 1
    with pytest.raises(claim_control.ClaimError, match="dispatch"):
        fixture["controller"].transition("one", "BLOCKED", expected_claim=fixture["claim"])
    with pytest.raises(claim_control.ClaimError, match="consumed"):
        _auth003_dispatch(fixture, lambda: calls.append(True),
                          owner=claim_control.TaskClaimController(fixture["controller"].board_path))
    assert not calls and json.loads(fixture["controller"].board_path.read_text())["execution_intents"] == consumed


def test_auth003_ir01_stale_held_lease_never_reopens_consumed_action(tmp_path):
    fixture = _auth003_owned(tmp_path)
    calls = []
    _auth003_dispatch(fixture, lambda: calls.append(True))
    marker = claim_control._dispatch_lock_file(fixture["controller"].board_path, fixture["claim"])
    saved = json.loads(marker.read_text())
    saved.update(state="HELD", owner_pid=2147483647, acquired_at="2000-01-01T00:00:00+00:00")
    marker.write_text(json.dumps(saved))
    restarted = claim_control.TaskClaimController(fixture["controller"].board_path)
    # Neither apparent age nor an implausible PID restores execution.
    with pytest.raises(claim_control.ClaimError, match="consumed"):
        _auth003_dispatch(fixture, lambda: calls.append(True), owner=restarted)
    assert len(calls) == 1 and json.loads(marker.read_text()) == saved
    # Lifecycle recovery proves exclusive OS ownership instead of inferring it
    # from that metadata; consumption remains immutable.
    restarted.transition("one", "BLOCKED", expected_claim=fixture["claim"])
    assert json.loads(marker.read_text())["state"] == "RELEASED"
    assert len(json.loads(restarted.board_path.read_text())["execution_intents"]) == 1


def test_auth003_ir01_dispatch_lease_release_uncertainty_never_replays(tmp_path, monkeypatch):
    fixture = _auth003_owned(tmp_path)
    marker = claim_control._dispatch_lock_file(fixture["controller"].board_path, fixture["claim"])
    original = claim_control._write_lock_record
    calls = []
    def uncertain(descriptor, record):
        if (record["board_path"] == claim_control._dispatch_lock_target(
                fixture["controller"].board_path, fixture["claim"]).resolve().as_posix().casefold()
                and record["state"] == "RELEASED" and calls):
            raise OSError("owned dispatch lease release uncertainty")
        return original(descriptor, record)
    monkeypatch.setattr(claim_control, "_write_lock_record", uncertain)
    with pytest.raises(claim_control.ClaimError, match="release metadata"):
        _auth003_dispatch(fixture, lambda: calls.append(True))
    assert json.loads(marker.read_text())["state"] == "HELD"
    monkeypatch.setattr(claim_control, "_write_lock_record", original)
    with pytest.raises(claim_control.ClaimError, match="consumed"):
        _auth003_dispatch(fixture, lambda: calls.append(True),
                          owner=claim_control.TaskClaimController(fixture["controller"].board_path))
    assert len(calls) == 1


def test_auth003_ir01_legacy_lifecycle_creates_no_dispatch_sidecars(tmp_path):
    ctl = controller(tmp_path)
    owned = ctl.acquire(claim(tmp_path))
    for state in ("VERIFYING", "INTEGRATING", "RELEASING"):
        ctl.transition("one", state, expected_claim=owned)
    receipt = ctl.release("one", expected_claim=owned)
    original = receipt.read_bytes()
    assert ctl.reconcile_release("one", expected_claim=owned) == receipt
    assert receipt.read_bytes() == original
    assert list(tmp_path.glob("*.dispatch-*")) == []


def _auth003_owned(root, **updates):
    helper_path = Path(__file__).with_name("test_aios_self_build_one_action_local_apply_executor.py")
    helper_spec = importlib.util.spec_from_file_location("auth003_owned_test_helpers", helper_path)
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    return helper._auth003_fixture(root, module=claim_control, claim_updates=updates)


def _auth003_dispatch(fixture, action, *, owner=None, reader=None):
    return (owner or fixture["controller"]).execute_once(
        expected_claim=fixture["claim"], invocation=fixture["invocation"],
        authority_reader=reader or (lambda: fixture["material"]), action=action, allow_test_trust=True)

def test_auth003_same_signed_claim_cannot_move_to_another_owned_board(tmp_path):
    fixture = _auth003_owned(tmp_path)
    original = fixture["controller"]
    alternate = claim_control.TaskClaimController(tmp_path / "alternate/active.json")
    # Copy only the existing exact active claim: the alternate board has never
    # consumed anything. Reuse the same authentic synthetic signature unchanged.
    claim_control._atomic_write(alternate.board_path, {
        "schema_version": claim_control.SCHEMA_VERSION, "claims": [fixture["claim"]],
    })
    calls = []
    with pytest.raises(claim_control.ClaimError, match="output scope"):
        _auth003_dispatch(fixture, lambda: calls.append(True), owner=alternate)
    assert not calls and "execution_intents" not in json.loads(alternate.board_path.read_text())
    # Matching existing owner still permits the single action.
    assert _auth003_dispatch(fixture, lambda: calls.append(True) or "one", owner=original) == "one"
    # Even rewriting the unsigned invocation's journal projection cannot change
    # the signed execution contract/output roots to authorize a second owner.
    fixture["invocation"]["output_roots"] = {
        **fixture["invocation"]["output_roots"],
        "execution_journal": alternate.board_path.resolve().as_posix().casefold(),
        "execution_dispatch_lease": claim_control._dispatch_lock_file(
            alternate.board_path, fixture["claim"]).resolve().as_posix().casefold(),
    }
    with pytest.raises(claim_control.ClaimError, match="binding mismatch"):
        _auth003_dispatch(fixture, lambda: calls.append(True), owner=alternate)
    assert len(calls) == 1



def test_auth003_consume_preserves_claim_contract_and_release_receipt(tmp_path):
    fixture = _auth003_owned(tmp_path)
    ctl, owned = fixture["controller"], fixture["claim"]
    original_claim = json.loads(ctl.board_path.read_text())["claims"][0]
    original_digest = claim_control._claim_contract(owned)
    assert _auth003_dispatch(fixture, lambda: "owned-action") == "owned-action"
    consumed = json.loads(ctl.board_path.read_text())["execution_intents"]
    assert json.loads(ctl.board_path.read_text())["claims"] == [original_claim]
    assert claim_control._claim_contract(owned) == original_digest
    for state in ("VERIFYING", "INTEGRATING", "RELEASING"):
        ctl.transition("one", state, expected_claim=owned)
    receipt = ctl.release("one", expected_claim=owned)
    original_bytes = receipt.read_bytes()
    payload = json.loads(original_bytes)
    assert claim_control._claim_contract(payload) == original_digest
    assert "execution_intents" not in payload
    restarted = claim_control.TaskClaimController(ctl.board_path)
    assert restarted.release("one", expected_claim=owned) == receipt
    assert receipt.read_bytes() == original_bytes
    board = json.loads(ctl.board_path.read_text())
    assert board["execution_intents"] == consumed and board["claims"] == []
    with pytest.raises(claim_control.ClaimError):
        _auth003_dispatch(fixture, lambda: pytest.fail("released attempt ran"), owner=restarted)


@pytest.mark.parametrize("malformed", [None, {}, [{}], [{"state": "CONSUMED"}]])
def test_auth003_partial_or_malformed_intent_blocks_all_dispatch(tmp_path, malformed):
    fixture = _auth003_owned(tmp_path)
    board = json.loads(fixture["controller"].board_path.read_text())
    board["execution_intents"] = malformed
    claim_control._atomic_write(fixture["controller"].board_path, board)
    before = fixture["controller"].board_path.read_bytes()
    calls = []
    with pytest.raises(claim_control.ClaimError):
        _auth003_dispatch(fixture, lambda: calls.append(True))
    assert not calls and fixture["controller"].board_path.read_bytes() == before


def test_auth003_duplicate_or_foreign_board_intent_fails_closed(tmp_path):
    fixture = _auth003_owned(tmp_path)
    _auth003_dispatch(fixture, lambda: None)
    board = json.loads(fixture["controller"].board_path.read_text())
    board["execution_intents"].append(dict(board["execution_intents"][0]))
    claim_control._atomic_write(fixture["controller"].board_path, board)
    with pytest.raises(claim_control.ClaimError, match="duplicate"):
        fixture["controller"].guard("one", repository="owned/engineering", worktree=tmp_path,
                                    branch="task/one", head_is_descendant=True, changed_paths=[])
    board["execution_intents"].pop()
    board["execution_intents"][0]["board_path"] = str(tmp_path / "foreign.json")
    claim_control._atomic_write(fixture["controller"].board_path, board)
    with pytest.raises(claim_control.ClaimError, match="another board"):
        _auth003_dispatch(fixture, lambda: pytest.fail("foreign board intent ran"))


def test_auth003_consumed_write_uncertainty_readback_failure_blocks_replay(tmp_path, monkeypatch):
    fixture = _auth003_owned(tmp_path)
    original = claim_control._atomic_write
    def uncertain(path, value):
        original(path, value)
        if value.get("execution_intents"):
            raise OSError("owned write committed but completion uncertain")
    monkeypatch.setattr(claim_control, "_atomic_write", uncertain)
    calls = []
    with pytest.raises(OSError):
        _auth003_dispatch(fixture, lambda: calls.append(True))
    monkeypatch.setattr(claim_control, "_atomic_write", original)
    restarted = claim_control.TaskClaimController(fixture["controller"].board_path)
    with pytest.raises(claim_control.ClaimError, match="consumed"):
        _auth003_dispatch(fixture, lambda: calls.append(True), owner=restarted)
    assert not calls


def test_auth003_partial_consumed_write_cannot_dispatch_or_retry(tmp_path, monkeypatch):
    fixture = _auth003_owned(tmp_path)
    original = claim_control._atomic_write
    def partial(path, value):
        if value.get("execution_intents"):
            path.write_text('{"schema_version":', encoding="utf-8")
            raise OSError("owned partial board")
        return original(path, value)
    monkeypatch.setattr(claim_control, "_atomic_write", partial)
    calls = []
    with pytest.raises(OSError):
        _auth003_dispatch(fixture, lambda: calls.append(True))
    monkeypatch.setattr(claim_control, "_atomic_write", original)
    with pytest.raises(claim_control.ClaimError, match="unreadable"):
        _auth003_dispatch(fixture, lambda: calls.append(True))
    assert not calls


def test_auth003_two_instances_contend_for_one_attempt(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, local

    fixture = _auth003_owned(tmp_path)
    barrier, per_thread = Barrier(2), local()
    calls = []
    def reader():
        if not getattr(per_thread, "read", False):
            per_thread.read = True
            barrier.wait(timeout=5)
        return fixture["material"]
    def attempt():
        owner = claim_control.TaskClaimController(fixture["controller"].board_path)
        try:
            return _auth003_dispatch(fixture, lambda: calls.append(True) or "executed", owner=owner, reader=reader)
        except claim_control.ClaimError:
            return "blocked"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt) for _ in range(2)]
        outcomes = [future.result(timeout=10) for future in futures]
    assert sorted(outcomes) == ["blocked", "executed"] and len(calls) == 1
    assert len(json.loads(fixture["controller"].board_path.read_text())["execution_intents"]) == 1


def test_auth003_arbitrary_runner_does_not_hold_global_board_lock(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    fixture = _auth003_owned(tmp_path / "one")
    started, finish = Event(), Event()
    def action():
        started.set()
        assert finish.wait(timeout=5)
        return "owned-action"
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_auth003_dispatch, fixture, action)
        try:
            assert started.wait(timeout=5)
            other = tmp_path / "other"
            other.mkdir()
            second = claim(other, "two")
            acquired = fixture["controller"].acquire(second)
            assert acquired["task_id"] == "two"
        finally:
            finish.set()
        assert future.result(timeout=10) == "owned-action"


def test_auth003_nonce_stays_consumed_for_different_exact_claim_attempt(tmp_path):
    fixture = _auth003_owned(tmp_path / "one")
    _auth003_dispatch(fixture, lambda: None)
    other = _auth003_owned(tmp_path / "two")
    # Both signed fixtures use the same engineering nonce. Bind the second to
    # the same existing owner before re-signing its exact invocation.
    owner = fixture["controller"]
    second_root = tmp_path / "two"
    (second_root / ".git/HEAD").write_text("ref: refs/heads/task/two\n")
    (second_root / ".git/refs/heads/task/two").write_text("a" * 40 + "\n")
    owned = owner.acquire({**other["claim"], "task_id": "two", "branch": "task/two"})
    other["invocation"]["output_roots"]["execution_journal"] = owner.board_path.resolve().as_posix().casefold()
    other["invocation"]["output_roots"]["execution_dispatch_lease"] = claim_control._dispatch_lock_file(
        owner.board_path, owned).resolve().as_posix().casefold()
    identity = owner.execution_identity(owned, other["invocation"])
    gate = other["material"]["gate"]
    gate["output_roots"] = identity["output_roots"]
    gate["execution_contract_sha256"] = claim_control._execution_digest(identity)
    other["sign"]()
    with pytest.raises(claim_control.ClaimError, match="consumed"):
        owner.execute_once(expected_claim=owned, invocation=other["invocation"],
                           authority_reader=lambda: other["material"],
                           action=lambda: pytest.fail("nonce replay ran"), allow_test_trust=True)




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
    lock = ctl.board_path.with_suffix(".json.lock")
    assert lock.is_file()
    assert json.loads(lock.read_text())["state"] == "RELEASED"


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



# N08 fixtures use only their own temporary claim boards; no runtime state.
def test_n08_identical_reacquire_preserves_one_owned_record(tmp_path):
    ctl = controller(tmp_path)
    request = claim(tmp_path, attempt_id="fixture-attempt", attempt=0)
    first = ctl.acquire(request)
    before = ctl.board_path.read_bytes()
    second = ctl.acquire(dict(request))
    assert second == first
    assert ctl.board_path.read_bytes() == before
    assert len(json.loads(before)["claims"]) == 1


@pytest.mark.parametrize("change", [
    {"worker": "another-worker"}, {"packet_id": "another-packet"},
    {"supervisor": "another-supervisor"}, {"repository": "other/repo"},
    {"claimed_paths": ["src/other"]}, {"ports": [8123]},
    {"attempt_id": "other-attempt"}, {"attempt": 1},
    {"acquired_at": "2026-01-01T00:00:00+00:00"},
])
def test_n08_changed_owner_scope_or_attempt_cannot_reacquire(tmp_path, change):
    ctl = controller(tmp_path)
    request = claim(tmp_path, attempt_id="fixture-attempt", attempt=0)
    ctl.acquire(request)
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError):
        ctl.acquire({**request, **change})
    assert ctl.board_path.read_bytes() == before


def test_n08_normalized_equivalent_contract_is_idempotent(tmp_path):
    ctl = controller(tmp_path)
    request = claim(tmp_path, claimed_paths=["src/ONE", "src/one"], ports=[8123, 8123])
    first = ctl.acquire(request)
    retry = {**request, "claimed_paths": ["src/one"], "ports": [8123],
             "branch": "refs/heads/task/one"}
    assert ctl.acquire(retry) == first
    assert len(json.loads(ctl.board_path.read_text())["claims"]) == 1


@pytest.mark.parametrize("state", ["VERIFYING", "INTEGRATING", "RELEASING", "BLOCKED"])
def test_n08_reacquire_never_resets_lifecycle_state(tmp_path, state):
    ctl = controller(tmp_path)
    request = claim(tmp_path)
    ctl.acquire(request)
    ctl.transition("one", "VERIFYING")
    if state in {"INTEGRATING", "RELEASING"}:
        ctl.transition("one", "INTEGRATING")
    if state == "RELEASING":
        ctl.transition("one", "RELEASING")
    if state == "BLOCKED":
        ctl.transition("one", "BLOCKED")
    before = ctl.board_path.read_bytes()
    assert ctl.acquire(request)["state"] == state
    assert ctl.board_path.read_bytes() == before


def test_n08_concurrent_same_id_acquisition_has_one_owner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    ctl = controller(tmp_path)
    request = claim(tmp_path)
    gate = Barrier(2)
    def acquire_once():
        gate.wait(timeout=5)
        try:
            return ctl.acquire(request)
        except claim_control.ClaimError as error:
            assert "board is locked" in str(error)
            return None  # explicit contention is not a second owner
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: acquire_once(), range(2)))
    assert any(value is not None for value in outcomes)
    assert len(json.loads(ctl.board_path.read_text())["claims"]) == 1
    assert ctl.acquire(request)["worker"] == request["worker"]


@pytest.mark.parametrize("change", [
    {"task_id": True}, {"worker": None}, {"packet_id": ""},
    {"acquired_at": "not-a-time"}, {"attempt_id": []},
    {"attempt": True}, {"attempt": -1}, {"claimed_paths": "src/one"},
    {"state": []}, {"state": "COMPLETE_RECEIPT"},
])
def test_n08_malformed_identity_cannot_create_owned_record(tmp_path, change):
    ctl = controller(tmp_path)
    with pytest.raises(claim_control.ClaimError):
        ctl.acquire({**claim(tmp_path), **change})
    assert not ctl.board_path.exists()


@pytest.mark.parametrize("operation", ["acquire", "transition", "guard", "release"])
def test_n08_duplicate_legacy_ids_fail_closed_without_mutation(tmp_path, operation):
    ctl = controller(tmp_path)
    request = claim(tmp_path)
    owned = ctl.acquire(request)
    board = json.loads(ctl.board_path.read_text())
    board["claims"].append({**owned, "worker": "different-owner"})
    ctl.board_path.write_text(json.dumps(board), encoding="utf-8")
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError, match="duplicate"):
        if operation == "acquire":
            ctl.acquire(request)
        elif operation == "transition":
            ctl.transition("one", "VERIFYING")
        elif operation == "guard":
            ctl.guard("one", repository=request["repository"], worktree=tmp_path,
                      branch=request["branch"], head_is_descendant=True, changed_paths=[])
        else:
            ctl.release("one")
    assert ctl.board_path.read_bytes() == before


@pytest.mark.parametrize("operation", ["transition", "guard", "release"])
def test_n08_exact_expected_contract_protects_later_operations(tmp_path, operation):
    ctl = controller(tmp_path)
    expected = ctl.acquire(claim(tmp_path))
    if operation == "release":
        ctl.transition("one", "VERIFYING")
        ctl.transition("one", "INTEGRATING")
        ctl.transition("one", "RELEASING")
    board = json.loads(ctl.board_path.read_text())
    board["claims"][0]["worker"] = "different-owner"
    ctl.board_path.write_text(json.dumps(board), encoding="utf-8")
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError, match="identity"):
        if operation == "transition":
            ctl.transition("one", "VERIFYING", expected_claim=expected)
        elif operation == "guard":
            ctl.guard("one", repository=expected["repository"], worktree=tmp_path,
                      branch=expected["branch"], head_is_descendant=True,
                      changed_paths=[], expected_claim=expected)
        else:
            ctl.release("one", expected_claim=expected)
    assert ctl.board_path.read_bytes() == before


def test_n08_expired_same_owned_attempt_does_not_reauthorize_itself(tmp_path):
    ctl = controller(tmp_path)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    request = claim(tmp_path, acquired_at=old.isoformat(), heartbeat_at=old.isoformat(),
                    expires_at=(old + timedelta(hours=1)).isoformat())
    ctl.board_path.write_text(json.dumps({"schema_version": claim_control.SCHEMA_VERSION,
                                        "claims": [request]}), encoding="utf-8")
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError, match="stale|expired"):
        ctl.acquire(request)
    assert ctl.board_path.read_bytes() == before



def test_n08_terminal_attempt_is_not_reexecuted_by_reacquisition(tmp_path):
    ctl = controller(tmp_path)
    request = claim(tmp_path)
    acquired = ctl.acquire(request)
    ctl.transition("one", "VERIFYING", expected_claim=acquired)
    ctl.transition("one", "INTEGRATING", expected_claim=acquired)
    ctl.transition("one", "RELEASING", expected_claim=acquired)
    receipt = ctl.release("one", expected_claim=acquired)
    evidence = receipt.read_bytes()
    with pytest.raises(claim_control.ClaimError, match="terminal"):
        ctl.acquire(request)
    assert receipt.read_bytes() == evidence
    assert json.loads(ctl.board_path.read_text())["claims"] == []
    assert ctl.release("one", expected_claim=acquired) == receipt
    with pytest.raises(claim_control.ClaimError, match="identity"):
        ctl.release("one", expected_claim={**acquired, "worker": "another-worker"})


def test_n08_preexisting_malformed_same_id_is_not_adopted(tmp_path):
    ctl = controller(tmp_path)
    request = claim(tmp_path)
    ctl.board_path.write_text(json.dumps({"schema_version": claim_control.SCHEMA_VERSION,
                                        "claims": [{**request, "worker": None}]}), encoding="utf-8")
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError, match="identity"):
        ctl.acquire(request)
    assert ctl.board_path.read_bytes() == before



@pytest.mark.parametrize("update", [
    {"ports": [8123.75]}, {"ports": [float("inf")]},
    {"ports": [float("-inf")]}, {"ports": [float("nan")]},
    {"ports": [True]}, {"ports": [0]}, {"ports": [65536]},
    {"ports": [None]}, {"ports": [{}]}, {"ports": ["8123.5"]},
    {"acquired_at": "0001-01-01T00:00:00+23:59"},
    {"acquired_at": "9999-12-31T23:59:59-23:59"},
    {"acquired_at": "2026-01-01T00:00:00+24:00"},
    {"acquired_at": "2026-01-01T00:00:00"},
    {"acquired_at": "not-a-date"}, {"acquired_at": True},
])
def test_n08_review_invalid_resource_and_utc_boundaries_reject_controlled(tmp_path, update):
    ctl = controller(tmp_path)
    with pytest.raises(claim_control.ClaimError):
        ctl.acquire({**claim(tmp_path), **update})
    assert not ctl.board_path.exists()


@pytest.mark.parametrize("value", [8123, "8123", " 08123 ", 8123.0])
def test_n08_review_valid_integral_ports_reacquire_idempotently(tmp_path, value):
    ctl = controller(tmp_path)
    request = claim(tmp_path, ports=[8123])
    owned = ctl.acquire(request)
    before = ctl.board_path.read_bytes()
    assert ctl.acquire({**request, "ports": [value]}) == owned
    assert ctl.board_path.read_bytes() == before


@pytest.mark.parametrize("change", [
    {"ports": [8123.75]},
    {"acquired_at": "0001-01-01T00:00:00+23:59"},
    {"acquired_at": "9999-12-31T23:59:59-23:59"},
])
def test_n08_review_malformed_legacy_normalization_does_not_pass_guard(tmp_path, change):
    ctl = controller(tmp_path)
    owned = ctl.acquire(claim(tmp_path, ports=[8123]))
    board = json.loads(ctl.board_path.read_text())
    board["claims"][0].update(change)
    ctl.board_path.write_text(json.dumps(board), encoding="utf-8")
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError):
        ctl.guard("one", repository=owned["repository"], worktree=tmp_path,
                  branch=owned["branch"], head_is_descendant=True,
                  changed_paths=[], expected_claim=owned)
    assert ctl.board_path.read_bytes() == before


def test_n08_review_fractional_port_cannot_alias_owned_integer_request(tmp_path):
    ctl = controller(tmp_path)
    request = claim(tmp_path, ports=[8123])
    ctl.acquire(request)
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError):
        ctl.acquire({**request, "ports": [8123.75]})
    assert ctl.board_path.read_bytes() == before


def test_n08_review_same_instant_timezone_contract_is_idempotent(tmp_path):
    ctl = controller(tmp_path)
    request = claim(tmp_path)
    owned = ctl.acquire(request)
    offset = timezone(timedelta(hours=5, minutes=30))
    retry = {**request, **{name: datetime.fromisoformat(request[name]).astimezone(offset).isoformat()
                          for name in ("acquired_at", "heartbeat_at", "expires_at")}}
    before = ctl.board_path.read_bytes()
    assert ctl.acquire(retry) == owned
    assert ctl.board_path.read_bytes() == before



def _n09_releasing(ctl, request):
    owned = ctl.acquire(request)
    for state in ("VERIFYING", "INTEGRATING", "RELEASING"):
        ctl.transition(request["task_id"], state, expected_claim=owned)
    return owned


def test_n09_receipt_success_board_failure_recovers_without_overwrite(tmp_path, monkeypatch):
    ctl = controller(tmp_path)
    request = claim(tmp_path)
    owned = _n09_releasing(ctl, request)
    receipt = Path(request["receipt_path"])
    actual_write = claim_control._atomic_write
    def fail_after_receipt(path, value):
        if path == ctl.board_path and receipt.exists():
            raise OSError("owned board replacement failure after receipt")
        return actual_write(path, value)
    monkeypatch.setattr(claim_control, "_atomic_write", fail_after_receipt)
    with pytest.raises((OSError, claim_control.ClaimError)):
        ctl.release("one", expected_claim=owned)
    evidence = receipt.read_bytes()
    assert json.loads(ctl.board_path.read_text())["claims"]
    monkeypatch.setattr(claim_control, "_atomic_write", actual_write)
    restarted = controller(tmp_path)
    assert restarted.release("one", expected_claim=owned) == receipt
    assert receipt.read_bytes() == evidence
    assert json.loads(ctl.board_path.read_text())["claims"] == []


def test_n09_central_receipt_repeated_release_uses_exact_board_reference(tmp_path):
    ctl = controller(tmp_path)
    request = claim(tmp_path, receipt_path=str(tmp_path / "central-store" / "not-task-named.json"))
    owned = _n09_releasing(ctl, request)
    receipt = ctl.release("one", expected_claim=owned)
    original = receipt.read_bytes()
    assert controller(tmp_path).release("one", expected_claim=owned) == receipt
    assert receipt.read_bytes() == original
    with pytest.raises(claim_control.ClaimError):
        ctl.acquire({**request, "worker": "another", "receipt_path": str(tmp_path / "another" / "new.json")})


def test_n09_unknown_once_cleanup_never_repeats_side_effect(tmp_path):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path, containers=["box-one"]))
    calls = []
    def uncertain(field, value):
        calls.append((field, value))
        raise OSError("side effect occurred; outcome is not confirmed")
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned, owned_resources={"containers": ["box-one"]}, cleanup=uncertain)
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError):
        controller(tmp_path).release("one", expected_claim=owned, owned_resources={"containers": ["box-one"]}, cleanup=uncertain)
    assert calls == [("containers", "box-one")]
    assert ctl.board_path.read_bytes() == before
    assert not Path(owned["receipt_path"]).exists()


def test_n09_declared_idempotent_cleanup_can_resume_unknown_outcome(tmp_path):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path, containers=["box-one"]))
    calls = []
    def idempotent(field, value):
        calls.append((field, value))
        if len(calls) == 1:
            raise OSError("owned interruption after idempotent operation")
    for index in range(2):
        if index == 0:
            with pytest.raises(claim_control.ClaimError):
                ctl.release("one", expected_claim=owned, owned_resources={"containers": ["box-one"]}, cleanup=idempotent, cleanup_idempotent=True)
        else:
            receipt = controller(tmp_path).release("one", expected_claim=owned, owned_resources={"containers": ["box-one"]}, cleanup=idempotent, cleanup_idempotent=True)
    assert len(calls) == 2 and receipt.is_file()


def test_n09_reconciled_cleanup_skips_confirmed_completed_side_effect(tmp_path):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path, containers=["box-one"]))
    calls = []
    def uncertain(field, value):
        calls.append((field, value))
        raise OSError("owned operation completed before interruption")
    def confirmed(field, value):
        assert (field, value) == ("containers", "box-one")
        return "COMPLETE"
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned, owned_resources={"containers": ["box-one"]}, cleanup=uncertain, reconcile_cleanup=confirmed)
    assert controller(tmp_path).release("one", expected_claim=owned, owned_resources={"containers": ["box-one"]}, cleanup=uncertain, reconcile_cleanup=confirmed).is_file()
    assert len(calls) == 1


def test_n09_cleanup_policy_cannot_be_retroactively_widened(tmp_path):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path, containers=["box-one"]))
    def uncertain(field, value):
        raise OSError("unknown")
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned, owned_resources={"containers": ["box-one"]}, cleanup=uncertain)
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned, owned_resources={"containers": ["box-one"]}, cleanup=uncertain, cleanup_idempotent=True)
    assert ctl.board_path.read_bytes() == before


def test_n09_completed_cleanup_progress_is_not_replayed_after_receipt_failure(tmp_path, monkeypatch):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path, containers=["box-one"]))
    calls = []
    original_open = claim_control.os.open
    def fail_receipt(path, flags, *args, **kwargs):
        if Path(path) == Path(owned["receipt_path"]):
            raise OSError("owned receipt creation failure")
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(claim_control.os, "open", fail_receipt)
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned, owned_resources={"containers": ["box-one"]}, cleanup=lambda field, value: calls.append((field, value)))
    assert calls == [("containers", "box-one")]
    monkeypatch.setattr(claim_control.os, "open", original_open)
    assert ctl.release("one", expected_claim=owned, owned_resources={"containers": ["box-one"]}, cleanup=lambda field, value: calls.append((field, value))).is_file()
    assert len(calls) == 1


@pytest.mark.parametrize("policy", ["once", "idempotent"])
def test_n09_cleanup_effect_before_progress_save_needs_explicit_safe_retry(tmp_path, monkeypatch, policy):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path, containers=["box-one"]))
    calls = []
    actual = claim_control._atomic_write
    def interrupt_after_effect(path, value):
        if calls:
            raise OSError("effect complete; progress save interrupted")
        return actual(path, value)
    monkeypatch.setattr(claim_control, "_atomic_write", interrupt_after_effect)
    options = dict(expected_claim=owned, owned_resources={"containers": ["box-one"]},
                   cleanup=lambda field, value: calls.append((field, value)), cleanup_idempotent=policy == "idempotent")
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", **options)
    assert len(calls) == 1
    monkeypatch.setattr(claim_control, "_atomic_write", actual)
    if policy == "once":
        with pytest.raises(claim_control.ClaimError):
            ctl.release("one", **options)
        assert len(calls) == 1
    else:
        assert ctl.release("one", **options).is_file()
        assert len(calls) == 2


def test_n09_partial_receipt_is_preserved_and_blocks_reconciliation(tmp_path, monkeypatch):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path, containers=["box-one"]))
    receipt = Path(owned["receipt_path"])
    actual = claim_control._atomic_write
    def stop_after_receipt(path, value):
        if receipt.exists():
            raise OSError("owned board failure")
        return actual(path, value)
    monkeypatch.setattr(claim_control, "_atomic_write", stop_after_receipt)
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned)
    monkeypatch.setattr(claim_control, "_atomic_write", actual)
    receipt.chmod(0o600)
    receipt.write_bytes(b'{"partial":')
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned)
    assert receipt.read_bytes() == b'{"partial":'
    assert ctl.board_path.read_bytes() == before


def test_n09_cleanup_ports_use_integer_identity_and_names_require_exact_match(tmp_path):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path, ports=[8123]))
    calls = []
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned, owned_resources={"pull_request": ["pr"]}, cleanup=lambda *args: calls.append(args))
    assert calls == []
    assert ctl.release("one", expected_claim=owned, owned_resources={"ports": ["8123"]}, cleanup=lambda *args: calls.append(args)).is_file()
    assert calls == [("ports", 8123)]


def test_n09_lock_is_persistent_and_os_owned_contention_never_unlinks_it(tmp_path):
    ctl = controller(tmp_path)
    ctl.acquire(claim(tmp_path))
    lock = ctl.board_path.with_suffix(".json.lock")
    assert lock.is_file()
    with claim_control._exclusive_lock(ctl.board_path):
        held = lock.read_bytes()
        with pytest.raises(claim_control.ClaimError, match="locked"):
            with claim_control._exclusive_lock(ctl.board_path):
                raise AssertionError("must not enter held lock")
        assert lock.read_bytes() == held
    assert lock.is_file()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX record-lock semantics")
def test_local_contender_cannot_drop_owners_cross_process_lock(tmp_path):
    import subprocess

    ctl = controller(tmp_path)
    lock = ctl.board_path.with_suffix(".json.lock")
    child = """
import errno, os, runpy, sys
region_lock = runpy.run_path(sys.argv[1])["_claim_file_lock"]
fd = os.open(sys.argv[2], os.O_RDWR)
try:
    region_lock(fd)
except OSError as error:
    if error.errno not in (errno.EACCES, errno.EAGAIN):
        raise
    sys.exit(23)
finally:
    os.close(fd)
"""
    with claim_control._exclusive_lock(ctl.board_path):
        held = lock.read_bytes()
        with pytest.raises(claim_control.ClaimError, match="locked"):
            with claim_control._exclusive_lock(ctl.board_path):
                pytest.fail("local contender entered")
        result = subprocess.run([sys.executable, "-c", child, str(MODULE), str(lock)], timeout=10, check=False)
        assert result.returncode == 23
        assert lock.read_bytes() == held
    assert subprocess.run([sys.executable, "-c", child, str(MODULE), str(lock)], timeout=10, check=False).returncode == 0


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX record-lock semantics")
def test_dispatch_lease_keeps_os_lock_during_metadata_verification(tmp_path):
    import subprocess

    fixture = _auth003_owned(tmp_path)
    target = claim_control._dispatch_lock_target(fixture["controller"].board_path, fixture["claim"])
    child = """
import pathlib, runpy, sys
owner = runpy.run_path(sys.argv[1])
try:
    with owner["_exclusive_lock"](pathlib.Path(sys.argv[2])):
        pass
except owner["ClaimError"]:
    sys.exit(23)
"""
    with claim_control._claim_dispatch_lease(fixture["controller"].board_path, fixture["claim"], initialize=True) as verify:
        verify()
        assert subprocess.run([sys.executable, "-c", child, str(MODULE), str(target)], timeout=10).returncode == 23
        verify()
    assert subprocess.run([sys.executable, "-c", child, str(MODULE), str(target)], timeout=10).returncode == 0


def test_n09_unheld_versioned_lock_can_reconcile_but_legacy_empty_stays_blocked(tmp_path):
    ctl = controller(tmp_path)
    request = claim(tmp_path)
    owned = ctl.acquire(request)
    lock = ctl.board_path.with_suffix(".json.lock")
    record = json.loads(lock.read_text())
    record["state"] = "HELD"
    record["owner_pid"] = 2147483647  # never used as proof of inactivity
    lock.write_text(json.dumps(record), encoding="utf-8")
    assert ctl.acquire(request) == owned  # the acquired OS lock is the proof
    lock.write_bytes(b"")
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError):
        ctl.acquire(request)
    assert lock.read_bytes() == b"" and ctl.board_path.read_bytes() == before


def test_legacy_record_lock_held_is_preserved_and_released_can_migrate(tmp_path):
    ctl = controller(tmp_path)
    request = claim(tmp_path)
    owned = ctl.acquire(request)
    lock = ctl.board_path.with_suffix(".json.lock")
    legacy = {**json.loads(lock.read_text()), "schema": "AIOS_TASK_CLAIM_BOARD_LOCK.v1", "state": "HELD"}
    lock.write_text(json.dumps(legacy))
    before = lock.read_bytes()
    with pytest.raises(claim_control.ClaimError, match="legacy"):
        ctl.acquire(request)
    assert lock.read_bytes() == before
    lock.write_text(json.dumps({**legacy, "state": "RELEASED"}))
    assert ctl.acquire(request) == owned
    assert json.loads(lock.read_text())["schema"] == "AIOS_TASK_CLAIM_BOARD_LOCK.v2"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX legacy lock compatibility")
def test_changed_legacy_metadata_during_migration_is_preserved(tmp_path, monkeypatch):
    ctl = controller(tmp_path)
    ctl.acquire(claim(tmp_path))
    lock = ctl.board_path.with_suffix(".json.lock")
    legacy = {**json.loads(lock.read_text()), "schema": "AIOS_TASK_CLAIM_BOARD_LOCK.v1", "state": "RELEASED"}
    lock.write_text(json.dumps(legacy))
    original = claim_control._region_lock
    def legacy_change(descriptor, *, unlock=False):
        original(descriptor, unlock=unlock)
        if not unlock:
            claim_control._write_lock_record(descriptor, {**legacy, "state": "HELD"})
    monkeypatch.setattr(claim_control, "_region_lock", legacy_change)
    with pytest.raises(claim_control.ClaimError, match="legacy"):
        with claim_control._exclusive_lock(ctl.board_path):
            pytest.fail("changed legacy ownership was overwritten")
    assert json.loads(lock.read_text()) == {**legacy, "state": "HELD"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX legacy lock compatibility")
def test_legacy_acquisition_in_progress_prevents_migration(tmp_path):
    import subprocess

    ctl = controller(tmp_path)
    ctl.acquire(claim(tmp_path))
    lock = ctl.board_path.with_suffix(".json.lock")
    legacy = {**json.loads(lock.read_text()), "schema": "AIOS_TASK_CLAIM_BOARD_LOCK.v1", "state": "RELEASED"}
    lock.write_text(json.dumps(legacy))
    before = lock.read_bytes()
    script = """
import fcntl, os, select, sys
fd = os.open(sys.argv[1], os.O_RDWR)
fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 65536)
print("held", flush=True)
select.select([sys.stdin], [], [], 10)
os.close(fd)
"""
    child = subprocess.Popen([sys.executable, "-c", script, str(lock)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "held"
        with pytest.raises(claim_control.ClaimError, match="legacy"):
            with claim_control._exclusive_lock(ctl.board_path):
                pytest.fail("migrated while legacy owner was acquiring")
        assert lock.read_bytes() == before
    finally:
        child.communicate("release", timeout=10)
    assert child.returncode == 0
    with claim_control._exclusive_lock(ctl.board_path):
        pass
    assert json.loads(lock.read_text())["schema"] == "AIOS_TASK_CLAIM_BOARD_LOCK.v2"


def test_n09_caller_progress_cannot_authorize_release(tmp_path):
    ctl = controller(tmp_path)
    with pytest.raises(claim_control.ClaimError):
        ctl.acquire(claim(tmp_path, release_intent={"cleanup_status": "COMPLETE"}))
    assert not ctl.board_path.exists()



@pytest.mark.parametrize("invalid_part", ["cleanup_mode", "progress_status"])
def test_n09_malformed_release_metadata_rejects_controlled(tmp_path, invalid_part):
    owned = claim_control.normalize_claim(claim(tmp_path, state="RELEASING"))
    intent = {"schema": claim_control.RELEASE_SCHEMA,
              "claim_sha256": claim_control._claim_contract(owned),
              "started_at": datetime.now(timezone.utc).isoformat(),
              "receipt_path": owned["receipt_path"], "cleanup_mode": "once", "resources": []}
    if invalid_part == "cleanup_mode":
        intent["cleanup_mode"] = []
    else:
        intent["resources"] = [{"field": "containers", "value": "box-one", "status": []}]
    with pytest.raises(claim_control.ClaimError):
        claim_control.normalize_claim({**owned, "release_intent": intent})


def test_n09_malformed_lock_metadata_preserves_bytes(tmp_path):
    ctl = controller(tmp_path)
    lock = ctl.board_path.with_suffix(".json.lock")
    record = {"schema": claim_control.LOCK_SCHEMA,
              "board_path": ctl.board_path.resolve().as_posix().casefold(),
              "owner_pid": 123, "owner_token": "a" * 32,
              "acquired_at": datetime.now(timezone.utc).isoformat(), "state": []}
    lock.write_bytes(json.dumps(record).encode())
    before = lock.read_bytes()
    with pytest.raises(claim_control.ClaimError):
        with claim_control._exclusive_lock(ctl.board_path):
            raise AssertionError("must not enter malformed lock")
    assert lock.read_bytes() == before


def test_n09_conflicting_receipt_blocks_before_cleanup_or_intent_write(tmp_path):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path, containers=["box-one"]))
    receipt = Path(owned["receipt_path"])
    receipt.parent.mkdir()
    receipt.write_bytes(b'{"foreign":true}')
    before = ctl.board_path.read_bytes()
    calls = []
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned, owned_resources={"containers": ["box-one"]}, cleanup=lambda *args: calls.append(args))
    assert calls == [] and ctl.board_path.read_bytes() == before
    assert receipt.read_bytes() == b'{"foreign":true}'



def test_n09_board_saved_then_interruption_reuses_exact_terminal_receipt(tmp_path, monkeypatch):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path))
    receipt = Path(owned["receipt_path"])
    actual = claim_control._atomic_write
    def after_replacement(path, value):
        result = actual(path, value)
        if path == ctl.board_path and receipt.exists():
            raise OSError("owned interruption after board replacement")
        return result
    monkeypatch.setattr(claim_control, "_atomic_write", after_replacement)
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned)
    original = receipt.read_bytes()
    assert json.loads(ctl.board_path.read_text())["claims"] == []
    monkeypatch.setattr(claim_control, "_atomic_write", actual)
    assert ctl.release("one", expected_claim=owned) == receipt
    assert receipt.read_bytes() == original


@pytest.mark.parametrize("save_boundary", [1, 2])
def test_n09_pre_cleanup_save_failure_has_no_side_effect(tmp_path, monkeypatch, save_boundary):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path, containers=["box-one"]))
    actual = claim_control._atomic_write
    count = 0
    def before_save(path, value):
        nonlocal count
        count += 1
        if count == save_boundary:
            raise OSError("owned pre-cleanup save interruption")
        return actual(path, value)
    monkeypatch.setattr(claim_control, "_atomic_write", before_save)
    calls = []
    options = dict(expected_claim=owned, owned_resources={"containers": ["box-one"]},
                   cleanup=lambda *args: calls.append(args))
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", **options)
    assert calls == []
    monkeypatch.setattr(claim_control, "_atomic_write", actual)
    assert ctl.release("one", **options).is_file()
    assert calls == [("containers", "box-one")]


def test_n09_short_receipt_write_is_preserved_and_never_accepted(tmp_path, monkeypatch):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path))
    receipt = Path(owned["receipt_path"])
    original_open = claim_control.os.open
    original_fdopen = claim_control.os.fdopen
    receipt_descriptors = set()
    def owned_open(path, flags, *args, **kwargs):
        descriptor = original_open(path, flags, *args, **kwargs)
        if Path(path) == receipt:
            receipt_descriptors.add(descriptor)
        return descriptor
    class ShortWriter:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            self.stream.__enter__()
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def write(self, payload):
            return self.stream.write(payload[:3])
    def owned_fdopen(descriptor, *args, **kwargs):
        stream = original_fdopen(descriptor, *args, **kwargs)
        return ShortWriter(stream) if descriptor in receipt_descriptors else stream
    monkeypatch.setattr(claim_control.os, "open", owned_open)
    monkeypatch.setattr(claim_control.os, "fdopen", owned_fdopen)
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned)
    assert len(receipt.read_bytes()) == 3
    before = ctl.board_path.read_bytes()
    monkeypatch.setattr(claim_control.os, "open", original_open)
    monkeypatch.setattr(claim_control.os, "fdopen", original_fdopen)
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", expected_claim=owned)
    assert len(receipt.read_bytes()) == 3 and ctl.board_path.read_bytes() == before


@pytest.mark.parametrize("outcome", [True, "UNKNOWN", "unrecognized"])
def test_n09_unknown_or_invalid_cleanup_reconciliation_does_not_repeat(tmp_path, outcome):
    ctl = controller(tmp_path)
    owned = _n09_releasing(ctl, claim(tmp_path, containers=["box-one"]))
    calls = []
    def uncertain(*args):
        calls.append(args)
        raise OSError("owned uncertain effect")
    options = dict(expected_claim=owned, owned_resources={"containers": ["box-one"]},
                   cleanup=uncertain, reconcile_cleanup=lambda *args: outcome)
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", **options)
    before = ctl.board_path.read_bytes()
    with pytest.raises(claim_control.ClaimError):
        ctl.release("one", **options)
    assert calls == [("containers", "box-one")]
    assert ctl.board_path.read_bytes() == before


# Existing permission material loader, connected without any new authority.
def _connection_reader_fixture(monkeypatch, tmp_path):
    from automation.validators import aios_approval_authority_integrity_validator as canonical
    calls = []
    monkeypatch.setattr(canonical, "canonical_production_repo_root", lambda: tmp_path)
    def load(path):
        calls.append(Path(path))
        return {"fixture_record_version": len(calls)}
    monkeypatch.setattr(canonical, "load_json", load)
    environment = {"AIOS_HUMAN_APPROVAL_HMAC_KEY": "TEST_ONLY_NOT_A_REAL_KEY"}
    return canonical, calls, environment


def test_connection_reader_construction_reads_nothing(monkeypatch):
    from automation.validators import aios_approval_authority_integrity_validator as canonical
    from unittest.mock import patch
    def forbidden(*args, **kwargs):
        raise AssertionError("construction must read nothing")
    class NoEnvironmentRead(dict):
        get = forbidden
    monkeypatch.setattr(canonical, "canonical_production_repo_root", forbidden)
    monkeypatch.setattr(canonical, "load_json", forbidden)
    with patch.object(claim_control.os, "environ", NoEnvironmentRead()):
        reader = claim_control.make_canonical_authority_reader()
    assert callable(reader)


def test_connection_reader_reloads_exact_six_fields(monkeypatch, tmp_path):
    from unittest.mock import patch
    canonical, calls, environment = _connection_reader_fixture(monkeypatch, tmp_path)
    reader = claim_control.make_canonical_authority_reader()
    with patch.object(claim_control.os, "environ", environment):
        first = reader()
        environment["AIOS_HUMAN_APPROVAL_HMAC_KEY"] = "SECOND_TEST_KEY"
        second = reader()
    expected_gate = tmp_path / "automation/orchestration/approval_inbox/APPLY_APPROVAL_GATE_001.json"
    assert calls == [expected_gate, tmp_path / canonical.DEFAULT_APPROVAL_INBOX_PATH,
                     tmp_path / canonical.DEFAULT_TRUST_METADATA_PATH] * 2
    assert set(first) == {"gate", "authority", "hmac_key", "trust_metadata", "approval_roots", "current_gate_path"}
    assert first["gate"] != second["gate"]
    assert first["hmac_key"] == "TEST_ONLY_NOT_A_REAL_KEY" and second["hmac_key"] == "SECOND_TEST_KEY"
    assert first["current_gate_path"] == expected_gate
    assert first["approval_roots"] == (tmp_path / canonical.DEFAULT_APPROVAL_ROOT,
                                        tmp_path / canonical.DEFAULT_APPROVAL_ARCHIVE)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("path", ["another-approval.json", "../outside.json", 7])
def test_connection_reader_refuses_wrong_selected_file(monkeypatch, tmp_path, path):
    from unittest.mock import patch
    _, calls, environment = _connection_reader_fixture(monkeypatch, tmp_path)
    reader = claim_control.make_canonical_authority_reader(path)
    with patch.object(claim_control.os, "environ", environment):
        with pytest.raises(claim_control.ClaimError, match="authority material unavailable"):
            reader()
    assert calls == []


@pytest.mark.parametrize("failure", ["missing_record", "bad_record", "missing_key", "root_failure"])
def test_connection_reader_refuses_missing_inputs_without_secret_error(monkeypatch, tmp_path, failure):
    from unittest.mock import patch
    canonical, _, environment = _connection_reader_fixture(monkeypatch, tmp_path)
    secret = environment["AIOS_HUMAN_APPROVAL_HMAC_KEY"]
    if failure == "missing_record":
        def missing(path):
            raise OSError(secret)
        monkeypatch.setattr(canonical, "load_json", missing)
    elif failure == "bad_record":
        monkeypatch.setattr(canonical, "load_json", lambda path: [secret])
    elif failure == "missing_key":
        environment.clear()
    else:
        def no_root():
            raise ValueError(secret)
        monkeypatch.setattr(canonical, "canonical_production_repo_root", no_root)
    with patch.object(claim_control.os, "environ", environment):
        with pytest.raises(claim_control.ClaimError) as caught:
            claim_control.make_canonical_authority_reader()()
    assert str(caught.value) == "production authority material unavailable"
    assert secret not in str(caught.value)
    assert caught.value.__suppress_context__ is True
    assert list(tmp_path.iterdir()) == []



def test_connection_reader_is_default_without_construction_effects(tmp_path, monkeypatch):
    from automation.validators import aios_approval_authority_integrity_validator as canonical
    def forbidden(*args, **kwargs):
        raise AssertionError("default reader must stay lazy")
    monkeypatch.setattr(canonical, "canonical_production_repo_root", forbidden)
    monkeypatch.setattr(canonical, "load_json", forbidden)
    admission = claim_control.ExecutionAdmission(claim_control.TaskClaimController(tmp_path / "board.json"), claim(tmp_path))
    assert callable(admission.authority_reader)
    assert admission.allow_test_trust is False
    assert list(tmp_path.iterdir()) == []


def test_connection_reader_default_missing_permission_never_calls_action(monkeypatch, tmp_path):
    from unittest.mock import patch
    _, _, environment = _connection_reader_fixture(monkeypatch, tmp_path)
    environment.clear()
    admission = claim_control.ExecutionAdmission(claim_control.TaskClaimController(tmp_path / "board.json"), claim(tmp_path))
    calls = []
    with patch.object(claim_control.os, "environ", environment):
        with pytest.raises(claim_control.ClaimError, match="authority material unavailable"):
            admission.execute({}, lambda: calls.append(True))
    assert calls == []
    assert not (tmp_path / "board.json").exists()
