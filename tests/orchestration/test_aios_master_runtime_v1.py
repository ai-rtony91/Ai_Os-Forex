import ast
import json
from pathlib import Path

import pytest

from automation.orchestration.aios_master_runtime_v1 import AIOSMasterRuntime, ResumeRejected, STAGES
from automation.orchestration.platform import OrchestrationPlatform


def runtime(tmp_path: Path) -> AIOSMasterRuntime:
    active = AIOSMasterRuntime(".")
    active.state_path = tmp_path / "master-runtime-v1.json"
    return active


def test_plan_is_deterministic_and_complete(tmp_path: Path) -> None:
    active = runtime(tmp_path)
    first = active.execute(command="plan")
    second = active.execute(command="plan")
    assert first["normalized_fingerprint"] == second["normalized_fingerprint"]
    assert [item["stage_id"] for item in first["stages"]] == list(STAGES)
    assert active.validate_state(first)["status"] == "PASS"
    assert not any(first["protected_actions"].values())
    assert first["composition"].keys() >= {
        "spine", "braid", "queue", "dispatcher", "packet_builder",
        "packet_resolver", "autonomy_governor", "countdown",
    }


def test_checkpoint_resume_and_incompatible_head(tmp_path: Path) -> None:
    active = runtime(tmp_path)
    active.execute(command="run", checkpoint=True)
    assert active.resume()["status"] == "PASS"
    saved = json.loads(active.state_path.read_text())
    saved["identity"]["head"] = "0" * 40
    active.state_path.write_text(json.dumps(saved))
    with pytest.raises(ResumeRejected, match="INCOMPATIBLE_HEAD"):
        active.resume()


def test_platform_integration_and_schema() -> None:
    state = OrchestrationPlatform(".").master_runtime(command="plan")
    schema = json.loads(Path("schemas/orchestration/aios_master_runtime_v1.schema.json").read_text())
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator(schema).validate(state)


def test_repository_local_schema_contract() -> None:
    state = OrchestrationPlatform(".").master_runtime(command="plan")
    assert state["schema"] == "AIOS_MASTER_RUNTIME.v1"
    assert len(state["stages"]) == 13
    assert all(value is False for value in state["permissions"].values())


