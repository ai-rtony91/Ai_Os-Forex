from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "automation" / "orchestration" / "aios_resume_state.py"


def load_module():
    spec = importlib.util.spec_from_file_location("aios_resume_state", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def wake_report(result: str = "DONE_FOR_CURRENT_GOAL", handoff_status: str = "ready") -> dict[str, object]:
    return {
        "schema": "AIOS_WAKE_CONTINUE.v1",
        "goal": "forex-paper-bot",
        "result": result,
        "selected_action": "validate_all_forex",
        "goal_decision": {
            "decision": "continue_build",
            "reason_code": "acceptable_report",
            "decision_reasons": ["acceptable_report"],
        },
        "next_build_plan": {
            "schema": "AIOS_NEXT_BUILD_PLAN.v1",
            "route": "build_next_paper_component",
            "next_component": "forex_risk_controls",
            "next_packet_id": "PKT-AIOS-FOREX-RISK-CONTROLS-CONTINUATION-APPLY",
        },
        "bounded_executor_handoff": {
            "schema": "AIOS_BOUNDED_EXECUTOR_HANDOFF.v1",
            "handoff_status": handoff_status,
            "allowed_action": "build_forex_risk_controls",
            "credentials": {"sample": "safe-placeholder"},
        },
        "validators_run": [
            {
                "name": "forex_tests",
                "command": "python -m pytest tests/trading_lab/test_forex_decision_policy.py",
                "returncode": 0,
                "passed": True,
                "stdout": "bulk stdout must be stripped",
                "stderr": "bulk stderr must be stripped",
            }
        ],
        "approval_required": {"commit": True, "push": True, "merge": True},
        "next_safe_action": "Prepare the bounded handoff for Anthony review.",
        "safety": {"queue_mutation": False},
    }


def test_resume_state_module_imports():
    module = load_module()
    assert module.SCHEMA == "AIOS_RESUME_STATE.v1"
    assert callable(module.build_resume_state)


def test_builds_valid_resume_state_from_wake_continue_fixture():
    module = load_module()
    resume = module.build_resume_state(wake_report())
    assert resume["schema"] == "AIOS_RESUME_STATE.v1"
    assert resume["goal"] == "forex-paper-bot"
    assert resume["last_decision"]["decision"] == "continue_build"
    assert resume["next_build_plan"]["next_component"] == "forex_risk_controls"
    assert resume["bounded_executor_handoff"]["allowed_action"] == "build_forex_risk_controls"


def test_strips_stdout_and_stderr_bulk_from_validators():
    module = load_module()
    resume = module.build_resume_state(wake_report())
    serialized = json.dumps(resume)
    assert "bulk stdout" not in serialized
    assert "bulk stderr" not in serialized
    assert resume["validators_summary"]["count"] == 1
    assert resume["validators_summary"]["passed_count"] == 1
    assert resume["validators_summary"]["failed_count"] == 0


def test_resume_ready_true_for_done_and_ready_handoff():
    module = load_module()
    resume = module.build_resume_state(wake_report())
    assert resume["resume_ready"] is True
    assert resume["resume_reason_code"] == "ready_for_resume"


def test_resume_ready_false_for_blocked_or_review_required():
    module = load_module()
    blocked = module.build_resume_state(wake_report(result="BLOCKED", handoff_status="blocked"))
    review = module.build_resume_state(wake_report(result="REVIEW_REQUIRED", handoff_status="stopped"))
    assert blocked["resume_ready"] is False
    assert blocked["resume_reason_code"] == "result_not_done_for_current_goal"
    assert review["resume_ready"] is False
    assert review["resume_reason_code"] == "result_not_done_for_current_goal"


def test_sensitive_payload_is_redacted():
    module = load_module()
    resume = module.build_resume_state(wake_report())
    assert resume["bounded_executor_handoff"]["credentials"] == "[redacted]"


def test_write_function_writes_timestamped_and_latest_files_under_resume_dir(tmp_path):
    module = load_module()
    resume = module.build_resume_state(wake_report())
    written = module.write_resume_state(
        tmp_path,
        resume,
        generated_at_utc=datetime(2026, 6, 14, 12, 30, 0, tzinfo=timezone.utc),
    )
    timestamped = tmp_path / written["resume_state_paths"]["timestamped"]
    latest = tmp_path / written["resume_state_paths"]["latest"]
    assert timestamped.exists()
    assert latest.exists()
    assert timestamped.name.startswith("AIOS_RESUME_STATE_20260614_123000Z_")
    assert timestamped.name.endswith(".json")
    assert latest.name == "AIOS_RESUME_STATE_latest.json"
    assert "Reports/aios_resume/" in written["resume_state_paths"]["timestamped"]


def test_write_function_rejects_path_traversal_or_outside_output(tmp_path):
    module = load_module()
    resume = module.build_resume_state(wake_report())
    for output_dir in [tmp_path / "outside", tmp_path / "Reports" / "aios_resume" / ".." / "other"]:
        try:
            module.write_resume_state(tmp_path, resume, output_dir=output_dir)
        except ValueError as exc:
            assert str(exc) == "resume_state_dir_outside_allowed_root"
        else:
            raise AssertionError("unsafe output dir was accepted")


def test_no_unsafe_flags_are_enabled():
    module = load_module()
    resume = module.build_resume_state(wake_report())
    assert all(value is False for value in resume["safety"].values())


def test_no_queue_approval_worker_scheduler_broker_or_live_paths_in_source():
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    for forbidden in [
        "subprocess",
        "requests",
        "socket",
        "urllib",
        "http.client",
        "queue_mutation = true",
        "approval_mutation = true",
        "worker_dispatch = true",
        "scheduler = true",
        "daemon = true",
        "live_trading = true",
        "real_orders = true",
        "real_webhooks = true",
    ]:
        assert forbidden not in source


def contract_module(name):
    path = REPO_ROOT / "automation" / "orchestration" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def produced_wake_report(component="forex_risk_controls"):
    report = wake_report()
    report["next_build_plan"]["next_component"] = component
    report["next_build_plan"]["safety"] = {"credentials": False, "broker": False}
    report["next_build_plan"]["approval_required"] = {"credentials": True, "local_plan_preview": False}
    report["bounded_executor_handoff"] = contract_module(
        "aios_bounded_executor_handoff"
    ).build_bounded_executor_handoff(report["next_build_plan"])
    report["approval_required"]["credentials"] = True
    return report


def controller_for(resume, handoff, **overrides):
    arguments = {
        "resume_state": resume,
        "bounded_executor_handoff": handoff,
        "bounded_executor_ready": {"status": "ready_for_human_review"},
        "mode_registry": contract_module("aios_mode_capability_registry").build_mode_capability_registry(),
        "user_goal": "forex-paper-bot",
    }
    arguments.update(overrides)
    return contract_module("aios_continuation_controller").build_continuation_controller(**arguments)


def save_and_reload(tmp_path, report):
    module = load_module()
    resume = module.build_resume_state(report)
    module.write_resume_state(
        tmp_path, resume,
        generated_at_utc=datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc),
    )
    return json.loads((tmp_path / "Reports/aios_resume/AIOS_RESUME_STATE_latest.json").read_text(encoding="utf-8"))


def test_real_handoff_false_round_trip_keeps_approval_gated_route(tmp_path):
    report = produced_wake_report()
    frozen = deepcopy(report)
    baseline = controller_for({"goal": report["goal"]}, report["bounded_executor_handoff"])
    assert baseline["action_type"] == "execute_existing_tool_after_human_approval"
    assert baseline["reason_code"] == "productive_executor_support_available"
    assert baseline["sos_required"] is False

    loaded = save_and_reload(tmp_path, report)
    loaded_frozen = deepcopy(loaded)
    continued = controller_for(loaded, loaded["bounded_executor_handoff"])
    assert continued["action_type"] == baseline["action_type"]
    assert continued["reason_code"] == baseline["reason_code"]
    assert continued["sos_required"] is False
    assert continued["execution_authority_granted"] is False
    assert continued["approval_required"]["human_review"] is True
    assert loaded["bounded_executor_handoff"]["safety"]["credentials"] is False
    assert loaded["next_build_plan"]["safety"]["credentials"] is False
    assert loaded["next_build_plan"]["approval_required"]["credentials"] is True
    assert loaded["next_build_plan"]["approval_required"]["local_plan_preview"] is False
    assert loaded["approval_required"]["credentials"] is True
    assert report == frozen
    assert loaded == loaded_frozen


def test_real_handoff_true_remains_a_safety_stop_after_round_trip(tmp_path):
    report = produced_wake_report()
    report["bounded_executor_handoff"]["safety"]["credentials"] = True
    baseline = controller_for({"goal": report["goal"]}, report["bounded_executor_handoff"])
    loaded = save_and_reload(tmp_path, report)
    continued = controller_for(loaded, loaded["bounded_executor_handoff"])
    for result in (baseline, continued):
        assert result["action_type"] == "sos_stop"
        assert result["reason_code"] == "safety_blocker_present"
        assert result["safety"]["credentials"] is True
        assert result["productive_executor_available"] is False
        assert result["execution_authority_granted"] is False
    assert loaded["bounded_executor_handoff"]["safety"]["credentials"] is True


def test_only_schema_bound_metadata_gets_boolean_redaction_exception(tmp_path):
    report = produced_wake_report()
    payload = {
        "credentials": False,
        "safety": {"credentials": False},
        "approval_required": {"credentials": True},
        "items": [{"safety": {"credentials": False}}],
        "secret": "inert-secret-placeholder",
        "stdout": "inert-bulk-output",
        "stderr": "inert-bulk-error",
    }
    for name in ("next_build_plan", "bounded_executor_handoff"):
        report[name]["payload"] = deepcopy(payload)
        report[name]["credentials"] = False
        report[name]["stdout"] = "inert-bulk-output"
        report[name]["stderr"] = "inert-bulk-error"
    loaded = save_and_reload(tmp_path, report)
    for name in ("next_build_plan", "bounded_executor_handoff"):
        contract = loaded[name]
        assert contract["safety"]["credentials"] is False
        assert contract["credentials"] == "[redacted]"
        assert contract["payload"]["credentials"] == "[redacted]"
        assert contract["payload"]["safety"]["credentials"] == "[redacted]"
        assert contract["payload"]["approval_required"]["credentials"] == "[redacted]"
        assert contract["payload"]["items"][0]["safety"]["credentials"] == "[redacted]"
        assert contract["payload"]["secret"] == "[redacted]"
    serialized = json.dumps(loaded)
    for text in ("inert-secret-placeholder", "inert-bulk-output", "inert-bulk-error", '"stdout"', '"stderr"'):
        assert text not in serialized


@pytest.mark.parametrize("name", ["next_build_plan", "bounded_executor_handoff"])
def test_wrong_contract_schema_does_not_exempt_sensitive_boolean(name):
    report = produced_wake_report()
    report[name]["schema"] = "untrusted-contract"
    loaded = load_module().build_resume_state(report)
    assert loaded[name]["safety"]["credentials"] == "[redacted]"


@pytest.mark.parametrize("invalid", ["[redacted]", "false", 0, None, []])
@pytest.mark.parametrize("slot", ["resume_state", "control_plane_status", "bounded_executor_handoff", "bounded_executor_ready", "next_build_plan", "persisted_handoff"])
def test_malformed_known_safety_flag_is_invalid_evidence_without_fabricated_use(invalid, slot):
    report = produced_wake_report()
    resume = {"goal": report["goal"]}
    handoff = report["bounded_executor_handoff"]
    overrides = {}
    if slot == "resume_state":
        resume["safety"] = {"credentials": invalid}
    elif slot == "bounded_executor_handoff":
        handoff["safety"]["credentials"] = invalid
    elif slot in {"next_build_plan", "persisted_handoff"}:
        name = "next_build_plan" if slot == "next_build_plan" else "bounded_executor_handoff"
        resume[name] = {"safety": {"credentials": invalid}}
    else:
        overrides[slot] = {"status": "ready_for_human_review", "safety": {"credentials": invalid}}
    frozen = deepcopy((resume, handoff, overrides))
    result = controller_for(resume, handoff, **overrides)
    assert result["action_type"] == "human_review"
    assert result["reason_code"] == "invalid_safety_evidence"
    assert result["continuation_status"] == "blocked"
    assert result["sos_required"] is False
    assert result["safety"]["credentials"] is False
    assert result["productive_executor_available"] is False
    assert result["local_runner_available"] is False
    assert result["execution_authority_granted"] is False
    assert result["invalid_evidence_fields"]
    assert all(path.endswith(".safety.credentials") for path in result["invalid_evidence_fields"])
    assert "[redacted]" not in json.dumps(result)
    assert (resume, handoff, overrides) == frozen


@pytest.mark.parametrize("invalid", [None, [], "not-a-mapping", 0])
@pytest.mark.parametrize("metadata", ["safety", "safety_summary", "approval_required"])
def test_present_malformed_metadata_mapping_cannot_offer_local_execution(invalid, metadata):
    report = produced_wake_report()
    report["bounded_executor_handoff"][metadata] = invalid
    result = controller_for({"goal": report["goal"]}, report["bounded_executor_handoff"])
    assert result["action_type"] == "human_review"
    assert result["reason_code"] == "invalid_safety_evidence"
    assert result["local_runner_available"] is False
    assert result["productive_executor_available"] is False
    assert result["invalid_evidence_fields"] == [f"bounded_executor_handoff.{metadata}"]


