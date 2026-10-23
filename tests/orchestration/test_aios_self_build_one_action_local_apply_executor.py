from __future__ import annotations

from pathlib import Path

from automation.orchestration.aios_self_build_one_action_local_apply_executor import (
    DEFAULT_WORKING_DIRECTORY,
    LOCAL_EXECUTOR_MODE,
    ONE_ACTION_APPLY_MODE,
    SCHEMA,
    build_self_build_one_action_local_apply_executor,
)


ACTION_ID = "build_self_build_one_action_local_apply_executor"


def _auth003_command():
    import sys
    return '"' + sys.executable.replace("\\", "/") + '" ' + _command().split(" ", 1)[1]

def _auth003_fixture(root, module=None, claim_updates=None):
    """Engineering-only synthetic TEST_ONLY trust; never a production grant."""
    import hashlib
    from datetime import datetime, timedelta, timezone
    from automation.orchestration.claims import aios_task_claim_control as public_claim
    from automation.validators import aios_approval_authority_integrity_validator as canonical

    module = module or public_claim
    root.mkdir(parents=True, exist_ok=True)
    repository = Path(__file__).parents[2]
    for name in module._EXECUTION_SOURCE_PATHS:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repository / name).read_bytes())
    entry = root / "automation/orchestration/aios_productive_bounded_executor.py"
    entry.write_text("# Owned synthetic source, never executed.\n", encoding="utf-8")
    git = root / ".git"
    (git / "refs/heads/task").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/task/one\n", encoding="utf-8")
    (git / "refs/heads/task/one").write_text("a" * 40 + "\n", encoding="utf-8")
    now = datetime.now(timezone.utc)
    raw = {
        "schema_version": module.SCHEMA_VERSION, "task_id": "one", "packet_id": "packet-one",
        "repository": "owned/engineering", "supervisor": "engineering-only", "worker": "worker-one",
        "worktree": str(root), "branch": "task/one", "base_branch": "main", "base_sha": "a" * 40,
        "claimed_paths": _allowed_paths(), "ports": [], "processes_or_services": [], "containers": [],
        "cache_dirs": [], "temp_dirs": [], "log_dirs": [], "env_files": [], "databases_or_schemas": [],
        "deployment_targets": [], "pull_request": "", "state": "ACTIVE",
        "acquired_at": now.isoformat(), "heartbeat_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(), "cleanup_policy": "owned-only",
        "receipt_path": str(root / "receipts/one.json"),
    }
    raw.update(claim_updates or {})
    ctl = module.TaskClaimController(root / "claims/active.json")
    owned = ctl.acquire(raw)
    queue = _queue_item(packet_id="packet-one", blocked_paths=["private"],
                        output_roots={"report": _allowed_paths()[2],
                                      "execution_journal": ctl.board_path.resolve().as_posix().casefold(),
                                      "execution_dispatch_lease": module._dispatch_lock_file(
                                          ctl.board_path, owned).resolve().as_posix().casefold()},
                        stop_point="after-one-owned-action")
    invocation = {
        "packet_id": queue["packet_id"], "goal_id": queue["goal"], "requested_action": ACTION_ID,
        "command": _auth003_command(), "working_directory": str(root), "allowed_paths": _allowed_paths(),
        "blocked_paths": queue["blocked_paths"], "validator_chain": _validators(),
        "resource_limits": {"max_repairs": 1, "max_files_changed": 3},
        "output_roots": queue["output_roots"], "stop_point": queue["stop_point"],
    }
    identity = ctl.execution_identity(owned, invocation)
    authority = {
        "approval_gate_id": "auth003-engineering-only", "authority_status": "active_authority",
        "packet_id": identity["packet_id"], "requested_action": ACTION_ID, "requested_mode": "APPLY",
        "approval_status": "completed", "approved_by_human": True, "risk_level": "engineering-only",
        "allowed_paths": identity["allowed_paths"], "blocked_paths": identity["blocked_paths"],
        "validator_chain_required": True, "commit_package_required": True, "push_blocked_until_final_review": True,
    }
    key = "AUTH003-ENGINEERING-ONLY-NOT-A-PRODUCTION-KEY"
    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
    v2 = canonical.approval_contract_v2
    gate = {
        "schema": v2.SCHEMA, "purpose": v2.PURPOSE, "algorithm": v2.ALGORITHM,
        "request_id": authority["approval_gate_id"], "request_revision": "engineering-1",
        "gate_id": authority["approval_gate_id"], "approval_request_id": authority["approval_gate_id"],
        "approval_gate_id": authority["approval_gate_id"], "requested_mode": "APPLY", "approved_mode": "APPLY",
        "approval_status": "approved_for_apply", "approved_by_human": True, "approved_by": v2.OWNER,
        "owner_identity": v2.OWNER, "approval_authority": v2.OWNER,
        "trust_root_id": canonical.TRUST_ROOT_ID, "key_id": "auth003-engineering-only", "key_version": 1,
        "key_fingerprint_sha256": fingerprint, "approval_nonce": "1620" * 16,
        "created_at_utc": (now - timedelta(minutes=2)).isoformat(),
        "approval_timestamp_utc": (now - timedelta(minutes=1)).isoformat(),
        "not_before_utc": (now - timedelta(minutes=2)).isoformat(),
        "latest_entry_utc": (now + timedelta(minutes=10)).isoformat(),
        "expires_at_utc": (now + timedelta(minutes=20)).isoformat(), "closure_reserve_hours": 0.01,
        "worker_identity": identity["worker"], "package_sha256": identity["command_source_sha256"],
        "authority_bundle_sha256": v2.canonical_digest(authority),
        "execution_contract_sha256": v2.canonical_digest(identity), "research_scope": {"engineering": True},
        "data_hashes": {"owned_synthetic": "a" * 64},
        "strategy_identity": {"strategy_id": "engineering", "strategy_version": "1"},
        "cost_identity": "owned-fake-only", "trial_allocation": {"actions": 1},
        "capabilities": {name: False for name in ("broker", "paper", "live", "commit", "push", "merge")},
        "resume_policy": {"allow_resume": False}, "validator_chain_required": True,
        "commit_package_required": True, "push_blocked_until_final_review": True,
    }
    for field in ("packet_id", "goal_id", "requested_action", "allowed_paths", "blocked_paths",
                  "validator_chain", "resource_limits", "output_roots", "stop_point", "source_hashes",
                  "worker", "lane", "worktree"):
        gate[field] = identity[field]
    gate["research_scope_sha256"] = v2.canonical_digest(gate["research_scope"])
    gate["source_map_sha256"] = v2.canonical_digest(gate["source_hashes"])
    gate["budget_identity_sha256"] = v2.canonical_digest(
        {"trial_allocation": gate["trial_allocation"], "resource_limits": gate["resource_limits"]})
    trust = {
        "schema": canonical.TRUST_ROOT_SCHEMA, "trust_root_id": canonical.TRUST_ROOT_ID,
        "authority": v2.OWNER, "environment": "TEST_ONLY", "state": "ACTIVE", "current_key_version": 1,
        "keys": [{"key_id": gate["key_id"], "key_version": 1, "key_fingerprint_sha256": fingerprint,
                  "status": "ACTIVE", "created_at_utc": gate["created_at_utc"]}],
    }
    material = {"gate": gate, "authority": authority, "hmac_key": key, "trust_metadata": trust}

    def sign():
        gate["budget_identity_sha256"] = v2.canonical_digest(
            {"trial_allocation": gate["trial_allocation"], "resource_limits": gate["resource_limits"]})
        gate["approval_evidence"] = {
            "type": "HMAC_SHA256", "status": "SIGNED_BY_HUMAN_OWNER", "canonical_payload_schema": v2.SCHEMA,
            **{field: gate[field] for field in ("key_id", "key_version", "key_fingerprint_sha256", "approval_nonce")},
            "canonical_payload_sha256": v2.payload_sha256(gate), "approval_hmac_sha256": v2.approval_hmac(gate, key),
        }
    sign()
    assert canonical.validate_authority_bundle(
        gate, authority, hmac_key=key, trust_metadata=trust, allow_test_trust=True,
    ).hardened_approval_verified
    admission = module.ExecutionAdmission(ctl, owned, lambda: material, allow_test_trust=True)
    return {
        "module": module, "controller": ctl, "claim": owned, "invocation": invocation,
        "identity": identity, "material": material, "admission": admission, "sign": sign,
        "build": {"selected_queue_item": queue,
                  "local_apply_executor_bridge": _bridge(command_to_run=_auth003_command()),
                  "single_action_executor": _executor(command_to_run=_auth003_command()),
                  "one_action_execution_controller": _controller(command_to_run=_auth003_command()),
                  "one_action_apply_runner": _runner(command_to_run=_auth003_command()),
                  "one_action_execute_gate": _gate(command_to_run=_auth003_command()),
                  "local_executor_request": _local_executor_request(working_directory=str(root)),
                  "execution_admission": admission},
    }


