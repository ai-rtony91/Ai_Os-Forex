from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from automation.orchestration.aios_abcd_autonomy_runner import run_one_abcd_task
from automation.orchestration.claims.aios_task_claim_control import (
    SCHEMA_VERSION,
    TaskClaimController,
)


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
    now = datetime.now(UTC)
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
    result = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=TaskClaimController(tmp_path / "board.json"),
                               execute=lambda _: {"status": "COMPLETE"}, changed_paths=["src/one/file.py"])
    assert result.status == "COMPLETE"
    assert result.receipt_path and result.receipt_path.exists()


def test_validation_failed_returns_claim_to_active(tmp_path: Path) -> None:
    args = _inputs(tmp_path); controller = TaskClaimController(tmp_path / "board.json")
    result = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=controller,
                               execute=lambda _: {"status": "FAILED", "reason": "validator failed"})
    assert result.status == "VALIDATION_FAILED"
    assert controller.guard("one", repository="ai-rtony91/Ai_Os", worktree=tmp_path,
                            branch="task/one", head_is_descendant=True, changed_paths=[])["state"] == "ACTIVE"


def test_base_drift_returns_claim_to_active(tmp_path: Path) -> None:
    args = _inputs(tmp_path); controller = TaskClaimController(tmp_path / "board.json")
    result = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=controller,
                               execute=lambda _: {"status": "COMPLETE", "base_drift": True})
    assert result.status == "BASE_DRIFT"
    assert controller.guard("one", repository="ai-rtony91/Ai_Os", worktree=tmp_path,
                            branch="task/one", head_is_descendant=True, changed_paths=[])["state"] == "ACTIVE"


def test_collision_reports_complete_canonical_reason(tmp_path: Path) -> None:
    args = _inputs(tmp_path); controller = TaskClaimController(tmp_path / "board.json")
    controller.acquire(_claim(tmp_path, "owner", branch="task/one"))
    result = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=controller, execute=lambda _: {"status": "COMPLETE"})
    assert result.reason == "claim blocked: branch:owner, claimed_path:owner, worktree_path:owner"


def test_one_task_execution_limit(tmp_path: Path) -> None:
    args = _inputs(tmp_path, two=True); executed = []
    result = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=TaskClaimController(tmp_path / "board.json"),
                               execute=lambda packet: executed.append(packet["packet_id"]) or {"status": "COMPLETE"})
    assert executed == ["one"]
    assert result.status == "COMPLETE"


def test_cleanup_ownership_isolation(tmp_path: Path) -> None:
    args = _inputs(tmp_path); cleaned = []
    result = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=TaskClaimController(tmp_path / "board.json"),
                               execute=lambda _: {"status": "COMPLETE"},
                               cleanup_resources={"containers": ["not-owned"]},
                               cleanup=lambda field, value: cleaned.append((field, value)))
    assert result.status == "BLOCKED"
    assert result.reason == "cleanup requested for resource not owned by task"
    assert cleaned == []


def test_next_eligible_task_is_returned_but_not_executed(tmp_path: Path) -> None:
    args = _inputs(tmp_path, two=True); executed = []
    result = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=TaskClaimController(tmp_path / "board.json"),
                               execute=lambda packet: executed.append(packet["packet_id"]) or {"status": "COMPLETE"})
    assert result.next_task and result.next_task["id"] == "two"
    assert executed == ["one"]



def test_n08_connector_fail_retry_success_has_one_owner_and_receipt(tmp_path):
    import json
    args = _inputs(tmp_path)
    ctl = TaskClaimController(tmp_path / "board.json")
    first = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=ctl,
                              execute=lambda _: {"status": "FAILED"})
    assert first.status == "VALIDATION_FAILED"
    def verified_callback(_):
        assert len(json.loads(ctl.board_path.read_text())["claims"]) == 1
        return {"status": "COMPLETE"}
    second = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=ctl, execute=verified_callback)
    assert second.status == "COMPLETE"
    assert len(list((tmp_path / "receipts").glob("*.json"))) == 1
    assert json.loads(ctl.board_path.read_text())["claims"] == []


@pytest.mark.parametrize("state", ["VERIFYING", "INTEGRATING", "RELEASING", "BLOCKED"])
def test_n08_connector_does_not_reexecute_in_progress_or_blocked_attempt(tmp_path, state):
    args = _inputs(tmp_path)
    ctl = TaskClaimController(tmp_path / "board.json")
    request = args[3]["one"]
    ctl.acquire(request)
    ctl.transition("one", "VERIFYING")
    if state in {"INTEGRATING", "RELEASING"}:
        ctl.transition("one", "INTEGRATING")
    if state == "RELEASING":
        ctl.transition("one", "RELEASING")
    if state == "BLOCKED":
        ctl.transition("one", "BLOCKED")
    before = ctl.board_path.read_bytes()
    result = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=ctl,
                               execute=lambda _: (_ for _ in ()).throw(AssertionError("must not execute")))
    assert result.status == "BLOCKED"
    assert ctl.board_path.read_bytes() == before