@pytest.mark.parametrize("flag", ["credentials", "broker", "runtime_launch", "file_writes"])
def test_non_boolean_known_flags_are_not_truthy_or_silently_ignored(flag):
    report = produced_wake_report()
    report["bounded_executor_handoff"]["safety"][flag] = {"payload": "inert-malformed-value"}
    result = controller_for({"goal": report["goal"]}, report["bounded_executor_handoff"])
    assert result["reason_code"] == "invalid_safety_evidence"
    assert result["invalid_evidence_fields"] == [f"bounded_executor_handoff.safety.{flag}"]
    assert "inert-malformed-value" not in json.dumps(result)


def test_malformed_approval_flag_does_not_offer_approval_gated_execution():
    report = produced_wake_report()
    report["bounded_executor_handoff"]["approval_required"]["human_review_before_local_apply"] = "false"
    result = controller_for({"goal": report["goal"]}, report["bounded_executor_handoff"])
    assert result["reason_code"] == "invalid_safety_evidence"
    assert result["invalid_evidence_fields"] == ["bounded_executor_handoff.approval_required.human_review_before_local_apply"]
    assert result["productive_executor_available"] is False
    assert result["local_runner_available"] is False


def test_legacy_checkpoint_is_rejected_without_rewriting_original_bytes(tmp_path):
    report = produced_wake_report()
    resume = load_module().build_resume_state(report)
    resume["bounded_executor_handoff"]["safety"]["credentials"] = "[redacted]"
    path = tmp_path / "legacy-checkpoint.json"
    original = json.dumps(resume, sort_keys=True).encode("utf-8")
    path.write_bytes(original)
    loaded = json.loads(path.read_bytes())
    result = controller_for(loaded, loaded["bounded_executor_handoff"])
    assert result["reason_code"] == "invalid_safety_evidence"
    assert result["safety"]["credentials"] is False
    assert result["sos_required"] is False
    assert path.read_bytes() == original


def test_unrelated_executor_support_and_authority_controls_survive_round_trip(tmp_path):
    report = produced_wake_report("forex_paper_execution_simulator")
    loaded = save_and_reload(tmp_path, report)
    result = controller_for(loaded, loaded["bounded_executor_handoff"])
    assert result["action_type"] == "build_executor_support_packet"
    assert result["reason_code"] == "productive_executor_support_missing"
    assert result["productive_executor_available"] is False
    assert result["execution_authority_granted"] is False
    assert result["approval_required"]["human_review"] is True
    assert result["approval_required"]["commit"] is True
    assert result["approval_required"]["push"] is True
    assert result["approval_required"]["merge"] is True



def test_distinct_same_second_checkpoints_do_not_clobber_each_other(tmp_path):
    module = load_module()
    moment = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
    first = module.write_resume_state(tmp_path, module.build_resume_state(wake_report()), generated_at_utc=moment)
    first_path = tmp_path / first["resume_state_paths"]["timestamped"]
    original = first_path.read_bytes()
    changed = wake_report()
    changed["selected_action"] = "validate_all_forex_with_risk_controls"
    second = module.write_resume_state(tmp_path, module.build_resume_state(changed), generated_at_utc=moment)
    assert first["resume_state_paths"]["timestamped"] != second["resume_state_paths"]["timestamped"]
    assert first_path.read_bytes() == original
    assert json.loads((tmp_path / second["resume_state_paths"]["latest"]).read_bytes())["selected_action"] == "validate_all_forex_with_risk_controls"


def test_identical_retry_reuses_immutable_checkpoint_across_seconds(tmp_path):
    module = load_module()
    resume = module.build_resume_state(wake_report())
    first = module.write_resume_state(tmp_path, resume, generated_at_utc=datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc))
    original = (tmp_path / first["resume_state_paths"]["timestamped"]).read_bytes()
    retry = module.write_resume_state(tmp_path, resume, generated_at_utc=datetime(2026, 10, 17, 12, 0, 1, tzinfo=timezone.utc))
    assert retry["resume_state_paths"] == first["resume_state_paths"]
    assert (tmp_path / retry["resume_state_paths"]["latest"]).read_bytes() == original


def test_concurrent_distinct_checkpoint_saves_leave_complete_latest(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    module = load_module()
    moment = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)

    def save(number):
        report = wake_report()
        report["selected_action"] = f"attempt-{number}"
        return module.write_resume_state(tmp_path, module.build_resume_state(report), generated_at_utc=moment)

    with ThreadPoolExecutor(max_workers=4) as pool:
        saved = list(pool.map(save, range(8)))
    paths = {item["resume_state_paths"]["timestamped"] for item in saved}
    assert len(paths) == 8
    latest_bytes = (tmp_path / "Reports/aios_resume/AIOS_RESUME_STATE_latest.json").read_bytes()
    assert latest_bytes in {(tmp_path / path).read_bytes() for path in paths}
    assert json.loads(latest_bytes)["selected_action"] in {f"attempt-{number}" for number in range(8)}


def test_preview_write_refuses_before_changing_accepted_history(tmp_path, capsys):
    module = load_module()
    module.write_resume_state(tmp_path, module.build_resume_state(wake_report()), generated_at_utc=datetime(2020, 1, 1, tzinfo=timezone.utc))
    before = {path.name: path.read_bytes() for path in (tmp_path / "Reports/aios_resume").glob("*.json")}
    assert module.main(["--repo-root", str(tmp_path), "--write"]) == 2
    assert {path.name: path.read_bytes() for path in (tmp_path / "Reports/aios_resume").glob("*.json")} == before
    assert "preview" in capsys.readouterr().err.lower()


# Native component contract: explicit admission is required even for typed context.
def test_native_identity_requires_source_qualified_admission(tmp_path):
    module = load_module()
    with pytest.raises(ValueError, match="native_admission"):
        module.verify_execution_identity(tmp_path, {"identity_contract": "AIOS_NATIVE_EXECUTION_IDENTITY.v1"})


def test_unknown_identity_contract_never_falls_back_to_legacy(tmp_path):
    module = load_module()
    with pytest.raises(ValueError, match="identity_contract"):
        module.verify_execution_identity(tmp_path, {"identity_contract": "future"})


def test_native_history_requires_admission_before_owner_io(tmp_path):
    module = load_module()
    with pytest.raises(ValueError, match="native_admission"):
        module.load_native_requirement(tmp_path, output_dir="Reports/aios_resume", expected_request=None, admitted_context=None, native_admission_reader=None)


# Native owner fixtures are inert saved evidence only; no child is launched.
def _np_json(value):
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import canonical_json
    return canonical_json(value)


def _np_hash(value):
    import hashlib
    return hashlib.sha256(value).hexdigest()


def _np_snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _np_process(cycle, executable, argv, cwd, stdin):
    return dict(shape_valid=True, root_exit_confirmed=True, tree_exit_confirmed=True,
        drains_completed=True, stdin_completed=True, stdin_writer_joined=True,
        timed_out=False, startup_failed=False, process_error_present=False,
        stdout_truncated=False, stderr_truncated=False, retry_allowed=False,
        exit_code=0, child_exit_code=0, stdin_error_code=0, stdin_close_error_code=0,
        cleanup_error_code=0, cancellation_error_code=0, root_process_id=123,
        stdin_bytes_written=len(stdin.encode("utf-8")), duration_sec=0.01,
        cleanup_state="CONFIRMED", executable=str(executable), arguments=argv,
        command_line_arguments=cycle._native_windows_arguments(argv), working_directory=str(cwd))


def _np_case(root, monkeypatch, task="A", lookup=None):
    import base64
    import shutil
    from pathlib import Path
    from automation.orchestration import aios_resume_state as owner, aios_wake_continue as wake
    from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1 as cycle
    from automation.orchestration.relay import aios_codex_prompt_consumer_v1 as consumer
    from automation.orchestration.aios_abcd_autonomy_runner import _acceptance_request
    from automation.orchestration.claims.aios_task_claim_control import normalize_claim, _claim_contract, SCHEMA_VERSION
    assert hasattr(cycle, "NativeRequirementContext"), "native component context API is absent"
    root = root.resolve(); root.mkdir(parents=True, exist_ok=True)
    source_root = Path(__file__).resolve().parents[2]
    relatives = set(consumer.BOUND_IMPLEMENTATIONS)
    relatives |= {"automation/orchestration/" + name for name in owner.SOURCE_FILES}
    relatives |= {"automation/orchestration/aios_abcd_autonomy_runner.py",
                  "automation/orchestration/claims/aios_task_claim_control.py"}
    for relative in relatives:
        destination = root / relative; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / relative, destination)
    manifest = {relative: _np_hash((root / relative).read_bytes()) for relative in sorted(relatives)}
    target = root / "safe/file.py"; target.parent.mkdir(exist_ok=True)
    if not target.exists(): target.write_bytes(b"original dirty fixture\n")
    before_bytes = target.read_bytes()
    before = {"safe/file.py": _np_hash(before_bytes)}
    provider = root / "bin/codex.exe"; provider.parent.mkdir(exist_ok=True)
    provider.write_bytes(b"inert provider fixture; never executable work")
    policy = root / "owned-policy.json"; policy.write_bytes(b'{"cost_ceiling_per_cycle_usd":1,"cost_ceiling_per_day_usd":10}')
    manifest["owned-policy.json"] = _np_hash(policy.read_bytes())
    validator_root = root / "validation" / task; validator_root.mkdir(parents=True)
    script = validator_root / "test_contract.py"; script.write_bytes(b"def test_result():\n    assert True\n")
    config = validator_root / "pytest.ini"; config.write_bytes(b"[pytest]\njunit_family=xunit2\n")
    producer = validator_root / "owned_producer.py"; producer.write_bytes(b"# inert parser-provenance fixture; not launched\n")
    receipt = validator_root / "pytest.xml"
    descriptor = dict(schema="AIOS_PYTEST_JUNIT_REQUIREMENT.v1", validator_id="owned-native-"+task,
        executable=str(provider), executable_sha256=_np_hash(provider.read_bytes()),
        argv=["-B", "-m", "pytest", "-c", str(config), "--noconftest", "-p", "no:cacheprovider",
              "--junitxml="+str(receipt), "test_contract.py::test_result"],
        cwd=str(validator_root), environment={"PYTHONDONTWRITEBYTECODE":"1"},
        stdin_utf8="", stdin_byte_count=0, receipt_path=str(receipt), receipt_max_bytes=1048576,
        required_cases=[{"node_id":"test_contract.py::test_result","classname":"test_contract","name":"test_result"}],
        required_counts={"tests":1,"failures":0,"errors":0,"skipped":0},
        result_contract="exact-case-set-and-all-pass",
        input_manifest={str(script):_np_hash(script.read_bytes()),str(config):_np_hash(config.read_bytes())},
        observed_producer_sources={str(producer):_np_hash(producer.read_bytes())})
    claim = dict(schema_version=SCHEMA_VERSION, task_id=task, packet_id="PACKET-"+task,
        repository="ai-rtony91/Ai_Os-Forex",supervisor="owner-fixture",worker="fixture",
        worktree=str(root),branch="codex/fixture",base_branch="main",base_sha="a"*40,
        claimed_paths=["safe/file.py"],ports=[],processes_or_services=[],containers=[],cache_dirs=[],
        temp_dirs=[],log_dirs=[],env_files=[],databases_or_schemas=[],deployment_targets=[],pull_request="",
        state="ACTIVE",acquired_at="2026-10-17T14:00:00+00:00",heartbeat_at="2026-10-17T14:00:00+00:00",
        expires_at="2099-10-17T14:00:00+00:00",cleanup_policy="owned fixture only",
        receipt_path=str(root / "claims" / (task+".json")),attempt_id="attempt-"+task,attempt=0)
    claim = normalize_claim(claim)
    node = {"id":task,"packet_id":"PACKET-"+task,"state":"QUEUED","depends_on":[],"attempt":0,"max_attempts":3,"priority":"P1"}
    queue_item = {"packet_id":"PACKET-"+task,"depends_on":[],"attempt":0,"max_attempts":3,"mission":"owned native requirement"}
    selected = _acceptance_request(node, queue_item, claim)
    prompt = root / "prompts" / (task+".md"); prompt.parent.mkdir(exist_ok=True)
    prompt.write_text("CODEX-ONLY PROMPT\nAI_OS EXECUTION TOKEN\nAI_OS BOOTSTRAP REQUIRED\nIDENTITY MARKER: owned fixture\nSUPERVISOR IDENTITY: owner\nWORKER IDENTITY: codex\nPACKET ID: PACKET-"+task+"\nMODE: APPLY\nZONE: LOCAL\nLANE: FIXTURE\nALLOWED PATHS\n- safe/file.py\nFORBIDDEN PATHS\n- AGENTS.md\nAPPROVAL AUTHORITY\nOwned source fixture only\nVALIDATOR CHAIN\nowned validator\nSTOP POINT\nEnd fixture\nMISSION\nOwned native fixture\nPREFLIGHT\nsource only\nFINAL REPORT FORMAT\nstatus\n",encoding="utf-8")
    request = dict(schema="AIOS_RELAY_REQUEST.v1",campaign_id="owned-native",repository="ai-rtony91/Ai_Os-Forex",
        repository_id="1227385337",repo_root=str(root),relay_root=str(root/"relay/owned-native"),
        repository_identity={"resolved":True,"repo_root":str(root),"git_dir":str(root/".git"),"branch":"codex/fixture","commit":"a"*40},
        task_id=task,packet_id="PACKET-"+task,priority="P1",depends_on=[],attempt_id="attempt-"+task,
        attempt_number=0,max_attempts=3,claim_ref={"owner":"TaskClaimController","task_id":task,
            "acquired_at":claim["acquired_at"],"identity_sha256":_claim_contract(claim)},
        prompt_path=str(prompt),prompt_sha256=_np_hash(prompt.read_bytes()),
        allowed_paths=["safe/file.py"],source_paths=["safe/file.py",*manifest],
        controller_metadata_paths=["owned-policy.json"],source_manifest=manifest,
        source_manifest_sha256=_np_hash(_np_json(manifest)),validator_spec_sha256=_np_hash(_np_json(descriptor)),
        provider="codex",provider_executable=str(provider),provider_sha256=_np_hash(provider.read_bytes()),
        provider_args=["--no-daemon","exec","--sandbox","workspace-write","-"],
        python_executable=str(Path(__import__('sys').executable).resolve()),timeout_sec=5,cycle_id="owned-native",policy_path=str(policy))
    request['preservation_contract'] = consumer.build_preservation_contract(request)
    # Exact accepted v1 producer is exercised against an owned tree, never Worker.
    enqueued = consumer.enqueue_prompt(prompt, Path(request["relay_root"]),
        {name:False for name in consumer.PROTECTED_FLAGS},bound_request=request)
    packet = enqueued["task"]; binding = consumer.request_binding(request,packet["request_sha256"])
    outbox = Path(request["relay_root"])/"outbox"; outbox.mkdir(parents=True, exist_ok=True)
    launch_path = outbox/(packet["id"]+".launch.json"); capture_path = outbox/(packet["id"]+".execution.json")
    launch = dict(schema="AIOS_RELAY_LAUNCH_OBSERVATION.v1",binding=binding,request_json=packet["request_json"],
        packet_sha256=enqueued["packet_sha256"],started_at="2026-10-17T14:01:00+00:00",authority_granted=False)
    launch_bytes = _np_json(launch)+b"\n"; launch_path.write_bytes(launch_bytes)
    raw_status = b"## codex/fixture\0 M safe/file.py\0"
    status = {"raw_base64":base64.b64encode(raw_status).decode("ascii"),"sha256":_np_hash(raw_status),"paths":["safe/file.py"]}
    capture_before = {**before, capture_path.relative_to(root).as_posix():None,
        launch_path.relative_to(root).as_posix():_np_hash(launch_bytes)}
    process = _np_process(cycle,provider,request["provider_args"],root,packet["prompt_text"])
    capture = dict(schema="AIOS_RELAY_EXECUTION.v1",binding=binding,request_json=packet["request_json"],
        packet_sha256=enqueued["packet_sha256"],started_at=launch["started_at"],ended_at="2026-10-17T14:02:00+00:00",
        process=process,controller_capture_contract={"path":capture_path.relative_to(root).as_posix(),"required_before":None,"write_mode":"CreateNew"},
        before_manifest=capture_before,before_status_paths=["safe/file.py"],authority_granted=False,retry_allowed=False)
    capture_bytes = _np_json(capture)+b"\n"; capture_path.write_bytes(capture_bytes)
    target.write_text("validated native output "+task+"\n",encoding="utf-8")
    after = {"safe/file.py":_np_hash(target.read_bytes())}
    observation = dict(schema="AIOS_RELAY_OBSERVATION.v1",repo_root=str(root),relay_root=request["relay_root"],
        status="EXECUTED_AWAITING_VALIDATION",reason="fixture",authority_granted=False,retry_allowed=False,
        execution_path=str(capture_path),execution_sha256=_np_hash(capture_bytes),**binding)
    observation_bytes = _np_json(observation)+b"\n"
    observation_path = outbox/(packet["id"]+".result."+_np_hash(observation_bytes)+".json"); observation_path.write_bytes(observation_bytes)
    def evidence(path):
        raw=path.read_bytes()
        return {"path":str(path),"sha256":_np_hash(raw),"utf8":raw.decode("utf-8")}
    requested = dict(state_path="Reports/owned-native-state.json",write_resume=True,
        resume_dir="Reports/aios_resume/owned-native",write_control=True,
        control_dir="Reports/aios_control_plane/owned-native",emit_continuation_controller=False)
    data = dict(schema="AIOS_NATIVE_REQUIREMENT_CONTEXT.v1",dispatch_item=node,queue_item=queue_item,claim=claim,
        request_json=packet["request_json"],evidence={"packet":evidence(Path(enqueued["target"])),
            "observation":evidence(observation_path),"launch":evidence(launch_path),"capture":evidence(capture_path)},
        implementation_manifest=manifest,descriptor=descriptor,descriptor_sha256=request["validator_spec_sha256"],
        task_before=before,task_after=after,status={"before":status,"after":dict(status),
            "parser_sha256":manifest["automation/orchestration/aios_repo_state_evidence.py"]},
        requested=requested,host={"executable":str(provider),"sha256":_np_hash(provider.read_bytes()),
            "timeout_sec":5,"maximum_output_characters":1048576},
        original_resolver_packet={"packet_id":"PACKET-"+task,"codex_prompt_text":packet["prompt_text"]})
    xml=b'<testsuites name="pytest tests"><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="test_contract" name="test_result" time="0"/></testsuite></testsuites>'
    receipt.write_bytes(xml)
    validation=dict(schema="AIOS_NATIVE_REQUIREMENT_RESULT.v1",descriptor_sha256=data["descriptor_sha256"],
        process=_np_process(cycle,provider,descriptor["argv"],validator_root,""),
        receipt_utf8=xml.decode("utf-8"),receipt_sha256=_np_hash(xml),
        summary={"tests":1,"failures":0,"errors":0,"skipped":0,"cases":[{"classname":"test_contract","name":"test_result"}]})
    lookup = {} if lookup is None else lookup
    context=cycle.NativeRequirementContext(selected,_np_json(data).decode("ascii"));lookup[selected]=context
    def reader(expected):
        if expected not in lookup: raise ValueError("owned admission absent")
        return lookup[expected]
    monkeypatch.setattr(wake,"resume_owner",lambda:owner)
    return dict(root=root,owner=owner,wake=wake,cycle=cycle,data=data,context=context,reader=reader,
        lookup=lookup,validation=validation,requested=requested,target=target,task_before_bytes=before_bytes)