def _auth003_build(root, command_runner, **overrides):
    fixture = _auth003_fixture(root)
    return _build(command_runner=command_runner, executor_options=_options(execute=True), **fixture["build"], **overrides)




def test_auth003_projection_only_cannot_invoke_runner():
    calls = []
    result = _build(
        command_runner=lambda *args: calls.append(args) or {"returncode": 0},
        executor_options=_options(execute=True),
    )
    assert calls == []
    assert result["executor_status"] == "blocked"
    assert "final_authority_provider_missing" in result["rejection_reasons"]


def _allowed_paths():
    return [
        "automation/orchestration/aios_self_build_one_action_local_apply_executor.py",
        "tests/orchestration/test_aios_self_build_one_action_local_apply_executor.py",
        "docs/orchestration/AIOS_SELF_BUILD_ONE_ACTION_LOCAL_APPLY_EXECUTOR.md",
    ]


def _validators():
    return [
        "python -m pytest -p no:cacheprovider tests/orchestration/test_aios_self_build_one_action_local_apply_executor.py",
    ]


def _command():
    return (
        "python automation/orchestration/aios_productive_bounded_executor.py "
        "--goal self-build-core --action build_self_build_one_action_local_apply_executor --apply --max-repairs 1"
    )


def _queue_item(**overrides):
    item = {
        "schema": "AIOS_SELF_BUILD_WORK_QUEUE_ITEM.v1",
        "action_id": ACTION_ID,
        "goal": "self-build-core",
        "allowed_paths": _allowed_paths(),
        "validators": _validators(),
        "max_repairs": 1,
        "max_files_changed": 3,
        "protected_action_flags": {
            "git_add": False,
            "git_commit": False,
            "git_push": False,
            "merge": False,
            "scheduler_activation": False,
            "daemon_activation": False,
            "worker_dispatch": False,
            "queue_mutation": False,
            "approval_mutation": False,
            "broker_live_trading": False,
            "credentials": False,
            "real_orders": False,
            "real_webhooks": False,
            "destructive_cleanup": False,
        },
    }
    item.update(overrides)
    return item


def _approval(**overrides):
    approval = {
        "schema": "AIOS_SELF_BUILD_APPLY_APPROVAL_GATE.v1",
        "approval_status": "approved",
        "requested_action": ACTION_ID,
        "selected_queue_action": ACTION_ID,
        "approved_by": "Anthony Meza",
        "approval_token_present": True,
        "allowed_paths_match": True,
        "validators_present": True,
        "local_allowlisted_apply_allowed": True,
        "can_apply_without_human": False,
        "rejection_reasons": [],
        "safety": {"protected_action_requested": False},
    }
    approval.update(overrides)
    return approval