def test_n08_connector_rejects_claim_for_different_selected_task(tmp_path):
    args = _inputs(tmp_path)
    args[3]["one"]["task_id"] = "other"
    ctl = TaskClaimController(tmp_path / "board.json")
    result = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=ctl,
                               execute=lambda _: (_ for _ in ()).throw(AssertionError("must not execute")))
    assert result.status == "BLOCKED"
    assert not ctl.board_path.exists()



def test_n09_connector_reconciles_release_without_replaying_execute(tmp_path, monkeypatch):
    import json

    from automation.orchestration.claims import aios_task_claim_control as claims_module
    args = _inputs(tmp_path)
    ctl = TaskClaimController(tmp_path / "board.json")
    calls = []
    receipt = Path(args[3]["one"]["receipt_path"])
    actual = claims_module._atomic_write
    def stop_after_receipt(path, value):
        if receipt.exists():
            raise OSError("owned board replacement failure")
        return actual(path, value)
    monkeypatch.setattr(claims_module, "_atomic_write", stop_after_receipt)
    try:
        result = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=ctl,
                                   execute=lambda packet: calls.append(packet["packet_id"]) or {"status": "COMPLETE"})
        assert result.status == "BLOCKED"
    except (OSError, claims_module.ClaimError):
        pass  # original causal failure is followed by the actual restart check
    assert calls == ["one"] and receipt.exists()
    original = receipt.read_bytes()
    monkeypatch.setattr(claims_module, "_atomic_write", actual)
    resumed = run_one_abcd_task(*args, legacy_independent_tasks=True, claim_controller=TaskClaimController(ctl.board_path),
                                execute=lambda _: (_ for _ in ()).throw(AssertionError("accepted execution must not replay")))
    assert resumed.status == "RELEASE_RECONCILED"
    assert resumed.next_task is None  # release is not requirement acceptance
    assert resumed.receipt_path == receipt and receipt.read_bytes() == original
    assert json.loads(ctl.board_path.read_text())["claims"] == []


def test_n06_pure_next_task_retains_already_qualified_dependency_fact():
    # Pure selection control only: DONE here stands for an upstream reader's
    # already-qualified fact. This test does not create acceptance evidence.
    from automation.orchestration.aios_abcd_autonomy_runner import _next_task
    queue = {"schema": "AIOS_RUNTIME_EXECUTION_QUEUE.v1", "items": [
        {"id": "A", "state": "DONE", "depends_on": []},
        {"id": "B", "state": "QUEUED", "depends_on": ["A"]},
    ]}
    selected = _next_task(queue, "A")
    assert selected is not None and selected["id"] == "B"


class _N06PublicationFixture:
    """Inert owner stand-in, not a native publication implementation/proof store."""

    def __init__(self, accepted=None):
        self.accepted = dict(accepted or {})
        self.seen = {}

    def __call__(self, request):
        from automation.orchestration.aios_abcd_autonomy_runner import (
            AcceptedRequirement,
        )
        self.seen[request.task_id] = request
        saved = self.accepted.get(request.task_id)
        if saved is None:
            return None  # This fixture independently knows its accepted set.
        if saved != request:
            raise ValueError("fixture existing-owner source/request/claim evidence changed")
        return AcceptedRequirement(saved)

    def publish(self, task):
        self.accepted[task] = self.seen[task]


def _n06_inputs(tmp_path):
    queue, state, items, claims = _inputs(tmp_path, two=True)
    queue["items"][1]["depends_on"] = ["one"]
    items["two"]["depends_on"] = ["one"]
    queue["items"].append({**queue["items"][1], "id": "three", "packet_id": "three", "depends_on": ["two"]})
    items["three"] = {**_item("three"), "depends_on": ["two"]}
    claims["three"] = _claim(tmp_path, "three")
    return queue, state, items, claims


def _n06_execute(reader, calls):
    def execute(packet):
        calls.append(packet["packet_id"])
        reader.publish(packet["packet_id"])
        return {"status": "COMPLETE"}
    return execute