def _np_capture(case):
    return case["wake"].capture_native_finalization(case["root"],admitted_context=case["context"],
        validation_record=case["validation"],requested=case["requested"],native_admission_reader=case["reader"])


def _np_recover(case, attempt):
    return case["wake"].recover_native_finalization(case["root"],attempt,admitted_context=case["context"],
        native_admission_reader=case["reader"])


def _np_read(case):
    return case["owner"].load_native_requirement(case["root"],output_dir=case["requested"]["resume_dir"],
        expected_request=case["context"].request,admitted_context=case["context"],native_admission_reader=case["reader"])


def _np_admit_mutation(case, change):
    from copy import deepcopy
    data=deepcopy(case["data"]);change(data)
    context=case["cycle"].NativeRequirementContext(case["context"].request,_np_json(data).decode("ascii"))
    return context, lambda request: context if request == context.request else (_ for _ in ()).throw(ValueError("absent"))


def test_native_owner_exact_saved_fixture_roundtrip(tmp_path, monkeypatch):
    case=_np_case(tmp_path,monkeypatch)
    identity=case["cycle"].native_execution_identity(tmp_path,case["context"],case["validation"],native_admission_reader=case["reader"])
    assert identity["task_id"]=="A" and identity["attempt_id"]=="attempt-A"
    assert "goal" not in identity and "selected_action" not in identity
    attempt=_np_capture(case);result=_np_recover(case,attempt)
    assert result["result"]=="COMPLETE"
    assert _np_read(case)["execution_identity"]==identity


@pytest.mark.parametrize("field,value",[("attempt_number",False),("attempt_number",0.0),("task_id",["A"]),
    ("attempt_id",1),("context_sha256",["a"*64]),("successful_result_sha256",True)])
def test_native_owner_identity_raw_aliases_reject(tmp_path,monkeypatch,field,value):
    case=_np_case(tmp_path,monkeypatch)
    identity=case["cycle"].native_execution_identity(tmp_path,case["context"],case["validation"],native_admission_reader=case["reader"])
    identity[field]=value
    before=_np_snapshot(tmp_path)
    with pytest.raises(ValueError):
        case["owner"].verify_execution_identity(tmp_path,identity,admitted_context=case["context"],native_admission_reader=case["reader"])
    assert _np_snapshot(tmp_path)==before


@pytest.mark.parametrize("kind",["selection","after","status_digest","status_endpoints","capture_digest","descriptor_digest","missing_source"])
def test_native_owner_cross_evidence_changes_reject(tmp_path,monkeypatch,kind):
    case=_np_case(tmp_path,monkeypatch)
    def change(data):
        if kind=="selection":data["dispatch_item"]["attempt"]=1
        elif kind=="after":data["task_after"]["safe/file.py"]="f"*64
        elif kind=="status_digest":data["status"]["after"]["sha256"]="f"*64
        elif kind=="status_endpoints":data["status"]["after"]["paths"]=[]
        elif kind=="capture_digest":data["evidence"]["capture"]["sha256"]="f"*64
        elif kind=="descriptor_digest":data["descriptor_sha256"]="f"*64
        else:data["implementation_manifest"].pop("automation/orchestration/aios_wake_continue.py")
    context,reader=_np_admit_mutation(case,change)
    with pytest.raises(ValueError):
        case["cycle"].native_execution_identity(tmp_path,context,case["validation"],native_admission_reader=reader)


def test_native_history_A_B_C_rechecks_each_lookup_and_preserves_latest(tmp_path,monkeypatch):
    lookup={};cases=[]
    for task in ("A","B","C"):
        case=_np_case(tmp_path,monkeypatch,task,lookup);assert _np_recover(case,_np_capture(case))["result"]=="COMPLETE";cases.append(case)
    before=_np_snapshot(tmp_path)
    for case in cases:assert _np_read(case)["execution_identity"]["task_id"]==case["context"].request.task_id
    assert _np_snapshot(tmp_path)==before
    lookup.pop(cases[-1]["context"].request)
    with pytest.raises(ValueError):_np_read(cases[0])
    assert _np_snapshot(tmp_path)==before


@pytest.mark.parametrize("corruption",["completion_subset","snapshot","coordinated","pending","attempt"])
def test_native_history_corruption_rejects_without_writes(tmp_path,monkeypatch,corruption):
    case=_np_case(tmp_path,monkeypatch);attempt=_np_capture(case);state=_np_recover(case,attempt)["resume_state"]
    from pathlib import Path
    owner=case["owner"];archive=tmp_path/state["resume_state_paths"]["timestamped"]
    completion=archive.with_name(archive.stem+".completion.json");receipt=json.loads(completion.read_bytes())
    if corruption=="completion_subset":receipt["outputs"].pop();completion.write_bytes(_np_json(receipt))
    elif corruption in {"snapshot","coordinated"}:
        output=receipt["outputs"][0];snapshot=tmp_path/output["snapshot"];snapshot.write_bytes(b'{"changed":true}\n')
        if corruption=="coordinated":output["sha256"]=_np_hash(snapshot.read_bytes());completion.write_bytes(_np_json(receipt))
    elif corruption=="pending":(tmp_path/state["publication"]["pending_checkpoint"]).write_bytes(b"{}")
    else:Path(attempt).write_bytes(b"{}")
    before=_np_snapshot(tmp_path)
    with pytest.raises(ValueError):_np_read(case)
    assert _np_snapshot(tmp_path)==before


def test_native_owner_immutable_source_change_blocks_same_attempt(tmp_path,monkeypatch):
    case=_np_case(tmp_path,monkeypatch)
    (tmp_path/"automation/orchestration/aios_repo_state_evidence.py").write_bytes(b"# changed source\n")
    before=_np_snapshot(tmp_path)
    with pytest.raises(ValueError):_np_capture(case)
    assert _np_snapshot(tmp_path)==before