def test_runtime_has_no_arbitrary_shell_execution_surface() -> None:
    tree = ast.parse(Path("automation/orchestration/aios_master_runtime_v1.py").read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(
        isinstance(call.func, ast.Attribute)
        and call.func.attr in {"system", "popen"}
        for call in calls
    )
    assert not any(
        keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
        for call in calls for keyword in call.keywords
    )


def test_duplicate_capability_owner_fails_closed(tmp_path: Path) -> None:
    active = runtime(tmp_path)
    source, test = next(iter(active.CAPABILITIES.values()))
    active.CAPABILITIES = {"first": (source, test), "duplicate": (source, test)}
    with pytest.raises(Exception, match="DUPLICATE_CAPABILITY_OWNER"):
        active.capabilities()


# Durable campaign additions: PKT-AIOS-DURABLE-AUTONOMOUS-DEVELOPMENT-CONTROL-PLANE-20261021
def durable_runtime(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    active = AIOSMasterRuntime(root)
    monkeypatch.setattr(active, "repository", lambda: {
        "root": str(root), "branch": "task/durable", "head": "a" * 40,
        "status_lines": [" M unrelated.txt"],
    })
    return active


def test_durable_atomic_revision_journal_and_compact_resume(tmp_path, monkeypatch):
    active = durable_runtime(tmp_path, monkeypatch)
    with active.controller_lease():
        first = active.save_durable({"active_task_id": "original-one", "active_claim_id": "claim-one",
                                     "authority_identity": "b" * 64, "stop_class": "OWNER_ACTION_REQUIRED"})
        second = active.save_durable({**first, "next_safe_action": "Read accepted result"})
        assert second["state_revision"] == first["state_revision"] + 1
        assert active.load_durable() == second
        brief = active.resume_brief(second)
        assert brief["active_task_id"] == "original-one"
        assert brief["active_claim_id"] == "claim-one"
        assert brief["state_sha256"] == second["state_sha256"]
        assert len(json.dumps(brief).encode()) <= 4096
    rows = [json.loads(line) for line in active.journal_path.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[1]["prior_event_sha256"] == rows[0]["event_sha256"]


@pytest.mark.parametrize("kind", ["truncated", "duplicate", "changed_state", "missing_journal"])
def test_durable_corruption_is_blocked(tmp_path, monkeypatch, kind):
    active = durable_runtime(tmp_path, monkeypatch)
    with active.controller_lease():
        active.save_durable({"active_task_id": "one", "stop_class": "OWNER_ACTION_REQUIRED"})
    if kind == "truncated":
        raw = active.journal_path.read_bytes()
        active.journal_path.write_bytes(raw[:-1])
    elif kind == "duplicate":
        raw = active.journal_path.read_bytes()
        active.journal_path.write_bytes(raw + raw)
    elif kind == "changed_state":
        state = json.loads(active.state_path.read_bytes())
        state["active_task_id"] = "different"
        active.state_path.write_text(json.dumps(state))
    else:
        active.journal_path.unlink()
    with pytest.raises(ResumeRejected):
        active.load_durable()


def test_durable_second_controller_is_blocked_and_release_allows_next(tmp_path, monkeypatch):
    active = durable_runtime(tmp_path, monkeypatch)
    second = AIOSMasterRuntime(active.root)
    monkeypatch.setattr(second, "repository", active.repository)
    with active.controller_lease():
        with pytest.raises(Exception, match="CONTROLLER_LEASE"):
            with second.controller_lease():
                pytest.fail("Second controller acquired an active lease")
    with second.controller_lease():
        assert second.lease_held is True


def test_durable_write_requires_controller_lease(tmp_path, monkeypatch):
    active = durable_runtime(tmp_path, monkeypatch)
    with pytest.raises(Exception, match="CONTROLLER_LEASE"):
        active.save_durable({"stop_class": "OWNER_ACTION_REQUIRED"})
    assert not active.state_path.exists()


def test_durable_failed_checkpoint_save_never_becomes_success(tmp_path, monkeypatch):
    active = durable_runtime(tmp_path, monkeypatch)
    def fail_save(_state):
        raise OSError("test-owned disk failure")
    with active.controller_lease():
        monkeypatch.setattr(active, "_write_checkpoint", fail_save)
        with pytest.raises(OSError, match="disk failure"):
            active.save_durable({"active_task_id": "one", "stop_class": "OWNER_ACTION_REQUIRED"})
    assert not active.state_path.exists()
    with pytest.raises(ResumeRejected):
        active.load_durable()


def test_durable_live_process_cannot_be_reclaimed_from_unlocked_file(tmp_path, monkeypatch):
    active = durable_runtime(tmp_path, monkeypatch)
    with active.controller_lease():
        pass
    record = json.loads(active.lease_path.read_bytes())
    record["state"] = "ACTIVE"
    active.lease_path.write_text(json.dumps(record))
    before = active.lease_path.read_bytes()
    with pytest.raises(Exception, match="CONTROLLER_LEASE_OWNER_STILL_LIVE"):
        with active.controller_lease():
            pytest.fail("A live recorded owner was reclaimed")
    assert active.lease_path.read_bytes() == before


def test_durable_resume_brief_refuses_oversized_identity(tmp_path, monkeypatch):
    active = durable_runtime(tmp_path, monkeypatch)
    with pytest.raises(ResumeRejected, match="RESUME_BRIEF_TOO_LARGE"):
        active.resume_brief({"active_task_id": "x" * 5000})



def campaign_fixture(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    from automation.orchestration.aios_abcd_autonomy_runner import AcceptedRequirement
    from automation.orchestration.claims.aios_task_claim_control import SCHEMA_VERSION, TaskClaimController
    active = durable_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(active, "repository", lambda: {"root": str(active.root), "branch": "task/durable", "head": "a" * 40, "status_lines": []})
    now = datetime.now(UTC)
    executed, accepted, admissions = [], set(), []
    items, claims, queue_items = [], {}, {}
    for task in ["one", "two"]:
        identity = {"mission_id": "M", "mission_name": "Local test", "program_id": "P", "program_name": "Local test",
                    "epic_id": "E", "epic_name": "Local test", "bucket_id": "B", "bucket_name": "Local test",
                    "packet_id": task, "packet_name": "Local test", "supervisor_identity": "Anthony", "zone": "EAST",
                    "worker_identity": "test-worker", "lane": "durable-test", "stop_point": "Return local evidence"}
        deps = [] if task == "one" else ["one"]
        items.append({"id": task, "packet_id": task, "state": "QUEUED", "priority": "P0", "mode": "APPLY",
                      "approval_required": True, "approval_state": "APPROVED", "attempt": 0, "max_attempts": 1,
                      "depends_on": deps, "allowed_paths": ["src/" + task], "forbidden_paths": [], "protected_action": False})
        queue_items[task] = {"queue_schema": "AIOS_RUNTIME_EXECUTION_QUEUE.v1", "packet_id": task, "packet_identity": identity,
                            "mode": "APPLY", "approval_state": "APPROVED", "approval_authority": "Local test fixture only",
                            "commit_message": "test: durable flow", "pr_authority": "No publishing", "mission": "Local test",
                            "allowed_paths": ["src/" + task], "forbidden_paths": ["RISK_POLICY.md"], "validators": ["local check"],
                            "depends_on": deps, "attempt": 0, "max_attempts": 1, "protected_action": False}
        claims[task] = {"schema_version": SCHEMA_VERSION, "task_id": task, "packet_id": task,
            "repository": "local-test", "supervisor": "Anthony", "worker": "test-worker", "worktree": str(active.root),
            "branch": "task/durable", "base_branch": "main", "base_sha": "a" * 40, "claimed_paths": ["src/" + task],
            "ports": [], "processes_or_services": [], "containers": [], "cache_dirs": [], "temp_dirs": [],
            "log_dirs": [], "env_files": [], "databases_or_schemas": [], "deployment_targets": [], "pull_request": "",
            "state": "ACTIVE", "acquired_at": now.isoformat(), "heartbeat_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(), "cleanup_policy": "test-owned-only",
            "receipt_path": str(active.root / "release" / (task + ".json"))}
    contract = {"mission_id": "M", "program_id": "P", "epic_id": "E", "bucket_id": "B", "packet_id": "campaign",
                "repository_identity": {key: active.repository()[key] for key in ["root", "branch", "head"]},
                "expires_utc": (now + timedelta(hours=1)).isoformat(), "max_cycles": 5, "timebox_seconds": 60,
                "allowed_paths": ["src/one", "src/two"], "task_ids": ["one", "two"], "source_hashes": {}}
    source = active.root / "proof-source.py"
    source.write_text("# test-owned source\n")
    contract["acceptance_requirements"] = {task: {"id": task + ":result", "validator_id": "local check",
        "source_path": str(source), "source_sha256": __import__("hashlib").sha256(source.read_bytes()).hexdigest(), "consumer_destination": str(active.root / "requirements" / (task + ".json"))}
        for task in ["one", "two"]}
    path = active.root / "approved-test-contract.json"
    path.write_text(json.dumps(contract))
    def read_inputs():
        return ({"schema": "AIOS_RUNTIME_EXECUTION_QUEUE.v1", "items": items},
                {"worktree": str(active.root), "branch": "task/durable", "status_lines": [], "dependency_states": {}, "head_is_descendant": True},
                queue_items, claims)
    def execute(packet):
        task = packet["packet_id"]
        saved = active.load_durable()
        assert saved["active_task_id"] == task and saved["phase"] == "EXECUTION_INTENT"
        executed.append(task)
        accepted.add(task)
        return {"status": "COMPLETE"}
    def verify_campaign(value, digest):
        admissions.append(digest)
        assert value == contract
        return True
    def read_receipt(request):
        path = active.root / (request.task_id + ".accepted.json")
        if not path.exists():
            output = active.root / (request.task_id + ".output.txt")
            output.write_text("test-owned output")
            digest = __import__("hashlib").sha256
            path.write_text(json.dumps({"task_id": request.task_id, "packet_id": request.packet_id,
                "acceptance_requirement_id": request.task_id + ":result", "validator_status": "PASS",
                "validator_id": "local check", "reviewer_id": "independent-test-reader",
                "source_path": str(source), "source_sha256": digest(source.read_bytes()).hexdigest(),
                "input_sha256": {"request": request.request_sha256, "claim": request.claim_sha256},
                "output_path": str(output), "output_sha256": digest(output.read_bytes()).hexdigest(),
                "result_classification": "ENGINEERING_ACCEPTED", "cleanup_confirmed": True,
                "consumer_destination": contract["acceptance_requirements"][request.task_id]["consumer_destination"]}))
        return {"path": str(path), "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
                "acceptance_requirement_id": request.task_id + ":result"}
    bindings = SimpleNamespace(read_current_inputs=read_inputs, claim_controller=TaskClaimController(active.root / "board.json"),
        execute=execute, acceptance_reader=lambda request: AcceptedRequirement(request) if request.task_id in accepted else None,
        verify_campaign=verify_campaign, read_receipt=read_receipt, single_task_options={})
    return active, path, bindings, executed, accepted, admissions


def test_durable_campaign_consumes_two_original_tasks_and_resumes_without_repeat(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert executed == ["one", "two"]
    assert state["stop_class"] == "CAMPAIGN_COMPLETE"
    assert set(state["closed_requirements"]) == {"one", "two"}
    assert state["forex_edge_proven"] is False
    assert len(admissions) >= 2
    resumed = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60, resume=True)
    assert resumed["stop_class"] == "CAMPAIGN_COMPLETE" and executed == ["one", "two"]


@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize("change", ["changed", "missing"])
def test_durable_completed_resume_rechecks_saved_result(tmp_path, monkeypatch, completed, change):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    state = active.run_campaign(path, bindings=bindings, max_cycles=5 if completed else 1, timebox_seconds=60)
    assert state["stop_class"] == ("CAMPAIGN_COMPLETE" if completed else "RESOURCE_TIME_BLOCK")
    before_execution = list(executed)
    result = Path(state["intents"]["one"]["result_path"])
    if change == "changed":
        result.write_text('{"status":"COMPLETE","changed":true}')
    else:
        result.unlink()
    restarted = AIOSMasterRuntime(active.root)
    monkeypatch.setattr(restarted, "repository", active.repository)
    resumed = restarted.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60, resume=True)
    assert resumed["stop_class"] == "SAFETY_INTEGRITY_BLOCK"
    assert executed == before_execution
    assert restarted.load_durable()["stop_class"] == "SAFETY_INTEGRITY_BLOCK"


@pytest.mark.parametrize("change", ["missing_release_reference", "active_claim"])
def test_durable_completed_resume_rechecks_claim_release(tmp_path, monkeypatch, change):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert state["stop_class"] == "CAMPAIGN_COMPLETE" and executed == ["one", "two"]
    claim = bindings.read_current_inputs()[3]["one"]
    board_path = bindings.claim_controller.board_path
    board = json.loads(board_path.read_bytes())
    if change == "missing_release_reference":
        reference = next(row for row in board["completed_receipts"] if row["task_id"] == "one")
        reference["receipt_path"] = str(active.root / "missing-release.json")
    else:
        board["completed_receipts"] = [row for row in board["completed_receipts"] if row["task_id"] != "one"]
        board["claims"].append(claim)
    board_path.write_text(json.dumps(board))
    restarted = AIOSMasterRuntime(active.root)
    monkeypatch.setattr(restarted, "repository", active.repository)
    resumed = restarted.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60, resume=True)
    assert resumed["stop_class"] == "SAFETY_INTEGRITY_BLOCK"
    assert executed == ["one", "two"]
    assert restarted.load_durable()["stop_class"] == "SAFETY_INTEGRITY_BLOCK"


def test_durable_campaign_unknown_outcome_never_repeats(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    def uncertain(packet):
        executed.append(packet["packet_id"])
        raise OSError("test-owned interrupted result")
    bindings.execute = uncertain
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert executed == ["one"]
    assert state["stop_class"] == "SAFETY_INTEGRITY_BLOCK"
    resumed = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60, resume=True)
    assert resumed["stop_class"] == "SAFETY_INTEGRITY_BLOCK" and executed == ["one"]


def test_durable_campaign_refuses_missing_or_expired_authority_before_mutation(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    with pytest.raises(Exception, match="CAMPAIGN_AUTHORITY"):
        active.run_campaign(path, max_cycles=5, timebox_seconds=60)
    assert not active.state_path.exists() and not executed



def test_durable_control_pane_is_short_truthful_and_read_only(tmp_path, monkeypatch):
    active = durable_runtime(tmp_path, monkeypatch)
    view = active.control_view()
    text = active.render_control(view)
    assert len(text.splitlines()) <= 30
    assert "PROJECT EXECUTION GRANT: NONE" in text
    assert "OPENAI ACCOUNT CREDITS: NOT INSPECTED" in text
    assert view["forex_edge_proven"] is False
    assert view["state_revision"] is None
    assert not active.state_path.parent.exists()


def test_durable_root_cli_json_and_dry_run_do_not_create_state(tmp_path, monkeypatch, capsys):
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "aios.py"
    spec = importlib.util.spec_from_file_location("durable_root_cli_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(AIOSMasterRuntime, "repository", lambda self: {
        "root": str(self.root), "branch": "task/durable", "head": "a" * 40, "status_lines": []})
    target = tmp_path / "state"
    assert module.main(["status", "--format", "json", "--state-dir", str(target)]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["project_execution_grant"] == "NONE"
    assert value["openai_account_credits"] == "NOT INSPECTED"
    assert module.main(["run", "--mode", "DRY_RUN", "--max-cycles", "2", "--timebox-seconds", "120", "--state-dir", str(target)]) == 0
    capsys.readouterr()
    assert not target.exists()


def test_durable_root_cli_apply_without_actual_contract_is_blocked_without_writes(tmp_path, monkeypatch, capsys):
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "aios.py"
    spec = importlib.util.spec_from_file_location("durable_root_cli_apply_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = tmp_path / "state"
    assert module.main(["run", "--mode", "APPLY", "--state-dir", str(target)]) == 2
    value = json.loads(capsys.readouterr().out)
    assert "MISSION_CONTRACT_REQUIRED" in value["reason_codes"]
    assert not target.exists()


@pytest.mark.parametrize("field,bad", [
    ("source_sha256", "0" * 64), ("output_sha256", "0" * 64),
    ("acceptance_requirement_id", "another-original-requirement"),
    ("consumer_destination", "unbound"), ("reviewer_id", ""),
    ("cleanup_confirmed", False), ("result_classification", "PAPER_QUALIFIED"),
])
def test_durable_campaign_requires_bound_current_receipt_fields(tmp_path, monkeypatch, field, bad):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    original = bindings.read_receipt
    def changed_receipt(request):
        reference = original(request)
        evidence = Path(reference["path"])
        value = json.loads(evidence.read_bytes())
        value[field] = bad
        evidence.write_text(json.dumps(value))
        reference["sha256"] = __import__("hashlib").sha256(evidence.read_bytes()).hexdigest()
        if field == "acceptance_requirement_id":
            reference["acceptance_requirement_id"] = bad
        return reference
    bindings.read_receipt = changed_receipt
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert not state["closed_requirements"]
    assert state["stop_class"] == "SAFETY_INTEGRITY_BLOCK"
    assert executed == ["one"]


def test_durable_campaign_reload_accepted_result_closes_original_without_replay(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    accepted_reader = bindings.acceptance_reader
    bindings.acceptance_reader = lambda request: None
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert executed == ["one"] and not state["closed_requirements"]
    bindings.acceptance_reader = accepted_reader
    resumed = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60, resume=True)
    assert executed == ["one", "two"]
    assert set(resumed["closed_requirements"]) == {"one", "two"}
    assert resumed["stop_class"] == "CAMPAIGN_COMPLETE"


def test_durable_corrupt_control_view_is_safety_block_not_new_campaign(tmp_path, monkeypatch):
    active = durable_runtime(tmp_path, monkeypatch)
    active.state_path.parent.mkdir(parents=True)
    active.state_path.write_text("broken state")
    view = active.control_view()
    assert view["stop_class"] == "SAFETY_INTEGRITY_BLOCK"
    assert view["controller_status"] == "RECOVERY_BLOCKED"


def test_durable_changed_receipt_source_cannot_rebind_original(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    original = bindings.execute
    def change_source(packet):
        (active.root / "proof-source.py").write_text("changed source")
        return original(packet)
    bindings.execute = change_source
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert state["stop_class"] == "SAFETY_INTEGRITY_BLOCK"
    assert not state["closed_requirements"]


@pytest.mark.parametrize("change", ["expired", "branch", "source", "bounds"])
def test_durable_campaign_rechecks_real_identity_before_mutation(tmp_path, monkeypatch, change):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    contract = json.loads(path.read_bytes())
    if change == "expired":
        contract["expires_utc"] = "2000-01-01T00:00:00+00:00"
    elif change == "branch":
        contract["repository_identity"]["branch"] = "different"
    elif change == "source":
        contract["source_hashes"] = {"proof-source.py": "0" * 64}
    else:
        contract["max_cycles"] = 1
    path.write_text(json.dumps(contract))
    with pytest.raises(Exception, match="CAMPAIGN"):
        active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert not active.state_path.exists() and not executed


def test_durable_previous_accepted_receipt_changed_blocks_resume(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    evidence = active.root / "one.output.txt"
    evidence.write_text("changed output")
    result = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60, resume=True)
    assert result["stop_class"] == "SAFETY_INTEGRITY_BLOCK"
    assert executed == ["one", "two"]


def test_durable_zero_eligible_work_preserves_unrelated_dirty_file(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    dirty = active.root / "unrelated.txt"
    dirty.write_bytes(b"owner's existing edits")
    inputs = bindings.read_current_inputs()
    inputs[0]["items"][0]["depends_on"] = ["missing"]
    inputs[2]["one"]["depends_on"] = ["missing"]
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert state["stop_class"] == "OWNER_ACTION_REQUIRED"
    assert not executed and dirty.read_bytes() == b"owner's existing edits"


def test_durable_time_spent_reading_inputs_blocks_worker(tmp_path, monkeypatch):
    import time
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    original = bindings.read_current_inputs
    reads = [0]
    def delayed_inputs():
        reads[0] += 1
        if reads[0] > 1:
            clock[0] += 61
        return original()
    bindings.read_current_inputs = delayed_inputs
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert not executed
    assert state["stop_class"] == "RESOURCE_TIME_BLOCK"


@pytest.mark.parametrize("kind", ["contract", "source", "allowed_path"])
def test_durable_parent_traversal_refused_before_any_worker(tmp_path, monkeypatch, kind):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    original_contract = json.loads(path.read_bytes())
    if kind == "contract":
        target = active.root.parent / "outside-contract.json"
        target.write_bytes(path.read_bytes())
        path = active.root / ".." / "outside-contract.json"
    elif kind == "source":
        outside = active.root.parent / "outside-source.txt"
        outside.write_text("harmless example")
        original_contract["source_hashes"] = {"../outside-source.txt": __import__("hashlib").sha256(outside.read_bytes()).hexdigest()}
        path.write_text(json.dumps(original_contract))
    else:
        original_contract["allowed_paths"] += ["../outside"]
        path.write_text(json.dumps(original_contract))
    bindings.verify_campaign = lambda *args: True
    with pytest.raises(Exception, match="PATH"):
        active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert not executed and not active.state_path.exists()


def test_durable_result_write_failure_records_unknown_and_never_repeats(tmp_path, monkeypatch):
    import automation.orchestration.aios_resume_state as owner
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    original = owner.atomic_write
    def failed_receipt(target, data):
        if str(target).endswith(".result.json"):
            raise OSError("example result disk failure")
        return original(target, data)
    monkeypatch.setattr(owner, "atomic_write", failed_receipt)
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert state["stop_class"] == "SAFETY_INTEGRITY_BLOCK" and executed == ["one"]
    monkeypatch.setattr(owner, "atomic_write", original)
    resumed = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60, resume=True)
    assert resumed["stop_class"] == "SAFETY_INTEGRITY_BLOCK" and executed == ["one"]


def test_durable_denied_authority_return_cannot_be_ignored(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    bindings.verify_campaign = lambda *args: False
    with pytest.raises(Exception, match="CAMPAIGN_AUTHORITY"):
        active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert not executed and not active.state_path.exists()


def test_durable_cli_stopped_work_does_not_return_success(monkeypatch, capsys):
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "aios.py"
    spec = importlib.util.spec_from_file_location("blocked_campaign_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "run", lambda **kwargs: {"stop_class": "SAFETY_INTEGRITY_BLOCK", "blocker": "test only"})
    assert module.main(["run", "--mode", "APPLY", "--mission-contract", "example.json"]) == 2
    capsys.readouterr()


def test_durable_current_reader_failure_saves_stopped_state(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    original = bindings.read_current_inputs
    reads = [0]
    def failed_reader():
        reads[0] += 1
        if reads[0] > 1:
            raise OSError("example unreadable current input")
        return original()
    bindings.read_current_inputs = failed_reader
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert state["stop_class"] == "SAFETY_INTEGRITY_BLOCK" and not executed
    assert active.load_durable()["stop_class"] == "SAFETY_INTEGRITY_BLOCK"


def test_durable_canonical_cli_uses_own_repository_from_another_folder(tmp_path, monkeypatch, capsys):
    import importlib.util
    source = Path(__file__).resolve().parents[2] / "aios.py"
    spec = importlib.util.spec_from_file_location("canonical_root_cli", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    monkeypatch.setattr(module, "run", lambda **kwargs: calls.append(kwargs) or {})
    monkeypatch.chdir(tmp_path)
    assert module.main(["status"]) == 0
    assert Path(calls[0]["repo_root"]) == source.parent
    capsys.readouterr()


def test_durable_resume_distinguishes_total_and_current_call_time(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    state = active.run_campaign(path, bindings=bindings, max_cycles=1, timebox_seconds=60)
    assert executed == ["one"]
    with active.controller_lease():
        active.save_durable({**state, "elapsed_seconds": 2.0})
    resumed = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60,
                                  invocation_timebox_seconds=5, resume=True)
    assert resumed["stop_class"] == "CAMPAIGN_COMPLETE" and executed == ["one", "two"]


@pytest.mark.parametrize("kind", ["receipt", "result", "repository"])
def test_durable_validation_checks_current_references_and_repository(tmp_path, monkeypatch, kind):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    if kind == "receipt":
        Path(state["closed_requirements"]["one"]["path"]).write_text("changed receipt")
    elif kind == "result":
        Path(state["intents"]["one"]["result_path"]).write_text("changed result")
    else:
        old = active.repository()
        monkeypatch.setattr(active, "repository", lambda: {**old, "branch": "changed"})
    with pytest.raises(Exception, match="RUNTIME|RECEIPT|RESULT|REPOSITORY"):
        active.validate_durable()


def test_durable_initial_permission_read_counts_against_invocation_time(tmp_path, monkeypatch):
    import time
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    original = bindings.verify_campaign
    reads = [0]
    def delayed_permission(contract, digest):
        reads[0] += 1
        if reads[0] == 1:
            clock[0] += 61
        return original(contract, digest)
    bindings.verify_campaign = delayed_permission
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert not executed
    assert state["stop_class"] == "RESOURCE_TIME_BLOCK"


def test_durable_preview_shows_conditional_next_job_without_writes(tmp_path, monkeypatch):
    import copy
    from automation.orchestration.runtime_queue import aios_runtime_execution_queue as queue
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(queue, "build_queue_view", lambda root: copy.deepcopy(bindings.read_current_inputs()[0]))
    before = {p.relative_to(active.root).as_posix(): p.read_bytes() for p in active.root.rglob("*") if p.is_file()}
    result = active.campaign_preview(max_cycles=2, timebox_seconds=12)
    assert [step["selected_task_id"] for step in result["preview_cycles"]] == ["one", "two"]
    assert result["preview_cycles"][1]["requires_prior_acceptance"] is True
    assert result["execution_authorized"] is False
    assert result["timebox_seconds"] == 12
    after = {p.relative_to(active.root).as_posix(): p.read_bytes() for p in active.root.rglob("*") if p.is_file()}
    assert before == after and not executed and not accepted


def test_durable_cli_refusal_reports_one_of_the_named_stop_classes(monkeypatch, capsys):
    import importlib.util
    from automation.orchestration.aios_master_runtime_v1 import RuntimeBlocked
    source = Path(__file__).resolve().parents[2] / "aios.py"
    spec = importlib.util.spec_from_file_location("typed_stop_cli", source)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    def unavailable(**kwargs):
        raise RuntimeBlocked("QUALIFIED_WINDOWS_WORKER_CONNECTION_REQUIRED")
    monkeypatch.setattr(cli, "run", unavailable)
    assert cli.main(["run", "--mode", "APPLY", "--mission-contract", "example-only.json"]) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["stop_class"] == "SAFETY_INTEGRITY_BLOCK"


@pytest.mark.parametrize('kind', ['receipt-changed', 'receipt-missing', 'result-changed',
    'result-missing', 'repository', 'source', 'output'])
def test_status_rechecks_current_original_proof_before_completion(tmp_path, monkeypatch, kind):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert state['stop_class'] == 'CAMPAIGN_COMPLETE'
    if kind.startswith('receipt-'):
        target = Path(state['closed_requirements']['one']['path'])
    elif kind.startswith('result-'):
        target = Path(state['intents']['one']['result_path'])
    elif kind in {'source', 'output'}:
        receipt = json.loads(Path(state['closed_requirements']['one']['path']).read_bytes())
        target = Path(receipt[kind + '_path'])
    else:
        original = active.repository()
        monkeypatch.setattr(active, 'repository', lambda: {**original, 'branch': 'changed'})
        target = None
    if target is not None:
        if kind.endswith('missing'): target.unlink()
        else: target.write_text('changed owned example')
    before = {p: p.read_bytes() for p in active.root.rglob('*') if p.is_file()}
    before_calls = list(admissions), list(executed)
    view = active.control_view()
    assert view['controller_status'] == 'RECOVERY_BLOCKED'
    assert view['closed_original_requirement_count'] is None
    assert view['last_accepted_receipt'] is None
    assert view['project_execution_grant'] == 'NONE'
    assert before_calls == (admissions, executed)
    assert before == {p: p.read_bytes() for p in active.root.rglob('*') if p.is_file()}


def test_status_keeps_valid_completion_without_new_permission_or_writes(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    before = {p: p.read_bytes() for p in active.root.rglob('*') if p.is_file()}
    before_calls = list(admissions), list(executed)
    view = active.control_view()
    assert view['controller_status'] == state['phase']
    assert view['stop_class'] == 'CAMPAIGN_COMPLETE'
    assert view['closed_original_requirement_count'] == 2
    assert view['project_execution_grant'] == 'NONE'
    assert before_calls == (admissions, executed)
    assert before == {p: p.read_bytes() for p in active.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('relative', ['private/example-only.txt', 'services/mobile_gateway/secrets.py',
    'services/mobile_gateway/enrollment-example.db'])
def test_status_refuses_private_proof_reference_before_reading(tmp_path, monkeypatch, relative):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    target = active.root / relative
    target.parent.mkdir(parents=True)
    target.write_text('owned dummy value')
    state['closed_requirements']['one']['path'] = str(target)
    with active.controller_lease():
        active.save_durable(state)
    original_read = Path.read_bytes
    def guarded_read(selected):
        assert selected != target, 'Private proof reference was read'
        return original_read(selected)
    monkeypatch.setattr(Path, 'read_bytes', guarded_read)
    view = active.control_view()
    assert view['controller_status'] == 'RECOVERY_BLOCKED'
    assert view['closed_original_requirement_count'] is None


def test_status_shows_pending_work_as_unverified_without_recovery_failure(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    original = bindings.execute
    views = []
    def execute(packet):
        before = {p: p.read_bytes() for p in active.root.rglob('*') if p.is_file()}
        view = active.control_view()
        views.append(view)
        assert view['controller_status'] == 'WORK_OUTCOME_UNVERIFIED'
        assert view['active_work_outcome_verified'] is False
        assert view['running_task_count'] is None
        assert view['closed_original_requirement_count'] == len(executed)
        assert view['project_execution_grant'] == 'NONE'
        assert before == {p: p.read_bytes() for p in active.root.rglob('*') if p.is_file()}
        return original(packet)
    bindings.execute = execute
    active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert len(views) == 2 and executed == ['one', 'two']


import os
import stat
import time

class _OwnedStatusProofReader:
    instances = []
    before_data_open = None
    after_read = None
    fail_close = False

    def __init__(self, deadline):
        self.deadline = deadline
        self.guards, self.handles, self.read_paths = {}, {}, []
        self.closed = False
        self.instances.append(self)

    def tick(self):
        if time.monotonic() >= self.deadline:
            raise ValueError('Fake reader deadline')

    def drive_mapping(self, drive):
        self.tick()
        return 'owned-fixture-volume'

    def _handle(self, path, stream=None):
        handle = len(self.handles) + 1
        self.handles[handle] = path, stream
        return handle

    def open_root(self, drive, components):
        root = Path(drive + '\\').joinpath(*components)
        handle = self._handle(root)
        self.guards[handle] = self.metadata(handle)
        return handle, self.drive_mapping(drive)

    def open_relative(self, parent, name, access):
        self.tick()
        assert access in (0x100080, 0x100081)
        assert '/' not in name and '\\' not in name and name not in ('.', '..')
        if self.metadata(parent) != self.guards[parent]:
            raise ValueError('Fake parent changed')
        path = self.handles[parent][0] / name
        if access == 0x100081:
            hook = type(self).before_data_open
            if hook is not None:
                hook(path)
            return self._handle(path, path.open('rb'))
        return self._handle(path)

    def metadata(self, handle):
        self.tick()
        path, stream = self.handles[handle]
        facts = os.fstat(stream.fileno()) if stream is not None else path.lstat()
        directory = stat.S_ISDIR(facts.st_mode)
        if stat.S_ISLNK(facts.st_mode) or getattr(facts, 'st_file_attributes', 0) & 1024:
            raise ValueError('Fake redirect refused')
        if not directory and (not stat.S_ISREG(facts.st_mode) or facts.st_nlink != 1):
            raise ValueError('Fake file alias refused')
        return {'identity': {'device': facts.st_dev, 'inode': facts.st_ino},
            'directory': directory, 'links': facts.st_nlink, 'size': facts.st_size,
            # Python's Windows fstat/lstat creation-time values differed in the
            # owned fixture. This adapter models identity, size and write time;
            # the actual existing native reader separately checks all NT times.
            'modified': facts.st_mtime_ns}

    def streams(self, handle, directory):
        facts = self.metadata(handle)
        return [] if directory else [('::$DATA', facts['size'], facts['size'])]

    def read(self, handle, count):
        self.tick()
        assert type(count) is int and 0 < count <= 65536
        path, stream = self.handles[handle]
        assert stream is not None
        self.read_paths.append(path)
        raw = stream.read(count)
        hook = type(self).after_read
        if hook is not None:
            hook(path)
        return raw

    def close_all(self):
        for _, stream in reversed(list(self.handles.values())):
            if stream is not None:
                stream.close()
        self.closed = True
        if type(self).fail_close:
            raise ValueError('Owned fake cleanup failure')



@pytest.mark.parametrize('role', ['receipt', 'source', 'output', 'result'])
def test_status_refuses_multiple_file_names_before_reading_proof(tmp_path, monkeypatch, role):
    from automation.orchestration import aios_repo_state_evidence as native
    monkeypatch.setattr(_OwnedStatusProofReader, 'instances', [])
    monkeypatch.setattr(native, '_FullWorktreeWindowsReader', _OwnedStatusProofReader)
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    receipt_path = Path(state['closed_requirements']['one']['path'])
    receipt = json.loads(receipt_path.read_bytes())
    target = {'receipt': receipt_path, 'source': Path(receipt['source_path']),
        'output': Path(receipt['output_path']), 'result': Path(state['intents']['one']['result_path'])}[role]
    private = active.root / 'private' / 'owned-example.txt'
    private.parent.mkdir()
    private.write_text('dummy fixture; no actual private data')
    target.unlink()
    target.hardlink_to(private)
    assert target.stat().st_nlink == 2
    original = Path.read_bytes
    def guarded_read(selected):
        assert selected != target, 'Proof contents were opened before checking file identity'
        return original(selected)
    monkeypatch.setattr(Path, 'read_bytes', guarded_read)
    view = active.control_view()
    assert view['controller_status'] == 'RECOVERY_BLOCKED'
    assert view['closed_original_requirement_count'] is None
    assert view['last_accepted_receipt'] is None
    assert _OwnedStatusProofReader.instances
    assert all(reader.closed for reader in _OwnedStatusProofReader.instances)
    assert all(target not in reader.read_paths for reader in _OwnedStatusProofReader.instances)

class _StatusProofReaderDouble:
    """A file-reader stand-in; never calls the Windows file reader."""
    instances = []
    mode = 'valid'

    def __init__(self, deadline):
        self.deadline = deadline
        self.guards, self.handles = {}, []
        self.closed, self.reads, self.eof = False, [], False
        type(self).instances.append(self)

    def tick(self):
        if self.mode == 'expired':
            raise ValueError('Example expired read budget')

    def drive_mapping(self, drive):
        return 'example-volume'

    def open_root(self, drive, parts):
        self.handles.append(('directory', 'root'))
        self.guards[1] = self.metadata(1)
        return 1, self.drive_mapping(drive)

    def open_relative(self, parent, name, access):
        assert parent in self.guards and self.guards[parent]['directory']
        assert access in (0x100080, 0x100081)
        self.handles.append(('data' if access == 0x100081 else 'metadata', name))
        return len(self.handles)

    def metadata(self, handle):
        kind, name = self.handles[handle - 1]
        directory = kind == 'directory'
        identity = name + ('-switched' if self.mode == 'switched' and kind == 'data' else '')
        return {'directory': directory, 'links': 1, 'size': 0 if directory else 3,
            'identity': identity, 'changed': self.mode == 'changed' and self.eof}

    def streams(self, handle, directory):
        if directory:
            return []
        return [('::$DATA', 3, 3)] + ([(':extra:$DATA', 1, 1)] if self.mode == 'extra-stream' else [])

    def read(self, handle, count):
        assert self.handles[handle - 1][0] == 'data'
        self.reads.append((handle, count))
        if count == 1:
            self.eof = True
            return b'x' if self.mode == 'extra-byte' else b''
        return b'' if self.mode == 'short' else b'abc'

    def close_all(self):
        self.closed = True
        if self.mode == 'cleanup':
            raise ValueError('Example close failure')


@pytest.mark.parametrize('mode', ['valid', 'switched', 'changed', 'extra-stream',
    'short', 'extra-byte', 'cleanup', 'expired', 'unavailable'])
def test_status_proof_reader_retains_identity_and_refuses_uncertainty(tmp_path, monkeypatch, mode):
    from automation.orchestration import aios_repo_state_evidence as native
    active = durable_runtime(tmp_path, monkeypatch)
    proof = active.root / 'proof.txt'
    proof.write_bytes(b'abc')
    monkeypatch.setattr(_StatusProofReaderDouble, 'instances', [])
    monkeypatch.setattr(_StatusProofReaderDouble, 'mode', mode)
    if mode == 'unavailable':
        def unavailable(deadline):
            raise ValueError('Example reader unavailable')
        monkeypatch.setattr(native, '_FullWorktreeWindowsReader', unavailable)
    else:
        monkeypatch.setattr(native, '_FullWorktreeWindowsReader', _StatusProofReaderDouble)
    def no_ordinary_read(selected):
        pytest.fail('Protected proof read used ordinary file contents')
    monkeypatch.setattr(Path, 'read_bytes', no_ordinary_read)
    if mode == 'valid':
        with active._current_proof_bytes() as read:
            assert read(proof) == b'abc'
            assert read(proof) == b'abc'
    else:
        with pytest.raises(ResumeRejected):
            with active._current_proof_bytes() as read:
                read(proof)
    assert all(reader.closed for reader in _StatusProofReaderDouble.instances)
    if mode in ('switched', 'extra-stream', 'expired'):
        assert not _StatusProofReaderDouble.instances[0].reads
    if mode == 'valid':
        assert len(_StatusProofReaderDouble.instances[0].reads) == 2


def _saved_selection_inputs(active, bindings):
    original = bindings.read_current_inputs
    view_path = active.root / 'owned-queue-view.json'
    view_path.write_text(json.dumps(original()[0]), encoding='utf-8')
    def read_saved():
        _, repository, queue_items, claims = original()
        return json.loads(view_path.read_text(encoding='utf-8')), repository, queue_items, claims
    bindings.read_current_inputs = read_saved
    return view_path


def test_durable_selection_keeps_priority_across_saved_queue_and_dependencies(tmp_path, monkeypatch):
    import copy
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    queue, _, queue_items, claims = bindings.read_current_inputs()
    # The urgent dependent must wait; a ready independent task still runs first.
    queue['items'][0]['priority'] = 'P2'
    queue['items'][1]['priority'] = 'P0'
    third = copy.deepcopy(queue['items'][0])
    third.update(id='three', packet_id='three', priority='P1', allowed_paths=['src/three'])
    queue['items'].append(third)
    queue_items['three'] = copy.deepcopy(queue_items['one'])
    queue_items['three'].update(packet_id='three', allowed_paths=['src/three'])
    queue_items['three']['packet_identity'].update(packet_id='three', packet_name='Local third fixture')
    claims['three'] = copy.deepcopy(claims['one'])
    claims['three'].update(task_id='three', packet_id='three', claimed_paths=['src/three'],
        receipt_path=str(active.root / 'release/three.json'))
    contract = json.loads(path.read_text())
    contract['task_ids'].append('three')
    contract['allowed_paths'].append('src/three')
    contract['acceptance_requirements']['three'] = copy.deepcopy(contract['acceptance_requirements']['one'])
    contract['acceptance_requirements']['three'].update(id='three:result',
        consumer_destination=str(active.root / 'requirements/three.json'))
    # Keep the fixture's exact authority closure bound to the updated dummy contract.
    bindings.verify_campaign = lambda value, digest: value == contract
    path.write_text(json.dumps(contract))
    original_read_receipt = bindings.read_receipt
    def read_three_receipt(request):
        if request.task_id != 'three':
            return original_read_receipt(request)
        assert 'three' in accepted and 'three' in executed
        import hashlib
        output = active.root / 'three.output.txt'
        receipt = active.root / 'three.accepted.json'
        evidence = contract['acceptance_requirements']['three']
        if receipt.exists():
            return {'path': str(receipt), 'sha256': hashlib.sha256(receipt.read_bytes()).hexdigest(),
                'acceptance_requirement_id': evidence['id']}
        output.write_text('owned third output')
        payload = {'task_id': request.task_id, 'packet_id': request.packet_id,
            'acceptance_requirement_id': evidence['id'], 'validator_status': 'PASS',
            'validator_id': 'local check', 'reviewer_id': 'independent-test-reader',
            'source_path': evidence['source_path'], 'source_sha256': evidence['source_sha256'],
            'input_sha256': {'request': request.request_sha256, 'claim': request.claim_sha256},
            'output_path': str(output), 'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'result_classification': 'ENGINEERING_ACCEPTED', 'cleanup_confirmed': True,
            'consumer_destination': evidence['consumer_destination']}
        receipt.write_text(json.dumps(payload))
        return {'path': str(receipt), 'sha256': hashlib.sha256(receipt.read_bytes()).hexdigest(),
            'acceptance_requirement_id': evidence['id']}
    bindings.read_receipt = read_three_receipt
    saved = _saved_selection_inputs(active, bindings)
    original_queue = saved.read_bytes()
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert executed == ['three', 'one', 'two']
    assert state['stop_class'] == 'CAMPAIGN_COMPLETE'
    assert set(state['closed_requirements']) == {'one', 'two', 'three'}
    assert saved.read_bytes() == original_queue
    # A completed saved queue is reread; accepted tasks must not run again.
    active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60, resume=True)
    assert executed == ['three', 'one', 'two']


def test_durable_selection_keeps_existing_tie_order_after_queue_reload(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    queue, _, queue_items, claims = bindings.read_current_inputs()
    queue['items'][1]['depends_on'] = []
    queue_items['two']['depends_on'] = []
    for item in queue['items']:
        item['priority'] = 'P1'
    queue['items'].reverse()
    saved = _saved_selection_inputs(active, bindings)
    original_queue = saved.read_bytes()
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert executed == ['two', 'one']
    assert state['stop_class'] == 'CAMPAIGN_COMPLETE'
    assert set(state['closed_requirements']) == {'one', 'two'}
    assert saved.read_bytes() == original_queue
    active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60, resume=True)
    assert executed == ['two', 'one']


def test_durable_selection_missing_prerequisite_does_not_freeze_independent_task(tmp_path, monkeypatch):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    queue, _, queue_items, claims = bindings.read_current_inputs()
    queue['items'][0].update(priority='P0', depends_on=['missing-prerequisite'])
    queue_items['one']['depends_on'] = ['missing-prerequisite']
    queue['items'][1].update(priority='P2', depends_on=[])
    queue_items['two']['depends_on'] = []
    saved = _saved_selection_inputs(active, bindings)
    original_queue = saved.read_bytes()
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert executed == ['two']
    assert state['stop_class'] == 'OWNER_ACTION_REQUIRED'
    assert set(state['closed_requirements']) == {'two'}
    assert 'one' not in state['intents']
    assert saved.read_bytes() == original_queue
    active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60, resume=True)
    assert executed == ['two']


@pytest.mark.parametrize("resume", [False, True])
def test_durable_campaign_refuses_external_state_before_any_work(tmp_path, monkeypatch, resume):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    target = tmp_path / "external-state"
    active.state_path = target / "master-runtime-v1.json"
    with pytest.raises(ResumeRejected, match="RUNTIME_PATH_OUTSIDE_REPOSITORY"):
        active.run_campaign(path, bindings=bindings, max_cycles=5,
                            timebox_seconds=60, resume=resume)
    assert executed == [] and accepted == set() and admissions == []
    assert not target.exists()


@pytest.mark.parametrize("private_class", [False, True])
def test_durable_acceptance_reader_fault_never_saves_private_error(tmp_path, monkeypatch, private_class):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    marker = "synthetic_private_acceptance_marker"
    calls = []
    error_type = type(marker, (Exception,), {}) if private_class else RuntimeError

    def unavailable(request):
        calls.append(request.task_id)
        if len(calls) > 2:
            raise error_type(marker)
        return None

    bindings.acceptance_reader = unavailable
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert len(calls) == 3 and executed == [] and accepted == set()
    assert state["stop_class"] == "OWNER_ACTION_REQUIRED"
    assert "existing publication reader failed" in state["blocker"]
    assert marker not in json.dumps(state)
    assert marker not in active.state_path.read_text()
    assert marker not in active.journal_path.read_text()
    assert marker not in json.dumps(active.control_view())


@pytest.mark.parametrize("fault", ["profile-message", "profile-class", "input-class", "receipt-class"])
def test_durable_callback_diagnostics_keep_private_details_out_of_saved_state(tmp_path, monkeypatch, fault):
    active, path, bindings, executed, accepted, admissions = campaign_fixture(tmp_path, monkeypatch)
    marker = "synthetic_private_callback_marker"
    error_type = RuntimeError if fault == "profile-message" else type(marker, (ValueError,), {})

    def unavailable(*args, **kwargs):
        raise error_type(marker)

    if fault.startswith("profile"):
        bindings.single_task_options = {"packet_profile_reader": unavailable,
                                       "campaign_admission_reader": lambda *a, **k: None}
    elif fault == "input-class":
        bindings.read_current_inputs = unavailable
    else:
        bindings.read_receipt = unavailable
    state = active.run_campaign(path, bindings=bindings, max_cycles=5, timebox_seconds=60)
    assert executed == (["one"] if fault == "receipt-class" else [])
    assert state["stop_class"] == ("OWNER_ACTION_REQUIRED" if fault.startswith("profile") else "SAFETY_INTEGRITY_BLOCK")
    assert marker not in json.dumps(state)
    assert marker not in active.state_path.read_text()
    assert marker not in active.journal_path.read_text()
    assert marker not in json.dumps(active.control_view())