def _bridge(**overrides):
    bridge = {
        "schema": "AIOS_SELF_BUILD_LOCAL_APPLY_EXECUTOR_BRIDGE.v1",
        "bridge_status": "ready",
        "selected_action": ACTION_ID,
        "command_to_run": _command(),
        "allowed_paths": _allowed_paths(),
        "validators": _validators(),
        "max_repairs": 1,
        "max_files_changed": 3,
        "execution_status": "prepared_not_executed",
        "safety": {"commands_executed": False},
    }
    bridge.update(overrides)
    return bridge


def _executor(**overrides):
    executor = {
        "schema": "AIOS_SELF_BUILD_SINGLE_ACTION_EXECUTOR.v1",
        "executor_status": "ready",
        "execution_mode": "APPLY_ALLOWED_NOT_RUN",
        "selected_action": ACTION_ID,
        "command_to_run": _command(),
        "command_would_run": True,
        "command_executed": False,
        "allowed_paths": _allowed_paths(),
        "validators": _validators(),
        "max_repairs": 1,
        "max_files_changed": 3,
        "approval_status": "approved",
        "bridge_status": "ready",
        "rejection_reasons": [],
        "safety": {"commands_executed": False, "command_executed": False},
    }
    executor.update(overrides)
    return executor


def _controller(**overrides):
    controller = {
        "schema": "AIOS_SELF_BUILD_ONE_ACTION_EXECUTION_CONTROLLER.v1",
        "controller_status": "ready",
        "execution_decision": "execute_one_action_allowed",
        "selected_action": ACTION_ID,
        "command_to_run": _command(),
        "command_execution_allowed": True,
        "command_executed": False,
        "allowed_paths": _allowed_paths(),
        "validators": _validators(),
        "max_repairs": 1,
        "max_files_changed": 3,
        "rejection_reasons": [],
        "safety": {"commands_executed": False, "command_executed": False},
    }
    controller.update(overrides)
    return controller


def _runner(**overrides):
    runner = {
        "schema": "AIOS_SELF_BUILD_ONE_ACTION_APPLY_RUNNER.v1",
        "runner_status": "preview_ready",
        "runner_mode": "DRY_RUN",
        "selected_action": ACTION_ID,
        "command_to_run": _command(),
        "command_execution_allowed": True,
        "command_executed": False,
        "commands_executed": False,
        "allowed_paths": _allowed_paths(),
        "validators": _validators(),
        "max_repairs": 1,
        "max_files_changed": 3,
        "rejection_reasons": [],
        "safety": {"commands_executed": False, "files_written": False, "reports_written": False},
    }
    runner.update(overrides)
    return runner


def _gate(**overrides):
    gate = {
        "schema": "AIOS_SELF_BUILD_ONE_ACTION_EXECUTE_GATE.v1",
        "gate_status": "armed",
        "execution_gate_decision": "one_action_execution_armed",
        "selected_action": ACTION_ID,
        "command_to_run": _command(),
        "command_execution_allowed": True,
        "command_executed": False,
        "commands_executed": False,
        "allowed_paths": _allowed_paths(),
        "validators": _validators(),
        "max_repairs": 1,
        "max_files_changed": 3,
        "rejection_reasons": [],
        "safety": {"commands_executed": False, "command_executed": False},
    }
    gate.update(overrides)
    return gate


def _verifier(**overrides):
    verifier = {
        "schema": "AIOS_SELF_BUILD_APPLY_RESULT_VERIFIER.v1",
        "verifier_status": "blocked",
        "selected_action": ACTION_ID,
        "changed_files": [],
        "allowed_paths": _allowed_paths(),
        "unexpected_files": [],
        "validators": [],
        "validators_passed": 0,
        "validators_failed": 0,
        "max_files_changed": 3,
        "file_count_ok": True,
        "allowed_paths_ok": True,
        "result_safe_to_report": True,
        "result_safe_to_package": False,
        "rejection_reasons": ["command_not_executed"],
        "safety": {"commands_executed": False},
    }
    verifier.update(overrides)
    return verifier


def _execution_request(**overrides):
    request = {
        "requested": True,
        "mode": ONE_ACTION_APPLY_MODE,
        "requested_action": ACTION_ID,
        "requested_write_paths": _allowed_paths(),
    }
    request.update(overrides)
    return request


def _local_executor_request(**overrides):
    request = {
        "requested": True,
        "mode": LOCAL_EXECUTOR_MODE,
        "requested_action": ACTION_ID,
        "approved_by": "Anthony Meza",
        "approval_token_present": True,
        "requested_write_paths": _allowed_paths(),
    }
    request.update(overrides)
    return request


def _options(**overrides):
    options = {"execute": False}
    options.update(overrides)
    return options


def _build(command_runner=None, **overrides):
    payload = {
        "selected_queue_item": _queue_item(),
        "apply_approval": _approval(),
        "local_apply_executor_bridge": _bridge(),
        "single_action_executor": _executor(),
        "one_action_execution_controller": _controller(),
        "one_action_apply_runner": _runner(),
        "one_action_execute_gate": _gate(),
        "apply_result_verifier": _verifier(),
        "execution_request": _execution_request(),
        "local_executor_request": _local_executor_request(),
        "executor_options": _options(),
        "command_runner": command_runner,
    }
    payload.update(overrides)
    return build_self_build_one_action_local_apply_executor(**payload)


def test_import_and_required_schema_fields():
    result = build_self_build_one_action_local_apply_executor()

    assert result["schema"] == SCHEMA
    assert set(result) >= {
        "schema",
        "executor_status",
        "executor_mode",
        "selected_action",
        "command_to_run",
        "command_execution_allowed",
        "command_executed",
        "command_returncode",
        "command_stdout_preview",
        "command_stderr_preview",
        "allowed_paths",
        "validators",
        "max_repairs",
        "max_files_changed",
        "pre_execution_checks",
        "post_execution_evidence",
        "rejection_reasons",
        "next_safe_action",
        "safety",
    }
    assert result["executor_status"] == "blocked"
    assert result["command_executed"] is False