def _np_case_c1(root, monkeypatch, task="A", lookup=None, *, descriptor_override=None, host_override=None):
    import base64
    import shutil
    from pathlib import Path
    from automation.orchestration import aios_resume_state as owner, aios_wake_continue as wake
    from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1 as cycle
    from automation.orchestration.relay import aios_codex_prompt_consumer_v1 as consumer
    from automation.orchestration.aios_abcd_autonomy_runner import _acceptance_request
    from automation.orchestration.claims.aios_task_claim_control import normalize_claim, _claim_contract, SCHEMA_VERSION
    assert hasattr(cycle, "NativeRequirementContext"), "native component context API is absent"
    root = root.resolve(); root.mkdir(parents=True, exist_ok=True)
    source_root = Path(__file__).resolve().parents[2]
    relatives = set(consumer.BOUND_IMPLEMENTATIONS)
    relatives |= {"automation/orchestration/" + name for name in owner.SOURCE_FILES}
    relatives |= {"automation/orchestration/aios_abcd_autonomy_runner.py",
                  "automation/orchestration/claims/aios_task_claim_control.py"}
    for relative in relatives:
        destination = root / relative; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / relative, destination)
    manifest = {relative: _np_hash((root / relative).read_bytes()) for relative in sorted(relatives)}
    target = root / "safe/file.py"; target.parent.mkdir(exist_ok=True)
    if not target.exists(): target.write_bytes(b"original dirty fixture\n")
    before_bytes = target.read_bytes()
    before = {"safe/file.py": _np_hash(before_bytes)}
    provider = root / "bin/codex.exe"; provider.parent.mkdir(exist_ok=True)
    provider.write_bytes(b"inert provider fixture; never executable work")
    policy = root / "owned-policy.json"; policy.write_bytes(b'{"cost_ceiling_per_cycle_usd":1,"cost_ceiling_per_day_usd":10}')
    manifest["owned-policy.json"] = _np_hash(policy.read_bytes())
    validator_root = root / "validation" / task; validator_root.mkdir(parents=True)
    script = validator_root / "test_contract.py"; script.write_bytes(b"def test_result():\n    assert True\n")
    config = validator_root / "pytest.ini"; config.write_bytes(b"[pytest]\njunit_family=xunit2\n")
    producer = validator_root / "owned_producer.py"; producer.write_bytes(b"# inert parser-provenance fixture; not launched\n")
    receipt = validator_root / "pytest.xml"
    descriptor = dict(schema="AIOS_PYTEST_JUNIT_REQUIREMENT.v1", validator_id="owned-native-"+task,
        executable=str(provider), executable_sha256=_np_hash(provider.read_bytes()),
        argv=["-B", "-m", "pytest", "-c", str(config), "--noconftest", "-p", "no:cacheprovider",
              "--junitxml="+str(receipt), "test_contract.py::test_result"],
        cwd=str(validator_root), environment={"PYTHONDONTWRITEBYTECODE":"1"},
        stdin_utf8="", stdin_byte_count=0, receipt_path=str(receipt), receipt_max_bytes=1048576,
        required_cases=[{"node_id":"test_contract.py::test_result","classname":"test_contract","name":"test_result"}],
        required_counts={"tests":1,"failures":0,"errors":0,"skipped":0},
        result_contract="exact-case-set-and-all-pass",
        input_manifest={str(script):_np_hash(script.read_bytes()),str(config):_np_hash(config.read_bytes())},
        observed_producer_sources={str(producer):_np_hash(producer.read_bytes())})
    if descriptor_override is not None:
        from copy import deepcopy
        descriptor = deepcopy(descriptor_override)
    claim = dict(schema_version=SCHEMA_VERSION, task_id=task, packet_id="PACKET-"+task,
        repository="ai-rtony91/Ai_Os-Forex",supervisor="owner-fixture",worker="fixture",
        worktree=str(root),branch="codex/fixture",base_branch="main",base_sha="a"*40,
        claimed_paths=["safe/file.py"],ports=[],processes_or_services=[],containers=[],cache_dirs=[],
        temp_dirs=[],log_dirs=[],env_files=[],databases_or_schemas=[],deployment_targets=[],pull_request="",
        state="ACTIVE",acquired_at="2026-10-17T14:00:00+00:00",heartbeat_at="2026-10-17T14:00:00+00:00",
        expires_at="2099-10-17T14:00:00+00:00",cleanup_policy="owned fixture only",
        receipt_path=str(root / "claims" / (task+".json")),attempt_id="attempt-"+task,attempt=0)
    claim = normalize_claim(claim)
    node = {"id":task,"packet_id":"PACKET-"+task,"state":"QUEUED","depends_on":[],"attempt":0,"max_attempts":3,"priority":"P1"}
    queue_item = {"packet_id":"PACKET-"+task,"depends_on":[],"attempt":0,"max_attempts":3,"mission":"owned native requirement"}
    selected = _acceptance_request(node, queue_item, claim)
    prompt = root / "prompts" / (task+".md"); prompt.parent.mkdir(exist_ok=True)
    prompt.write_text("CODEX-ONLY PROMPT\nAI_OS EXECUTION TOKEN\nAI_OS BOOTSTRAP REQUIRED\nIDENTITY MARKER: owned fixture\nSUPERVISOR IDENTITY: owner\nWORKER IDENTITY: codex\nPACKET ID: PACKET-"+task+"\nMODE: APPLY\nZONE: LOCAL\nLANE: FIXTURE\nALLOWED PATHS\n- safe/file.py\nFORBIDDEN PATHS\n- AGENTS.md\nAPPROVAL AUTHORITY\nOwned source fixture only\nVALIDATOR CHAIN\nowned validator\nSTOP POINT\nEnd fixture\nMISSION\nOwned native fixture\nPREFLIGHT\nsource only\nFINAL REPORT FORMAT\nstatus\n",encoding="utf-8")
    request = dict(schema="AIOS_RELAY_REQUEST.v1",campaign_id="owned-native",repository="ai-rtony91/Ai_Os-Forex",
        repository_id="1227385337",repo_root=str(root),relay_root=str(root/"relay/owned-native"),
        repository_identity={"resolved":True,"repo_root":str(root),"git_dir":str(root/".git"),"branch":"codex/fixture","commit":"a"*40},
        task_id=task,packet_id="PACKET-"+task,priority="P1",depends_on=[],attempt_id="attempt-"+task,
        attempt_number=0,max_attempts=3,claim_ref={"owner":"TaskClaimController","task_id":task,
            "acquired_at":claim["acquired_at"],"identity_sha256":_claim_contract(claim)},
        prompt_path=str(prompt),prompt_sha256=_np_hash(prompt.read_bytes()),
        allowed_paths=["safe/file.py"],source_paths=["safe/file.py",*manifest],
        controller_metadata_paths=["owned-policy.json"],source_manifest=manifest,
        source_manifest_sha256=_np_hash(_np_json(manifest)),validator_spec_sha256=_np_hash(_np_json(descriptor)),
        provider="codex",provider_executable=str(provider),provider_sha256=_np_hash(provider.read_bytes()),
        provider_args=["--no-daemon","exec","--sandbox","workspace-write","-"],
        python_executable=str(Path(__import__('sys').executable).resolve()),timeout_sec=5,cycle_id="owned-native",policy_path=str(policy))
    request['preservation_contract'] = consumer.build_preservation_contract(request)
    # Exact accepted v1 producer is exercised against an owned tree, never Worker.
    enqueued = consumer.enqueue_prompt(prompt, Path(request["relay_root"]),
        {name:False for name in consumer.PROTECTED_FLAGS},bound_request=request)
    packet = enqueued["task"]; binding = consumer.request_binding(request,packet["request_sha256"])
    outbox = Path(request["relay_root"])/"outbox"; outbox.mkdir(parents=True, exist_ok=True)
    launch_path = outbox/(packet["id"]+".launch.json"); capture_path = outbox/(packet["id"]+".execution.json")
    launch = dict(schema="AIOS_RELAY_LAUNCH_OBSERVATION.v1",binding=binding,request_json=packet["request_json"],
        packet_sha256=enqueued["packet_sha256"],started_at="2026-10-17T14:01:00+00:00",authority_granted=False)
    launch_bytes = _np_json(launch)+b"\n"; launch_path.write_bytes(launch_bytes)
    raw_status = b"## codex/fixture\0 M safe/file.py\0"
    status = {"raw_base64":base64.b64encode(raw_status).decode("ascii"),"sha256":_np_hash(raw_status),"paths":["safe/file.py"]}
    capture_before = {**before, capture_path.relative_to(root).as_posix():None,
        launch_path.relative_to(root).as_posix():_np_hash(launch_bytes)}
    process = _np_process(cycle,provider,request["provider_args"],root,packet["prompt_text"])
    capture = dict(schema="AIOS_RELAY_EXECUTION.v1",binding=binding,request_json=packet["request_json"],
        packet_sha256=enqueued["packet_sha256"],started_at=launch["started_at"],ended_at="2026-10-17T14:02:00+00:00",
        process=process,controller_capture_contract={"path":capture_path.relative_to(root).as_posix(),"required_before":None,"write_mode":"CreateNew"},
        before_manifest=capture_before,before_status_paths=["safe/file.py"],authority_granted=False,retry_allowed=False)
    capture_bytes = _np_json(capture)+b"\n"; capture_path.write_bytes(capture_bytes)
    target.write_text("validated native output "+task+"\n",encoding="utf-8")
    after = {"safe/file.py":_np_hash(target.read_bytes())}
    observation = dict(schema="AIOS_RELAY_OBSERVATION.v1",repo_root=str(root),relay_root=request["relay_root"],
        status="EXECUTED_AWAITING_VALIDATION",reason="fixture",authority_granted=False,retry_allowed=False,
        execution_path=str(capture_path),execution_sha256=_np_hash(capture_bytes),**binding)
    observation_bytes = _np_json(observation)+b"\n"
    observation_path = outbox/(packet["id"]+".result."+_np_hash(observation_bytes)+".json"); observation_path.write_bytes(observation_bytes)
    def evidence(path):
        raw=path.read_bytes()
        return {"path":str(path),"sha256":_np_hash(raw),"utf8":raw.decode("utf-8")}
    requested = dict(state_path="Reports/owned-native-state.json",write_resume=True,
        resume_dir="Reports/aios_resume/owned-native",write_control=True,
        control_dir="Reports/aios_control_plane/owned-native",emit_continuation_controller=False)
    data = dict(schema="AIOS_NATIVE_REQUIREMENT_CONTEXT.v1",dispatch_item=node,queue_item=queue_item,claim=claim,
        request_json=packet["request_json"],evidence={"packet":evidence(Path(enqueued["target"])),
            "observation":evidence(observation_path),"launch":evidence(launch_path),"capture":evidence(capture_path)},
        implementation_manifest=manifest,descriptor=descriptor,descriptor_sha256=request["validator_spec_sha256"],
        task_before=before,task_after=after,status={"before":status,"after":dict(status),
            "parser_sha256":manifest["automation/orchestration/aios_repo_state_evidence.py"]},
        requested=requested,host={"executable":str(provider),"sha256":_np_hash(provider.read_bytes()),
            "timeout_sec":5,"maximum_output_characters":1048576},
        original_resolver_packet={"packet_id":"PACKET-"+task,"codex_prompt_text":packet["prompt_text"]})
    xml=b'<testsuites name="pytest tests"><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="test_contract" name="test_result" time="0"/></testsuite></testsuites>'
    if descriptor_override is None: receipt.write_bytes(xml)
    validation=dict(schema="AIOS_NATIVE_REQUIREMENT_RESULT.v1",descriptor_sha256=data["descriptor_sha256"],
        process=_np_process(cycle,provider,descriptor["argv"],validator_root,""),
        receipt_utf8=xml.decode("utf-8"),receipt_sha256=_np_hash(xml),
        summary={"tests":1,"failures":0,"errors":0,"skipped":0,"cases":[{"classname":"test_contract","name":"test_result"}]})
    if descriptor_override is not None: validation = None
    if host_override is not None:
        from copy import deepcopy
        data["host"] = deepcopy(host_override)
    lookup = {} if lookup is None else lookup
    context=cycle.NativeRequirementContext(selected,_np_json(data).decode("ascii"));lookup[selected]=context
    def reader(expected):
        if expected not in lookup: raise ValueError("owned admission absent")
        return lookup[expected]
    monkeypatch.setattr(wake,"resume_owner",lambda:owner)
    return dict(root=root,owner=owner,wake=wake,cycle=cycle,data=data,context=context,reader=reader,
        lookup=lookup,validation=validation,requested=requested,target=target,task_before_bytes=before_bytes)


# C2 extends the preserved C1 fixture; both versions remain available to causal probes.
def _np_case(root, monkeypatch, task="A", lookup=None, *, descriptor_override=None, host_override=None):
    import json
    from pathlib import Path
    from automation.orchestration import aios_repo_state_evidence as repo_evidence
    case = _np_case_c1(root, monkeypatch, task, lookup, descriptor_override=descriptor_override, host_override=host_override)
    data = case["data"]; request = json.loads(data["request_json"])
    root = case["root"]; relay = Path(request["relay_root"])
    selected = "bound-" + _np_hash(_np_json(request))
    slots = { (relay / folder / (selected + suffix)).relative_to(root).as_posix()
        for folder, suffix in (("inbox", ".task.json"), ("running", ".task.json"),
                               ("outbox", ".launch.json"), ("outbox", ".execution.json")) }
    slots |= {(relay / "logs" / filename).relative_to(root).as_posix()
        for filename in ("cost_ledger.jsonl", "preflight.log", "output_validator.log")}
    inventory = set(request["source_paths"]) | set(request["controller_metadata_paths"]) | slots
    capture_path = Path(data["evidence"]["capture"]["path"])
    capture_relative = capture_path.relative_to(root).as_posix()
    capture = json.loads(data["evidence"]["capture"]["utf8"])
    before = {relative: _np_hash((root / relative).read_bytes()) if (root / relative).is_file() else None
        for relative in sorted(inventory)}
    before.update(data["task_before"]); before[capture_relative] = None
    capture["before_manifest"] = before
    capture_raw = _np_json(capture) + b"\n"; capture_path.write_bytes(capture_raw)
    def evidence(path):
        raw = path.read_bytes()
        return {"path":str(path), "sha256":_np_hash(raw), "utf8":raw.decode("utf-8")}
    data["evidence"]["capture"] = evidence(capture_path)
    observation = json.loads(data["evidence"]["observation"]["utf8"])
    observation["execution_sha256"] = _np_hash(capture_raw)
    raw = _np_json(observation) + b"\n"
    observation_path = relay / "outbox" / (selected + ".result." + _np_hash(raw) + ".json")
    observation_path.write_bytes(raw)
    data["evidence"]["observation"] = evidence(observation_path)
    data["evidence"]["prompt"] = evidence(Path(request["prompt_path"]))
    after = dict(before); after.update(data["task_after"]); after[capture_relative] = _np_hash(capture_raw)
    data["after_manifest"] = after
    identity = {**request["repository_identity"], "detached":False}
    monkeypatch.setattr(repo_evidence, "collect_repo_identity", lambda actual_root: dict(identity)
        if Path(actual_root).resolve() == root else (_ for _ in ()).throw(ValueError("unknown owned repository")))
    context = case["cycle"].NativeRequirementContext(case["context"].request, _np_json(data).decode("ascii"))
    case["context"] = context; case["lookup"][context.request] = context
    return case



