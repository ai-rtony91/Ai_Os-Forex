"""PB01-PB34: synthetic privacy boundary; never genuine broker evidence."""
from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import importlib.util
import io
import itertools
import json
import logging
import pickle
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'automation/forex_engine/ibkr_connection_probe_v1.py'
SCHEMA = ROOT / 'schemas/forex_delivery/aios_ibkr_connection_probe_receipt_v1.schema.json'
SENTINEL = b'FIXTURE_ONLY_ACCOUNT_PRIVATE_SENTINEL_PB_V1'
NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)
FIXTURE_GRANTS = itertools.count(1)


@pytest.fixture
def api():
    assert MODULE.is_file(), 'EXPECTED_RED: approved privacy contract is absent'
    spec = importlib.util.spec_from_file_location('ibkr_privacy_fixture_contract', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def signed(plan):
    plan['grant']['plan_sha256'] = hashlib.sha256(json.dumps(
        {**{k: v for k, v in plan.items() if k != 'grant'},
         'grant': {k: v for k, v in plan['grant'].items() if k != 'plan_sha256'}},
        sort_keys=True, separators=(',', ':'), allow_nan=False,
    ).encode()).hexdigest()
    return plan


def plan():
    return signed({
        'schema': 'AIOS_IBKR_CONNECTION_PLAN.v1',
        'evidence_kind': 'FIXTURE_ONLY',
        'profile': 'OFFLINE_PRIVACY_FIXTURE',
        'privacy_policy': 'FIXTURE_MINIMAL_STARTUP_V1',
        'host': '127.0.0.1', 'port': 7497, 'client_id': 132,
        'environment': 'FIXTURE_PAPER', 'read_only_api': True,
        'client_id_fresh': True, 'master_client_id': 0,
        'max_attempts': 1, 'max_elapsed_seconds': 30,
        'startup_timeout_seconds': 10, 'cleanup_timeout_seconds': 2,
        'max_retries': 0, 'max_reconnects': 0,
        'max_input_bytes': 65536, 'max_frame_bytes': 8192,
        'max_queue_frames': 16, 'max_notice_frames': 16,
        'expires_at_utc': '2026-10-13T00:01:00Z',
        'source_pins': {
            'evidence_kind': 'FIXTURE_ONLY', 'sdk_version': 'FIXTURE_VERSION',
            'sdk_source_sha256': 'a' * 64, 'dependency_sha256': 'b' * 64,
            'platform_version': 'FIXTURE_VERSION',
        },
        'privacy_controls': {k: True for k in (
            'outputs_armed', 'no_file_logging', 'no_telemetry', 'no_debugger',
            'no_sitecustomize', 'host_dump_verified', 'paging_verified',
            'hibernation_verified', 'platform_logging_verified',
        )},
        'grant': {'evidence_kind': 'FIXTURE_ONLY', 'grant_id': f'FIXTURE_ONLY_GRANT_{next(FIXTURE_GRANTS):032x}',
                  'used': False, 'plan_sha256': ''},
    })


def frame(payload):
    return bytearray(struct.pack('!I', len(payload)) + payload)


def legacy(kind, fields, version=200):
    body = b'\0'.join(fields) + b'\0'
    prefix = struct.pack('!I', kind) if version >= 201 else str(kind).encode() + b'\0'
    return frame(prefix + body)


def varint(value):
    value &= (1 << 64) - 1
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def pv(tag, value):
    return varint(tag << 3) + varint(value)


def ps(tag, value):
    return varint((tag << 3) | 2) + varint(len(value)) + value


def proto(kind, payload):
    return frame(struct.pack('!I', kind + 200) + payload)


def startup(version=200, reverse=False, order_id=17):
    if version >= 207:
        frames = [proto(15, ps(1, SENTINEL)), proto(9, pv(1, order_id))]
    else:
        frames = [legacy(15, [b'1', SENTINEL], version),
                  legacy(9, [b'1', str(order_id).encode()], version)]
    return frames[::-1] if reverse else frames


def run(api, chunks=None, version=200, timeline=None, p=None, cleanup=True):
    chunks = startup(version) if chunks is None else chunks
    transport = api.FixtureConnectionLifecycleTransport(chunks, version, cleanup)
    receipt = api.replay_connection_fixture(
        plan() if p is None else p, transport,
        [0.1] * len(chunks) if timeline is None else timeline, NOW,
    )
    return receipt, transport


def assert_private_free(value):
    rendered = json.dumps(value, sort_keys=True)
    assert SENTINEL.decode() not in rendered
    assert 'accountsList' not in rendered
    assert 'orderId' not in rendered
    assert value['evidence_kind'] == 'FIXTURE_ONLY'
    assert value['real_connection_verified'] is False
    assert value['source_admitted'] is False
    assert value['genuine_effects'] == 0


def test_pb01_authority_gates_before_opener(api):
    calls = []
    def opener():
        calls.append('forbidden')
    for mutate in ('missing', 'expired', 'altered', 'no_account'):
        p = plan()
        if mutate == 'missing':
            p.pop('grant')
        elif mutate == 'expired':
            p['expires_at_utc'] = '2026-10-12T00:00:00Z'
            signed(p)
        elif mutate == 'altered':
            p['host'] = 'localhost'
        else:
            p['privacy_policy'] = 'NO_ACCOUNT_DATA'
            signed(p)
        r = api.replay_connection_fixture(p, opener, [], NOW)
        assert r['status'] == 'BLOCKED'
        assert_private_free(r)
    assert calls == []
    r = api.classify_connection_readiness({'profile': 'STANDARD_IBKR_SDK', 'no_account_data': True})
    assert r['error_code'] == 'BLOCKED_AUTOMATIC_PRIVATE_STARTUP'
    assert r['real_connection_authorized'] is False


def test_pb02_missing_evidence_blocks(api):
    for key in ('sdk_source_sha256', 'dependency_sha256', 'platform_version'):
        p = plan()
        p['source_pins'].pop(key)
        signed(p)
        r, t = run(api, p=p)
        assert r['status'] == 'BLOCKED' and t.sent_envelopes == ()
    for missing in ('source_pins', 'privacy_controls'):
        p = plan(); p.pop(missing); signed(p)
        assert run(api, p=p)[0]['status'] == 'BLOCKED'


def test_pb03_exact_endpoint_identity_only(api):
    for key, value in [('host', 'localhost'), ('host', '192.0.2.1'), ('port', 7496),
                       ('environment', 'LIVE'), ('client_id', 0), ('client_id', True),
                       ('master_client_id', 132), ('client_id_fresh', False)]:
        p = plan(); p[key] = value; signed(p)
        r, t = run(api, p=p)
        assert r['status'] == 'BLOCKED' and t.sent_envelopes == ()


def test_pb04_exact_initialization_envelopes(api):
    init = b'API\0' + struct.pack('!I', 9) + b'v100..226'
    assert api.fixture_initialization_envelopes(200) == (init, bytes(legacy(71, [b'2', b'132', b''])))
    assert api.fixture_initialization_envelopes(206)[1] == bytes(legacy(71, [b'2', b'132', b''], 206))
    assert api.fixture_initialization_envelopes(226)[1] == bytes(proto(71, pv(1, 132) + ps(2, b'')))
    for version in (100, 200, 201, 206, 207, 212, 213, 226):
        r, t = run(api, version=version)
        assert r['status'] == 'MODEL_COMPLETE'
        assert t.sent_envelopes == api.fixture_initialization_envelopes(version)
        assert r['initialization_envelopes'] == 2
        assert r['forbidden_envelopes'] == 0


def test_pb05_all_noninitialization_sends_denied(api):
    for message_id in (3, 4, 5, 20, 49, 50, 1, 17):
        t = api.FixtureConnectionLifecycleTransport(startup(), 200)
        assert t.send_envelope(bytes(legacy(message_id, [SENTINEL]))) is False
        assert t.revoked and t.closed and t.sent_envelopes == ()
        # Deliberately exercise the pure model's active-lease sender boundary,
        # after the public fixture plan has been validated; no socket exists.
        t = api.FixtureConnectionLifecycleTransport(startup(), 200)
        api.validate_connection_plan(plan(), NOW)
        t._armed = True
        assert t.send_envelope(api.fixture_initialization_envelopes(200)[0]) is True
        assert t.send_envelope(bytes(legacy(message_id, [SENTINEL]))) is False
        assert t.revoked and t.closed and len(t.sent_envelopes) == 1
    _, t = run(api)
    assert t.send_envelope(api.fixture_initialization_envelopes(200)[1]) is False
    assert t.revoked and t.closed
    assert len(t.sent_envelopes) == 2


def test_pb06_callback_dispatch_is_not_exposed(api):
    t = api.FixtureConnectionLifecycleTransport(startup(), 200)
    for name in ('connectAck', 'nextValidId', 'error', 'placeOrder', 'reqHistoricalData', 'sendMsg', 'sendMsgProtoBuf'):
        assert not hasattr(t, name)
        with pytest.raises(AttributeError):
            setattr(t, name, lambda *args: pytest.fail('callback must never execute'))
    assert t.send_envelope(b'forbidden callback send') is False


def test_pb07_foreign_and_modified_transports_block(api, monkeypatch):
    class Foreign:
        def __getattribute__(self, name):
            pytest.fail('foreign transport inspected')
    assert api.replay_connection_fixture(plan(), Foreign(), [], NOW)['status'] == 'BLOCKED'
    class Derived(api.FixtureConnectionLifecycleTransport):
        pass
    d = Derived(startup(), 200)
    assert api.replay_connection_fixture(plan(), d, [0.1, 0.2], NOW)['status'] == 'BLOCKED'
    called = []
    t = api.FixtureConnectionLifecycleTransport(startup(), 200)
    monkeypatch.setattr(api.FixtureConnectionLifecycleTransport, 'send_envelope', lambda *a: called.append(1))
    assert api.replay_connection_fixture(plan(), t, [0.1, 0.2], NOW)['status'] == 'BLOCKED'
    assert called == [] and t.revoked
    monkeypatch.undo()
    for name in ('placeOrder', '__iter__', '__getattribute__'):
        called = []
        t = api.FixtureConnectionLifecycleTransport(startup(), 200)
        def forbidden(*args):
            called.append('injected capability')
            raise RuntimeError('FIXTURE_ONLY injected capability')
        with monkeypatch.context() as patch:
            patch.setattr(api.FixtureConnectionLifecycleTransport, name, forbidden, raising=False)
            r = api.replay_connection_fixture(plan(), t, [0.1, 0.2], NOW)
        assert r['status'] == 'BLOCKED' and called == [] and t.revoked
        assert t.retained_input_chunks == 0


def test_pb08_private_callbacks_only_leave_presence_flags(api):
    for version in (200, 206, 207, 226):
        for reverse in (False, True):
            chunks = startup(version, reverse)
            r, t = run(api, chunks, version)
            assert r['status'] == 'MODEL_COMPLETE'
            assert r['managed_accounts_seen'] and r['next_valid_id_seen']
            assert_private_free(r)
            assert all(not any(c) for c in chunks)
            assert SENTINEL.decode() not in repr(t)


def test_pb09_protobuf_dual_callback_is_one_semantic_frame(api):
    r, t = run(api, version=226)
    assert r['status'] == 'MODEL_COMPLETE'
    assert r['managed_accounts_seen'] and r['next_valid_id_seen']
    assert t.callback_forms_processed == 4
    assert t.semantic_startup_frames == 2
    assert t.pending_bytes == 0


def test_pb10_duplicate_and_postterminal_frames_fail(api):
    a, n = startup()
    r, t = run(api, [a, bytearray(a), n])
    assert r['status'] == 'BLOCKED' and t.revoked
    r, t = run(api)
    late = legacy(15, [b'1', SENTINEL])
    assert t.ingest(late) is False and not any(late)
    assert t.revoked and t.closed
    r, t = run(api, startup() + [legacy(15, [b'1', SENTINEL])])
    assert r['status'] == 'BLOCKED'


def test_pb11_next_id_bounds_without_retention(api):
    for value in (0, 1, 2147483647):
        r, t = run(api, startup(order_id=value))
        assert r['status'] == 'MODEL_COMPLETE'
        assert not hasattr(t, 'order_id')
    for bad in (b'True', b'-1', b'2147483648', b'1.0', b''):
        r, _ = run(api, [legacy(15, [b'1', SENTINEL]), legacy(9, [b'1', bad])])
        assert r['status'] == 'BLOCKED'
    assert run(api, [proto(15, ps(1, SENTINEL)), proto(9, pv(1, 1 << 63))], 226)[0]['status'] == 'BLOCKED'


def test_pb12_notice_envelope_presence_rules(api):
    for code in (2104, 2106, 2158):
        for version in (200, 226):
            notice = (proto(4, pv(3, code) + ps(4, SENTINEL)) if version == 226 else
                      legacy(4, [b'2', b'-1', str(code).encode(), SENTINEL]))
            r, _ = run(api, [notice] + startup(version), version)
            assert r['status'] == 'MODEL_COMPLETE'; assert_private_free(r)
        for request_id in (0, 7):
            assert run(api, [proto(4, pv(1, request_id) + pv(3, code))] + startup(226), 226)[0]['status'] == 'BLOCKED'
    assert run(api, [proto(4, pv(1, -1) + pv(3, 2104))] + startup(226), 226)[0]['status'] == 'MODEL_COMPLETE'


def test_pb13_error_and_rejection_never_recover(api):
    for code in (1100, 1101, 1102, 1300, 9999):
        r, t = run(api, [proto(4, pv(3, code) + ps(4, SENTINEL))], 226)
        assert r['status'] == 'BLOCKED' and t.revoked
        assert_private_free(r)
    r, _ = run(api, [proto(4, pv(3, 2104) + ps(5, SENTINEL))], 226)
    assert r['status'] == 'BLOCKED'


def test_pb14_unknown_ingress_types_drop_before_dispatch(api):
    for kind in (1, 2, 3, 5, 6, 7, 11, 17, 61):
        c = legacy(kind, [SENTINEL])
        r, t = run(api, [c])
        assert r['status'] == 'BLOCKED' and t.closed and not any(c)


def test_pb15_bounded_fragmentation_and_proto_parser(api):
    merged = startup(226)[0] + startup(226)[1]
    pieces = [merged[:2], merged[2:17], merged[17:]]
    assert run(api, pieces, 226)[0]['status'] == 'MODEL_COMPLETE'
    assert run(api, [merged], 226)[0]['status'] == 'MODEL_COMPLETE'
    for bad in (bytearray(b'\0\0'), frame(b''), bytearray(struct.pack('!I', 8193)),
                proto(15, ps(2, SENTINEL)), proto(15, ps(1, SENTINEL) + ps(1, SENTINEL)),
                proto(9, b'\x08\x80'), proto(9, b'\x0d\0\0\0\0'),
                legacy(15, [b'1', SENTINEL])[:-1]):
        r, t = run(api, [bad], 226)
        assert r['status'] == 'BLOCKED' and t.pending_bytes == 0


def test_pb16_fixed_budgets_cannot_expand(api):
    for key, value in [('max_input_bytes', 65537), ('max_queue_frames', 17),
                       ('max_notice_frames', 17), ('max_attempts', 2), ('max_retries', 1),
                       ('max_elapsed_seconds', float('nan')), ('cleanup_timeout_seconds', True)]:
        p = plan(); p[key] = value
        if value == value:
            signed(p)
        assert run(api, p=p)[0]['status'] == 'BLOCKED'
    for timeline in ([10.1, 10.1], [1, 0], [False, 0.1], [0.1, float('inf')], [10 ** 1000, 1]):
        assert run(api, timeline=timeline)[0]['status'] == 'BLOCKED'
    with pytest.raises(api.PrivacyBoundaryError):
        api.FixtureConnectionLifecycleTransport([bytearray(4097) for _ in range(16)], 200)
    with pytest.raises(api.PrivacyBoundaryError):
        api.FixtureConnectionLifecycleTransport([bytearray() for _ in range(17)], 200)
    notices = b''.join(bytes(proto(4, pv(3, 2104))) for _ in range(17))
    assert run(api, [bytearray(notices)], 226)[0]['status'] == 'BLOCKED'


def test_pb17_logging_levels_and_lastresort_have_no_private_output(api):
    sink = io.StringIO(); handler = logging.StreamHandler(sink)
    root = logging.getLogger(); previous = root.level
    root.addHandler(handler); root.setLevel(logging.DEBUG)
    old_resort = logging.lastResort; logging.lastResort = handler
    try:
        r, _ = run(api, [proto(4, pv(3, 9999) + ps(4, SENTINEL))], 226)
        assert r['status'] == 'BLOCKED'
        assert sink.getvalue() == ''
    finally:
        root.removeHandler(handler); root.setLevel(previous); logging.lastResort = old_resort


def test_pb18_console_and_exception_hooks_not_used(api, capsys, monkeypatch):
    called = []
    monkeypatch.setattr(sys, 'excepthook', lambda *args: called.append(args))
    r, _ = run(api, [proto(4, pv(3, 1300) + ps(4, SENTINEL))], 226)
    assert_private_free(r)
    captured = capsys.readouterr()
    assert captured.out == captured.err == '' and called == []


def test_pb19_no_file_or_cache_sink(api, monkeypatch):
    def deny(*a, **kw):
        pytest.fail('offline contract attempted a file operation')
    monkeypatch.setattr(builtins, 'open', deny)
    monkeypatch.setattr(Path, 'open', deny)
    monkeypatch.setattr(logging, 'FileHandler', deny)
    assert run(api)[0]['status'] == 'MODEL_COMPLETE'


def test_pb20_telemetry_or_capture_hooks_block_startup(api):
    for key in ('no_telemetry', 'no_debugger', 'no_file_logging'):
        p = plan(); p['privacy_controls'][key] = False; signed(p)
        r, t = run(api, p=p)
        assert r['status'] == 'BLOCKED' and t.sent_envelopes == ()
    p = plan(); p['privacy_controls']['crash_uploader'] = True; signed(p)
    assert run(api, p=p)[0]['status'] == 'BLOCKED'


def test_pb21_private_repr_and_exception_chain_never_run(api):
    class Hostile:
        def __repr__(self):
            pytest.fail('private repr called')
        __str__ = __repr__
    for value in (Hostile(), {'private': Hostile()}, SENTINEL):
        with pytest.raises(api.PrivacyBoundaryError) as info:
            api.validate_connection_plan(value, NOW)
        assert str(info.value) == 'BLOCKED_PLAN'
        assert info.value.__cause__ is None and info.value.__context__ is None
    r = api.replay_connection_fixture(Hostile(), Hostile(), [], NOW)
    assert_private_free(r)


def test_pb22_serialization_denies_private_containers(api):
    t = api.FixtureConnectionLifecycleTransport(startup(), 200)
    with pytest.raises(api.PrivacyBoundaryError):
        pickle.dumps(t)
    with pytest.raises(TypeError):
        vars(t)
    with pytest.raises(TypeError):
        json.dumps(t)
    with pytest.raises(api.PrivacyBoundaryError):
        api.validate_public_receipt({'private': t})


def test_pb23_no_derived_private_output(api):
    one = run(api)[0]
    many = run(api, [legacy(15, [b'1', SENTINEL + b',' + SENTINEL]), legacy(9, [b'1', b'17'])])[0]
    assert one == many
    assert_private_free(one)
    for key in ('account_hash', 'masked_account', 'account_count', 'account_suffix', 'account_encoded'):
        bad = dict(one); bad[key] = 'FIXTURE_ONLY'
        with pytest.raises(api.PrivacyBoundaryError):
            api.validate_public_receipt(bad)


def test_pb24_partial_startup_never_complete(api):
    for chunks in ([], [startup()[0]], [startup()[1]], [legacy(4, [b'2', b'-1', b'2104', SENTINEL])]):
        r, t = run(api, chunks)
        assert r['status'] == 'BLOCKED' and t.closed and t.revoked


def test_pb25_failed_cleanup_is_unverified(api):
    r, t = run(api, cleanup=False)
    assert r['status'] == 'DISCONNECT_UNVERIFIED'
    assert not r['cleanup_verified'] and not r['modeled_lifecycle_complete']
    assert t.revoked and t.closed
    assert_private_free(r)


def test_pb26_owned_buffers_overwritten_and_refs_dropped(api):
    chunks = startup(); views = [memoryview(c) for c in chunks]
    r, t = run(api, chunks)
    assert r['owned_mutable_buffers_cleared']
    assert all(not any(v) for v in views)
    assert t.pending_bytes == 0 and t.retained_input_chunks == 0
    assert not r['forensic_erasure_verified']


def test_pb27_one_attempt_no_worker_reuse(api):
    p = plan(); t = api.FixtureConnectionLifecycleTransport(startup(), 200)
    assert api.replay_connection_fixture(p, t, [0.1, 0.2], NOW)['status'] == 'MODEL_COMPLETE'
    for reused in (p, copy.deepcopy(p)):
        r, fresh = run(api, p=reused)
        assert r['status'] == 'BLOCKED' and fresh.sent_envelopes == ()
    r = api.replay_connection_fixture(plan(), t, [0.1, 0.2], NOW)
    assert r['status'] == 'BLOCKED' and t.revoked
    p['grant']['used'] = True
    assert run(api, p=p)[0]['status'] == 'BLOCKED'


def test_pb28_schema_rejects_promotion_and_private_keys(api):
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    good, _ = run(api); validator.validate(good)
    for key, value in [('evidence_kind', 'GENUINE'), ('evidence_kind', 'ADMITTED'),
                       ('source_admitted', True), ('real_connection_verified', True),
                       ('paper_ready', True), ('live_ready', True), ('accountsList', SENTINEL.decode())]:
        bad = dict(good); bad[key] = value
        assert list(validator.iter_errors(bad))


def test_pb29_unknown_host_assurances_block(api):
    for key in ('host_dump_verified', 'paging_verified', 'hibernation_verified', 'platform_logging_verified'):
        for value in (None, False, 'UNKNOWN', 1):
            p = plan(); p['privacy_controls'][key] = value; signed(p)
            r, t = run(api, p=p)
            assert r['status'] == 'BLOCKED' and t.sent_envelopes == ()


def test_pb30_scoped_files_unchanged_and_no_artifact_writer(api, monkeypatch):
    paths = (MODULE, Path(__file__), SCHEMA)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'write_text', lambda *a, **k: pytest.fail('write attempted'))
        patch.setattr(Path, 'write_bytes', lambda *a, **k: pytest.fail('write attempted'))
        assert run(api)[0]['status'] == 'MODEL_COMPLETE'
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert SENTINEL not in MODULE.read_bytes() and SENTINEL not in SCHEMA.read_bytes()