def test_safe_approved_chain_with_execute_false_returns_dry_run_ready():
    result = _build()

    assert result["executor_status"] == "dry_run_ready"
    assert result["executor_mode"] == "DRY_RUN"
    assert result["selected_action"] == ACTION_ID
    assert result["command_to_run"] == _command()
    assert result["command_execution_allowed"] is True
    assert result["command_executed"] is False
    assert result["command_returncode"] is None
    assert result["allowed_paths"] == _allowed_paths()
    assert result["validators"] == _validators()
    assert result["max_repairs"] == 1
    assert result["max_files_changed"] == 3
    assert result["rejection_reasons"] == []


def test_default_execute_false_does_not_call_command_runner():
    calls = []

    def fake_runner(command: str, cwd: str):
        calls.append((command, cwd))
        return {"returncode": 0, "stdout": "ok", "stderr": "", "changed_files": []}

    result = _build(command_runner=fake_runner)

    assert result["executor_status"] == "dry_run_ready"
    assert calls == []
    assert result["post_execution_evidence"]["command_runner_called"] is False


def test_execute_true_with_fake_command_runner_returns_executed(tmp_path):
    calls = []

    def fake_runner(command: str, cwd: str):
        calls.append((command, cwd))
        return {
            "returncode": 0,
            "stdout": "ok",
            "stderr": "",
            "changed_files": ["automation/orchestration/aios_self_build_one_action_local_apply_executor.py"],
            "validators_run": _validators(),
        }

    result = _auth003_build(tmp_path, fake_runner)

    assert result["executor_status"] == "executed"
    assert result["executor_mode"] == "EXECUTE_ONE_ACTION"
    assert result["command_executed"] is True
    assert result["command_returncode"] == 0
    assert calls == [(_auth003_command(), str(tmp_path))]
    assert result["post_execution_evidence"]["command_runner_called"] is True
    assert result["post_execution_evidence"]["changed_files"] == [
        "automation/orchestration/aios_self_build_one_action_local_apply_executor.py",
    ]


def test_execute_true_without_command_runner_returns_blocked():
    result = _build(executor_options=_options(execute=True))

    assert result["executor_status"] == "blocked"
    assert result["executor_mode"] == "EXECUTE_ONE_ACTION"
    assert result["command_executed"] is False
    assert "command_runner_missing_for_execution" in result["rejection_reasons"]


def test_command_executed_false_in_dry_run():
    result = _build()

    assert result["command_executed"] is False
    assert result["safety"]["commands_executed"] is False


def test_command_executed_true_only_through_fake_command_runner(tmp_path):
    def fake_runner(_command: str, _cwd: str):
        return {"returncode": 0, "stdout": "", "stderr": "", "changed_files": []}

    dry_run = _build(command_runner=fake_runner)
    executed = _auth003_build(tmp_path, fake_runner)

    assert dry_run["command_executed"] is False
    assert executed["command_executed"] is True


def test_missing_local_executor_request_returns_blocked():
    result = _build(local_executor_request=None)

    assert result["executor_status"] == "blocked"
    assert "local_executor_request_missing" in result["rejection_reasons"]


def test_wrong_local_executor_request_mode_returns_blocked():
    result = _build(local_executor_request=_local_executor_request(mode="DRY_RUN"))

    assert result["executor_status"] == "blocked"
    assert "local_executor_request_mode_not_one_action_local_apply_executor" in result["rejection_reasons"]


def test_missing_approval_token_returns_blocked():
    result = _build(local_executor_request=_local_executor_request(approval_token_present=False))

    assert result["executor_status"] == "blocked"
    assert "local_executor_request_approval_token_missing" in result["rejection_reasons"]


def test_rejected_approval_returns_blocked():
    result = _build(apply_approval=_approval(approval_status="rejected"))

    assert result["executor_status"] == "blocked"
    assert "apply_approval_not_approved" in result["rejection_reasons"]


def test_bridge_not_ready_returns_blocked():
    result = _build(local_apply_executor_bridge=_bridge(bridge_status="blocked"))

    assert result["executor_status"] == "blocked"
    assert "local_apply_bridge_not_ready" in result["rejection_reasons"]


def test_single_action_executor_not_ready_returns_blocked():
    result = _build(single_action_executor=_executor(executor_status="blocked"))

    assert result["executor_status"] == "blocked"
    assert "single_action_executor_not_ready" in result["rejection_reasons"]


def test_one_action_execution_controller_not_ready_returns_blocked():
    result = _build(one_action_execution_controller=_controller(controller_status="blocked"))

    assert result["executor_status"] == "blocked"
    assert "one_action_execution_controller_not_ready" in result["rejection_reasons"]


def test_one_action_apply_runner_not_preview_ready_returns_blocked():
    result = _build(one_action_apply_runner=_runner(runner_status="blocked"))

    assert result["executor_status"] == "blocked"
    assert "one_action_apply_runner_not_preview_ready" in result["rejection_reasons"]


def test_execute_gate_not_armed_returns_blocked():
    result = _build(one_action_execute_gate=_gate(gate_status="blocked"))

    assert result["executor_status"] == "blocked"
    assert "one_action_execute_gate_not_armed" in result["rejection_reasons"]


def test_command_execution_allowed_false_returns_blocked():
    result = _build(one_action_execute_gate=_gate(command_execution_allowed=False))

    assert result["executor_status"] == "blocked"
    assert "one_action_execute_gate_not_allowed" in result["rejection_reasons"]


def test_action_mismatch_returns_rejected():
    result = _build(one_action_apply_runner=_runner(selected_action="build_different_item"))

    assert result["executor_status"] == "rejected"
    assert "selected_action_mismatch" in result["rejection_reasons"]


def test_missing_validators_returns_rejected():
    result = _build(
        selected_queue_item=_queue_item(validators=[]),
        local_apply_executor_bridge=_bridge(validators=[]),
        single_action_executor=_executor(validators=[]),
        one_action_execution_controller=_controller(validators=[]),
        one_action_apply_runner=_runner(validators=[]),
        one_action_execute_gate=_gate(validators=[]),
    )

    assert result["executor_status"] == "rejected"
    assert "validators_missing" in result["rejection_reasons"]