def _np_refresh(case):
    context = case["cycle"].NativeRequirementContext(case["context"].request, _np_json(case["data"]).decode("ascii"))
    case["context"] = context; case["lookup"][context.request] = context
    return case


def _np_reseal_saved(case, role, value):
    import json
    from pathlib import Path
    data=case["data"];root=case["root"]
    def save(name, payload, path=None):
        entry=data["evidence"][name];selected=Path(entry["path"] if path is None else path)
        raw=payload if type(payload) is bytes else _np_json(payload)+b"\n"
        selected.parent.mkdir(parents=True,exist_ok=True);selected.write_bytes(raw)
        data["evidence"][name]={"path":str(selected),"sha256":_np_hash(raw),"utf8":raw.decode("utf-8")}
        return raw
    raw=save(role,value)
    if role in {"packet","launch"}:
        capture=json.loads(data["evidence"]["capture"]["utf8"])
        if role=="packet":
            launch=json.loads(data["evidence"]["launch"]["utf8"])
            launch["packet_sha256"]=_np_hash(raw);save("launch",launch)
            capture["packet_sha256"]=_np_hash(raw)
            relative=Path(data["evidence"]["packet"]["path"]).relative_to(root).as_posix()
            if relative in capture["before_manifest"]:capture["before_manifest"][relative]=_np_hash(raw)
            if relative in data.get("after_manifest",{}):data["after_manifest"][relative]=_np_hash(raw)
        launch_relative=Path(data["evidence"]["launch"]["path"]).relative_to(root).as_posix()
        capture["before_manifest"][launch_relative]=data["evidence"]["launch"]["sha256"]
        if launch_relative in data.get("after_manifest",{}):data["after_manifest"][launch_relative]=data["evidence"]["launch"]["sha256"]
        save("capture",capture)
    if role in {"packet","launch","capture"}:
        capture_relative=Path(data["evidence"]["capture"]["path"]).relative_to(root).as_posix()
        if capture_relative in data.get("after_manifest",{}):data["after_manifest"][capture_relative]=data["evidence"]["capture"]["sha256"]
        observation=json.loads(data["evidence"]["observation"]["utf8"])
        observation["execution_sha256"]=data["evidence"]["capture"]["sha256"]
        raw=_np_json(observation)+b"\n"
        old=Path(data["evidence"]["observation"]["path"])
        selected=old.parent/(json.loads(data["evidence"]["packet"]["utf8"])["id"]+".result."+_np_hash(raw)+".json")
        save("observation",raw,selected)
    return _np_refresh(case)


def _np_status_evidence(paths):
    import base64
    raw=b"## codex/fixture\0"+b"".join(b" M "+name.encode("utf-8")+b"\0" for name in sorted(paths))
    return {"raw_base64":base64.b64encode(raw).decode("ascii"),"sha256":_np_hash(raw),"paths":sorted(paths)}


def test_native_archived_same_length_prompt_requires_original_raw_binding(tmp_path,monkeypatch):
    import json
    case=_np_case(tmp_path,monkeypatch)
    packet=json.loads(case["data"]["evidence"]["packet"]["utf8"])
    original=packet["prompt_text"];packet["prompt_text"]=original.replace("Owned native fixture","Owned native fixturE")
    assert packet["prompt_text"]!=original and len(packet["prompt_text"].encode("utf-8"))==len(original.encode("utf-8"))
    _np_reseal_saved(case,"packet",packet)
    before=_np_snapshot(tmp_path)
    with pytest.raises(ValueError):case["cycle"].native_execution_identity(tmp_path,case["context"],case["validation"],native_admission_reader=case["reader"],live=False)
    assert _np_snapshot(tmp_path)==before


@pytest.mark.parametrize("role",["packet","observation","launch","capture"])
def test_native_saved_role_nonobject_is_controlled_rejection(tmp_path,monkeypatch,role):
    case=_np_case(tmp_path,monkeypatch)
    entry=case["data"]["evidence"][role];raw=b"[]"
    entry.update(utf8=raw.decode("ascii"),sha256=_np_hash(raw));_np_refresh(case)
    before=_np_snapshot(tmp_path)
    with pytest.raises(ValueError):case["cycle"].native_execution_identity(tmp_path,case["context"],case["validation"],native_admission_reader=case["reader"],live=False)
    assert _np_snapshot(tmp_path)==before


@pytest.mark.parametrize("slot",["capture","launch","running"])
def test_native_exact_derived_status_slots_are_inspectable(tmp_path,monkeypatch,slot):
    import json
    from pathlib import Path
    case=_np_case(tmp_path,monkeypatch);data=case["data"]
    if slot=="running":
        packet=Path(data["evidence"]["packet"]["path"])
        selected=packet.parent.parent/"running"/packet.name;selected.parent.mkdir(exist_ok=True)
        selected.write_bytes(packet.read_bytes());relative=selected.relative_to(tmp_path).as_posix()
        capture=json.loads(data["evidence"]["capture"]["utf8"])
        capture["before_manifest"][relative]=_np_hash(selected.read_bytes())
        if "after_manifest" in data:data["after_manifest"][relative]=_np_hash(selected.read_bytes())
        _np_reseal_saved(case,"capture",capture)
        # This positive fixture adds a file before the example provider interval.
        # Rebuild both full-tree observations; never relax the production check.
        _p505_attach_interval(case, monkeypatch, {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()})
    else:relative=Path(data["evidence"][slot]["path"]).relative_to(tmp_path).as_posix()
    data["status"]["after"]=_np_status_evidence(["safe/file.py",relative]);_np_refresh(case)
    identity=case["cycle"].native_execution_identity(tmp_path,case["context"],case["validation"],native_admission_reader=case["reader"])
    assert identity["task_id"]=="A"


def test_native_guard_receives_task_delta_not_approved_dirty_baseline(tmp_path,monkeypatch):
    import json
    from automation.orchestration.claims.aios_task_claim_control import TaskClaimController
    case=_np_case(tmp_path,monkeypatch);data=case["data"]
    paths=["safe/file.py","automation/orchestration/aios_repo_state_evidence.py"]
    data["status"]["before"]=_np_status_evidence(paths);data["status"]["after"]=_np_status_evidence(paths)
    capture=json.loads(data["evidence"]["capture"]["utf8"]);capture["before_status_paths"]=sorted(paths)
    _np_reseal_saved(case,"capture",capture)
    decision={}
    def guard(*args,**kwargs):
        decision.update(kwargs)
        assert kwargs["changed_paths"]==["safe/file.py"]
        return data["claim"]
    controller=object.__new__(TaskClaimController);monkeypatch.setattr(TaskClaimController,"guard",guard)
    monkeypatch.setattr(case["owner"],"find_native_attempt",lambda *a,**k: (_ for _ in ()).throw(ValueError("owned probe after guard")))
    adapter=case["cycle"].make_native_execution_adapter(tmp_path,expected_request=case["context"].request,
        native_admission_reader=case["reader"],claim_controller=controller,requested=case["requested"])
    with pytest.raises(ValueError,match="owned probe after guard"):adapter(data["original_resolver_packet"])
    assert decision["head_is_descendant"] is True and decision["expected_claim"]==data["claim"]



def test_native_raw_prompt_CRLF_is_preserved_and_LF_stdin_bound(tmp_path,monkeypatch):
    import json
    case=_np_case(tmp_path,monkeypatch);data=case["data"]
    raw=data["evidence"]["prompt"]["utf8"].encode("utf-8")
    packet=json.loads(data["evidence"]["packet"]["utf8"])
    assert b"\r\n" in raw and "\r" not in packet["prompt_text"]
    identity=case["cycle"].native_execution_identity(tmp_path,case["context"],case["validation"],native_admission_reader=case["reader"])
    assert identity["prompt_binding"]=={"raw_sha256":_np_hash(raw),"text_sha256":_np_hash(packet["prompt_text"].encode("utf-8")),"stdin_byte_count":len(packet["prompt_text"].encode("utf-8"))}


@pytest.mark.parametrize("kind",["missing_after","missing_before","foreign_source_delta","wrong_capture_delta"])
def test_native_full_before_after_inventory_is_required(tmp_path,monkeypatch,kind):
    import json
    case=_np_case(tmp_path,monkeypatch);data=case["data"]
    source="automation/orchestration/aios_repo_state_evidence.py"
    if kind=="missing_after":data["after_manifest"].pop(source)
    elif kind=="missing_before":
        capture=json.loads(data["evidence"]["capture"]["utf8"]);capture["before_manifest"].pop(source)
        _np_reseal_saved(case,"capture",capture)
    elif kind=="foreign_source_delta":data["after_manifest"][source]="f"*64
    else:
        from pathlib import Path
        data["after_manifest"][Path(data["evidence"]["capture"]["path"]).relative_to(tmp_path).as_posix()]=None
    _np_refresh(case);before=_np_snapshot(tmp_path)
    with pytest.raises(ValueError):case["cycle"].native_execution_identity(tmp_path,case["context"],case["validation"],native_admission_reader=case["reader"])
    assert _np_snapshot(tmp_path)==before


@pytest.mark.parametrize("field,value",[("branch","foreign"),("commit","b"*40),("detached",True),("resolved",1)])
def test_native_current_repo_owner_identity_is_rechecked(tmp_path,monkeypatch,field,value):
    import json
    from automation.orchestration import aios_repo_state_evidence as repo_evidence
    case=_np_case(tmp_path,monkeypatch)
    actual={**json.loads(case["data"]["request_json"])["repository_identity"],"detached":False};actual[field]=value
    monkeypatch.setattr(repo_evidence,"collect_repo_identity",lambda root:dict(actual))
    before=_np_snapshot(tmp_path)
    with pytest.raises(ValueError):case["cycle"].native_execution_identity(tmp_path,case["context"],case["validation"],native_admission_reader=case["reader"])
    assert _np_snapshot(tmp_path)==before


# Existing ClaimError is a controlled source-contract rejection.
@pytest.mark.parametrize("kind",["selection","after","status_digest","status_endpoints","capture_digest","descriptor_digest","missing_source"])
def test_native_owner_cross_evidence_changes_reject(tmp_path,monkeypatch,kind):
    from automation.orchestration.claims.aios_task_claim_control import ClaimError
    case=_np_case(tmp_path,monkeypatch)
    def change(data):
        if kind=="selection":data["dispatch_item"]["attempt"]=1
        elif kind=="after":data["task_after"]["safe/file.py"]="f"*64
        elif kind=="status_digest":data["status"]["after"]["sha256"]="f"*64
        elif kind=="status_endpoints":data["status"]["after"]["paths"]=[]
        elif kind=="capture_digest":data["evidence"]["capture"]["sha256"]="f"*64
        elif kind=="descriptor_digest":data["descriptor_sha256"]="f"*64
        else:data["implementation_manifest"].pop("automation/orchestration/aios_wake_continue.py")
    context,reader=_np_admit_mutation(case,change)
    with pytest.raises((ValueError,ClaimError)):
        case["cycle"].native_execution_identity(tmp_path,context,case["validation"],native_admission_reader=reader)



def test_native_owner_immutable_source_change_blocks_same_attempt(tmp_path,monkeypatch):
    case=_np_case(tmp_path,monkeypatch)
    (tmp_path/"automation/orchestration/aios_repo_state_evidence.py").write_bytes(b"# changed source\n")
    before=_np_snapshot(tmp_path)
    with pytest.raises(ValueError):_np_capture(case)
    after=_np_snapshot(tmp_path)
    assert all(after.get(name)==raw for name,raw in before.items())
    added=set(after)-set(before)
    assert all(name.startswith(case["requested"]["resume_dir"]+"/") and
        (name.endswith("/.publication.lock") or "/AIOS_RESUME_FAILURE_" in name) for name in added)
    assert not any("AIOS_RESUME_ATTEMPT_" in name for name in added)


# C3 source-compatible fixture override; all earlier fixture definitions remain preserved.
def _np_process(cycle, executable, argv, cwd, stdin):
    return dict(shape_valid=True, root_exit_confirmed=True, tree_exit_confirmed=True,
        drains_completed=True, stdin_completed=True, stdin_writer_joined=True,
        timed_out=False, startup_failed=False, process_error_present=False,
        stdout_truncated=False, stderr_truncated=False, retry_allowed=True,
        exit_code=0, child_exit_code=0, stdin_error_code=0, stdin_close_error_code=0,
        cleanup_error_code=0, cancellation_error_code=0, root_process_id=123,
        stdin_bytes_written=len(stdin.encode("utf-8")), duration_sec=0.01,
        cleanup_state="CONFIRMED", executable=str(executable), arguments=argv,
        command_line_arguments=cycle._native_windows_arguments(argv), working_directory=str(cwd))