def test_pb31_gates_precede_model_dispatch(api):
    for key in ('outputs_armed', 'no_sitecustomize', 'no_debugger'):
        p = plan(); p['privacy_controls'][key] = False; signed(p)
        chunks = startup()
        r, t = run(api, chunks, p=p)
        assert r['status'] == 'BLOCKED' and t.sent_envelopes == ()
        assert all(not any(c) for c in chunks)
    assert 'ibapi' not in sys.modules


def test_pb32_faults_end_in_revocation_and_sanitized_failure(api, monkeypatch):
    scenarios = [(bytearray(b'\0'), 200), (frame(SENTINEL), 200),
                 (proto(9, pv(1, 1 << 63)), 226),
                 (proto(15, ps(1, SENTINEL) + b'\x10\x01'), 226)]
    for chunk, version in scenarios:
        r, t = run(api, [chunk], version)
        assert r['status'] == 'BLOCKED' and t.revoked and t.closed
        assert not any(chunk) and r['forbidden_envelopes'] == 0
        assert_private_free(r)
    assert run(api, cleanup=False)[0]['status'] == 'DISCONNECT_UNVERIFIED'
    for helper in ('_varint', '_proto_fields', '_legacy_fields'):
        chunks = startup(226 if helper != '_legacy_fields' else 200)
        def fault(*a, **kw):
            raise RuntimeError(SENTINEL.decode())
        with monkeypatch.context() as patch:
            patch.setattr(api, helper, fault)
            r, t = run(api, chunks, 226 if helper != '_legacy_fields' else 200)
        assert r['status'] == 'BLOCKED' and t.revoked and t.closed
        assert all(not any(c) for c in chunks)
        assert_private_free(r)
    for helper in ('fixture_initialization_envelopes', '_wipe'):
        chunks = startup(226)
        t = api.FixtureConnectionLifecycleTransport(chunks, 226)
        with monkeypatch.context() as patch:
            patch.setattr(api, helper, fault)
            r = api.replay_connection_fixture(plan(), t, [0.1, 0.2], NOW)
        assert r['status'] in ('BLOCKED', 'DISCONNECT_UNVERIFIED')
        assert t.revoked and t.closed and t.retained_input_chunks == 0
        if helper == '_wipe':
            assert not r['owned_mutable_buffers_cleared'] and not r['cleanup_verified']
        assert_private_free(r)