def test_path_outside_allowed_scope_returns_rejected():
    result = _build(local_executor_request=_local_executor_request(requested_write_paths=[*_allowed_paths(), "Reports/outside.md"]))

    assert result["executor_status"] == "rejected"
    assert "requested_paths_outside_allowed_paths" in result["rejection_reasons"]


def test_max_files_changed_above_five_returns_rejected():
    result = _build(one_action_execute_gate=_gate(max_files_changed=6))

    assert result["executor_status"] == "rejected"
    assert "max_files_changed_exceeds_five" in result["rejection_reasons"]


def test_max_repairs_above_one_returns_rejected():
    result = _build(one_action_execute_gate=_gate(max_repairs=2))

    assert result["executor_status"] == "rejected"
    assert "max_repairs_exceeds_one" in result["rejection_reasons"]


def test_protected_git_action_request_returns_rejected():
    result = _build(local_executor_request=_local_executor_request(git_push_requested=True))

    assert result["executor_status"] == "rejected"
    assert "protected_action_requested" in result["rejection_reasons"]


def test_broker_live_trading_credentials_request_returns_rejected():
    result = _build(
        local_executor_request=_local_executor_request(
            broker=True,
            live_trading=True,
            credentials=True,
            real_orders=True,
            real_webhooks=True,
        )
    )

    assert result["executor_status"] == "rejected"
    assert "protected_action_requested" in result["rejection_reasons"]
    assert result["safety"]["broker"] is False
    assert result["safety"]["live_trading"] is False
    assert result["safety"]["credentials"] is False


def test_scheduler_daemon_worker_dispatch_request_returns_rejected():
    result = _build(
        local_executor_request=_local_executor_request(
            scheduler_activation_requested=True,
            daemon_activation_requested=True,
            worker_dispatch_requested=True,
        )
    )

    assert result["executor_status"] == "rejected"
    assert "protected_action_requested" in result["rejection_reasons"]
    assert result["safety"]["scheduler"] is False
    assert result["safety"]["daemon"] is False
    assert result["safety"]["worker_dispatch"] is False


def test_queue_or_approval_mutation_request_returns_rejected():
    result = _build(local_executor_request=_local_executor_request(queue_mutation_requested=True, approval_mutation_requested=True))

    assert result["executor_status"] == "rejected"
    assert "protected_action_requested" in result["rejection_reasons"]


def test_destructive_cleanup_request_returns_rejected():
    result = _build(local_executor_request=_local_executor_request(destructive_cleanup_requested=True))

    assert result["executor_status"] == "rejected"
    assert "protected_action_requested" in result["rejection_reasons"]


def test_fake_command_runner_changed_file_outside_allowed_paths_returns_rejected(tmp_path):
    def fake_runner(_command: str, _cwd: str):
        return {"returncode": 0, "stdout": "ok", "stderr": "", "changed_files": ["Reports/outside.md"]}

    result = _auth003_build(tmp_path, fake_runner)

    assert result["executor_status"] == "rejected"
    assert result["command_executed"] is True
    assert "command_runner_changed_files_outside_allowed_paths" in result["rejection_reasons"]


def test_safety_flags_prove_no_external_automation_in_dry_run():
    result = _build()
    safety = result["safety"]

    assert safety["direct_command_runner_used"] is False
    assert safety["commands_executed"] is False
    assert safety["git_add"] is False
    assert safety["git_commit"] is False
    assert safety["git_push"] is False
    assert safety["merge"] is False
    assert safety["reports_written"] is False
    assert safety["broker"] is False
    assert safety["network_access"] is False


def test_stdout_and_stderr_previews_are_bounded(tmp_path):
    def fake_runner(_command: str, _cwd: str):
        return {"returncode": 0, "stdout": "o" * 1000, "stderr": "e" * 1000, "changed_files": []}

    result = _auth003_build(tmp_path, fake_runner)

    assert len(result["command_stdout_preview"]) == 400
    assert len(result["command_stderr_preview"]) == 400
    assert len(result["post_execution_evidence"]["stdout_preview"]) == 400
    assert len(result["post_execution_evidence"]["stderr_preview"]) == 400


def test_auth003_actual_canonical_one_shot_across_instances(tmp_path):
    import json
    from automation.orchestration.claims.aios_task_claim_control import ExecutionAdmission, TaskClaimController

    fixture = _auth003_fixture(tmp_path)
    calls = []
    kwargs = dict(command_runner=lambda *args: calls.append(args) or {"returncode": 0},
                  executor_options=_options(execute=True), **fixture["build"])
    before = fixture["controller"].board_path.read_bytes()
    first = _build(**kwargs)
    assert first["executor_status"] == "executed" and len(calls) == 1
    board = json.loads(fixture["controller"].board_path.read_text())
    assert len(board["execution_intents"]) == 1
    assert json.loads(before)["claims"] == board["claims"]
    kwargs["execution_admission"] = ExecutionAdmission(
        TaskClaimController(fixture["controller"].board_path), fixture["claim"],
        lambda: fixture["material"], allow_test_trust=True)
    second = _build(**kwargs)
    assert second["executor_status"] == "blocked" and len(calls) == 1


def test_auth003_callback_pass_dictionary_is_not_authority(tmp_path):
    from dataclasses import replace
    fixture = _auth003_fixture(tmp_path)
    fixture["build"]["execution_admission"] = replace(
        fixture["admission"], authority_reader=lambda: {"status": "PASS", "apply_allowed": True})
    calls = []
    result = _build(command_runner=lambda *args: calls.append(args) or {"returncode": 0},
                    executor_options=_options(execute=True), **fixture["build"])
    assert result["executor_status"] == "blocked" and not calls


import pytest