# C2 extends the preserved C1 fixture; both versions remain available to causal probes.
def _np_case(root, monkeypatch, task="A", lookup=None, *, descriptor_override=None, host_override=None):
    import json
    from pathlib import Path
    from automation.orchestration import aios_repo_state_evidence as repo_evidence
    case = _np_case_c1(root, monkeypatch, task, lookup, descriptor_override=descriptor_override, host_override=host_override)
    data = case["data"]; request = json.loads(data["request_json"])
    root = case["root"]; relay = Path(request["relay_root"])
    selected = "bound-" + _np_hash(_np_json(request))
    slots = { (relay / folder / (selected + suffix)).relative_to(root).as_posix()
        for folder, suffix in (("inbox", ".task.json"), ("running", ".task.json"),
                               ("outbox", ".launch.json"), ("outbox", ".execution.json")) }
    slots |= {(relay / "logs" / filename).relative_to(root).as_posix()
        for filename in ("cost_ledger.jsonl", "preflight.log", "output_validator.log")}
    inventory = set(request["source_paths"]) | set(request["controller_metadata_paths"]) | slots
    capture_path = Path(data["evidence"]["capture"]["path"])
    capture_relative = capture_path.relative_to(root).as_posix()
    capture = json.loads(data["evidence"]["capture"]["utf8"])
    before = {relative: _np_hash((root / relative).read_bytes()) if (root / relative).is_file() else None
        for relative in sorted(inventory)}
    before.update(data["task_before"]); before[capture_relative] = None
    capture["before_manifest"] = before
    capture_raw = _np_json(capture) + b"\n"; capture_path.write_bytes(capture_raw)
    def evidence(path):
        raw = path.read_bytes()
        return {"path":str(path), "sha256":_np_hash(raw), "utf8":raw.decode("utf-8")}
    data["evidence"]["capture"] = evidence(capture_path)
    observation = json.loads(data["evidence"]["observation"]["utf8"])
    observation["execution_sha256"] = _np_hash(capture_raw)
    observation["reason"] = "INDEPENDENT_ACCEPTANCE_REQUIRED"
    raw = _np_json(observation) + b"\n"
    observation_path = relay / "outbox" / (selected + ".result." + _np_hash(raw) + ".json")
    observation_path.write_bytes(raw)
    data["evidence"]["observation"] = evidence(observation_path)
    data["evidence"]["prompt"] = evidence(Path(request["prompt_path"]))
    after = dict(before); after.update(data["task_after"]); after[capture_relative] = _np_hash(capture_raw)
    data["after_manifest"] = after
    data["requested"]["write_control"] = False
    data["requested"]["emit_continuation_controller"] = False
    identity = {**request["repository_identity"], "detached":False}
    monkeypatch.setattr(repo_evidence, "collect_repo_identity", lambda actual_root: dict(identity)
        if Path(actual_root).resolve() == root else (_ for _ in ()).throw(ValueError("unknown owned repository")))
    # Only external Git input is doubled; source checks and process owners remain actual.
    def owned_git_status(actual_root, runner):
        import base64
        from subprocess import CompletedProcess
        from subprocess import run as expected_runner
        if Path(actual_root).resolve()!=root:raise ValueError("unknown owned Git status root")
        if runner is not expected_runner:raise ValueError("unexpected owned Git status runner")
        raw=base64.b64decode(data["status"]["after"]["raw_base64"],validate=True)
        return CompletedProcess(["git","--no-optional-locks","status","--porcelain=v1","-z","--branch","--untracked-files=all"],0,stdout=raw,stderr=b"")
    monkeypatch.setattr(repo_evidence,"_run_git_status",owned_git_status)
    context = case["cycle"].NativeRequirementContext(case["context"].request, _np_json(data).decode("ascii"))
    case["context"] = context; case["lookup"][context.request] = context
    return case



def _np_c3_case(root,monkeypatch):
    return _np_case(root,monkeypatch),globals()


def _np_c3_identity(case):
    return case["cycle"].native_execution_identity(case["root"],case["context"],case["validation"],native_admission_reader=case["reader"],live=False)