def test_n06_abc_restarts_unchanged_graph_feed_both_actual_owners(tmp_path, monkeypatch):
    import copy

    from automation.orchestration import aios_abcd_autonomy_runner as runner
    args = _n06_inputs(tmp_path)
    original = copy.deepcopy(args)
    calls, resolver_states, dispatch_views = [], [], []
    actual_resolve, actual_dispatch = runner.resolve_execution_packet, runner.build_dispatch_plan
    def resolve(item, state):
        resolver_states.append((item["packet_id"], dict(state["dependency_states"])))
        return actual_resolve(item, state)
    def dispatch(view, **kwargs):
        dispatch_views.append(copy.deepcopy(view))
        return actual_dispatch(view, **kwargs)
    monkeypatch.setattr(runner, "resolve_execution_packet", resolve)
    monkeypatch.setattr(runner, "build_dispatch_plan", dispatch)
    reader = _N06PublicationFixture()
    for expected, successor in (("one", "two"), ("two", "three"), ("three", None)):
        # Fresh reader/controller and the same immutable source graph simulate
        # restart. The test's accepted records are external fixture observations.
        reader = _N06PublicationFixture(reader.accepted)
        result = run_one_abcd_task(*args, claim_controller=TaskClaimController(tmp_path / "board.json"),
                                  execute=_n06_execute(reader, calls), acceptance_reader=reader)
        assert result.status == "COMPLETE" and result.task_id == expected
        assert (result.next_task["id"] if result.next_task else None) == successor
    assert calls == ["one", "two", "three"]
    assert args == original
    assert resolver_states[1][1]["one"] == "DONE"
    assert resolver_states[2][1]["one"] == resolver_states[2][1]["two"] == "DONE"
    assert any({item["id"]: item["state"] for item in view["items"]}.get("one") == "DONE"
               for view in dispatch_views)


def test_n06_requires_explicit_reader_or_legacy_mode(tmp_path):
    args = _inputs(tmp_path)
    result = run_one_abcd_task(*args, claim_controller=TaskClaimController(tmp_path / "board.json"),
                              execute=lambda _: pytest.fail("unqualified mode executed"))
    assert result.status == "BLOCKED" and not (tmp_path / "board.json").exists()


def test_n06_legacy_compatibility_cannot_supply_dependency_acceptance(tmp_path):
    result = run_one_abcd_task(*_n06_inputs(tmp_path), legacy_independent_tasks=True,
                              claim_controller=TaskClaimController(tmp_path / "board.json"),
                              execute=lambda _: pytest.fail("legacy dependency executed"))
    assert result.status == "BLOCKED" and not (tmp_path / "board.json").exists()


@pytest.mark.parametrize("untrusted", [True, "DONE", {"status": "COMPLETE"}, {"accepted": True}])
def test_n06_generic_results_do_not_mean_acceptance(tmp_path, untrusted):
    result = run_one_abcd_task(*_n06_inputs(tmp_path), acceptance_reader=lambda _: untrusted,
                              claim_controller=TaskClaimController(tmp_path / "board.json"),
                              execute=lambda _: pytest.fail("malformed acceptance executed"))
    assert result.status == "BLOCKED" and not (tmp_path / "board.json").exists()


@pytest.mark.parametrize("field", ["task_id", "packet_id", "request_sha256", "claim_sha256", "acquired_at"])
def test_n06_typed_readback_must_correlate_exact_request(tmp_path, field):
    from dataclasses import replace

    from automation.orchestration.aios_abcd_autonomy_runner import AcceptedRequirement
    result = run_one_abcd_task(*_n06_inputs(tmp_path),
                              acceptance_reader=lambda request: AcceptedRequirement(replace(request, **{field: "other"})),
                              claim_controller=TaskClaimController(tmp_path / "board.json"),
                              execute=lambda _: pytest.fail("cross-request evidence executed"))
    assert result.status == "BLOCKED" and not (tmp_path / "board.json").exists()


@pytest.mark.parametrize("reason", ["unknown acceptance", "stale owner source", "failed validators", "conflicting records"])
def test_n06_reader_errors_block_and_preserve_evidence(tmp_path, reason):
    args = _n06_inputs(tmp_path)
    sentinel = tmp_path / "evidence.txt"
    sentinel.write_text("original owner evidence")
    def reader(_):
        raise ValueError(reason)
    result = run_one_abcd_task(*args, acceptance_reader=reader,
                              claim_controller=TaskClaimController(tmp_path / "board.json"),
                              execute=lambda _: pytest.fail("unknown evidence executed"))
    assert result.status == "BLOCKED"
    assert result.reason == "existing publication reader failed"
    assert reason not in result.reason
    assert sentinel.read_text() == "original owner evidence" and not (tmp_path / "board.json").exists()


def test_n06_done_labels_and_resolver_state_cannot_bypass_readers(tmp_path):
    args = _n06_inputs(tmp_path)
    args[0]["items"][0]["state"] = "DONE"
    args[1]["dependency_states"] = {"one": "DONE", "two": "DONE"}
    result = run_one_abcd_task(*args, acceptance_reader=lambda _: None,
                              claim_controller=TaskClaimController(tmp_path / "board.json"),
                              execute=lambda _: pytest.fail("literal DONE executed"))
    assert result.status == "BLOCKED" and not (tmp_path / "board.json").exists()


