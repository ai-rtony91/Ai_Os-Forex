from automation.orchestration.platform import OrchestrationPlatform, create_platform


def test_platform_consolidates_queue_and_dispatch_without_mutation(tmp_path):
    platform = create_platform(tmp_path)
    queue = platform.queue({"candidates": []})
    dispatch = platform.dispatch({"schema": "AIOS_RUNTIME_EXECUTION_QUEUE.v1", "items": []})

    assert queue["safety"]["queue_mutation"] is False
    assert dispatch["status"] == "NO_DISPATCHABLE_WORK"
    assert dispatch["safety"]["worker_launch"] is False


def test_platform_packet_generator_preserves_safety_gates(tmp_path):
    platform = OrchestrationPlatform(tmp_path)
    result = platform.generate_packet({"action_id": "unsafe_unbounded"})

    assert result["packet_ready"] is False
    assert result["reason_code"] == "allowed_paths_missing"
    assert "No live trading." in result["safety_blocks"]


def test_platform_validator_fails_closed_on_enabled_protected_action(tmp_path):
    platform = OrchestrationPlatform(tmp_path)
    state = {
        "schema": "AIOS_CANONICAL_ORCHESTRATION_SPINE.v1",
        "status": "READY",
        "permissions": {"queue_mutation": False},
        "protected_actions": {"broker_access": True},
    }

    result = platform.validate(state)

    assert result["status"] == "BLOCKED"
    assert result["defects"] == ["unsafe_protected_actions"]
    assert result["grants_approval"] is False


def test_platform_report_reuses_canonical_renderer(tmp_path):
    platform = OrchestrationPlatform(tmp_path)
    state = {
        "status": "READY",
        "coverage": {"classification_coverage_percent": 100, "discovered_item_count": 0, "classified_item_count": 0, "duplicate_item_count": 0, "unclassified_item_count": 0},
        "economic_anchor": {"first_withdrawable_dollar_status": "NOT_VERIFIED", "engineering_hours_status": "NOT_VERIFIED", "verified_engineering_hours_remaining": None, "current_highest_blocker": "NOT_VERIFIED"},
        "queue_plan": {},
        "dependency_graph": {"ready_nodes": [], "blocked_nodes": [], "cyclic_dependencies": []},
        "controller_registry": [],
        "task_catalog": [],
        "next_verified_task": None,
        "owner_action_required": False,
    }
    assert "AI_OS CANONICAL ORCHESTRATION SPINE" in platform.report(state)


def test_campaign_factory_requires_qualified_source_connections_before_effects(tmp_path):
    from automation.orchestration.aios_master_runtime_v1 import RuntimeBlocked
    platform = OrchestrationPlatform(tmp_path)
    with __import__("pytest").raises(RuntimeBlocked, match="QUALIFIED_WINDOWS_WORKER_CONNECTION_REQUIRED"):
        platform.campaign_bindings(tmp_path / "example-only.json")
    assert not list(tmp_path.iterdir())


def test_campaign_factory_rejects_report_flags_as_host_connections(tmp_path):
    from automation.orchestration.aios_master_runtime_v1 import RuntimeBlocked
    platform = OrchestrationPlatform(tmp_path, campaign_host={"approved": True, "qualified": True})
    with __import__("pytest").raises(RuntimeBlocked, match="QUALIFIED_WINDOWS_WORKER_CONNECTION_REQUIRED"):
        platform.campaign_bindings(tmp_path / "example-only.json")
    assert not list(tmp_path.iterdir())


def test_original_campaign_record_reader_component_exists():
    # Missing source readers must be implemented without starting a worker.
    from automation.orchestration import platform as implementation
    assert callable(getattr(implementation, "OriginalCampaignRecordReaders", None))