@pytest.mark.parametrize("defect", [
    "forged", "expired", "revoked", "production_test_trust", "wrong_packet", "wrong_path",
    "wrong_source", "wrong_runtime", "wrong_command", "wrong_validator", "wrong_limit",
    "wrong_stop", "wrong_output", "wrong_claim", "wrong_branch", "unsigned_v1", "missing",
    "history_replay", "ambiguous_runtime", "extra_capability",
])
def test_auth003_invalid_authority_zero_runner_calls(tmp_path, monkeypatch, defect):
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone
    from automation.orchestration.claims import aios_task_claim_control as owner

    fixture = _auth003_fixture(tmp_path)
    gate, trust = fixture["material"]["gate"], fixture["material"]["trust_metadata"]
    admission = fixture["admission"]
    if defect == "forged":
        gate["approval_evidence"]["approval_hmac_sha256"] = "0" * 64
    elif defect == "expired":
        gate["latest_entry_utc"] = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        gate["expires_at_utc"] = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        fixture["sign"]()
    elif defect == "revoked":
        trust["state"] = "REVOKED"
        trust["keys"][0].update(status="REVOKED", revoked_at_utc=gate["created_at_utc"], revocation_reason="engineering")
    elif defect == "production_test_trust":
        admission = replace(admission, allow_test_trust=False)
    elif defect == "wrong_packet":
        gate["packet_id"] = "other-packet"
        fixture["sign"]()
    elif defect == "wrong_path":
        gate["allowed_paths"] = [str(tmp_path / "outside")]
        fixture["sign"]()
    elif defect == "wrong_source":
        (tmp_path / "automation/orchestration/aios_productive_bounded_executor.py").write_text("# drift")
    elif defect == "wrong_runtime":
        monkeypatch.setattr(owner.sys, "version_info", (0, 0, 0))
    elif defect == "wrong_command":
        fixture["build"]["one_action_execute_gate"] = _gate(command_to_run=_command() + " --drift")
    elif defect == "wrong_validator":
        gate["validator_chain"] = ["other-validator"]
        fixture["sign"]()
    elif defect == "wrong_limit":
        gate["resource_limits"]["max_files_changed"] = 2
        fixture["sign"]()
    elif defect == "wrong_stop":
        gate["stop_point"] = "continue"
        fixture["sign"]()
    elif defect == "wrong_output":
        gate["output_roots"] = {"report": "outside"}
        fixture["sign"]()
    elif defect == "wrong_claim":
        admission = replace(admission, expected_claim={**fixture["claim"], "worker": "another-worker"})
    elif defect == "wrong_branch":
        (tmp_path / ".git/HEAD").write_text("ref: refs/heads/another\n")
    elif defect == "history_replay":
        import json
        history = tmp_path / "history"
        history.mkdir()
        for name in ("first.json", "second.json"):
            (history / name).write_text(json.dumps(gate))
        fixture["material"]["approval_roots"] = [history]
    elif defect == "ambiguous_runtime":
        fixture["build"]["one_action_execute_gate"] = _gate(command_to_run=_command())
    elif defect == "extra_capability":
        gate["capabilities"]["network"] = True
        fixture["sign"]()
    elif defect == "unsigned_v1":
        gate["schema"] = "AIOS_HUMAN_OWNER_APPROVAL_PAYLOAD.v1"
    elif defect == "missing":
        admission = None
    fixture["build"]["execution_admission"] = admission
    calls = []
    result = _build(command_runner=lambda *args: calls.append(args) or {"returncode": 0},
                    executor_options=_options(execute=True), **fixture["build"])
    assert calls == [] and result["executor_status"] == "blocked"