def test_n06_complete_and_release_alone_do_not_accept_requirement(tmp_path):
    args = _n06_inputs(tmp_path)
    calls = []
    ctl = TaskClaimController(tmp_path / "board.json")
    first = run_one_abcd_task(*args, acceptance_reader=lambda _: None, claim_controller=ctl,
                             execute=lambda packet: calls.append(packet["packet_id"]) or {"status": "COMPLETE"})
    assert first.status == "AWAITING_ACCEPTANCE" and first.next_task is None
    original = first.receipt_path.read_bytes()
    again = run_one_abcd_task(*args, acceptance_reader=lambda _: None, claim_controller=ctl,
                             execute=lambda _: pytest.fail("released task executed twice"))
    assert again.status == "RELEASE_RECONCILED" and again.next_task is None
    assert calls == ["one"] and first.receipt_path.read_bytes() == original


def test_n06_accepted_without_terminal_release_never_executes_or_acquires(tmp_path):
    from automation.orchestration.aios_abcd_autonomy_runner import AcceptedRequirement
    args = _n06_inputs(tmp_path)
    result = run_one_abcd_task(*args, acceptance_reader=lambda request: AcceptedRequirement(request) if request.task_id == "one" else None,
                              claim_controller=TaskClaimController(tmp_path / "board.json"),
                              execute=lambda _: pytest.fail("accepted work executed twice"))
    assert result.status == "BLOCKED" and "terminal release" in result.reason
    assert not (tmp_path / "board.json").exists()


def test_n06_accepted_release_pending_reconciles_even_input_done_then_b(tmp_path, monkeypatch):
    import json

    from automation.orchestration.claims import aios_task_claim_control as owner
    args = _n06_inputs(tmp_path)
    reader, calls = _N06PublicationFixture(), []
    ctl = TaskClaimController(tmp_path / "board.json")
    receipt = Path(args[3]["one"]["receipt_path"])
    actual = owner._atomic_write
    def stop_after_receipt(path, value):
        if receipt.exists():
            raise OSError("fixture interrupted board replacement")
        return actual(path, value)
    monkeypatch.setattr(owner, "_atomic_write", stop_after_receipt)
    first = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl,
                             execute=_n06_execute(reader, calls))
    assert first.status == "BLOCKED" and calls == ["one"] and receipt.exists()
    saved = receipt.read_bytes()
    assert json.loads(ctl.board_path.read_text())["claims"][0]["state"] == "RELEASING"
    monkeypatch.setattr(owner, "_atomic_write", actual)
    args[0]["items"][0]["state"] = "DONE"  # Explicitly not ownership evidence.
    reader = _N06PublicationFixture(reader.accepted)
    resumed = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=TaskClaimController(ctl.board_path),
                               execute=lambda _: pytest.fail("pending release must not execute"))
    assert resumed.status == "RELEASE_RECONCILED" and resumed.task_id == "one" and resumed.next_task is None
    assert receipt.read_bytes() == saved and json.loads(ctl.board_path.read_text())["claims"] == []
    next_result = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=TaskClaimController(ctl.board_path),
                                   execute=_n06_execute(reader, calls))
    assert next_result.task_id == "two" and next_result.status == "COMPLETE" and calls == ["one", "two"]


@pytest.mark.parametrize("change", ["validator", "scope", "approval", "attempt", "claim_attempt", "source"])
def test_n06_changed_accepted_input_or_attempt_blocks_without_replay(tmp_path, change):
    args = _n06_inputs(tmp_path)
    reader, calls = _N06PublicationFixture(), []
    ctl = TaskClaimController(tmp_path / "board.json")
    first = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl, execute=_n06_execute(reader, calls))
    assert first.status == "COMPLETE"
    board, receipt = ctl.board_path.read_bytes(), first.receipt_path.read_bytes()
    if change == "validator":
        args[2]["one"]["validators"] = ["different validator"]
    elif change == "scope":
        args[0]["items"][0]["allowed_paths"] = ["different/path"]
    elif change == "approval":
        args[2]["one"]["approval_authority"] = "changed authority"
    elif change == "attempt":
        args[0]["items"][0]["attempt"] = args[2]["one"]["attempt"] = 1
    elif change == "claim_attempt":
        args[3]["one"]["acquired_at"] = (datetime.fromisoformat(args[3]["one"]["acquired_at"]) + timedelta(seconds=1)).isoformat()
    else:
        args[2]["one"]["source_sha256"] = "different source"
    result = run_one_abcd_task(*args, acceptance_reader=_N06PublicationFixture(reader.accepted), claim_controller=ctl,
                              execute=lambda _: pytest.fail("changed accepted work replayed"))
    assert result.status == "BLOCKED" and calls == ["one"]
    assert ctl.board_path.read_bytes() == board and first.receipt_path.read_bytes() == receipt