def _original_record_examples(tmp_path):
    """Owned example records only; no production authority or worker proof."""
    import hashlib
    import json
    from datetime import UTC, datetime, timedelta
    from automation.orchestration.claims.aios_task_claim_control import SCHEMA_VERSION, TaskClaimController
    def save(name, value):
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        path = tmp_path / name
        path.write_bytes(raw)
        return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}
    now = datetime.now(UTC)
    claim = {"schema_version": SCHEMA_VERSION, "task_id": "example", "packet_id": "example",
        "repository": "example-only", "supervisor": "example", "worker": "example", "worktree": str(tmp_path),
        "branch": "example", "base_branch": "main", "base_sha": "a" * 40, "claimed_paths": ["example.py"],
        "ports": [], "processes_or_services": [], "containers": [], "cache_dirs": [], "temp_dirs": [],
        "log_dirs": [], "env_files": [], "databases_or_schemas": [], "deployment_targets": [], "pull_request": "",
        "state": "ACTIVE", "acquired_at": now.isoformat(), "heartbeat_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(), "cleanup_policy": "example-only",
        "receipt_path": str(tmp_path / "release.json")}
    queue = {"packet_id": "example", "approved": False, "attempt": 0, "depends_on": []}
    selection = {"packet": {"packet_id": "example"}, "claim": claim, "queue_item": queue}
    keys = ["selected_queue_item", "apply_approval", "local_apply_executor_bridge", "single_action_executor",
            "one_action_execution_controller", "one_action_apply_runner", "one_action_execute_gate",
            "apply_result_verifier", "execution_request", "local_executor_request", "executor_options"]
    executor = {key: {} for key in keys}
    executor["selected_queue_item"] = queue
    result = {"executor_status": "not-executed-example", "command_executed": False}
    verification = {"selected_queue_item": queue, "single_action_executor": result, "validator_results": []}
    refs = {"selection": save("selection.json", selection), "executor_inputs": save("executor.json", executor),
            "verification_inputs": save("verification.json", verification),
            "before_manifest": save("before.json", b'{"before":"original bytes"}\r\n'),
            "after_manifest": save("after.json", b'{"after":"original bytes"}\r\n'), "output_dir": "native-output"}
    inputs = {"queue_view": {"items": [{"id": "example", "packet_id": "example", "depends_on": [], "attempt": 0}]},
              "repository_state": {"worktree": str(tmp_path)}, "queue_items": {"example": queue}, "claims": {"example": claim}}
    sources = {"inputs": save("inputs.json", inputs), "tasks": {"example": refs}}
    board = tmp_path / "existing-board.json"
    board.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "claims": [claim]}))
    return sources, TaskClaimController(board), selection, executor, result, verification