@pytest.mark.parametrize("defect", ["revoked", "expired", "claim_expired", "source", "runtime", "claim", "provider_error"])
def test_auth003_final_fresh_check_burns_intent_without_dispatch(tmp_path, monkeypatch, defect):
    import json
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone
    from automation.orchestration.claims import aios_task_claim_control as owner

    fixture = _auth003_fixture(tmp_path)
    reads = []
    def reader():
        reads.append(True)
        if len(reads) == 2:
            if defect == "revoked":
                fixture["material"]["trust_metadata"]["keys"][0]["status"] = "REVOKED"
            elif defect in {"expired", "claim_expired"}:
                future = datetime.now(timezone.utc) + timedelta(minutes=30 if defect == "expired" else 120)
                class Later(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return future
                monkeypatch.setattr(owner, "datetime", Later)
            elif defect == "source":
                (tmp_path / "automation/orchestration/aios_productive_bounded_executor.py").write_text("# drift")
            elif defect == "runtime":
                monkeypatch.setattr(owner.sys, "version_info", (0, 0, 0))
            elif defect == "claim":
                fixture["controller"].transition("one", "BLOCKED", expected_claim=fixture["claim"])
            elif defect == "provider_error":
                raise RuntimeError("owned provider failed")
        return fixture["material"]
    fixture["build"]["execution_admission"] = replace(fixture["admission"], authority_reader=reader)
    calls = []
    result = _build(command_runner=lambda *args: calls.append(args) or {"returncode": 0},
                    executor_options=_options(execute=True), **fixture["build"])
    assert result["executor_status"] == "blocked" and not calls and len(reads) == 2
    saved = json.loads(fixture["controller"].board_path.read_text())["execution_intents"]
    assert len(saved) == 1 and saved[0]["state"] == "CONSUMED"
    retry = _build(command_runner=lambda *args: calls.append(args) or {"returncode": 0},
                   executor_options=_options(execute=True), **fixture["build"])
    assert retry["executor_status"] == "blocked" and not calls
    assert json.loads(fixture["controller"].board_path.read_text())["execution_intents"] == saved


def test_auth003_slow_canonical_history_scan_cannot_use_old_clock_or_sources(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from automation.orchestration.claims import aios_task_claim_control as owner
    from automation.validators import aios_approval_authority_integrity_validator as canonical

    fixture = _auth003_fixture(tmp_path)
    original = canonical.nonce_reused
    def slow_history(*args, **kwargs):
        outcome = original(*args, **kwargs)
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return future
        monkeypatch.setattr(owner, "datetime", Later)
        return outcome
    monkeypatch.setattr(canonical, "nonce_reused", slow_history)
    calls = []
    result = _build(command_runner=lambda *args: calls.append(args) or {"returncode": 0},
                    executor_options=_options(execute=True), **fixture["build"])
    assert result["executor_status"] == "blocked" and not calls


def test_auth003_uncertain_runner_never_reopens_attempt(tmp_path):
    import json
    fixture = _auth003_fixture(tmp_path)
    calls = []
    def uncertain(*args):
        calls.append(args)
        raise RuntimeError("engineering uncertainty")
    kwargs = dict(command_runner=uncertain, executor_options=_options(execute=True), **fixture["build"])
    assert _build(**kwargs)["executor_status"] == "blocked"
    saved = json.loads(fixture["controller"].board_path.read_text())["execution_intents"]
    assert _build(**kwargs)["executor_status"] == "blocked" and len(calls) == 1
    assert json.loads(fixture["controller"].board_path.read_text())["execution_intents"] == saved


@pytest.mark.parametrize("timing", ["unchanged", "second_provider_read", "after_final_lock_exit"])
def test_auth003_ir01_actual_builder_dispatch_handoff(tmp_path, timing):
    import inspect
    import json
    import sys
    from automation.orchestration.claims import aios_task_claim_control as owner

    fixture = _auth003_fixture(tmp_path)
    calls, events, reads = [], [], []
    source, start = inspect.getsourcelines(owner.TaskClaimController.execute_once)
    dispatch_line = start + next(i for i, line in enumerate(source) if line.strip() == "return action()")
    def reader():
        reads.append(True)
        if timing == "second_provider_read" and len(reads) == 2:
            fixture["controller"].transition("one", "BLOCKED", expected_claim=fixture["claim"])
            events.append("invalidation_won_before_dispatch")
        return fixture["material"]
    fixture["build"]["execution_admission"] = owner.ExecutionAdmission(
        fixture["controller"], fixture["claim"], reader, True)
    def runner(*args):
        calls.append(json.loads(fixture["controller"].board_path.read_text())["claims"][0]["state"])
        return {"returncode": 0}
    def trace(frame, event, arg):
        if (timing == "after_final_lock_exit" and event == "line"
                and frame.f_code is owner.TaskClaimController.execute_once.__code__
                and frame.f_lineno == dispatch_line):
            try:
                fixture["controller"].transition("one", "BLOCKED", expected_claim=fixture["claim"])
                events.append("invalidation_completed_after_final_lock_exit")
            except owner.ClaimError as error:
                assert "dispatch" in str(error)
                events.append("invalidation_refused_pending_dispatch")
        return trace
    previous_trace = sys.gettrace()
    try:
        sys.settrace(trace)
        result = _build(command_runner=runner, executor_options=_options(execute=True), **fixture["build"])
    finally:
        sys.settrace(previous_trace)
    retry = _build(command_runner=runner, executor_options=_options(execute=True), **fixture["build"])
    if timing == "second_provider_read":
        assert result["executor_status"] == "blocked" and not calls
        assert events == ["invalidation_won_before_dispatch"]
    else:
        assert result["executor_status"] == "executed" and calls == ["ACTIVE"]
        assert events == ([] if timing == "unchanged" else ["invalidation_refused_pending_dispatch"])
    assert retry["executor_status"] == "blocked"
    assert len(json.loads(fixture["controller"].board_path.read_text())["execution_intents"]) == 1


def test_source_has_no_direct_command_or_file_side_effect_apis():
    source = Path("automation/orchestration/aios_self_build_one_action_local_apply_executor.py").read_text()

    forbidden_terms = [
        "subprocess",
        "requests",
        "socket",
        "urllib",
        ".write_text",
        ".write_bytes",
        "open(",
        "os.system",
        "git add",
        "git commit",
        "git push",
        "git merge",
    ]
    assert all(term not in source for term in forbidden_terms)


def _campaign_owned_inputs(fixture):
    inputs = {"selected_queue_item": fixture["build"]["selected_queue_item"], "apply_approval": _approval(),
        "local_apply_executor_bridge": _bridge(), "single_action_executor": _executor(),
        "one_action_execution_controller": _controller(), "one_action_apply_runner": _runner(),
        "one_action_execute_gate": _gate(), "apply_result_verifier": _verifier(),
        "execution_request": _execution_request(), "local_executor_request": _local_executor_request(),
        "executor_options": _options(execute=True)}
    inputs.update({key: value for key, value in fixture["build"].items() if key != "execution_admission"})
    return inputs


def test_campaign_connection_refuses_malformed_claim_before_effects(tmp_path):
    from automation.orchestration import aios_self_build_one_action_local_apply_executor as owner
    from automation.orchestration.claims.aios_task_claim_control import TaskClaimController
    inputs = {"selected_queue_item": _queue_item(packet_id="example-only"), "apply_approval": _approval(),
        "local_apply_executor_bridge": _bridge(), "single_action_executor": _executor(),
        "one_action_execution_controller": _controller(), "one_action_apply_runner": _runner(),
        "one_action_execute_gate": _gate(), "apply_result_verifier": _verifier(),
        "execution_request": _execution_request(), "local_executor_request": _local_executor_request(),
        "executor_options": _options(execute=True)}
    calls = []
    execute = owner.make_campaign_execution_connection(
        TaskClaimController(tmp_path / "test-board.json"), read_claim=lambda task: {},
        read_executor_inputs=lambda task: inputs, read_verification_inputs=lambda task: {},
        command_runner=lambda *args: calls.append(args), read_original_selection=lambda task: {})
    result = execute({"packet_id": inputs["selected_queue_item"]["packet_id"]})
    assert result["status"] == "BLOCKED"
    assert not calls
    assert not (tmp_path / "test-board.json").exists()


def test_campaign_connection_binds_verification_to_current_execution(tmp_path, monkeypatch):
    from automation.orchestration import aios_self_build_one_action_local_apply_executor as owner
    from automation.orchestration import aios_self_build_apply_result_verifier as verifier
    fixture = _auth003_fixture(tmp_path)
    inputs = {"selected_queue_item": fixture["build"]["selected_queue_item"], "apply_approval": _approval(),
        "local_apply_executor_bridge": _bridge(), "single_action_executor": _executor(),
        "one_action_execution_controller": _controller(), "one_action_apply_runner": _runner(),
        "one_action_execute_gate": _gate(), "apply_result_verifier": _verifier(),
        "execution_request": _execution_request(), "local_executor_request": _local_executor_request(),
        "executor_options": _options(execute=True)}
    actual = {"executor_status": "executed", "command_executed": True, "command_returncode": 0, "actual_result": "new"}
    monkeypatch.setattr(owner, "build_self_build_one_action_local_apply_executor", lambda **kwargs: actual)
    checked = []
    monkeypatch.setattr(verifier, "build_self_build_apply_result_verifier", lambda **kwargs: checked.append(kwargs) or {"verifier_status": "passed"})
    execute = owner.make_campaign_execution_connection(fixture["controller"], read_claim=lambda task: fixture["claim"],
        read_executor_inputs=lambda task: inputs,
        read_verification_inputs=lambda *args: {"selected_queue_item": inputs["selected_queue_item"],
            "single_action_executor": {"executor_status": "executed", "command_executed": True, "actual_result": "old"}},
        command_runner=lambda *args: None,
        read_original_selection=lambda task: {"packet": {"packet_id": fixture["claim"]["packet_id"]},
            "claim": fixture["claim"], "queue_item": inputs["selected_queue_item"]})
    result = execute({"packet_id": fixture["claim"]["packet_id"]})
    assert result["status"] == "BLOCKED"
    assert not checked


def test_campaign_connection_refuses_changed_original_selection(tmp_path, monkeypatch):
    from automation.orchestration import aios_self_build_one_action_local_apply_executor as owner
    fixture = _auth003_fixture(tmp_path)
    inputs = _campaign_owned_inputs(fixture)
    calls = []
    monkeypatch.setattr(owner, "build_self_build_one_action_local_apply_executor", lambda **kwargs: calls.append(kwargs))
    packet = {"packet_id": fixture["claim"]["packet_id"], "original": "one"}
    execute = owner.make_campaign_execution_connection(fixture["controller"], read_claim=lambda task: fixture["claim"],
        read_executor_inputs=lambda task: inputs, read_verification_inputs=lambda *args: {}, command_runner=lambda *args: None,
        read_original_selection=lambda task: {"packet": {**packet, "original": "changed"},
            "claim": fixture["claim"], "queue_item": inputs["selected_queue_item"]})
    assert execute(packet)["status"] == "BLOCKED"
    assert not calls


def test_campaign_connection_valid_claim_still_requires_raw_signed_permission(tmp_path, monkeypatch):
    from automation.orchestration import aios_self_build_one_action_local_apply_executor as owner
    from automation.orchestration.claims.aios_task_claim_control import ExecutionAdmission
    fixture = _auth003_fixture(tmp_path)
    inputs = _campaign_owned_inputs(fixture)
    reads, calls = [], []
    class MissingRawPermission(ExecutionAdmission):
        def __init__(self, controller, claim):
            super().__init__(controller, claim, lambda: reads.append("original authority read") or {})
    # Use the real admission and board owner, with an inert empty raw-material
    # reader so no actual key/approval store is accessed by this example.
    monkeypatch.setattr(owner, "ExecutionAdmission", MissingRawPermission)
    packet = {"packet_id": fixture["claim"]["packet_id"]}
    execute = owner.make_campaign_execution_connection(fixture["controller"], read_claim=lambda task: fixture["claim"],
        read_executor_inputs=lambda task: inputs, read_verification_inputs=lambda *args: {},
        command_runner=lambda *args: calls.append(args),
        read_original_selection=lambda task: {"packet": packet, "claim": fixture["claim"],
            "queue_item": inputs["selected_queue_item"]})
    result = execute(packet)
    assert result["status"] == "BLOCKED"
    assert reads == ["original authority read"] and not calls
    assert "final_authority_admission_blocked" in result["execution"]["rejection_reasons"]


@__import__("pytest").mark.parametrize("failure", ["boolean_substitution", "nonzero_exit", "mutate_result"])
def test_campaign_connection_current_result_is_strict_and_frozen(tmp_path, monkeypatch, failure):
    from automation.orchestration import aios_self_build_one_action_local_apply_executor as owner
    from automation.orchestration import aios_self_build_apply_result_verifier as verifier
    fixture = _auth003_fixture(tmp_path)
    inputs = _campaign_owned_inputs(fixture)
    packet = {"packet_id": fixture["claim"]["packet_id"]}
    actual = {"executor_status": "executed", "command_executed": True,
              "command_returncode": 5 if failure == "nonzero_exit" else 0}
    monkeypatch.setattr(owner, "build_self_build_one_action_local_apply_executor", lambda **kwargs: actual)
    checked = []
    monkeypatch.setattr(verifier, "build_self_build_apply_result_verifier", lambda **kwargs: checked.append(kwargs) or {"verifier_status": "passed"})
    def verification(task, received):
        if failure == "mutate_result":
            received["command_returncode"] = 5
        value = dict(received)
        if failure == "boolean_substitution":
            value["command_returncode"] = False
        return {"selected_queue_item": inputs["selected_queue_item"], "single_action_executor": value}
    execute = owner.make_campaign_execution_connection(fixture["controller"], read_claim=lambda task: fixture["claim"],
        read_executor_inputs=lambda task: inputs, read_verification_inputs=verification, command_runner=lambda *args: None,
        read_original_selection=lambda task: {"packet": packet, "claim": fixture["claim"], "queue_item": inputs["selected_queue_item"]})
    assert execute(packet)["status"] == "BLOCKED"
    assert not checked
    if failure == "mutate_result":
        assert actual["command_returncode"] == 0