def test_n06_unrelated_arrival_preserves_acceptance_and_priority(tmp_path):
    args = _n06_inputs(tmp_path)
    reader, calls = _N06PublicationFixture(), []
    ctl = TaskClaimController(tmp_path / "board.json")
    first = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl, execute=_n06_execute(reader, calls))
    assert first.next_task["id"] == "two"
    args[0]["items"].append({**args[0]["items"][0], "id": "urgent", "packet_id": "urgent", "priority": "P0"})
    args[2]["urgent"], args[3]["urgent"] = _item("urgent"), _claim(tmp_path, "urgent")
    reader = _N06PublicationFixture(reader.accepted)
    result = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl, execute=_n06_execute(reader, calls))
    assert result.status == "COMPLETE" and result.task_id == "urgent"
    assert result.next_task["id"] == "two" and calls == ["one", "urgent"]


@pytest.mark.parametrize("defect", ["different_edges", "unknown_dependency", "duplicate_task", "malformed_request", "malformed_attempt"])
def test_n06_graph_defects_block_actual_dispatch_or_resolution(tmp_path, defect):
    args = _n06_inputs(tmp_path)
    if defect == "different_edges":
        args[2]["two"]["depends_on"] = []
    elif defect == "unknown_dependency":
        args[0]["items"][0]["depends_on"] = args[2]["one"]["depends_on"] = ["missing"]
    elif defect == "duplicate_task":
        args[0]["items"].append(dict(args[0]["items"][0]))
    elif defect == "malformed_request":
        args[2]["one"]["validators"] = ("tuple aliases JSON list",)
    else:
        args[0]["items"][0]["attempt"] = args[2]["one"]["attempt"] = False
    result = run_one_abcd_task(*args, acceptance_reader=lambda _: None,
                              claim_controller=TaskClaimController(tmp_path / "board.json"),
                              execute=lambda _: pytest.fail("invalid graph executed"))
    assert result.status == "BLOCKED" and not (tmp_path / "board.json").exists()


def test_n06_corrupt_terminal_evidence_preserved_and_blocks_successor(tmp_path):
    args = _n06_inputs(tmp_path)
    reader, calls = _N06PublicationFixture(), []
    ctl = TaskClaimController(tmp_path / "board.json")
    first = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl, execute=_n06_execute(reader, calls))
    # Deliberately corrupt only this owned immutable receipt fixture.
    first.receipt_path.chmod(0o600)
    first.receipt_path.write_text('{"partial":true}')
    damaged, board = first.receipt_path.read_bytes(), ctl.board_path.read_bytes()
    result = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl,
                              execute=lambda _: pytest.fail("corrupt predecessor allowed successor"))
    assert result.status == "BLOCKED" and calls == ["one"]
    assert first.receipt_path.read_bytes() == damaged and ctl.board_path.read_bytes() == board



def test_n06_failed_validation_does_not_promote_dependency(tmp_path):
    args = _n06_inputs(tmp_path)
    reader, calls = _N06PublicationFixture(), []
    ctl = TaskClaimController(tmp_path / "board.json")
    result = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl,
                              execute=lambda packet: calls.append(packet["packet_id"]) or {"status": "FAILED"})
    assert result.status == "VALIDATION_FAILED" and result.next_task is None
    assert reader.accepted == {} and calls == ["one"]
    retried = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl, execute=_n06_execute(reader, calls))
    assert retried.status == "COMPLETE" and calls == ["one", "one"]
    assert retried.next_task["id"] == "two"


def test_n06_terminal_reader_independently_rejects_cross_attempt_publication(tmp_path):
    from automation.orchestration.aios_abcd_autonomy_runner import AcceptedRequirement

    args = _n06_inputs(tmp_path)
    reader, calls = _N06PublicationFixture(), []
    ctl = TaskClaimController(tmp_path / "board.json")
    first = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl, execute=_n06_execute(reader, calls))
    board, receipt = ctl.board_path.read_bytes(), first.receipt_path.read_bytes()
    args[3]["one"]["attempt_id"] = "different exact claim attempt"
    # Even a qualified publication observation for a newer claim must not bind
    # the old claim owner's terminal receipt to that new incarnation.
    result = run_one_abcd_task(*args, acceptance_reader=lambda request: AcceptedRequirement(request) if request.task_id == "one" else None,
                              claim_controller=ctl, execute=lambda _: pytest.fail("wrong terminal identity executed"))
    assert result.status == "BLOCKED" and "terminal claim reference" in result.reason
    assert calls == ["one"] and ctl.board_path.read_bytes() == board
    assert first.receipt_path.read_bytes() == receipt