def test_original_readers_preserve_original_records_and_manifest_bytes(tmp_path):
    from automation.orchestration import platform as implementation
    assert callable(getattr(implementation, "OriginalCampaignRecordReaders", None)), "Original reader connection is missing"
    sources, owner, selection, executor, result, verification = _original_record_examples(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    readers = implementation.OriginalCampaignRecordReaders(tmp_path, sources, owner, native_admission_reader=None)
    assert readers.read_original_selection("example") == selection
    assert readers.read_executor_inputs("example") == executor
    assert readers.read_claim("example")["packet_id"] == "example"
    view, repo, items, claims = readers.read_current_inputs()
    assert view["items"][0]["attempt"] == 0
    assert items["example"] == selection["queue_item"]
    assert claims["example"] == selection["claim"]
    checked = readers.read_verification_inputs("example", result)
    assert checked["before_manifest"] == b'{"before":"original bytes"}\r\n'
    assert checked["after_manifest"] == b'{"after":"original bytes"}\r\n'
    assert checked["single_action_executor"] == result
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before


def test_original_readers_reject_changed_source_instead_of_using_cached_data(tmp_path):
    from automation.orchestration import platform as implementation
    import pytest
    assert callable(getattr(implementation, "OriginalCampaignRecordReaders", None)), "Original reader connection is missing"
    sources, owner, *_ = _original_record_examples(tmp_path)
    readers = implementation.OriginalCampaignRecordReaders(tmp_path, sources, owner, native_admission_reader=None)
    readers.read_executor_inputs("example")
    (tmp_path / "executor.json").write_text('{"approved":true}')
    with pytest.raises(ValueError, match="ORIGINAL_RECORD"):
        readers.read_executor_inputs("example")


def test_original_readers_reject_missing_board_foreign_result_and_path_escape(tmp_path):
    from automation.orchestration import platform as implementation
    import copy
    import pytest
    assert callable(getattr(implementation, "OriginalCampaignRecordReaders", None)), "Original reader connection is missing"
    sources, owner, *_ = _original_record_examples(tmp_path)
    readers = implementation.OriginalCampaignRecordReaders(tmp_path, sources, owner, native_admission_reader=None)
    with pytest.raises(ValueError, match="ORIGINAL_RECORD"):
        readers.read_verification_inputs("example", {"command_executed": True})
    escaped = copy.deepcopy(sources)
    escaped["tasks"]["example"]["selection"]["path"] = "../outside.json"
    with pytest.raises(ValueError, match="ORIGINAL_RECORD"):
        implementation.OriginalCampaignRecordReaders(tmp_path, escaped, owner, native_admission_reader=None).read_original_selection("example")
    owner.board_path.unlink()
    with pytest.raises(ValueError, match="ORIGINAL_RECORD"):
        readers.read_claim("example")
    assert not owner.board_path.exists()


def test_source_host_binds_original_readers_without_creating_permission(tmp_path):
    from types import SimpleNamespace
    from automation.orchestration import platform as implementation
    from automation.orchestration.aios_master_runtime_v1 import RuntimeBlocked
    import pytest
    sources, owner, *_ = _original_record_examples(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("No worker, authority, or publication callback should run during construction")
    host = SimpleNamespace(claim_controller=owner, original_record_sources=sources,
        verify_campaign=forbidden, command_runner=forbidden, native_admission_reader=forbidden)
    platform = implementation.OrchestrationPlatform(tmp_path, campaign_host=host)
    bindings = platform.campaign_bindings(tmp_path / "not-read-during-construction.json")
    assert bindings.read_current_inputs()[2]["example"]["approved"] is False
    assert bindings.claim_controller is owner
    with pytest.raises(RuntimeBlocked, match="QUALIFIED_WINDOWS_WORKER_CONNECTION_REQUIRED"):
        implementation.OrchestrationPlatform(tmp_path).campaign_bindings(tmp_path / "absent.json")


def test_original_readers_preserve_verifier_arguments_and_reject_unknown_fields(tmp_path):
    import hashlib
    import inspect
    import json
    import pytest
    from automation.orchestration.platform import OriginalCampaignRecordReaders
    from automation.orchestration.aios_self_build_apply_result_verifier import build_self_build_apply_result_verifier
    sources, owner, _, _, result, verification = _original_record_examples(tmp_path)
    verification['preservation_context'] = {'original': 'example-only'}
    def readers_for(value):
        raw = json.dumps(value).encode()
        (tmp_path / 'verification.json').write_bytes(raw)
        sources['tasks']['example']['verification_inputs']['sha256'] = hashlib.sha256(raw).hexdigest()
        return OriginalCampaignRecordReaders(tmp_path, sources, owner, native_admission_reader=None)
    kwargs = readers_for(verification).read_verification_inputs('example', result)
    assert kwargs['preservation_context'] == verification['preservation_context']
    inspect.signature(build_self_build_apply_result_verifier).bind(**kwargs)
    verification['keywordpreservation_context'] = {}
    with pytest.raises(ValueError, match='ORIGINAL_RECORD'):
        readers_for(verification).read_verification_inputs('example', result)


def test_original_readers_bind_receipt_and_require_real_native_reader(tmp_path):
    import hashlib
    import json
    import pytest
    from automation.orchestration.platform import OriginalCampaignRecordReaders
    from automation.orchestration.aios_abcd_autonomy_runner import RequirementReadRequest
    sources, owner, *_ = _original_record_examples(tmp_path)
    from automation.orchestration.aios_abcd_autonomy_runner import _acceptance_request
    inputs = json.loads((tmp_path / 'inputs.json').read_bytes())
    request = _acceptance_request(inputs['queue_view']['items'][0], inputs['queue_items']['example'], inputs['claims']['example'])
    receipt = {'task_id': 'example', 'packet_id': 'example', 'acceptance_requirement_id': 'example-only',
               'input_sha256': {'request': request.request_sha256, 'claim': request.claim_sha256}}
    raw = json.dumps(receipt).encode()
    path = tmp_path / 'receipt.json'
    path.write_bytes(raw)
    sources['tasks']['example']['receipt'] = {'path': 'receipt.json', 'sha256': hashlib.sha256(raw).hexdigest()}
    readers = OriginalCampaignRecordReaders(tmp_path, sources, owner, native_admission_reader=None)
    assert readers.read_receipt(request) == {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                                            'acceptance_requirement_id': 'example-only'}
    with pytest.raises(ValueError, match='ORIGINAL_RECORD'):
        readers.read_receipt(RequirementReadRequest('example', 'example', 'c' * 64, request.claim_sha256, request.acquired_at))
    with pytest.raises(ValueError, match='ORIGINAL_RECORD_REQUEST_UNBOUND'):
        readers.read_receipt(RequirementReadRequest('example', 'example', request.request_sha256, request.claim_sha256, 'wrong-time'))
    with pytest.raises(ValueError, match='ORIGINAL_RECORD_REQUEST_UNBOUND'):
        readers.acceptance_reader(RequirementReadRequest('example', 'example', request.request_sha256, request.claim_sha256, 'wrong-time'))
    with pytest.raises(ValueError, match='ORIGINAL_RECORD_NATIVE_READER_REQUIRED'):
        readers.acceptance_reader(request)
    assert not (tmp_path / 'native-output').exists()
    path.write_text('{}')
    with pytest.raises(ValueError, match='ORIGINAL_RECORD'):
        readers.read_receipt(request)


def test_original_readers_refuse_duplicate_json_and_changed_claim_owner(tmp_path):
    import hashlib
    import json
    import pytest
    from automation.orchestration.platform import OriginalCampaignRecordReaders
    sources, owner, *_ = _original_record_examples(tmp_path)
    raw = b'{"selected_queue_item":{},"selected_queue_item":{"packet_id":"example"}}'
    (tmp_path / 'executor.json').write_bytes(raw)
    sources['tasks']['example']['executor_inputs']['sha256'] = hashlib.sha256(raw).hexdigest()
    readers = OriginalCampaignRecordReaders(tmp_path, sources, owner, native_admission_reader=None)
    with pytest.raises(ValueError, match='ORIGINAL_RECORD'):
        readers.read_executor_inputs('example')
    board = json.loads(owner.board_path.read_text())
    board['claims'][0]['worker'] = 'someone-else'
    owner.board_path.write_text(json.dumps(board))
    with pytest.raises(ValueError, match='ORIGINAL_RECORD'):
        readers.read_claim('example')


def test_original_readers_reject_bool_number_alias_in_result(tmp_path):
    import pytest
    from automation.orchestration.platform import OriginalCampaignRecordReaders
    sources, owner, _, _, result, _ = _original_record_examples(tmp_path)
    readers = OriginalCampaignRecordReaders(tmp_path, sources, owner, native_admission_reader=None)
    result['command_executed'] = 0
    with pytest.raises(ValueError, match='ORIGINAL_RECORD'):
        readers.read_verification_inputs('example', result)


def test_original_readers_keep_distinct_task_and_packet_ids(tmp_path):
    import hashlib
    import json
    import pytest
    from automation.orchestration.platform import OriginalCampaignRecordReaders
    sources, owner, selection, executor, result, verification = _original_record_examples(tmp_path)
    def save(name, value):
        raw = json.dumps(value).encode()
        (tmp_path / name).write_bytes(raw)
        return {'path': name, 'sha256': hashlib.sha256(raw).hexdigest()}
    selection['packet']['packet_id'] = 'packet-example'
    selection['queue_item']['packet_id'] = 'packet-example'
    selection['claim']['packet_id'] = 'packet-example'
    refs = sources['tasks']['example']
    refs['selection'] = save('selection.json', selection)
    refs['executor_inputs'] = save('executor.json', executor)
    refs['verification_inputs'] = save('verification.json', verification)
    board = json.loads(owner.board_path.read_text())
    board['claims'][0]['packet_id'] = 'packet-example'
    owner.board_path.write_text(json.dumps(board))
    readers = OriginalCampaignRecordReaders(tmp_path, sources, owner, native_admission_reader=None)
    assert readers.read_original_selection('example') == selection
    assert readers.read_original_selection('packet-example') == selection
    assert readers.read_claim('packet-example')['task_id'] == 'example'
    assert readers.read_executor_inputs('packet-example') == executor
    assert readers.read_verification_inputs('packet-example', result)['single_action_executor'] == result
    sources['tasks']['other-task'] = refs
    ambiguous = OriginalCampaignRecordReaders(tmp_path, sources, owner, native_admission_reader=None)
    with pytest.raises(ValueError, match='ORIGINAL_RECORD_CLAIM_UNBOUND'):
        ambiguous.read_claim('packet-example')


def test_source_host_consumes_fresh_inputs_receipts_and_verified_absence(tmp_path):
    import hashlib
    import json
    import pytest
    from types import SimpleNamespace
    from automation.orchestration.platform import OrchestrationPlatform
    from automation.orchestration.aios_abcd_autonomy_runner import _acceptance_request
    sources, owner, *_ = _original_record_examples(tmp_path)
    initial = json.loads((tmp_path / 'inputs.json').read_bytes())
    request = _acceptance_request(initial['queue_view']['items'][0], initial['queue_items']['example'], initial['claims']['example'])
    live_input = tmp_path / 'current-input.json'
    live_input.write_text(json.dumps(initial))
    publication = tmp_path / 'owned-publication'
    def read_current_inputs():
        value = json.loads(live_input.read_bytes())
        return tuple(value[key] for key in ('queue_view', 'repository_state', 'queue_items', 'claims'))
    def acceptance_reader(selected):
        assert selected == request
        if publication.exists():
            raise ValueError('Original publication is partial; never treat it as absence')
        return None
    def read_receipt(selected):
        assert selected == request
        path = tmp_path / 'new-receipt.json'
        raw = path.read_bytes()
        return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'acceptance_requirement_id': 'example-only'}
    def forbidden(*args, **kwargs):
        raise AssertionError('No worker, authority or native callback during this wiring check')
    host = SimpleNamespace(original_record_sources=sources, claim_controller=owner,
        verify_campaign=forbidden, command_runner=forbidden, native_admission_reader=forbidden,
        read_current_inputs=read_current_inputs, acceptance_reader=acceptance_reader, read_receipt=read_receipt)
    bindings = OrchestrationPlatform(tmp_path, campaign_host=host).campaign_bindings(tmp_path / 'unused-contract.json')
    assert bindings.acceptance_reader(request) is None
    initial['repository_state']['fresh_value'] = 'created after binding'
    live_input.write_text(json.dumps(initial))
    assert bindings.read_current_inputs()[1]['fresh_value'] == 'created after binding'
    (tmp_path / 'new-receipt.json').write_text('{"original":"new output bytes"}')
    reference = bindings.read_receipt(request)
    assert reference['sha256'] == hashlib.sha256((tmp_path / 'new-receipt.json').read_bytes()).hexdigest()
    publication.mkdir()
    with pytest.raises(ValueError, match='partial'):
        bindings.acceptance_reader(request)


def test_source_host_checks_actual_new_executor_result_with_original_verifier(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from automation.orchestration.platform import OrchestrationPlatform
    from automation.orchestration import aios_self_build_one_action_local_apply_executor as executor_owner
    sources, owner, selection, *_ = _original_record_examples(tmp_path)
    generated = tmp_path / 'new-execution-result.json'
    observed = []
    def read_verification_inputs(task, actual_result):
        assert task == 'example'
        assert actual_result == json.loads(generated.read_bytes())
        observed.append(actual_result)
        return {'selected_queue_item': selection['queue_item'], 'single_action_executor': actual_result,
                'validator_results': [], 'before_manifest': b'{"before":"new original bytes"}',
                'after_manifest': b'{"after":"new original bytes"}'}
    def forbidden(*args, **kwargs):
        raise AssertionError('No real runner or authority call is part of this component check')
    host = SimpleNamespace(original_record_sources=sources, claim_controller=owner,
        verify_campaign=forbidden, command_runner=forbidden, native_admission_reader=forbidden,
        read_verification_inputs=read_verification_inputs)
    bindings = OrchestrationPlatform(tmp_path, campaign_host=host).campaign_bindings(tmp_path / 'unused-contract.json')
    # Substitute only the executor result to check the real result-reader and
    # verifier connection. This supplies no execution or acceptance proof.
    generated.write_text(json.dumps({'executor_status': 'executed', 'command_executed': True,
        'command_returncode': 0, 'example_bytes_created_after_construction': True}))
    monkeypatch.setattr(executor_owner, 'build_self_build_one_action_local_apply_executor',
                        lambda **kwargs: json.loads(generated.read_bytes()))
    result = bindings.execute(selection['packet'])
    assert observed == [json.loads(generated.read_bytes())]
    assert result['status'] == 'VALIDATION_FAILED'
    assert result['verification']['verifier_status'] != 'passed'


def test_source_host_rejects_noncallable_live_reader_values(tmp_path):
    import pytest
    from types import SimpleNamespace
    from automation.orchestration.platform import OrchestrationPlatform
    from automation.orchestration.aios_master_runtime_v1 import RuntimeBlocked
    sources, owner, *_ = _original_record_examples(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('Construction must remain inert')
    for key in ('read_current_inputs', 'read_verification_inputs', 'acceptance_reader', 'read_receipt'):
        host = SimpleNamespace(original_record_sources=sources, claim_controller=owner,
            verify_campaign=forbidden, command_runner=forbidden, native_admission_reader=forbidden,
            **{key: {'qualified': True}})
        with pytest.raises(RuntimeBlocked, match='QUALIFIED_WINDOWS_WORKER_CONNECTION_REQUIRED'):
            OrchestrationPlatform(tmp_path, campaign_host=host).campaign_bindings(tmp_path / 'unused-contract.json')


def _default_connection_example(tmp_path, monkeypatch):
    """Invented original records and a verifier substitute; no real authority."""
    import hashlib
    import json
    from types import SimpleNamespace
    from automation.orchestration.claims import aios_task_claim_control as claims
    from automation.validators import aios_approval_authority_integrity_validator as authority
    sources, owner, *_ = _original_record_examples(tmp_path)
    contract = {'packet_id': 'example-campaign', 'repository_identity': {'root': str(tmp_path),
        'branch': 'example', 'head': 'a' * 40}, 'task_ids': ['example'],
        'worker_connection': {'schema': 'AIOS_ORIGINAL_CAMPAIGN_RECORD_CONNECTION.v1',
            'claim_board': owner.board_path.name, 'records': sources}}
    path = tmp_path / 'campaign.json'
    path.write_text(json.dumps(contract))
    material = {'gate': {'schema': authority.V2_PAYLOAD_SCHEMA,
                        'data_hashes': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}},
                'authority': {}, 'hmac_key': 'invented-not-a-real-key', 'trust_metadata': {},
                'approval_roots': (tmp_path,), 'current_gate_path': tmp_path / 'invented-gate.json'}
    calls = []
    monkeypatch.setattr(claims, 'make_canonical_authority_reader', lambda: lambda: material)
    def check(gate, inbox, **options):
        assert gate is material['gate'] and inbox is material['authority']
        assert options['allow_test_trust'] is False
        calls.append(options)
        return SimpleNamespace(status='PASS', hardened_approval_verified=True)
    monkeypatch.setattr(authority, 'validate_authority_bundle', check)
    return path, contract, material, calls, owner


def test_default_connection_loads_existing_original_records_and_claim_owner(tmp_path, monkeypatch):
    from automation.orchestration import platform as implementation
    path, contract, material, calls, owner = _default_connection_example(tmp_path, monkeypatch)
    connection = implementation.DefaultCampaignRecordConnection(tmp_path, path)
    assert connection.claim_controller.board_path == owner.board_path
    assert connection.readers.read_original_selection('example')['claim']['worker'] == 'example'
    assert connection.verify_authority(contract, connection.digest) is True
    assert len(calls) == 1
    assert not (tmp_path / '.aios').exists()


def test_default_connection_normal_command_stops_before_intent_without_native_producer(tmp_path, monkeypatch):
    import pytest
    from automation.orchestration.aios_master_runtime_v1 import run, RuntimeBlocked
    path, _, _, calls, _ = _default_connection_example(tmp_path, monkeypatch)
    before = {item.relative_to(tmp_path).as_posix(): item.read_bytes() for item in tmp_path.rglob('*') if item.is_file()}
    with pytest.raises(RuntimeBlocked, match='NATIVE_ADMISSION_PRODUCER_REQUIRED'):
        run(tmp_path, command='run', mode='APPLY', mission_contract=path)
    assert len(calls) == 1
    assert not (tmp_path / '.aios').exists()
    assert before == {item.relative_to(tmp_path).as_posix(): item.read_bytes() for item in tmp_path.rglob('*') if item.is_file()}


@__import__('pytest').mark.parametrize('defect', ['missing-board', 'changed-input', 'wrong-task', 'wrong-branch',
    'private-board', 'dynamic-code', 'duplicate-contract'])
def test_default_connection_rejects_bad_sources_before_authority(tmp_path, monkeypatch, defect):
    import json
    import pytest
    from automation.orchestration import platform as implementation
    path, contract, _, calls, owner = _default_connection_example(tmp_path, monkeypatch)
    if defect == 'missing-board':
        owner.board_path.unlink()
    elif defect == 'changed-input':
        (tmp_path / 'inputs.json').write_text('{}')
    elif defect == 'wrong-task':
        contract['task_ids'] = ['different-task']
    elif defect == 'wrong-branch':
        contract['repository_identity']['branch'] = 'changed'
    elif defect == 'private-board':
        contract['worker_connection']['claim_board'] = '.env'
    elif defect == 'dynamic-code':
        contract['worker_connection']['module'] = 'arbitrary.py'
    else:
        path.write_text('{"worker_connection":{},"worker_connection":{}}')
    if defect != 'duplicate-contract':
        path.write_text(json.dumps(contract))
    with pytest.raises(ValueError):
        implementation.DefaultCampaignRecordConnection(tmp_path, path)
    assert calls == []
    assert not (tmp_path / '.aios').exists()


@__import__('pytest').mark.parametrize('defect', ['unbound-digest', 'bad-signature', 'false-hardening', 'changed-contract'])
def test_default_connection_rejects_unbound_or_unverified_campaign(tmp_path, monkeypatch, defect):
    import pytest
    from types import SimpleNamespace
    from automation.orchestration import platform as implementation
    from automation.validators import aios_approval_authority_integrity_validator as authority
    path, contract, material, _, _ = _default_connection_example(tmp_path, monkeypatch)
    connection = implementation.DefaultCampaignRecordConnection(tmp_path, path)
    if defect == 'unbound-digest':
        material['gate']['data_hashes'][path.name] = 'b' * 64
    elif defect in {'bad-signature', 'false-hardening'}:
        monkeypatch.setattr(authority, 'validate_authority_bundle', lambda *a, **kw:
            SimpleNamespace(status='BLOCKED' if defect == 'bad-signature' else 'PASS',
                            hardened_approval_verified=False))
    else:
        path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError):
        connection.verify_authority(contract, connection.digest)


def test_default_connection_refuses_legacy_signature_with_unsigned_data_hashes(tmp_path, monkeypatch):
    import pytest
    from automation.orchestration.platform import DefaultCampaignRecordConnection
    path, contract, material, _, _ = _default_connection_example(tmp_path, monkeypatch)
    material['gate']['schema'] = 'AIOS_HUMAN_OWNER_APPROVAL_PAYLOAD.v1'
    connection = DefaultCampaignRecordConnection(tmp_path, path)
    with pytest.raises(ValueError, match='AUTHORITY_UNBOUND_OR_UNVERIFIED'):
        connection.verify_authority(contract, connection.digest)


def test_default_connection_keeps_same_owned_claim_during_lifecycle_change(tmp_path, monkeypatch):
    import json
    from automation.orchestration.platform import DefaultCampaignRecordConnection
    path, _, _, _, owner = _default_connection_example(tmp_path, monkeypatch)
    board = json.loads(owner.board_path.read_bytes())
    board['claims'][0]['state'] = 'VERIFYING'
    owner.board_path.write_text(json.dumps(board))
    connection = DefaultCampaignRecordConnection(tmp_path, path)
    assert connection.readers.read_claim('example')['state'] == 'VERIFYING'


def test_default_connection_rejects_replaced_reader_sources(tmp_path, monkeypatch):
    import hashlib
    import json
    import pytest
    from automation.orchestration.platform import DefaultCampaignRecordConnection
    path, contract, _, _, _ = _default_connection_example(tmp_path, monkeypatch)
    connection = DefaultCampaignRecordConnection(tmp_path, path)
    value = json.loads((tmp_path / 'inputs.json').read_bytes())
    value['repository_state']['unbound_replacement'] = True
    raw = json.dumps(value).encode()
    (tmp_path / 'replaced-inputs.json').write_bytes(raw)
    connection.readers.sources['inputs'] = {'path': 'replaced-inputs.json', 'sha256': hashlib.sha256(raw).hexdigest()}
    with pytest.raises(ValueError, match='SOURCES_CHANGED'):
        connection.verify_authority(contract, connection.digest)


def test_default_connection_does_not_acquire_an_unclaimed_original_task(tmp_path, monkeypatch):
    import json
    from automation.orchestration.platform import DefaultCampaignRecordConnection
    path, _, _, _, owner = _default_connection_example(tmp_path, monkeypatch)
    board = json.loads(owner.board_path.read_bytes())
    board['claims'] = []
    owner.board_path.write_text(json.dumps(board))
    before = owner.board_path.read_bytes()
    connection = DefaultCampaignRecordConnection(tmp_path, path)
    assert connection.claim_controller.board_path == owner.board_path
    assert owner.board_path.read_bytes() == before


def test_default_connection_reuses_exact_terminal_claim_without_accepting_task(tmp_path, monkeypatch):
    import hashlib
    import json
    from datetime import UTC, datetime
    from pathlib import Path
    import pytest
    from automation.orchestration.claims.aios_task_claim_control import normalize_claim, _claim_contract
    from automation.orchestration.platform import DefaultCampaignRecordConnection
    path, _, _, _, owner = _default_connection_example(tmp_path, monkeypatch)
    board = json.loads(owner.board_path.read_bytes())
    original = normalize_claim(board['claims'][0])
    payload = {**original, 'state': 'COMPLETE_RECEIPT', 'released_at': datetime.now(UTC).isoformat()}
    receipt = Path(original['receipt_path'])
    raw = json.dumps(payload).encode()
    receipt.write_bytes(raw)
    board['claims'] = []
    board['completed_receipts'] = [{'task_id': 'example', 'claim_sha256': _claim_contract(original),
        'receipt_path': original['receipt_path'], 'receipt_sha256': hashlib.sha256(raw).hexdigest()}]
    owner.board_path.write_text(json.dumps(board))
    before = owner.board_path.read_bytes()
    connection = DefaultCampaignRecordConnection(tmp_path, path)
    assert connection.claim_controller.board_path == owner.board_path
    assert owner.board_path.read_bytes() == before
    assert receipt.read_bytes() == raw
    # Lifecycle cleanup is never native acceptance or a new active claim.
    with pytest.raises(ValueError, match='CLAIM_UNBOUND'):
        connection.readers.read_claim('example')


def test_default_connection_never_relabels_consumed_unknown_attempt_as_unclaimed(tmp_path, monkeypatch):
    import json
    import pytest
    from datetime import UTC, datetime
    from automation.orchestration.claims.aios_task_claim_control import normalize_claim, _claim_contract, EXECUTION_SCHEMA
    from automation.orchestration.platform import DefaultCampaignRecordConnection
    path, _, _, _, owner = _default_connection_example(tmp_path, monkeypatch)
    board = json.loads(owner.board_path.read_bytes())
    claim = normalize_claim(board['claims'][0])
    board['claims'] = []
    board['execution_intents'] = [{'schema': EXECUTION_SCHEMA, 'state': 'CONSUMED',
        'consumed_at': datetime.now(UTC).isoformat(), 'board_path': owner.board_path.as_posix().casefold(),
        'claim_sha256': _claim_contract(claim), 'nonce_sha256': 'a' * 64,
        'invocation_sha256': 'b' * 64, 'approval_sha256': 'c' * 64}]
    owner.board_path.write_text(json.dumps(board))
    before = owner.board_path.read_bytes()
    with pytest.raises(ValueError, match='OUTCOME_UNRESOLVED'):
        DefaultCampaignRecordConnection(tmp_path, path)
    assert owner.board_path.read_bytes() == before