def _np_c3_pins(root):
    return {path.relative_to(root).as_posix():_np_hash(path.read_bytes()) for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("role,value",[(role,value) for role in ("provider","validator") for value in (False,0,1,[True],"true")])
def test_native_confirmed_process_retry_projection_requires_true_bool(tmp_path,monkeypatch,role,value):
    import json
    case=_np_case(tmp_path,monkeypatch)
    if role=="provider":
        capture=json.loads(case["data"]["evidence"]["capture"]["utf8"]);capture["process"]["retry_allowed"]=value
        _np_reseal_saved(case,"capture",capture)
    else:case["validation"]["process"]["retry_allowed"]=value
    before=_np_c3_pins(tmp_path)
    with pytest.raises(ValueError):_np_c3_identity(case)
    assert _np_c3_pins(tmp_path)==before


@pytest.mark.parametrize("field,value",[(field,value) for field in ("write_control","emit_continuation_controller") for value in (True,0,1,[],"false")]+[("write_resume",False),("write_resume",1)])
def test_native_initial_projection_profile_is_exact_before_effects(tmp_path,monkeypatch,field,value):
    case=_np_case(tmp_path,monkeypatch)
    case["data"]["requested"][field]=value;_np_refresh(case)
    before=_np_c3_pins(tmp_path)
    with pytest.raises(ValueError):_np_c3_identity(case)
    assert _np_c3_pins(tmp_path)==before


def test_native_packet_is_exact_unchanged_consumer_producer_bytes(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from automation.orchestration.relay import aios_codex_prompt_consumer_v1 as consumer
    case=_np_case(tmp_path,monkeypatch);data=case["data"];request=json.loads(data["request_json"])
    prompt=consumer.validate_prompt(Path(request["prompt_path"]))
    expected=consumer._enqueue_bound(prompt,Path(request["relay_root"]),{name:False for name in consumer.PROTECTED_FLAGS},request,True)
    actual=data["evidence"]["packet"]["utf8"].encode("utf-8")
    assert actual==consumer.canonical_json(expected["task"])+b"\n"
    assert data["evidence"]["packet"]["sha256"]==expected["packet_sha256"]
    assert _np_c3_identity(case)["task_id"]=="A"


# These twelve strict-role negatives preserve the independently resealed C2 failures.
def test_native_c3_strict_role_valid_control(tmp_path,monkeypatch):
    case,h=_np_c3_case(tmp_path,monkeypatch)
    assert _np_c3_identity(case)["task_id"]=="A"

@pytest.mark.parametrize("kind",["allowed_paths","tier","source_mode","extra","noncanonical_raw"])
def test_native_c3_complete_packet_bytes_required(tmp_path,monkeypatch,kind):
    case,h=_np_c3_case(tmp_path,monkeypatch);packet=json.loads(case["data"]["evidence"]["packet"]["utf8"])
    if kind=="allowed_paths":packet["allowed_paths"]=["safe/foreign.py"]
    elif kind=="tier":packet["tier"]="TIER_UNADMITTED"
    elif kind=="source_mode":packet["source_mode"]="UNADMITTED"
    elif kind=="extra":packet["unknown_field"]={"unadmitted":True}
    else:packet=json.dumps(packet,indent=2).encode("utf-8")+b"\n"
    h["_np_reseal_saved"](case,"packet",packet)
    before=h["_np_snapshot"](tmp_path)
    with pytest.raises(ValueError):_np_c3_identity(case)
    assert h["_np_snapshot"](tmp_path)==before

@pytest.mark.parametrize("role,field",[(role,field) for role in ("launch","capture","observation") for field in ("stdout","unknown_field")])
def test_native_c3_saved_envelope_unknown_fields_reject(tmp_path,monkeypatch,role,field):
    case,h=_np_c3_case(tmp_path,monkeypatch);saved=json.loads(case["data"]["evidence"][role]["utf8"])
    saved[field]="unadmitted raw content"
    if role=="observation":
        raw=h["_np_json"](saved)+b"\n";digest=h["_np_hash"](raw)
        packet=json.loads(case["data"]["evidence"]["packet"]["utf8"])
        target=Path(case["data"]["evidence"][role]["path"]).parent/(packet["id"]+".result."+digest+".json")
        target.write_bytes(raw)
        case["data"]["evidence"][role]={"path":str(target),"sha256":digest,"utf8":raw.decode("utf-8")};h["_np_refresh"](case)
    else:h["_np_reseal_saved"](case,role,saved)
    before=h["_np_snapshot"](tmp_path)
    with pytest.raises(ValueError):_np_c3_identity(case)
    assert h["_np_snapshot"](tmp_path)==before

def test_native_c3_started_at_raw_bool_integer_alias_reject(tmp_path,monkeypatch):
    case,h=_np_c3_case(tmp_path,monkeypatch)
    launch=json.loads(case["data"]["evidence"]["launch"]["utf8"]);launch["started_at"]=1
    h["_np_reseal_saved"](case,"launch",launch)
    capture=json.loads(case["data"]["evidence"]["capture"]["utf8"]);capture["started_at"]=True
    h["_np_reseal_saved"](case,"capture",capture)
    before=h["_np_snapshot"](tmp_path)
    with pytest.raises(ValueError):_np_c3_identity(case)
    assert h["_np_snapshot"](tmp_path)==before



def _np_c3_fresh_aggregate_case(root,monkeypatch):
    from pathlib import Path
    root=root.resolve();root.mkdir(parents=True,exist_ok=True)
    selected=root/"fresh-aggregate-validator";selected.mkdir()
    executable=selected/"inert-python.exe";executable.write_bytes(b"inert validator executable; never launched")
    script=selected/"test_contract.py";script.write_bytes(b"def test_result():\n    assert True\n")
    config=selected/"pytest.ini";config.write_bytes(b"[pytest]\njunit_family=xunit2\n")
    producer=selected/"owned_producer.py";producer.write_bytes(b"# owned inert producer; never launched\n")
    receipt=selected/"fresh-result.xml"
    descriptor=dict(schema="AIOS_PYTEST_JUNIT_REQUIREMENT.v1",validator_id="owned-fresh-aggregate",
        executable=str(executable),executable_sha256=_np_hash(executable.read_bytes()),
        argv=["-B","-m","pytest","-c",str(config),"--noconftest","-p","no:cacheprovider",
            "--junitxml="+str(receipt),"test_contract.py::test_result"],
        cwd=str(selected),environment={"PYTHONDONTWRITEBYTECODE":"1"},stdin_utf8="",stdin_byte_count=0,
        receipt_path=str(receipt),receipt_max_bytes=1048576,
        required_cases=[{"node_id":"test_contract.py::test_result","classname":"test_contract","name":"test_result"}],
        required_counts={"tests":1,"failures":0,"errors":0,"skipped":0},result_contract="exact-case-set-and-all-pass",
        input_manifest={str(script):_np_hash(script.read_bytes()),str(config):_np_hash(config.read_bytes())},
        observed_producer_sources={str(producer):_np_hash(producer.read_bytes())})
    assert not receipt.exists()
    case=_np_case(root,monkeypatch,descriptor_override=descriptor)
    assert case["data"]["descriptor"]==descriptor and case["validation"] is None and not receipt.exists()
    return case,receipt


@pytest.mark.parametrize("kind",["typed_exit","failed_exit","raw_output","host_loss"])
def test_native_aggregate_rejection_keeps_receipt_sanitized_failure_and_no_replay(tmp_path,monkeypatch,kind):
    import json
    from pathlib import Path
    case,receipt=_np_c3_fresh_aggregate_case(tmp_path,monkeypatch)
    cycle=case["cycle"];descriptor=case["data"]["descriptor"]
    xml=b'<testsuites name="pytest tests"><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="test_contract" name="test_result" time="0"/></testsuite></testsuites>'
    marker="OWNED_RAW_OUTPUT_MUST_NEVER_BE_PERSISTED"
    expected_process=_np_process(cycle,Path(descriptor["executable"]),descriptor["argv"],Path(descriptor["cwd"]),"")
    if kind=="typed_exit":expected_process["exit_code"]=False
    else:expected_process.update(exit_code=7,child_exit_code=7)
    if kind=="raw_output":expected_process.update(stdout=marker,stderr=marker,unadmitted_payload=marker)
    launches=[]
    def host(actual_root,data):
        launches.append(str(actual_root));assert data["descriptor"]==descriptor
        receipt.write_bytes(xml)
        if kind=="host_loss":raise OSError("owned host result unavailable")
        return dict(expected_process)
    monkeypatch.setattr(cycle,"_invoke_native_aggregate_host",host)
    assert not receipt.exists()
    with pytest.raises((ValueError,OSError)):
        cycle.run_native_aggregate_validator(case["context"],native_admission_reader=case["reader"])
    assert len(launches)==1 and receipt.read_bytes()==xml
    selected=tmp_path/case["requested"]["resume_dir"]
    assert not list(selected.glob("AIOS_RESUME_ATTEMPT_*.json"))
    failures=list(selected.glob("AIOS_RESUME_FAILURE_*.json"));assert len(failures)==1
    raw=failures[0].read_bytes();failure=json.loads(raw)
    assert failures[0].name=="AIOS_RESUME_FAILURE_"+_np_hash(raw)+".json"
    assert marker.encode("ascii") not in raw
    assert failure["schema"]=="AIOS_NATIVE_VALIDATION_FAILURE.v1" and failure["result"]=="BLOCKED" and failure["replay_allowed"] is False
    assert failure["validator_receipt"]=={"path":str(receipt),"sha256":_np_hash(xml),"size":len(xml),"read_error_type":None}
    evidence=failure["process_evidence"]
    if kind=="host_loss":
        assert evidence=={"available":False,"projection":None,"field_types":{},"projection_sha256":None}
    else:
        assert evidence["available"] is True and evidence["projection_sha256"]==_np_hash(_np_json(expected_process))
        known=set(_np_process(cycle,Path(descriptor["executable"]),descriptor["argv"],Path(descriptor["cwd"]),""))
        assert set(evidence["projection"])<=known and set(evidence["field_types"])<=known
        assert not {"stdout","stderr","unadmitted_payload"}&evidence["projection"].keys()
        if kind=="typed_exit":assert evidence["projection"]["exit_code"] is False and evidence["field_types"]["exit_code"]=="bool"
        else:assert evidence["projection"]["exit_code"]==7
    after_first=_np_c3_pins(tmp_path)
    with pytest.raises(ValueError,match="existing_receipt|no_replay"):
        cycle.run_native_aggregate_validator(case["context"],native_admission_reader=case["reader"])
    assert len(launches)==1 and receipt.read_bytes()==xml and _np_c3_pins(tmp_path)==after_first
    assert failures[0].read_bytes()==raw and not list(selected.glob("AIOS_RESUME_ATTEMPT_*.json"))



def test_native_live_fresh_status_valid_owned_control(tmp_path,monkeypatch):
    case=_np_case(tmp_path,monkeypatch)
    before=_np_c3_pins(tmp_path)
    identity=case["cycle"].native_execution_identity(tmp_path,case["context"],case["validation"],native_admission_reader=case["reader"])
    assert identity["task_id"]=="A" and _np_c3_pins(tmp_path)==before


@pytest.mark.parametrize("kind",["unknown_endpoint","changed_code","foreign_rename_source","private_endpoint","failed_return","bool_return","float_return","nonbytes_stdout","missing_branch","wrong_branch","invalid_parser","duplicate_destination","staged_task","collector_exception"])
def test_native_live_fresh_status_unknown_or_malformed_blocks_before_effects(tmp_path,monkeypatch,kind):
    import base64
    from pathlib import Path
    from subprocess import CompletedProcess
    from automation.orchestration import aios_repo_state_evidence as repo_evidence
    case=_np_case(tmp_path,monkeypatch);root=case["root"]
    raw=base64.b64decode(case["data"]["status"]["after"]["raw_base64"],validate=True)
    returncode=0;private=None
    if kind=="unknown_endpoint":
        (root/"owned-unknown.txt").write_bytes(b"owned foreign delta sentinel\n")
        raw+=b"?? owned-unknown.txt\0"
    elif kind=="changed_code":raw=b"## codex/fixture\0?? safe/file.py\0"
    elif kind=="foreign_rename_source":
        (root/"owned-foreign-source.txt").write_bytes(b"owned rename source sentinel\n")
        raw=b"## codex/fixture\0R  safe/file.py\0owned-foreign-source.txt\0"
    elif kind=="private_endpoint":
        private=root/"owned-private-shaped"/".env"/"inert.txt";private.parent.mkdir(parents=True)
        private.write_bytes(b"inert owned private-shaped sentinel; no actual private payload")
        raw+=b"?? owned-private-shaped/.env/inert.txt\0"
    elif kind=="failed_return":returncode=1
    elif kind=="bool_return":returncode=False
    elif kind=="float_return":returncode=0.0
    elif kind=="nonbytes_stdout":raw=raw.decode("utf-8")
    elif kind=="missing_branch":raw=b" M safe/file.py\0"
    elif kind=="wrong_branch":raw=b"## foreign/branch\0 M safe/file.py\0"
    elif kind=="invalid_parser":raw=b"## codex/fixture\0XX malformed\0"
    elif kind=="duplicate_destination":raw+=b" M safe/file.py\0"
    elif kind=="staged_task":raw=b"## codex/fixture\0M  safe/file.py\0"
    calls=[]
    def fresh_status(actual_root,runner):
        from subprocess import run as expected_runner
        assert Path(actual_root).resolve()==root and runner is expected_runner;calls.append(str(actual_root))
        if kind=="collector_exception":raise OSError("owned status collector unavailable")
        return CompletedProcess(["git","--no-optional-locks","status","--porcelain=v1","-z","--branch","--untracked-files=all"],returncode,stdout=raw,stderr=b"")
    monkeypatch.setattr(repo_evidence,"_run_git_status",fresh_status)
    before=_np_c3_pins(root);directories={p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir()}
    read_attempts=[];original_open=Path.open
    def tracked_open(path,*args,**kwargs):
        mode=args[0] if args else kwargs.get("mode","r")
        if private is not None and path==private and ("r" in mode or "+" in mode):
            read_attempts.append(str(path));raise AssertionError("private-shaped payload read")
        return original_open(path,*args,**kwargs)
    with monkeypatch.context() as tracking:
        tracking.setattr(Path,"open",tracked_open)
        with pytest.raises((ValueError,OSError)):
            case["cycle"].native_execution_identity(root,case["context"],case["validation"],native_admission_reader=case["reader"])
    assert calls and not read_attempts
    assert _np_c3_pins(root)==before
    assert {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir()}==directories



@pytest.mark.parametrize("role,staged_code",[(role,code) for role in ("attempt","generic") for code in ("A ","M ")])
def test_native_verified_controller_bytes_never_authorize_index_transition(tmp_path,monkeypatch,role,staged_code):
    import base64
    from pathlib import Path
    from subprocess import CompletedProcess
    from automation.orchestration import aios_repo_state_evidence as repo_evidence
    case=_np_case(tmp_path,monkeypatch);attempt=_np_capture(case)
    assert _np_recover(case,attempt)["result"]=="COMPLETE"
    selected=attempt if role=="attempt" else tmp_path/case["requested"]["state_path"]
    assert selected.is_file()
    relative=selected.relative_to(tmp_path).as_posix().encode("utf-8")
    saved=base64.b64decode(case["data"]["status"]["after"]["raw_base64"],validate=True)
    observed=[saved+b"?? "+relative+b"\0"]
    def collect(actual_root,runner):
        from subprocess import run as expected_runner
        assert Path(actual_root).resolve()==case["root"] and runner is expected_runner
        return CompletedProcess(["git","--no-optional-locks","status","--porcelain=v1","-z","--branch","--untracked-files=all"],0,stdout=observed[0],stderr=b"")
    monkeypatch.setattr(repo_evidence,"_run_git_status",collect)
    before=_np_c3_pins(tmp_path)
    assert case["cycle"].native_execution_identity(tmp_path,case["context"],case["validation"],native_admission_reader=case["reader"])["task_id"]=="A"
    assert _np_c3_pins(tmp_path)==before
    observed[0]=saved+staged_code.encode("ascii")+b" "+relative+b"\0"
    with pytest.raises(ValueError):case["cycle"].native_execution_identity(tmp_path,case["context"],case["validation"],native_admission_reader=case["reader"])
    assert _np_c3_pins(tmp_path)==before
def _p505_memory_files(monkeypatch):
    """Owned BytesIO filesystem adapter; never creates an on-disk fixture."""
    import io
    import os
    import shutil
    from types import SimpleNamespace
    root = Path('C:/P505_SELECTED_MEMORY_ONLY').resolve()
    files, directories, descriptors = {}, {root}, {}
    originals = {name: getattr(Path, name) for name in (
        'read_bytes', 'write_bytes', 'write_text', 'mkdir', 'exists', 'is_file',
        'is_dir', 'is_symlink', 'is_junction', 'resolve', 'stat', 'open', 'rglob')}
    actual_fstat = os.fstat

    def owned(path):
        return path == root or path.is_relative_to(root)

    def facts(path):
        if path not in files and path not in directories:
            raise FileNotFoundError(str(path))
        return SimpleNamespace(st_mode=0o100666 if path in files else 0o40755,
            st_dev=5, st_ino=100 + sorted(map(str, files.keys() | directories)).index(str(path)),
            st_size=len(files[path]) if path in files else 0, st_mtime_ns=100,
            st_ctime_ns=100, st_nlink=1, st_file_attributes=0x80 if path in files else 0x10)

    def read(path):
        return files[path] if owned(path) else originals['read_bytes'](path)

    def write(path, raw):
        if not owned(path):
            raise AssertionError('P505_NO_DISK_WRITE:' + str(path))
        if path.parent not in directories:
            raise FileNotFoundError(str(path.parent))
        files[path] = bytes(raw)
        return len(raw)

    def mkdir(path, mode=0o777, parents=False, exist_ok=False):
        if not owned(path):
            raise AssertionError('P505_NO_DISK_MKDIR:' + str(path))
        if path in directories and not exist_ok:
            raise FileExistsError(str(path))
        directories.add(path)
        if parents:
            directories.update(parent for parent in path.parents if owned(parent))

    class Stream(io.BytesIO):
        def __init__(self, path, mode):
            if 'x' in mode and path in files:
                raise FileExistsError(str(path))
            self.path, self.mode = path, mode
            super().__init__(files.get(path, b'') if 'r' in mode else b'')
            self.fd = 100000 + len(descriptors)
            descriptors[self.fd] = self
        def fileno(self):
            return self.fd
        def flush(self):
            if any(letter in self.mode for letter in 'wxa'):
                write(self.path, self.getvalue())
        def close(self):
            if not self.closed:
                self.flush()
            super().close()

    def open_file(path, mode='r', *args, **kwargs):
        if not owned(path):
            if any(letter in mode for letter in 'wxa+'):
                raise AssertionError('P505_NO_DISK_OPEN_WRITE')
            return originals['open'](path, mode, *args, **kwargs)
        stream = Stream(path, mode)
        return stream if 'b' in mode else io.TextIOWrapper(stream, encoding=kwargs.get('encoding', 'utf-8'))

    monkeypatch.setattr(Path, 'read_bytes', read)
    monkeypatch.setattr(Path, 'write_bytes', write)
    monkeypatch.setattr(Path, 'write_text', lambda path, text, encoding='utf-8', **kw: write(path, text.encode(encoding)))
    monkeypatch.setattr(Path, 'mkdir', mkdir)
    for name in ('exists', 'is_file', 'is_dir'):
        # Resolve membership dynamically: fixture producers add files later.
        monkeypatch.setattr(Path, name, lambda path, name=name: (
            path in files or path in directories if name == 'exists' else
            path in files if name == 'is_file' else path in directories)
            if owned(path) else originals[name](path))
    for name in ('is_symlink', 'is_junction'):
        monkeypatch.setattr(Path, name, lambda path, name=name: False if owned(path) else originals[name](path))
    monkeypatch.setattr(Path, 'resolve', lambda path, *a, **kw: path if owned(path) else originals['resolve'](path, *a, **kw))
    monkeypatch.setattr(Path, 'stat', lambda path, *a, **kw: facts(path) if owned(path) else originals['stat'](path, *a, **kw))
    monkeypatch.setattr(Path, 'open', open_file)
    monkeypatch.setattr(Path, 'rglob', lambda path, pattern: iter(sorted(
        candidate for candidate in files.keys() | directories if candidate != path and candidate.is_relative_to(path)))
        if owned(path) and pattern == '*' else originals['rglob'](path, pattern))
    monkeypatch.setattr(os, 'fstat', lambda fd: facts(descriptors[fd].path) if fd in descriptors else actual_fstat(fd))
    monkeypatch.setattr(os, 'fsync', lambda fd: descriptors[fd].flush() if fd in descriptors else (_ for _ in ()).throw(AssertionError('P505_NO_REAL_FSYNC')))
    for name in ('copyfile', 'copy2'):
        monkeypatch.setattr(shutil, name, lambda source, destination, **kw: write(Path(destination), Path(source).read_bytes()))
    return root, files


def test_p505_selected_legacy_capture_missing_interval_rejects_before_publication(monkeypatch):
    """Causal baseline: explicit inventory alone is no full interval proof."""
    root, files = _p505_memory_files(monkeypatch)
    case = _p505_inventory_only_case(root, monkeypatch)
    before = dict(files)
    with pytest.raises(ValueError, match="preservation"):
        case["cycle"].native_execution_identity(
            case["root"], case["context"], case["validation"], native_admission_reader=case["reader"], live=False)
    assert files == before


@pytest.mark.parametrize('control', [
    'valid-role', 'exact-producer-bytes', 'fresh-owned-status',
    'inventory:missing_after', 'inventory:missing_before', 'inventory:foreign_source_delta', 'inventory:capture_delta',
    'packet:allowed_paths', 'packet:tier', 'packet:source_mode', 'packet:extra', 'packet:noncanonical_raw',
    'profile:write_control:true', 'profile:write_control:zero', 'profile:emit_continuation_controller:true',
    'profile:write_resume:false'])
def test_p505_selected_inherited_affected_native_controls_in_memory(monkeypatch, control):
    root, _ = _p505_memory_files(monkeypatch)
    if control == 'valid-role': test_native_c3_strict_role_valid_control(root, monkeypatch)
    elif control == 'exact-producer-bytes': test_native_packet_is_exact_unchanged_consumer_producer_bytes(root, monkeypatch)
    elif control == 'fresh-owned-status': test_native_live_fresh_status_valid_owned_control(root, monkeypatch)
    elif control.startswith('inventory:'):
        test_native_full_before_after_inventory_is_required(root, monkeypatch, control.split(':')[1])
    elif control.startswith('packet:'):
        test_native_c3_complete_packet_bytes_required(root, monkeypatch, control.split(':')[1])
    else:
        _, field, value = control.split(':')
        test_native_initial_projection_profile_is_exact_before_effects(root, monkeypatch, field,
            {'true': True, 'zero': 0, 'false': False}[value])


def _p505_ordinary_reader(monkeypatch, payloads):
    """Only the OS reader is doubled; capture traversal and comparator are real."""
    import hashlib

    from automation.orchestration import aios_repo_state_evidence as collector
    directories = {''}
    for relative in payloads:
        directories.update('/'.join(relative.split('/')[:index]) for index in range(1, len(relative.split('/'))))

    class OrdinaryReader:
        def __init__(self, deadline):
            self.handles, self.guards = [1, 2], {}
            self.directory_guards, self.stream_guards, self.positions = {}, {}, {}
            self.nodes = {1: '..', 2: ''}
            self.guards[2] = self.metadata(2)
        def tick(self):
            assert len(self.handles) < 2048
        def drive_mapping(self, drive):
            return '\\Device\\HarddiskVolume3'
        def open_root(self, drive, components):
            self.root_name = components[-1]
            return 2, self.drive_mapping(drive)
        def open_relative(self, parent, name, access):
            if parent == 1:
                assert name == self.root_name
                path = ''
            else:
                prefix = self.nodes[parent]
                path = (prefix + '/' if prefix else '') + name
            assert path in directories or path in payloads
            handle = max(self.nodes) + 1
            self.nodes[handle] = path
            self.handles.append(handle)
            return handle
        def metadata(self, handle):
            path = self.nodes[handle]
            directory = path in directories or path == '..'
            inode = int(hashlib.sha256(path.encode()).hexdigest()[:12], 16)
            return {'identity': {'device': 5, 'inode': inode},
                'attributes': 0x10 if directory else 0x80, 'directory': directory, 'links': 1,
                'size': 0 if directory else len(payloads[path]), 'mode': 0o40755 if directory else 0o100666,
                'created': 116444736000001000, 'modified': 116444736000001000,
                'changed': 116444736000001000, 'ctime_ns': 100000, 'mtime_ns': 100000, 'volume': (7, 0, 'NTFS')}
        def streams(self, handle, is_directory):
            return [] if is_directory else [('::$DATA', len(payloads[self.nodes[handle]]), 8)]
        def list_directory(self, handle, maximum):
            prefix = self.nodes[handle]
            result = []
            for path in sorted(directories | payloads.keys()):
                if not path or path.rpartition('/')[0] != prefix:
                    continue
                directory = path in directories
                result.append({'name': path.rsplit('/', 1)[-1],
                    'inode': int(hashlib.sha256(path.encode()).hexdigest()[:12], 16),
                    'attributes': 0x10 if directory else 0x80, 'size': 0 if directory else len(payloads[path]),
                    'created': 116444736000001000, 'modified': 116444736000001000, 'changed': 116444736000001000})
            return result
        def read(self, handle, count):
            at = self.positions.get(handle, 0)
            raw = payloads[self.nodes[handle]][at:at + count]
            self.positions[handle] = at + len(raw)
            return raw
        def close_all(self):
            self.handles.clear()
    monkeypatch.setattr(collector, '_FullWorktreeWindowsReader', OrdinaryReader)


def _p505_memory_case(monkeypatch, *, outside_change=False):
    root, files = _p505_memory_files(monkeypatch)
    case = _p505_inventory_only_case(root, monkeypatch)
    case['memory_files'] = files
    return _p505_attach_interval(case, monkeypatch, files, outside_change=outside_change)


def _p505_attach_interval(case, monkeypatch, files, *, outside_change=False):
    from datetime import UTC, datetime, timedelta

    from automation.orchestration import aios_repo_state_evidence as collector
    class OwnedClock(datetime):
        calls = 0
        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            return datetime(2026, 10, 20, 4, tzinfo=UTC) + timedelta(microseconds=cls.calls * 100)
    monkeypatch.setattr(collector, 'datetime', OwnedClock)
    root = case['root']
    data, cycle = case['data'], case['cycle']
    request = json.loads(data['request_json'])
    stamp = lambda: OwnedClock.now(UTC).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    launch = json.loads(data['evidence']['launch']['utf8'])
    launch['started_at'] = stamp()
    _np_reseal_saved(case, 'launch', launch)
    capture = json.loads(data['evidence']['capture']['utf8'])
    capture['started_at'] = launch['started_at']
    # Synthetic ordinary tree corresponding to the exact declared inventory.
    # All public source files are copied as bytes in memory; never real NTFS.
    payloads = {path.relative_to(root).as_posix(): raw for path, raw in files.items()
                if '/outbox/' not in path.as_posix() or path.suffixes[-2:] == ['.launch', '.json']}
    payloads['safe/file.py'] = case['task_before_bytes']
    payloads[Path(data['evidence']['launch']['path']).relative_to(root).as_posix()] = data['evidence']['launch']['utf8'].encode('utf-8')
    payloads['outside/ignored.txt'] = b'unchanged outside bytes\n'
    _p505_ordinary_reader(monkeypatch, payloads)
    packet_hash, launch_hash = data['evidence']['packet']['sha256'], data['evidence']['launch']['sha256']
    before = cycle.capture_provider_preservation(request, packet_hash, launch_hash, 'before')
    started = stamp()
    payloads['safe/file.py'] = case['target'].read_bytes()
    if outside_change:
        payloads['outside/ignored.txt'] = b'outside changed, same Git status\n'
    ended = stamp()
    capture['ended_at'] = ended
    after = cycle.capture_provider_preservation(request, packet_hash, launch_hash, 'after')
    case['proof_inputs'] = request, packet_hash, launch_hash, capture, before, after, started
    if not outside_change:
        capture['provider_interval'] = cycle.complete_provider_preservation(*case['proof_inputs'])
        _np_reseal_saved(case, 'capture', capture)
    return case


# Existing source-qualified fixtures now produce the successor contract. The
# exact inventory-only fixture remains named for the causal missing-proof test.
_p505_inventory_only_case = _np_case


def _np_case(root, monkeypatch, task='A', lookup=None, *, descriptor_override=None, host_override=None):
    case = _p505_inventory_only_case(root, monkeypatch, task, lookup,
        descriptor_override=descriptor_override, host_override=host_override)
    files = {path: path.read_bytes() for path in case['root'].rglob('*') if path.is_file()}
    return _p505_attach_interval(case, monkeypatch, files)


def test_p505_selected_actual_collector_comparator_valid_native_identity(monkeypatch):
    case = _p505_memory_case(monkeypatch)
    identity = case['cycle'].native_execution_identity(case['root'], case['context'], case['validation'],
        native_admission_reader=case['reader'], live=False)
    assert identity['task_id'] == case['context'].request.task_id
    print('P505_EXACT_VALID_MEMORY_FIXTURE ' + json.dumps({
        'tier': 'ACTUAL_COLLECTOR_COMPARATOR_READERS_WITH_MEMORY_FILES_READER_AND_CLOCK',
        'context_json': case['context'].context_json, 'context_sha256': _np_hash(case['context'].context_json.encode('ascii')),
        'validation': case['validation'], 'request': vars(case['context'].request)}, sort_keys=True))


def test_p505_selected_ignored_outside_change_same_status_rejects(monkeypatch):
    case = _p505_memory_case(monkeypatch, outside_change=True)
    assert case['data']['status']['before'] == case['data']['status']['after']
    before = dict(case['memory_files'])
    with pytest.raises(ValueError, match='preservation_rejected'):
        case['cycle'].complete_provider_preservation(*case['proof_inputs'])
    assert case['memory_files'] == before


@pytest.mark.parametrize('mutation', ['bytes', 'resealed-outside', 'task', 'root', 'rules', 'source',
    'claim', 'interval', 'time', 'partial', 'private', 'budget', 'missing', 'action', 'action-conflict'])
def test_p505_selected_invalid_proof_rejects_actual_readers_before_effects(monkeypatch, mutation):
    case = _p505_memory_case(monkeypatch)
    capture = json.loads(case['data']['evidence']['capture']['utf8'])
    proof = capture['provider_interval']
    if mutation == 'bytes':
        proof['before']['utf8'] += ' '
    elif mutation == 'resealed-outside':
        snapshot = json.loads(proof['after']['utf8'])
        snapshot['entries']['outside/ignored.txt']['sha256'] = 'f' * 64
        raw = _np_json(snapshot) + b'\n'
        proof['after'] = {'utf8': raw.decode('ascii'), 'sha256': _np_hash(raw)}
    elif mutation in {'task', 'root', 'rules', 'source'}:
        if mutation == 'task': proof['binding']['task']['task_id'] = 'OTHER'
        elif mutation == 'root': proof['binding']['repository_identity']['repo_root'] += '-other'
        elif mutation == 'rules': proof['binding']['capture_contract']['rules_sha256'] = 'f' * 64
        else: proof['binding']['implementation_manifest'][next(iter(proof['binding']['implementation_manifest']))] = 'f' * 64
    elif mutation in {'claim', 'interval'}:
        proof['execution']['launch_sha256' if mutation == 'claim' else 'request_sha256'] = 'f' * 64
    elif mutation == 'time':
        proof['execution']['started_at_utc'] = '2099-01-01T00:00:00+00:00'
    elif mutation in {'partial', 'private', 'budget'}:
        snapshot = json.loads(proof['after']['utf8'])
        snapshot['coverage']['inspection_complete'] = False
        snapshot['coverage']['errors'] = [{'path': 'outside/ignored.txt', 'reason':
            'private_refused' if mutation == 'private' else 'budget_exceeded' if mutation == 'budget' else 'read_failed'}]
        raw = _np_json(snapshot) + b'\n'
        proof['after'] = {'utf8': raw.decode('ascii'), 'sha256': _np_hash(raw)}
    elif mutation == 'missing':
        del capture['provider_interval']
    elif mutation == 'action-conflict':
        case['data']['original_resolver_packet'].update(action_id='A', selected_action='conflicting-real-action')
    else:
        case['data']['original_resolver_packet']['action_id'] = 'different-real-action'
    _np_reseal_saved(case, 'capture', capture)
    before = dict(case['memory_files'])
    calls = []
    with pytest.raises(ValueError):
        case['cycle']._native_admitted(case['context'], case['reader'])
    monkeypatch.setattr(case['cycle'], '_invoke_native_aggregate_host', lambda *a: calls.append('aggregate'))
    for consume in (
        lambda: case['cycle'].run_native_aggregate_validator(case['context'], native_admission_reader=case['reader']),
        lambda: _np_capture(case), lambda: _np_read(case),
        lambda: _np_recover(case, case['root'] / case['requested']['resume_dir'] / ('AIOS_RESUME_ATTEMPT_' + 'a' * 64 + '.json'))):
        with pytest.raises((ValueError, TypeError, KeyError)):
            consume()
        assert calls == []
        assert case['memory_files'] == before


def test_original_v2_capture_status_extracts_exact_saved_bytes():
    from copy import deepcopy
    from automation.orchestration.aios_repo_state_evidence import capture_status_evidence
    from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import read_capture_status
    status = {'before': capture_status_evidence(b'## main\0?? original.py\0'),
              'after': capture_status_evidence(b'## main\0 M original.py\0'), 'parser_sha256': 'a' * 64}
    capture = {'schema': 'AIOS_RELAY_EXECUTION.v2', 'status': status}
    assert read_capture_status(capture) == status
    wrong = deepcopy(capture)
    wrong['status']['after']['paths'] = ['substitute.py']
    with __import__('pytest').raises(ValueError):
        read_capture_status(wrong)
    with __import__('pytest').raises(ValueError, match='original_status'):
        read_capture_status({'schema': 'AIOS_RELAY_EXECUTION.v1'})


def test_original_worker_exports_status_at_both_observation_points():
    # Inspect the bound function only; never dot-source or start the worker.
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / 'automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1').read_text()
    helper = source.split('function Get-AiOsBoundRepositoryEvidence {', 1)[1].split('\nfunction ', 1)[0]
    assert "'status':s['status_evidence']" in helper
    bound = source.split('function Invoke-AiOsBoundRelayRequest {', 1)[1].split('\n# Bound profile', 1)[0]
    assert "schema='AIOS_RELAY_EXECUTION.v2'" in bound
    assert 'before=$beforeEvidence.status;after=$afterProviderEvidence.status' in bound
    assert bound.index('$providerRun=Invoke-AiOsBoundProvider') < bound.index('$afterProviderEvidence=Get-AiOsBoundRepositoryEvidence')


def test_original_v2_native_context_binds_saved_status_before_any_publication(monkeypatch):
    from copy import deepcopy
    case = _p505_memory_case(monkeypatch)
    capture = json.loads(case['data']['evidence']['capture']['utf8'])
    capture['schema'] = 'AIOS_RELAY_EXECUTION.v2'
    capture['status'] = deepcopy(case['data']['status'])
    _np_reseal_saved(case, 'capture', capture)
    verified = case['cycle']._verify_native_context(case['root'], case['context'], case['reader'], live=False)
    assert verified['status'] == capture['status']
    before = dict(case['memory_files'])
    case['data']['status']['after'] = deepcopy(case['data']['status']['before'])
    # Both observations in this example may contain the same paths. Changing
    # the parser source still makes the separately supplied context disagree.
    case['data']['status']['parser_sha256'] = 'f' * 64
    _np_refresh(case)
    with pytest.raises(ValueError):
        case['cycle']._verify_native_context(case['root'], case['context'], case['reader'], live=False)
    assert case['memory_files'] == before


def test_original_private_precheck_preserves_prior_attempt_and_avoids_launch_intent():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / 'automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1').read_text()
    bound = source.split('function Invoke-AiOsBoundRelayRequest {', 1)[1].split('\n# Bound profile', 1)[0]
    check = bound.index("'PRIVATE_BOUNDARY_PROTECTION_REQUIRED'")
    assert bound.index("'CAPTURED_ATTEMPT_NO_REPLAY'") < check
    assert bound.index("'LAUNCH_OBSERVED_WITHOUT_CONFIRMED_CAPTURE'") < check
    assert check < bound.index('$launchObserved=$true')