def test_n06_moved_terminal_receipt_is_not_readback(tmp_path):
    args = _n06_inputs(tmp_path)
    reader, calls = _N06PublicationFixture(), []
    ctl = TaskClaimController(tmp_path / "board.json")
    first = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl, execute=_n06_execute(reader, calls))
    retained = first.receipt_path.with_suffix(".retained")
    original = first.receipt_path.read_bytes()
    first.receipt_path.rename(retained)
    board = ctl.board_path.read_bytes()
    result = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl,
                              execute=lambda _: pytest.fail("moved terminal evidence executed"))
    assert result.status == "BLOCKED" and calls == ["one"]
    assert retained.read_bytes() == original and ctl.board_path.read_bytes() == board


def test_campaign_abcd_selected_request_correlates_and_forwards_actual_owners(tmp_path, monkeypatch):
    from automation.orchestration.aios_abcd_autonomy_runner import _acceptance_request
    from tests.orchestration.test_aios_repo_state_evidence import _campaign_fixture
    args = _inputs(tmp_path)
    args[2]["one"].pop("commit_message"); args[2]["one"].pop("pr_authority")
    args[3]["one"]["branch"] = "fixture/topic"
    request = _acceptance_request(args[0]["items"][0], args[2]["one"], args[3]["one"])
    selection = (request.task_id, request.packet_id, request.request_sha256, request.claim_sha256, request.acquired_at)
    _, _, state, profile, admission, _, _, _ = _campaign_fixture(tmp_path, monkeypatch, queue_item=args[2]["one"], selection=selection)
    args = (args[0], state, args[2], args[3])
    reader, calls, seen = _N06PublicationFixture(), [], []
    def profile_reader(actual):
        seen.append(actual)
        assert actual == request
        return profile
    result = run_one_abcd_task(*args, claim_controller=TaskClaimController(tmp_path / "board.json"),
        acceptance_reader=reader, packet_profile_reader=profile_reader, campaign_admission_reader=admission,
        execute=_n06_execute(reader, calls))
    assert result.status == "COMPLETE" and calls == ["one"] and seen == [request]
    assert result.packet["write_scope"] == ["src/one"]
    assert result.packet["repository_state"]["is_clean"] is False


def test_campaign_abcd_wrong_selected_profile_blocks_before_execution(tmp_path, monkeypatch):
    from tests.orchestration.test_aios_repo_state_evidence import _campaign_fixture
    args = _inputs(tmp_path)
    args[2]["one"].pop("commit_message"); args[2]["one"].pop("pr_authority")
    args[3]["one"]["branch"] = "fixture/topic"
    _, _, state, profile, admission, _, _, _ = _campaign_fixture(tmp_path, monkeypatch, queue_item=args[2]["one"])
    result = run_one_abcd_task(args[0], state, args[2], args[3], claim_controller=TaskClaimController(tmp_path / "board.json"),
        acceptance_reader=lambda _: None, packet_profile_reader=lambda _: profile, campaign_admission_reader=admission,
        execute=lambda _: pytest.fail("mismatched campaign profile executed"))
    assert result.status == "BLOCKED" and not (tmp_path / "board.json").exists()


# Finite existing-owner caller: synthetic task callbacks are not real workers.
def _connection_workflow(tmp_path, fresh, reader, execute, **options):
    from automation.orchestration import aios_abcd_autonomy_runner as runner
    values = {"max_tasks": 3, "max_elapsed_seconds": 10, "stop_requested": lambda: False,
              "monotonic": lambda: 0.0, **options}
    return runner.run_abcd_workflow(read_current_inputs=fresh,
        claim_controller=TaskClaimController(tmp_path / "board.json"),
        execute=execute, acceptance_reader=reader, **values)


def test_connection_workflow_advances_actual_owners_abc(tmp_path):
    import copy
    args = _n06_inputs(tmp_path)
    reader, calls, reads = _N06PublicationFixture(), [], []
    def fresh():
        for task in calls:
            assert Path(args[3][task]["receipt_path"]).exists()
            assert task in reader.accepted
        reads.append(True)
        return copy.deepcopy(args)
    result = _connection_workflow(tmp_path, fresh, reader, _n06_execute(reader, calls))
    assert result.status == "TASK_LIMIT"
    assert calls == ["one", "two", "three"] and len(reads) == 3
    assert [item.task_id for item in result.results] == calls
    assert all(item.status == "COMPLETE" for item in result.results)


def test_connection_workflow_fresh_frontier_replaces_old_preview(tmp_path):
    import copy
    args = _n06_inputs(tmp_path)
    reader, calls = _N06PublicationFixture(), []
    def fresh():
        current = copy.deepcopy(args)
        if calls:
            current[0]["items"] = [x for x in current[0]["items"] if x["id"] != "two"]
            current[0]["items"][1]["depends_on"] = ["one"]
            current[2].pop("two"); current[3].pop("two")
            current[2]["three"]["depends_on"] = ["one"]
        return current
    result = _connection_workflow(tmp_path, fresh, reader, _n06_execute(reader, calls), max_tasks=2)
    assert result.status == "TASK_LIMIT" and calls == ["one", "three"]
    assert result.results[0].next_task["id"] == "two"