def test_pb33_receipt_allowlist_never_invokes_foreign_values(api):
    r, _ = run(api); assert api.validate_public_receipt(r) == r
    class Hostile:
        def __eq__(self, other):
            pytest.fail('foreign equality called')
        def __repr__(self):
            pytest.fail('foreign repr called')
    for key in r:
        bad = dict(r); bad[key] = Hostile()
        with pytest.raises(api.PrivacyBoundaryError):
            api.validate_public_receipt(bad)
    bad = dict(r); bad['status'] = 'X' * 10000
    with pytest.raises(api.PrivacyBoundaryError):
        api.validate_public_receipt(bad)
    calls = []
    class ForeignKey:
        def __hash__(self):
            return hash('schema')
        def __eq__(self, other):
            calls.append('foreign equality')
            return other == 'schema'
    bad = dict(r); del bad['schema']; bad[ForeignKey()] = r['schema']
    with pytest.raises(api.PrivacyBoundaryError):
        api.validate_public_receipt(bad)
    assert calls == []


def test_pb34_static_and_effect_denials(api, monkeypatch):
    tree = ast.parse(MODULE.read_text())
    imports = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert imports <= {'__future__', 'datetime', 'hashlib', 'json', 'math', 'struct'}
    forbidden = {'open', 'eval', 'exec', '__import__', 'connect', 'placeOrder', 'reqHistoricalData', 'Popen'}
    assert not {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} & forbidden
    import socket
    import subprocess
    def deny(*a, **kw):
        pytest.fail('genuine effect attempted')
    monkeypatch.setattr(socket, 'socket', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)
    monkeypatch.setattr(subprocess, 'Popen', deny)
    monkeypatch.setattr(builtins, 'open', deny)
    r, _ = run(api, version=226)
    assert r['status'] == 'MODEL_COMPLETE' and r['genuine_effects'] == 0