def test_connection_workflow_false_completion_never_starts_successor(tmp_path):
    args, calls = _n06_inputs(tmp_path), []
    result = _connection_workflow(tmp_path, lambda: args, lambda request: None,
        lambda packet: calls.append(packet["packet_id"]) or {"status": "COMPLETE"})
    assert result.status == "AWAITING_ACCEPTANCE" and calls == ["one"]


@pytest.mark.parametrize("options", [
    {"max_tasks": True}, {"max_tasks": 0}, {"max_tasks": 6},
    {"max_elapsed_seconds": True}, {"max_elapsed_seconds": 0},
    {"max_elapsed_seconds": 10**1000}, {"stop_requested": lambda: True},
    {"max_elapsed_seconds": float("nan")}, {"max_elapsed_seconds": float("inf")},
    {"monotonic": lambda: False}, {"monotonic": lambda: float("nan")},
    {"stop_requested": lambda: "false"}, {"legacy_independent_tasks": True},
])
def test_connection_workflow_invalid_controls_never_read_or_run(tmp_path, options):
    def forbidden(*args):
        pytest.fail("invalid workflow control reached work")
    result = _connection_workflow(tmp_path, forbidden, forbidden, forbidden, **options)
    assert result.status == "BLOCKED" and list(tmp_path.iterdir()) == []


def test_connection_workflow_missing_acceptance_reader_never_reads(tmp_path):
    result = _connection_workflow(tmp_path, lambda: pytest.fail("missing reader loaded work"), None,
                                  lambda packet: pytest.fail("missing reader started work"))
    assert result.status == "BLOCKED" and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("cause", ["stop", "deadline", "clock_regression"])
def test_connection_workflow_mid_load_controls_stop_before_callback(tmp_path, cause):
    args, reader, calls = _n06_inputs(tmp_path), _N06PublicationFixture(), []
    clock, stopped = [1.0], [False]
    def fresh():
        if cause == "stop": stopped[0] = True
        elif cause == "deadline": clock[0] = 12.0
        else: clock[0] = 0.5
        return args
    result = _connection_workflow(tmp_path, fresh, reader, _n06_execute(reader, calls),
        monotonic=lambda: clock[0], stop_requested=lambda: stopped[0])
    assert result.status == "BLOCKED" and calls == []


def test_connection_workflow_limit_one_keeps_next_preview_unexecuted(tmp_path):
    args, reader, calls = _n06_inputs(tmp_path), _N06PublicationFixture(), []
    result = _connection_workflow(tmp_path, lambda: args, reader, _n06_execute(reader, calls), max_tasks=1)
    assert result.status == "TASK_LIMIT" and calls == ["one"]
    assert result.results[0].next_task["id"] == "two"


def test_connection_workflow_callback_error_never_retries(tmp_path):
    args, reader, calls = _n06_inputs(tmp_path), _N06PublicationFixture(), []
    def execute(packet):
        calls.append(packet["packet_id"])
        raise RuntimeError("owned uncertain callback")
    result = _connection_workflow(tmp_path, lambda: args, reader, execute)
    assert result.status == "BLOCKED" and calls == ["one"]


@pytest.mark.parametrize("duplicate", ["task", "packet"])
def test_connection_workflow_duplicate_id_stops_before_second_callback(tmp_path, monkeypatch, duplicate):
    from automation.orchestration import aios_abcd_autonomy_runner as runner
    calls, reads = [], []
    def fresh():
        index = len(reads); reads.append(True)
        task = "same-task" if duplicate == "task" else f"task-{index}"
        packet = "same-packet" if duplicate == "packet" else f"packet-{index}"
        return ({}, {}, {task: {"packet_id": packet}}, {})
    def one(view, state, items, claims, **options):
        task, item = next(iter(items.items()))
        value = options["execute"]({"packet_id": item["packet_id"]})
        return runner.AutonomyRunResult(value["status"], "guard control only", task)
    monkeypatch.setattr(runner, "run_one_abcd_task", one)
    result = _connection_workflow(tmp_path, fresh, lambda request: None,
        lambda packet: calls.append(packet["packet_id"]) or {"status": "COMPLETE"})
    assert result.status != "TASK_LIMIT" and len(calls) == 1


def test_connection_workflow_reconciled_release_stops_before_next_load(tmp_path, monkeypatch):
    from automation.orchestration.claims import aios_task_claim_control as owner
    args = _n06_inputs(tmp_path)
    reader, calls, reads = _N06PublicationFixture(), [], []
    ctl = TaskClaimController(tmp_path / "board.json")
    receipt = Path(args[3]["one"]["receipt_path"])
    actual = owner._atomic_write
    def stop_after_receipt(path, value):
        if receipt.exists():
            raise OSError("fixture interrupted board replacement")
        return actual(path, value)
    monkeypatch.setattr(owner, "_atomic_write", stop_after_receipt)
    first = run_one_abcd_task(*args, acceptance_reader=reader, claim_controller=ctl,
                             execute=_n06_execute(reader, calls))
    assert first.status == "BLOCKED" and calls == ["one"] and receipt.exists()
    saved = receipt.read_bytes()
    monkeypatch.setattr(owner, "_atomic_write", actual)
    args[0]["items"][0]["state"] = "DONE"
    reader = _N06PublicationFixture(reader.accepted)
    def fresh():
        reads.append(True)
        assert len(reads) == 1
        return args
    result = _connection_workflow(tmp_path, fresh, reader,
        lambda packet: pytest.fail("reconciliation must not launch work"))
    assert result.status == "RELEASE_RECONCILED" and len(result.results) == 1
    assert reads == [True] and calls == ["one"] and receipt.read_bytes() == saved


def _frozen_abcd_runner():
    """Load the exact runner named by AIOS_ABCD_RUNNER_PATH for red/green checks."""
    import hashlib
    import importlib.util
    import os
    import sys

    path_value = os.environ.get("AIOS_ABCD_RUNNER_PATH")
    if not path_value:
        from automation.orchestration import aios_abcd_autonomy_runner as runner
        return runner
    path = Path(path_value).resolve()
    module_name = "_aios_abcd_frozen_" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load frozen runner: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_frozen_runner_saves_release_intent_and_reloads_without_reexecution(tmp_path, monkeypatch):
    """An accepted stop must leave a readable release record for the next call."""
    import json
    from automation.orchestration.claims import aios_task_claim_control as claims_module

    runner = _frozen_abcd_runner()
    def writable(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(claims_module, "_atomic_write", writable)
    monkeypatch.setattr(runner, "_atomic_write", writable, raising=False)
    args = _inputs(tmp_path)
    controller = TaskClaimController(tmp_path / "board.json")
    calls = []
    accepted = [False]

    def reader(request):
        if not accepted[0]:
            return None
        return runner.AcceptedRequirement(request)

    first = runner.run_one_abcd_task(
        *args,
        acceptance_reader=reader,
        claim_controller=controller,
        execute=lambda packet: calls.append(packet["packet_id"]) or accepted.__setitem__(0, True) or {"status": "COMPLETE"},
        checkpoint_after_acceptance=lambda _: True,
    )
    assert first.status == "ACCEPTED_CHECKPOINT", first.reason
    saved = json.loads((tmp_path / "board.json").read_text(encoding="utf-8"))["claims"][0]
    assert saved["state"] == "RELEASING"
    assert isinstance(saved.get("release_intent"), dict)

    reloaded = runner.run_one_abcd_task(
        *args,
        acceptance_reader=reader,
        claim_controller=TaskClaimController(tmp_path / "board.json"),
        execute=lambda _: pytest.fail("accepted work was executed again after reload"),
    )
    assert reloaded.status == "RELEASE_RECONCILED"
    assert calls == ["one"]


@pytest.mark.parametrize("defect", ["bad_hash", "bad_shape"])
def test_frozen_runner_rejects_bad_saved_release_readback(tmp_path, defect, monkeypatch):
    """A saved release record with a bad hash or shape must stop before the checkpoint."""
    import json
    from automation.orchestration.claims import aios_task_claim_control as claims_module

    runner = _frozen_abcd_runner()
    def writable(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(claims_module, "_atomic_write", writable)
    monkeypatch.setattr(runner, "_atomic_write", writable, raising=False)
    args = _inputs(tmp_path)
    controller = TaskClaimController(tmp_path / "board.json")
    accepted = [False]

    def read_bad_release(self, task_id, expected_claim):
        saved = json.loads(self.board_path.read_text(encoding="utf-8"))["claims"][0]
        saved["release_intent"] = {
            "schema": runner.RELEASE_SCHEMA,
            "claim_sha256": runner._claim_contract(saved),
            "started_at": saved["acquired_at"],
            "receipt_path": saved["receipt_path"],
            "cleanup_mode": "once",
            "resources": [],
        }
        if defect == "bad_hash":
            saved["release_intent"]["claim_sha256"] = "0" * 64
        else:
            saved["release_intent"]["resources"] = {}
        return saved

    monkeypatch.setattr(
        TaskClaimController,
        "prepare_release_intent",
        lambda self, *args, **kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        TaskClaimController,
        "read_release_claim",
        read_bad_release,
        raising=False,
    )
    result = runner.run_one_abcd_task(
        *args,
        acceptance_reader=lambda request: runner.AcceptedRequirement(request) if accepted[0] else None,
        claim_controller=controller,
        execute=lambda _: accepted.__setitem__(0, True) or {"status": "COMPLETE"},
        checkpoint_after_acceptance=lambda _: True,
    )
    assert result.status == "BLOCKED"
