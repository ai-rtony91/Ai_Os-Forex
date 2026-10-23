"""Real SDK tests, synthetic wires only; never broker/source admission."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time

ROOT = Path('C:/AIOS_Tooling/IBKR/M6_SDK_OFFLINE_1051_1_V1')
MODULE = Path(__file__).parents[2] / 'automation/forex_engine/ibkr_sdk_privacy_binding_v1.py'
CANARY = 'FIXTURE_PRIVATE_CANARY_132'


def load_binding():
    assert MODULE.is_file(), 'Approved SDK privacy binding is not implemented'
    spec = importlib.util.spec_from_file_location('ibkr_sdk_privacy_binding_v1', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frame(payload):
    return struct.pack('!I', len(payload)) + payload


def varint(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def fixture_wire(version, mutation):
    negotiation = frame(f'{version}\0{CANARY}\0'.encode())
    if mutation == 'negotiation_extra':
        negotiation = frame(f'{version}\0{CANARY}\0EXTRA\0'.encode())
    if mutation == 'negotiation_business':
        negotiation = frame(b'15\0' + CANARY.encode() + b'\0')
    if version >= 213:
        ident = frame((209).to_bytes(4, 'big') + b'\x08' + varint(132999))
        accounts = frame((215).to_bytes(4, 'big') + b'\x0a' + varint(len(CANARY)) + CANARY.encode())
        notice = frame((204).to_bytes(4, 'big') + b'\x18' + varint(2104) + b'\x22' + varint(len(CANARY)) + CANARY.encode())
        if mutation == 'global_notice_id':
            notice = frame((204).to_bytes(4, 'big') + b'\x08' + b'\xff' * 9 + b'\x01\x18' + varint(2104) + b'\x22' + varint(len(CANARY)) + CANARY.encode())
        if mutation == 'explicit_zero_reqid':
            notice = frame((204).to_bytes(4, 'big') + b'\x08\x00\x18' + varint(2104))
        if mutation == 'unknown_protobuf':
            accounts = frame((215).to_bytes(4, 'big') + b'\x12\x00')
        if mutation == 'recursive_protobuf':
            accounts = frame((215).to_bytes(4, 'big') + b'\x0b\x0c')
        if mutation == 'duplicate_protobuf':
            accounts = frame((215).to_bytes(4, 'big') + b'\x0a\x01A\x0a\x01B')
        if mutation == 'protobuf_order_json':
            notice = frame((204).to_bytes(4, 'big') + b'\x18' + varint(2104) + b'\x2a\x02{}')
        if mutation == 'protobuf_reset':
            notice = frame((204).to_bytes(4, 'big') + b'\x18' + varint(1100))
    else:
        prefix = lambda n: n.to_bytes(4, 'big') if version >= 201 else f'{n}\0'.encode()
        ident = frame(prefix(9) + b'1\0' + b'132999\0')
        accounts = frame(prefix(15) + b'1\0' + CANARY.encode() + b'\0')
        fields = b'-1\0' + b'2104\0' + CANARY.encode() + b'\0\0' + b'0\0' if version >= 194 else b'2\0-1\0' + b'2104\0' + CANARY.encode() + b'\0' + (b'\0' if version >= 166 else b'')
        notice = frame(prefix(4) + fields)
        if mutation == 'legacy_order_json':
            notice = frame(prefix(4) + b'-1\0' + b'2104\0' + CANARY.encode() + b'\0{}\0' + b'0\0')
        if mutation == 'legacy_reset':
            notice = frame(prefix(4) + b'-1\0' + b'1100\0' + CANARY.encode() + b'\0\0' + b'0\0')
    startup = notice + ident + accounts
    if mutation == 'duplicate_startup':
        startup += accounts
    if mutation == 'unknown_inbound':
        startup += frame((999).to_bytes(4, 'big') if version >= 201 else b'999\0')
    if mutation == 'missing_accounts':
        startup = ident
    if mutation == 'queue_overflow':
        startup = notice * 17 + ident + accounts
    if mutation == 'queue_capacity':
        startup = notice * 15 + ident + accounts
    if mutation == 'oversized_frame':
        startup = struct.pack('!I', 8193)
    if mutation == 'truncated_frame':
        startup = b'\0\0\0\x0aX'
    if mutation == 'negative_frame':
        startup = b'\xff\xff\xff\xff'
    return negotiation + startup


def fixture_worker():
    """Test-only mock socket and injection stay out of production classes."""
    case = json.loads(sys.stdin.read())
    binding = load_binding()
    version = case.get('version', 213)
    requested_mutation = case.get('mutation', '')
    mutation = {'missing_accounts_after_callback':'missing_accounts',
        'delayed_unknown_protobuf':'unknown_protobuf',
        'reader_wire_before_decoder':'unknown_protobuf'}.get(requested_mutation,requested_mutation)
    local_close_started = threading.Event(); reader_waiting = threading.Event()
    callback_seen = threading.Event()
    start_api_sent = threading.Event(); reader_refused = threading.Event(); decoder_entered = threading.Event()
    if requested_mutation in ('delayed_unknown_protobuf','reader_wire_before_decoder'):
        original_refuse = binding._WireGate.refuse
        def observe_refuse(self,*args,**kwargs):
            try:
                return original_refuse(self,*args,**kwargs)
            finally:
                if self.reason != 'NONE': reader_refused.set()
        binding._WireGate.refuse = observe_refuse
    if requested_mutation == 'reader_wire_before_decoder':
        binding._validate_runtime()
        from ibapi import decoder
        def fail_after_reader(self,data):
            decoder_entered.set()
            assert reader_refused.wait(2), 'Synthetic reader refusal was not reached'
            raise RuntimeError(CANARY)
        decoder.Decoder.msgId2handleInfoProtoBuf[4].processMeth = fail_after_reader
    close_cases = ('local_close_os_error','local_close_eof','local_close_runtime_error','pre_close_os_error','delayed_pre_stop_os_error','delayed_pre_stop_eof','reader_stalls_until_close')
    if requested_mutation in close_cases:
        binding._validate_runtime()
        from ibapi import decoder
        original_accounts = decoder.Decoder.msgId2handleInfoProtoBuf[15].processMeth
        def accounts_after_reader_waits(self, data):
            assert reader_waiting.wait(2), 'Synthetic reader never entered receive'
            if requested_mutation == 'pre_close_os_error':
                assert reader_refused.wait(2), 'Pre-close fault was not recorded'
            original_accounts(self, data)
        decoder.Decoder.msgId2handleInfoProtoBuf[15].processMeth = accounts_after_reader_waits
        original_record_failure = binding._WireGate.record_failure
        def observe_record_failure(self, *args, **kwargs):
            result = original_record_failure(self, *args, **kwargs)
            reader_refused.set()
            return result
        binding._WireGate.record_failure = observe_record_failure
    if requested_mutation in ('delayed_pre_stop_os_error','delayed_pre_stop_eof'):
        from types import SimpleNamespace
        from ibapi import reader as reader_module
        native_event = threading.Event()
        receive_failed = threading.Event()
        cleanup_join_entered = threading.Event()
        class DelayedStopObservation:
            def __getattr__(self, name):
                return getattr(native_event, name)
            def is_set(self):
                if threading.current_thread() is not threading.main_thread() and receive_failed.is_set():
                    assert cleanup_join_entered.wait(2), 'Cleanup never reached reader join'
                return native_event.is_set()
        threading_proxy = SimpleNamespace(**threading.__dict__)
        threading_proxy.Event = DelayedStopObservation
        binding.threading = threading_proxy
        original_join = reader_module.EReader.join
        def observed_join(self, *args, **kwargs):
            cleanup_join_entered.set()
            return original_join(self, *args, **kwargs)
        reader_module.EReader.join = observed_join
    join_observations = []
    if requested_mutation == 'reader_stalls_until_close':
        from ibapi import reader as reader_module
        original_join = reader_module.EReader.join
        def measured_join(self, *args, **kwargs):
            join_observations.append((time.monotonic(), kwargs['timeout']))
            return original_join(self, *args, **kwargs)
        reader_module.EReader.join = measured_join
    trailing_cases = ('trailing_fragment_notice','trailing_fragment_unknown',
        'trailing_fragment_oversized','trailing_fragment_truncated')
    trailing_reader_waiting = threading.Event(); cleanup_join_started = threading.Event()
    if requested_mutation in trailing_cases:
        binding._validate_runtime()
        from ibapi import decoder, reader as reader_module
        original_accounts = decoder.Decoder.msgId2handleInfoProtoBuf[15].processMeth
        def accounts_after_trailing_receive(self, data):
            assert trailing_reader_waiting.wait(2), 'Trailing partial frame was not received'
            original_accounts(self, data)
            callback_seen.set()
        decoder.Decoder.msgId2handleInfoProtoBuf[15].processMeth = accounts_after_trailing_receive
        original_join = reader_module.EReader.join
        def observe_cleanup_join(self, *args, **kwargs):
            cleanup_join_started.set()
            return original_join(self, *args, **kwargs)
        reader_module.EReader.join = observe_cleanup_join
    wire = fixture_wire(version, mutation)
    initial_trailing_cut = None
    if requested_mutation in trailing_cases:
        initial_trailing_cut = len(wire) + 2
        trailer = frame((204).to_bytes(4, 'big') + b'\x08' + varint(2**64-1) +
            b'\x18' + varint(2104) + b'\x22' + varint(len(CANARY)) + CANARY.encode())
        if requested_mutation == 'trailing_fragment_unknown':
            trailer = frame((999).to_bytes(4, 'big'))
        elif requested_mutation == 'trailing_fragment_oversized':
            trailer = struct.pack('!I', 8193)
        elif requested_mutation == 'trailing_fragment_truncated':
            trailer = b'\0\0\0\x0aX'
        wire += trailer
    sockets = []
    clock = [100.0]
    if mutation in ('deadline_timeout','deadline_stall'):
        binding._now = lambda: clock[0]
    if mutation == 'deadline_stall':
        wire = frame(f'{version}\0{CANARY}\0'.encode())

    class FixtureSocket:
        def __init__(self):
            self.data = bytearray(wire)
            self.closed = False
            self.timeout = None
            self.sent = []
            self.connects = 0
            self.recvs = 0

        def settimeout(self, value):
            self.timeout = value

        def connect(self, endpoint):
            assert self.timeout is not None and 0 < self.timeout <= 10
            assert endpoint == ('127.0.0.1', 7496)
            self.connects += 1
            if mutation in ('deadline_timeout','deadline_stall'):
                clock[0] += 9
            if mutation == 'console_canary':
                print(CANARY)
                print(CANARY, file=sys.stderr)
            if mutation == 'write_attempt':
                Path('C:/Dev/Ai.Os/SDK_PRIVATE_CANARY.txt').write_text(CANARY)
            if mutation == 'credential_attempt':
                Path('C:/Dev/Ai.Os/.env').read_text()
            if mutation == 'process_attempt':
                subprocess.run(['cmd.exe','/c','echo',CANARY])
            if mutation.startswith(('forbidden:','sdk_method:')):
                from ibapi.client import EClient
                original = EClient.startApi
                def forbidden(client):
                    original(client)
                    if mutation.startswith('forbidden:'):
                        client.sendMsg(int(mutation.split(':')[1]), '')
                    else:
                        from ibapi.contract import Contract
                        from ibapi.order import Order
                        from ibapi.order_cancel import OrderCancel
                        from decimal import Decimal
                        contract = Contract(); contract.symbol = 'EUR'; contract.currency = 'USD'
                        contract.secType = 'CASH'; contract.exchange = 'IDEALPRO'
                        method = mutation.split(':')[1]
                        if method == 'placeOrder':
                            order = Order(); order.action = 'BUY'; order.orderType = 'MKT'
                            order.totalQuantity = Decimal('1')
                            client.placeOrder(132999, contract, order)
                        elif method == 'cancelOrder':
                            client.cancelOrder(132999, OrderCancel())
                        elif method == 'reqHistoricalData':
                            client.reqHistoricalData(132, contract, '', '1 D', '5 mins', 'BID', 0, 2, False, [])
                        elif method == 'reqMktData':
                            client.reqMktData(132, contract, '', False, False, [])
                        elif method == 'reqIds':
                            client.reqIds(1)
                        else:
                            getattr(client, method)()
                EClient.startApi = forbidden
            if mutation == 'connect_error':
                raise RuntimeError(CANARY)
            if mutation == 'real_socket_fallback':
                import socket
                socket.socket()

        def send(self, data):
            self.sent.append(data)
            if len(self.sent) == 2:
                start_api_sent.set()
                if requested_mutation == 'delayed_unknown_protobuf':
                    assert reader_refused.wait(2), 'Synthetic delayed frame was not refused'
            if mutation in ('deadline_timeout','deadline_stall'):
                assert 0 < self.timeout <= 1, 'Send reused original socket deadline'
            if mutation == 'queue_capacity' and len(self.sent) == 2:
                time.sleep(0.05)
            if mutation == 'start_api_error' and len(self.sent) == 2:
                raise RuntimeError(CANARY)
            if mutation == 'partial_send':
                return len(data) - 1
            if mutation == 'send_error':
                raise RuntimeError(CANARY)
            return len(data)

        def recv(self, size):
            self.recvs += 1
            if requested_mutation == 'first_recv_error': raise RuntimeError(CANARY)
            if requested_mutation == 'first_recv_os_error': raise OSError(CANARY)
            if requested_mutation == 'delayed_unknown_protobuf' and self.recvs > 1:
                assert start_api_sent.wait(2), 'Synthetic START_API send was not reached'
            if requested_mutation == 'reader_wire_before_decoder' and self.recvs > 2:
                assert decoder_entered.wait(2), 'Synthetic main decoder was not reached'
            if mutation in ('deadline_timeout','deadline_stall'):
                assert 0 < self.timeout <= 1, 'Receive reused original socket deadline'
            if mutation == 'reader_error' and self.recvs > 1:
                raise RuntimeError(CANARY)
            if self.closed:
                return b''
            if requested_mutation in trailing_cases and self.recvs > 1:
                trailing_reader_waiting.set()
                assert callback_seen.wait(2), 'Paired startup callbacks were not reached'
                # Old code enters cleanup while this allowed trailing frame is partial.
                # Wait for its join, or bound the delay when the repaired code waits.
                assert cleanup_join_started.wait(2), 'Cleanup was not started'
                if requested_mutation == 'trailing_fragment_truncated' and not self.data:
                    binding._now = lambda: 1e20
            if self.data:
                n = 1 if mutation == 'fragmented' else min(size, len(self.data))
                if initial_trailing_cut is not None and self.recvs == 1:
                    n = initial_trailing_cut
                if requested_mutation == 'reader_wire_before_decoder' and self.recvs == 2:
                    n = int.from_bytes(self.data[:4],'big') + 4
                if (mutation in ('reader_error','start_api_error') or requested_mutation in ('delayed_unknown_protobuf','reader_wire_before_decoder')) and self.recvs == 1:
                    n = len(frame(f'{version}\0{CANARY}\0'.encode()))
                if mutation == 'start_api_error' and self.recvs > 1:
                    time.sleep(0.1)
                data = bytes(self.data[:n]); del self.data[:n]
                return data
            if requested_mutation in close_cases:
                reader_waiting.set()
                if requested_mutation == 'pre_close_os_error':
                    raise OSError(CANARY)
                if requested_mutation in ('delayed_pre_stop_os_error','delayed_pre_stop_eof'):
                    receive_failed.set()
                    if requested_mutation == 'delayed_pre_stop_eof':
                        return b''
                    raise OSError(CANARY)
                if requested_mutation == 'reader_stalls_until_close':
                    assert local_close_started.wait(3), 'Forced local close never occurred'
                    raise OSError(CANARY)
                if requested_mutation == 'local_close_runtime_error':
                    time.sleep(self.timeout)
                    raise RuntimeError(CANARY)
                if not local_close_started.wait(self.timeout):
                    raise TimeoutError()
                if requested_mutation == 'local_close_eof':
                    return b''
                raise OSError(CANARY)
            if requested_mutation == 'missing_accounts_after_callback':
                assert callback_seen.wait(2), 'Synthetic next-ID callback not processed'
            if mutation in ('missing_accounts', 'truncated_frame'):
                binding._now = lambda: 1e20
            if mutation == 'deadline_stall':
                clock[0] += self.timeout
            time.sleep(0.001)
            raise TimeoutError()

        def close(self):
            if requested_mutation in ('local_close_os_error','local_close_eof'):
                assert not [t for t in threading.enumerate() if t is not threading.main_thread()], 'Socket closed before reader stopped'
            local_close_started.set()
            self.closed = True
            self.data[:] = b'\0' * len(self.data)
            self.data.clear()
            if mutation == 'close_error':
                raise RuntimeError(CANARY)

    def factory():
        sock = FixtureSocket(); sockets.append(sock); return sock

    # Source/runtime validation happens before any SDK construction.
    if mutation == 'runtime_pin_tamper':
        binding._RUNTIME_PIN_SHA = '0' * 64
    if mutation == 'seam_tamper':
        binding._validate_runtime()
        from ibapi.client import EClient
        EClient.connect = lambda *args: None
    if mutation == 'sdk_origin_tamper':
        binding._validate_runtime()
        import ibapi
        ibapi.__file__ = 'C:/unapproved-sdk/ibapi/__init__.py'
    spies = []
    if mutation == 'json_pickle_spies':
        binding._validate_runtime()
        import pickle
        from google.protobuf import json_format
        def refuse(*args, **kwargs):
            raise AssertionError('PRIVATE_SERIALIZATION_REFUSED')
        for owner, names in ((pickle, ('dumps','dump')), (json, ('dumps','dump')),
                             (json_format, ('ParseDict','Parse','MessageToJson','MessageToDict'))):
            for name in names:
                spies.append((owner,name,getattr(owner,name)))
                setattr(owner,name,refuse)
    paired = []
    if mutation == 'callback_pairing':
        binding._validate_runtime()
        from ibapi import decoder
        for ident, name, flag, field in ((15,'processManagedAccountsMsgProtoBuf','accounts_seen','accountsList'),
                                       (9,'processNextValidIdMsgProtoBuf','id_seen','orderId')):
            original = getattr(decoder.Decoder,name)
            def instrument(self, data, original=original, flag=flag, field=field):
                original(self,data)
                assert getattr(self.wrapper,flag)
                proto = self.wrapper.protos[-1]
                assert proto.HasField(field), 'Proto cleared before paired legacy callback'
                paired.append((proto,field))
            decoder.Decoder.msgId2handleInfoProtoBuf[ident].processMeth = instrument
    overflow = []
    if mutation == 'queue_capacity':
        import queue
        class RecordingQueue(queue.Queue):
            def put_nowait(self, item):
                try:
                    return super().put_nowait(item)
                except queue.Full:
                    overflow.append(True)
                    raise
        binding.queue.Queue = RecordingQueue
    if requested_mutation == 'missing_accounts_after_callback':
        binding._validate_runtime()
        from ibapi import decoder
        original_next = decoder.Decoder.msgId2handleInfoProtoBuf[9].processMeth
        def observe_next(self, data):
            original_next(self, data)
            callback_seen.set()
        decoder.Decoder.msgId2handleInfoProtoBuf[9].processMeth = observe_next
    result = binding._run_private(factory)
    if requested_mutation == 'reader_stalls_until_close':
        assert len(join_observations) == 2
        first_at, first_wait = join_observations[0]
        second_at, second_wait = join_observations[1]
        assert 0 <= first_wait <= 1
        assert 0 <= second_wait <= max(0, 2-(second_at-first_at)) + 0.05
        assert result['reason'] == 'CLEANUP_UNVERIFIED' and not result['cleanup_verified']
    for owner, name, original in spies:
        setattr(owner,name,original)
    assert CANARY not in repr(result)
    assert len(sockets) <= 1
    assert all(s.closed for s in sockets)
    assert all(s.connects <= 1 for s in sockets)
    assert all(not s.data for s in sockets)
    if mutation == 'deadline_timeout':
        assert clock[0] <= 110 and all(len(s.sent) == 2 for s in sockets)
    if mutation == 'deadline_stall':
        assert clock[0] <= 110.001
    if mutation == 'queue_capacity':
        assert overflow == [True], 'Notice budget did not exercise queue.Full'
    if mutation == 'callback_pairing':
        assert len(paired) == 2 and all(not proto.HasField(field) for proto,field in paired)
    assert not [t for t in threading.enumerate() if t is not threading.main_thread()], 'Owned reader not joined'
    result['fixture_status'] = 'FIXTURE_ONLY'
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__' and sys.argv[1:] == ['--fixture-worker']:
    fixture_worker()
    raise SystemExit(0)

import pytest


def run_case(version=213, mutation=''):
    assert MODULE.is_file(), 'Approved SDK privacy binding is not implemented'
    python = ROOT / 'runtime-env/Scripts/python.exe'
    assert python.is_file(), 'TEST_ENVIRONMENT_UNAVAILABLE'
    env = {'SystemRoot': os.environ['SystemRoot'], 'PYTHONDONTWRITEBYTECODE':'1'}
    result = subprocess.run([str(python), '-I', '-S', '-B', str(Path(__file__).resolve()), '--fixture-worker'],
                            input=json.dumps({'version':version, 'mutation':mutation}),
                            text=True, capture_output=True, timeout=30, env=env)
    assert result.returncode == 0, 'Private fixture worker did not exit cleanly'
    assert result.stderr == ''
    assert CANARY not in result.stdout + result.stderr
    output = json.loads(result.stdout)
    assert output['fixture_status'] == 'FIXTURE_ONLY'
    assert set(output) == {'status','reason','sdk_version','server_version','accounts_seen','id_seen',
                           'cleanup_verified','initialization_envelopes','fixture_status','failure_site'}
    assert all(type(x) in (str, int, bool) for x in output.values())
    return output


def test_default_facade_never_imports_sdk_or_creates_socket(monkeypatch):
    before = set(sys.modules)
    module = load_binding()
    probe = module.SdkProbe()
    assert probe.readiness()['status'] == 'BLOCKED'
    assert probe.probe()['reason'] == 'CONNECTION_AUTHORITY_UNAVAILABLE'
    assert probe.disconnect()['status'] == 'DISCONNECTED'
    assert not [n for n in set(sys.modules)-before if n.startswith(('ibapi','google.protobuf'))]
    assert not hasattr(probe, 'placeOrder') and not hasattr(probe, 'client')


@pytest.mark.parametrize('grant', [True, {}, {'approved':True}, 'ADMITTED', 'FIXTURE_ONLY'])
def test_caller_grants_cannot_activate(grant):
    with pytest.raises(TypeError):
        load_binding().SdkProbe().probe(grant)


@pytest.mark.parametrize('version', [100, 193, 194, 200, 201, 212, 213, 226])
def test_real_sdk_handshake_variants_and_privacy(version):
    result = run_case(version)
    assert result['status'] == 'VERIFIED_OFFLINE'
    assert result['server_version'] == version
    assert result['accounts_seen'] and result['id_seen'] and result['cleanup_verified']
    assert result['initialization_envelopes'] == 2


def test_split_frames_work():
    assert run_case(mutation='fragmented')['status'] == 'VERIFIED_OFFLINE'


def test_each_io_refreshes_remaining_startup_deadline():
    assert run_case(mutation='deadline_timeout')['status'] == 'VERIFIED_OFFLINE'


def test_stalled_read_obeys_remaining_startup_budget():
    result = run_case(mutation='deadline_stall')
    assert result['status'] == 'BLOCKED' and result['reason'] == 'DEADLINE_EXCEEDED'


def test_actual_queue_full_is_exercised_independently_of_notice_budget():
    assert run_case(mutation='queue_capacity')['status'] == 'BLOCKED'


@pytest.mark.parametrize('version,mutation', [(200,''),(213,''),(213,'negotiation_extra'),
                                            (213,'malformed_private_proto'), (213,'invalid_utf8_private_proto')])
def test_owned_mutable_parser_copies_are_wiped(version, mutation):
    binding = load_binding()
    retained = []
    class Tracked(bytearray):
        def __init__(self, value=b''):
            super().__init__(value); retained.append(self)
        def __getitem__(self, key):
            value = super().__getitem__(key)
            return Tracked(value) if isinstance(key, slice) else value
        def split(self, separator):
            return [Tracked(value) for value in super().split(separator)]
    binding.bytearray = Tracked
    gate = binding._WireGate()
    wire = fixture_wire(version,mutation)
    if mutation == 'malformed_private_proto':
        wire = frame(f'{version}\0{CANARY}\0'.encode()) + frame((215).to_bytes(4,'big') + b'\x0a' + varint(len(CANARY)) + CANARY.encode() + b'\x12\x00')
    if mutation == 'invalid_utf8_private_proto':
        wire = frame(f'{version}\0{CANARY}\0'.encode()) + frame((215).to_bytes(4,'big') + b'\x0a' + varint(len(CANARY)+1) + CANARY.encode() + b'\xff')
    gate.feed(wire)
    try:
        while True:
            payload = gate.take()
            if payload is None:
                break
            payload[:] = b'\0' * len(payload); payload.clear()
    except binding._Refused:
        assert mutation in ('negotiation_extra','malformed_private_proto','invalid_utf8_private_proto')
    finally:
        gate.clear()
    assert retained
    assert all(CANARY.encode() not in bytes(value) and b'132999' not in bytes(value) for value in retained)


def test_sdk_console_output_is_discarded():
    assert run_case(mutation='console_canary')['status'] == 'VERIFIED_OFFLINE'


def test_binary_profile_never_uses_private_json_or_pickle_serialization():
    assert run_case(mutation='json_pickle_spies')['status'] == 'VERIFIED_OFFLINE'


@pytest.mark.parametrize('code', [2104, 2106, 2158])
@pytest.mark.parametrize('request_id', [None, -1])
def test_official_sdk_global_startup_notices_are_accepted(code, request_id):
    binding = load_binding()
    binding._validate_runtime()
    from ibapi.protobuf.ErrorMessage_pb2 import ErrorMessage
    notice = ErrorMessage(errorCode=code, errorMsg='FIXTURE_ONLY_STARTUP_NOTICE', errorTime=0)
    if request_id is not None:
        notice.id = request_id
    gate = binding._WireGate(); gate.version = 226
    gate._validate_body(bytearray(notice.SerializeToString()), 204)
    assert gate.notices == 1 and gate.required == set() and not gate.revoked


@pytest.mark.parametrize('version', [213, 226])
def test_real_sdk_global_notice_reaches_paired_startup_and_cleanup(version):
    result = run_case(version=version, mutation='global_notice_id')
    assert result['status'] == 'VERIFIED_OFFLINE'
    assert result['accounts_seen'] and result['id_seen'] and result['cleanup_verified']


@pytest.mark.parametrize('request_id', [0, 1, 132, -2, -2147483648, 2147483647])
def test_startup_notice_rejects_request_specific_ids(request_id):
    binding = load_binding()
    binding._validate_runtime()
    from ibapi.protobuf.ErrorMessage_pb2 import ErrorMessage
    notice = ErrorMessage(id=request_id, errorCode=2104, errorMsg='FIXTURE_ONLY_NOTICE')
    gate = binding._WireGate(); gate.version = 226
    with pytest.raises(binding._Refused):
        gate._validate_body(bytearray(notice.SerializeToString()), 204)
    assert gate.revoked and gate.notices == 0


@pytest.mark.parametrize('suffix', [
    b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01',  # Duplicate global id.
    b'\x30\x00',  # Unknown field.
    b'\x2a\x02{}',  # Order rejection details.
    b'\x22\x01\xff',  # Invalid UTF-8.
])
def test_global_notice_still_rejects_unsafe_or_malformed_fields(suffix):
    binding = load_binding()
    gate = binding._WireGate(); gate.version = 226
    with pytest.raises(binding._Refused):
        gate._validate_body(bytearray(b'\x08' + b'\xff' * 9 + b'\x01\x18\xb8\x10' + suffix), 204)
    assert gate.revoked and gate.notices == 0


@pytest.mark.parametrize('body', [
    b'\x0a\x01A\x18\xb8\x10',  # Wrong field1 type.
    b'\x08\xff',  # Truncated id.
    b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x02\x18\xb8\x10',  # Overflow id.
    b'\x08\x80\x00\x18\xb8\x10',  # Noncanonical id.
])
def test_global_notice_rejects_malformed_id_encoding(body):
    binding = load_binding()
    gate = binding._WireGate(); gate.version = 226
    with pytest.raises(binding._Refused):
        gate._validate_body(bytearray(body), 204)
    assert gate.revoked and gate.notices == 0


@pytest.mark.parametrize('code', [0, 200, 326, 1100])
def test_global_id_does_not_admit_unapproved_notice_codes(code):
    binding = load_binding()
    gate = binding._WireGate(); gate.version = 226
    with pytest.raises(binding._Refused):
        gate._validate_body(bytearray(b'\x08' + b'\xff' * 9 + b'\x01\x18' + varint(code)), 204)
    assert gate.revoked and gate.notices == 0


def test_protobuf_pairing_is_complete_before_clearing_messages():
    assert run_case(mutation='callback_pairing')['status'] == 'VERIFIED_OFFLINE'


@pytest.mark.parametrize('name', ['placeOrder','cancelOrder','reqHistoricalData','reqMktData',
                                 'reqCurrentTime','reqManagedAccts','reqPositions','reqIds'])
def test_real_sdk_capability_methods_are_stopped(name):
    assert run_case(mutation='sdk_method:' + name)['status'] == 'BLOCKED'


@pytest.mark.parametrize('message_id', [1,3,5,6,11,17,61,62,999])
def test_business_inbound_families_rejected_before_decode(message_id):
    binding = load_binding()
    gate = binding._WireGate(); gate.version = 213
    with pytest.raises(binding._Refused):
        gate.validate(bytearray(message_id.to_bytes(4,'big') + b'\x0a\x00'))


@pytest.mark.parametrize('mutation', ['write_attempt','credential_attempt','process_attempt'])
def test_unexpected_persistent_or_host_effects_are_refused(mutation):
    assert run_case(mutation=mutation)['status'] == 'BLOCKED'


def test_outgoing_replay_and_alteration_gate():
    binding = load_binding()
    gate = binding._WireGate()
    with pytest.raises(binding._Refused):
        gate.outgoing(binding._initialization(213))
    gate = binding._WireGate()
    initial = b'API\0' + frame(b'v100..226')
    gate.outgoing(initial)
    with pytest.raises(binding._Refused):
        gate.outgoing(initial)


def test_input_byte_budget_is_finite():
    binding = load_binding()
    gate = binding._WireGate()
    for _ in range(16):
        gate.feed(b'X' * 4096)
        gate.buffer.clear()
    with pytest.raises(binding._Refused):
        gate.feed(b'X')


@pytest.mark.parametrize('version', [99, 227])
def test_unsupported_server_version_refuses(version):
    assert run_case(version)['status'] == 'BLOCKED'


@pytest.mark.parametrize('mutation', ['negotiation_extra','negotiation_business','duplicate_startup',
    'unknown_inbound','explicit_zero_reqid','unknown_protobuf','recursive_protobuf','duplicate_protobuf',
    'protobuf_order_json','protobuf_reset','queue_overflow','oversized_frame','negative_frame',
    'partial_send','send_error','connect_error','reader_error','close_error','missing_accounts',
    'truncated_frame','runtime_pin_tamper','seam_tamper','real_socket_fallback','start_api_error','sdk_origin_tamper'])
def test_fail_closed_real_sdk_paths(mutation):
    result = run_case(mutation=mutation)
    assert result['status'] == 'BLOCKED'
    if mutation == 'close_error':
        assert not result['cleanup_verified'] and result['reason'] == 'CLEANUP_UNVERIFIED'


@pytest.mark.parametrize('mutation', ['legacy_order_json','legacy_reset'])
def test_legacy_error_payloads_rejected(mutation):
    assert run_case(200, mutation)['status'] == 'BLOCKED'


@pytest.mark.parametrize('message_id', [1, 2, 3, 4, 5, 6, 7, 16, 17, 20, 24, 49, 61, 62, 71, 99])
def test_actual_sdk_non_initialization_sends_cannot_escape(message_id):
    result = run_case(mutation=f'forbidden:{message_id}')
    assert result['status'] == 'BLOCKED'
    assert result['initialization_envelopes'] <= 2


def test_public_fixture_results_deterministic():
    assert run_case() == run_case()


def test_installed_file_hash_drift_refuses_before_sdk_import(monkeypatch):
    binding = load_binding()
    original = Path.read_bytes
    def altered(path):
        data = original(path)
        return data + b'\n' if path == binding._SITE/'ibapi/client.py' else data
    monkeypatch.setattr(Path,'read_bytes',altered)
    with pytest.raises(binding._Refused, match='RUNTIME_REFUSED'):
        binding._validate_runtime()


@pytest.mark.parametrize('endpoint', [('localhost',7496,132), ('127.0.0.1',7497,132),
    ('8.8.8.8',7496,132), ('127.0.0.1',7496,0), ('127.0.0.1',7496,133)])
def test_endpoint_confinement(endpoint):
    with pytest.raises(ValueError):
        load_binding()._check_endpoint(*endpoint)


# M8A: all new approvals and signing material below are FIXTURE_ONLY.
@pytest.fixture
def activation_fixture(monkeypatch):
    import hashlib
    from datetime import datetime, timezone
    binding = load_binding()
    name = '_ibkr_activation_test_verifier'
    path = MODULE.parents[2] / 'automation/validators/aios_approval_authority_integrity_validator.py'
    spec = importlib.util.spec_from_file_location(name, path)
    verifier = importlib.util.module_from_spec(spec)
    sys.modules[name] = verifier
    try:
        spec.loader.exec_module(verifier)
    finally:
        sys.modules.pop(name, None)
    key = 'FIXTURE_ONLY_SIGNING_KEY_M8A_NEVER_USE_IN_PRODUCTION'
    signer = synthetic_p256_signer(binding)
    import base64
    fingerprint = hashlib.sha256(signer.public_blob).hexdigest()
    now = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
    trust = {
        'schema':'AIOS_HUMAN_OWNER_APPROVAL_TRUST_ROOT.v1',
        'trust_root_id':'AIOS-HUMAN-OWNER-APPROVAL-TRUST-ROOT-V1',
        'authority':'Anthony, Human Owner', 'environment':'TEST_ONLY',
        'state':'ACTIVE', 'current_key_version':1,
        'scope':binding._ibkr_trust_scope(), 'signature_algorithm':binding._IBKR_SIGNATURE_ALGORITHM,
        'keys':[{'key_id':binding._IBKR_OWNER_KEY_ID, 'key_version':1,
                 'key_fingerprint_sha256':fingerprint, 'status':'ACTIVE',
                 'public_key_blob_base64':base64.b64encode(signer.public_blob).decode(),
                 'created_at_utc':'2026-10-13T14:59:00Z'}],
    }
    chain = [
        'IBKR_PREFLIGHT_ONLY_V1',
        'BINDING_SHA256=' + hashlib.sha256(MODULE.read_bytes()).hexdigest(),
        'RUNTIME_SHA256=a791097eb5641672fca20077f88460e917137bcbc7b32f2e15c805cc026358b9',
        'RISK_POLICY_SHA256=f4a261c4d59c7ba05ce88760343895ab40c292aba7531f5db17071df641d6402',
        'PRIVACY_SHA256=a667db0c649626a2f628ff0efcc46345c0b3630a39bc6db92d9e41b4ed309b7e',
        'READ_ONLY_LOOPBACK_127.0.0.1:7496_CLIENT132',
        'NO_BROKER_CONNECTION_OR_REQUESTS',
    ]
    gate = {
        'schema':'AIOS_HUMAN_OWNER_APPROVAL_PAYLOAD.v1',
        'approval_gate_id':'FIXTURE_ONLY_IBKR_PREFLIGHT_' + 'a' * 32,
        'packet_id':'PKT-EAST-FOREX-IBKR-FIRST-READ-ONLY-HANDSHAKE-V1',
        'requested_action':'IBKR_READ_ONLY_PREFLIGHT', 'requested_mode':'APPLY',
        'allowed_paths':['automation/forex_engine/ibkr_sdk_privacy_binding_v1.py'],
        'blocked_paths':['broker','credentials','historical_requests','market_data',
                         'orders','account_requests','portfolio_requests','streaming'],
        'validator_chain':chain,
        'approval_status':'approved_for_apply', 'approved_by_human':True,
        'approval_timestamp_utc':'2026-10-13T14:59:30Z',
        'expires_at_utc':'2026-10-13T15:04:30Z',
        'approval_evidence':{
            'type':binding._IBKR_SIGNATURE_ALGORITHM,
            'canonical_payload_schema':'AIOS_HUMAN_OWNER_APPROVAL_PAYLOAD.v1',
            'approval_nonce':'FIXTURE_ONLY_' + 'b' * 32,
            'key_id':binding._IBKR_OWNER_KEY_ID, 'key_version':1,
            'key_fingerprint_sha256':fingerprint,
            'canonical_payload_sha256':'', 'approval_signature_base64':'',
        },
    }
    def sign():
        gate['approval_evidence']['canonical_payload_sha256'] = hashlib.sha256(
            verifier.canonical_payload(gate).encode()).hexdigest()
        gate['approval_evidence']['approval_signature_base64'] = base64.b64encode(signer.sign_digest(bytes.fromhex(gate['approval_evidence']['canonical_payload_sha256']))).decode()
    sign()
    monkeypatch.setattr(binding, '_owner_trust', lambda: trust, raising=False)
    monkeypatch.setattr(binding, '_utc_now', lambda: now, raising=False)
    try:
        yield binding, gate, key, trust, sign
    finally:
        signer.close()


def test_activation_bridge_signed_fixture_enables_preflight_only(activation_fixture):
    binding, gate, key, _, _ = activation_fixture
    before = set(sys.modules)
    result = binding.SdkProbe().readiness(activation=gate)
    assert result == {'status':'READY_FIXTURE_PREFLIGHT_ONLY', 'reason':'NONE',
                      'authorization_kind':'FIXTURE_ONLY', 'connection_authorized':False}
    assert not [n for n in set(sys.modules)-before if n.startswith(('ibapi','google.protobuf'))]


def test_activation_bridge_never_arms_probe_or_consumes_a_handshake(activation_fixture):
    binding, gate, key, _, _ = activation_fixture
    probe = binding.SdkProbe()
    assert probe.readiness(activation=gate)['status'] == 'READY_FIXTURE_PREFLIGHT_ONLY'
    assert probe.probe() == {'status':'BLOCKED','reason':'CONNECTION_AUTHORITY_UNAVAILABLE'}
    assert probe.readiness() == probe.probe()
    assert not hasattr(probe, '__dict__')


@pytest.mark.parametrize('mutation', [
    'signature','payload_hash','wrong_key','missing_key','expired','future',
    'oversized_window','action','mode','packet','allowed_paths','blocked_paths',
    'source_pin','runtime_pin','policy_pin','privacy_pin','endpoint','business_scope',
    'extra_field','not_human','unknown_key','revoked_key','revoked_trust','fixture_promoted',
])
def test_activation_bridge_rejects_invalid_authority_even_when_resigned(activation_fixture, mutation):
    binding, gate, key, trust, sign = activation_fixture
    if mutation == 'signature':
        gate['approval_evidence']['approval_signature_base64'] = '0' * 64
    elif mutation == 'payload_hash':
        gate['approval_evidence']['canonical_payload_sha256'] = '0' * 64
    elif mutation == 'wrong_key':
        trust['keys'][0]['public_key_blob_base64'] = 'INVALID'
    elif mutation == 'missing_key':
        trust['keys'][0].pop('public_key_blob_base64')
    else:
        if mutation == 'expired': gate['expires_at_utc'] = '2026-10-13T15:00:00Z'
        elif mutation == 'future': gate['approval_timestamp_utc'] = '2026-10-13T15:00:01Z'
        elif mutation == 'oversized_window': gate['expires_at_utc'] = '2026-10-13T16:00:00Z'
        elif mutation == 'action': gate['requested_action'] = 'IBKR_CONNECT'
        elif mutation == 'mode': gate['requested_mode'] = 'LIVE'
        elif mutation == 'packet': gate['packet_id'] = 'UNRELATED_PACKET'
        elif mutation == 'allowed_paths': gate['allowed_paths'].append('broker')
        elif mutation == 'blocked_paths': gate['blocked_paths'].remove('orders')
        elif mutation.endswith('_pin'):
            index = {'source_pin':1,'runtime_pin':2,'policy_pin':3,'privacy_pin':4}[mutation]
            gate['validator_chain'][index] = gate['validator_chain'][index].split('=')[0] + '=' + '0' * 64
        elif mutation == 'endpoint': gate['validator_chain'][5] = 'READ_ONLY_LOOPBACK_127.0.0.1:7497_CLIENT132'
        elif mutation == 'business_scope': gate['validator_chain'].append('ORDER_ALLOWED')
        elif mutation == 'extra_field': gate['orders_allowed'] = True
        elif mutation == 'not_human': gate['approved_by_human'] = False
        elif mutation == 'unknown_key': gate['approval_evidence']['key_id'] = 'FIXTURE_ONLY_UNKNOWN'
        elif mutation == 'revoked_key': trust['keys'][0]['status'] = 'REVOKED'
        elif mutation == 'revoked_trust': trust['state'] = 'REVOKED'
        elif mutation == 'fixture_promoted': trust['environment'] = 'PRODUCTION'
        sign()
    result = binding.SdkProbe().readiness(activation=gate)
    assert result == {'status':'BLOCKED','reason':'ACTIVATION_REFUSED','connection_authorized':False}


@pytest.mark.parametrize('activation', [True, {}, {'approved':True}, 'ADMITTED', 'FIXTURE_ONLY'])
def test_activation_bridge_rejects_unsigned_caller_flags(activation):
    assert load_binding().SdkProbe().readiness(activation=activation)['status'] == 'BLOCKED'


def test_activation_bridge_does_not_log_write_connect_or_construct_sdk(activation_fixture, monkeypatch, capsys):
    import socket
    binding, gate, key, _, _ = activation_fixture
    def refuse(*args, **kwargs):
        raise AssertionError('FORBIDDEN_SIDE_EFFECT')
    monkeypatch.setattr(socket, 'socket', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(Path, 'write_text', refuse)
    monkeypatch.setattr(Path, 'write_bytes', refuse)
    monkeypatch.setattr(binding, '_run_private', refuse)
    original = list(sys.path)
    first = binding.SdkProbe().readiness(activation=gate)
    second = binding.SdkProbe().readiness(activation=gate)
    assert first == second and first['status'] == 'READY_FIXTURE_PREFLIGHT_ONLY'
    assert sys.path == original
    captured = capsys.readouterr()
    assert captured.out == captured.err == ''
    assert key not in repr(first)


def test_activation_bridge_uses_pinned_production_trust_not_a_caller_root(activation_fixture, monkeypatch):
    binding, gate, key, _, _ = activation_fixture
    monkeypatch.undo()
    assert binding.SdkProbe().readiness(activation=gate)['status'] == 'BLOCKED'


def test_activation_bridge_handles_verifier_failure_without_foreign_diagnostics(activation_fixture, monkeypatch, capsys):
    binding, gate, key, _, _ = activation_fixture
    def broken():
        raise RuntimeError('FIXTURE_ONLY_PRIVATE_DIAGNOSTIC')
    monkeypatch.setattr(binding, '_owner_verifier', broken, raising=False)
    result = binding.SdkProbe().readiness(activation=gate)
    assert result['status'] == 'BLOCKED'
    assert 'FIXTURE_ONLY_PRIVATE_DIAGNOSTIC' not in repr(result)
    assert capsys.readouterr().out == ''


# M8B: signed authority below is synthetic; all native broker I/O is replaced.
@pytest.fixture
def one_shot_fixture(activation_fixture, monkeypatch):
    import hashlib
    binding, gate, key, trust, sign = activation_fixture
    trust['environment'] = 'PRODUCTION'
    gate['approval_evidence']['approval_nonce'] = 'SYNTHETIC_M8B_' + 'c' * 32
    gate['approval_gate_id'] = 'IBKR_HANDSHAKE_' + 'd' * 32
    gate['requested_action'] = 'IBKR_READ_ONLY_HANDSHAKE'
    gate['blocked_paths'] = ['credentials','historical_requests','market_data','orders',
        'account_requests','portfolio_requests','positions','scanners','news','streaming',
        'retry','reconnect']
    host = {
        'schema':'IBKR_HOST_QUALIFICATION.v1',
        'qualified_at_utc':'2026-10-13T14:59:30Z',
        'expires_at_utc':'2026-10-13T15:04:30Z',
        'tws_running':True, 'paper_logged_in':True, 'read_only_api':True,
        'localhost_only':True, 'auto_binding_blocked_for_client132':True, 'master_api_client_id_blank':True,
        'client132_unused_nonmaster':True, 'port':7496, 'client_id':132,
        'tws_build':'10.51', 'owner_host_storage_risk_accepted':True,
        'storage_controls':{name:'OWNER_ACCEPTED_RESIDUAL_RISK' for name in
            ('paging','dumps','crash_handlers','hibernation','debugger_telemetry','vendor_logs')},
    }
    probe = binding.SdkProbe()
    context = probe.execution_context()
    def sign_handshake():
        def sha(value):
            return hashlib.sha256(json.dumps(value,sort_keys=True,
                separators=(',',':')).encode()).hexdigest()
        gate['validator_chain'] = [
            'IBKR_ONE_SHOT_HANDSHAKE_V1',
            'BINDING_SHA256=' + hashlib.sha256(MODULE.read_bytes()).hexdigest(),
            'RUNTIME_SHA256=a791097eb5641672fca20077f88460e917137bcbc7b32f2e15c805cc026358b9',
            'RISK_POLICY_SHA256=' + binding._RISK_SHA,
            'PRIVACY_SHA256=a667db0c649626a2f628ff0efcc46345c0b3630a39bc6db92d9e41b4ed309b7e',
            'IBKR_TRUST_SHA256=' + binding._TRUST_SHA,
            'EXECUTION_LEASE_SHA256=' + 'e' * 64,
            'HOST_EVIDENCE_SHA256=' + sha(host),
            'EXECUTION_CONTEXT_SHA256=' + sha(context),
            'READ_ONLY_LOOPBACK_127.0.0.1:7496_CLIENT132',
            'MAX_ATTEMPTS=1_STARTUP10_CLEANUP2_WATCHDOG30',
            'NO_BUSINESS_REQUESTS_RETRY_RECONNECT',
            'STOP_AFTER_DISCONNECT',
        ]
        sign()
    monkeypatch.setattr(binding, '_handshake_lock_current', lambda: True, raising=False)
    monkeypatch.setattr(binding, '_handshake_lease_hash', lambda: 'e' * 64)
    sign_handshake()
    sign_handshake.resign = sign
    return binding, probe, gate, key, host, context, trust, sign_handshake


def test_one_shot_context_is_instance_and_process_bound():
    binding = load_binding()
    first = binding.SdkProbe(); second = binding.SdkProbe()
    a = first.execution_context(); b = second.execution_context()
    assert a['parent_pid'] == os.getpid()
    assert a['nonce'] != b['nonce']
    assert first.execution_context() == a
    a['nonce'] = '0' * 64
    assert first.execution_context()['nonce'] != a['nonce']
    assert not hasattr(first, '__dict__')


def test_one_shot_preflight_grant_cannot_launch(activation_fixture, monkeypatch):
    binding, gate, key, _, _ = activation_fixture
    launched = []
    monkeypatch.setattr(binding, '_launch_handshake_worker', lambda *a: launched.append(a), raising=False)
    result = binding.SdkProbe().probe(activation=gate, host_evidence={})
    assert result['status'] == 'BLOCKED'
    assert launched == []


def test_one_shot_signed_fixture_never_promotes_to_connection(one_shot_fixture, monkeypatch):
    binding, probe, gate, key, host, _, trust, sign = one_shot_fixture
    trust['environment'] = 'TEST_ONLY'
    sign()
    launched = []
    monkeypatch.setattr(binding, '_launch_handshake_worker', lambda *a: launched.append(a), raising=False)
    assert probe.probe(activation=gate,host_evidence=host)['status'] == 'BLOCKED'
    assert launched == []


def test_one_shot_valid_grant_dispatches_once_and_releases_signing_references(one_shot_fixture, monkeypatch):
    binding, probe, gate, key, host, _, _, _ = one_shot_fixture
    calls = []
    result = {'status':'BLOCKED','reason':'DEADLINE_EXCEEDED',
              'sdk_version':'1051.1','server_version':0,'accounts_seen':False,
              'id_seen':False,'cleanup_verified':True,'initialization_envelopes':0}
    def worker(*args):
        calls.append(args)
        return dict(result)
    monkeypatch.setattr(binding, '_launch_handshake_worker', worker, raising=False)
    assert probe.probe(activation=gate,host_evidence=host) == result
    second = probe.probe(activation=gate,host_evidence=host)
    assert second['status'] == 'BLOCKED' and second['reason'] == 'ATTEMPT_ALREADY_CONSUMED'
    assert len(calls) == 1
    assert key not in repr(probe)
    assert all(not isinstance(getattr(probe,name),str) or getattr(probe,name)!=key
               for name in probe.__slots__)


def test_one_shot_grant_for_another_instance_is_refused(one_shot_fixture, monkeypatch):
    binding, _, gate, key, host, _, _, _ = one_shot_fixture
    calls = []
    monkeypatch.setattr(binding, '_launch_handshake_worker', lambda *a:calls.append(a), raising=False)
    assert binding.SdkProbe().probe(activation=gate,host_evidence=host)['status']=='BLOCKED'
    assert calls == []


@pytest.mark.parametrize('mutation', [
    'missing_key','wrong_key','signature','action','packet','mode','expired',
    'short_window','future','unsigned_business_scope','wrong_port','wrong_client',
    'paper','readonly','localhost','openorders','client_in_use','host_expired',
    'host_future','unaccepted_storage','unknown_control','host_extra','tws_build',
    'context_pid','context_nonce','no_packet_lock','policy_pin','source_pin',
])
def test_one_shot_invalid_authority_never_spawns_even_if_resigned(one_shot_fixture, monkeypatch, mutation):
    binding, probe, gate, key, host, context, trust, sign = one_shot_fixture
    if mutation=='missing_key': trust['keys'][0].pop('public_key_blob_base64')
    elif mutation=='wrong_key': trust['keys'][0]['public_key_blob_base64']='INVALID'
    elif mutation=='signature': gate['approval_evidence']['approval_signature_base64']='0'*64
    else:
        if mutation=='action': gate['requested_action']='IBKR_READ_ONLY_PREFLIGHT'
        elif mutation=='packet': gate['packet_id']='UNRELATED'
        elif mutation=='mode': gate['requested_mode']='LIVE'
        elif mutation=='expired': gate['expires_at_utc']='2026-10-13T15:00:00Z'
        elif mutation=='short_window': gate['expires_at_utc']='2026-10-13T15:00:10Z'
        elif mutation=='future': gate['approval_timestamp_utc']='2026-10-13T15:00:01Z'
        elif mutation=='unsigned_business_scope': gate['blocked_paths'].remove('orders')
        elif mutation=='wrong_port': host['port']=7497
        elif mutation=='wrong_client': host['client_id']=0
        elif mutation=='paper': host['paper_logged_in']=False
        elif mutation=='readonly': host['read_only_api']=False
        elif mutation=='localhost': host['localhost_only']=False
        elif mutation=='openorders': host['auto_binding_blocked_for_client132']=False
        elif mutation=='client_in_use': host['client132_unused_nonmaster']=False
        elif mutation=='host_expired': host['expires_at_utc']='2026-10-13T15:00:00Z'
        elif mutation=='host_future': host['qualified_at_utc']='2026-10-13T15:00:01Z'
        elif mutation=='unaccepted_storage': host['owner_host_storage_risk_accepted']=False
        elif mutation=='unknown_control': host['storage_controls']['paging']='UNKNOWN'
        elif mutation=='host_extra': host['accounts']='SYNTHETIC_PRIVATE_CANARY'
        elif mutation=='tws_build': host['tws_build']='SYNTHETIC_PRIVATE_CANARY'
        elif mutation=='context_pid': context['parent_pid']+=1
        elif mutation=='context_nonce': context['nonce']='0'*64
        elif mutation=='no_packet_lock': monkeypatch.setattr(binding,'_handshake_lock_current',lambda:False)
        sign()
        if mutation in ('policy_pin','source_pin'):
            index=3 if mutation=='policy_pin' else 1
            gate['validator_chain'][index]=gate['validator_chain'][index].split('=')[0]+'='+'0'*64
            # Resign the mutated chain with the real canonical verifier.
            sign.resign()
    calls=[]
    monkeypatch.setattr(binding,'_launch_handshake_worker',lambda *a:calls.append(a),raising=False)
    result=probe.probe(activation=gate,host_evidence=host)
    assert result['status']=='BLOCKED' and calls==[]


@pytest.mark.parametrize('mutation', ['extra','private_reason','version_bool','missing_cleanup','too_many_sends','oversized','not_json','nonzero_exit'])
def test_one_shot_worker_receipt_rejects_foreign_or_private_output(mutation):
    binding=load_binding()
    result={'status':'VERIFIED_HANDSHAKE','reason':'NONE','sdk_version':'1051.1',
        'server_version':213,'accounts_seen':True,'id_seen':True,
        'cleanup_verified':True,'initialization_envelopes':2,'failure_site':'NONE'}
    code=0
    if mutation=='extra': result['account']='SYNTHETIC_PRIVATE_CANARY'
    elif mutation=='private_reason': result['reason']='SYNTHETIC_PRIVATE_CANARY'
    elif mutation=='version_bool': result['server_version']=True
    elif mutation=='missing_cleanup': result['cleanup_verified']=False
    elif mutation=='too_many_sends': result['initialization_envelopes']=3
    elif mutation=='nonzero_exit': code=1
    data=json.dumps(result).encode()
    if mutation=='oversized': data=b'X'*1025
    elif mutation=='not_json': data=b'SYNTHETIC_PRIVATE_CANARY'
    answer=binding._decode_handshake_receipt(data,code)
    assert answer['status']=='BLOCKED'
    assert 'SYNTHETIC_PRIVATE_CANARY' not in repr(answer)


def test_one_shot_native_permit_allows_one_exact_socket_and_connect():
    binding=load_binding()
    permit=binding._NativeSocketPermit(binding._NATIVE_PERMIT_TOKEN)
    sock=object(); other=object()
    permit.audit('socket.__new__',(sock,2,1,0))
    permit.audit('socket.connect',(sock,('127.0.0.1',7496)))
    for event,args in [('socket.__new__',(other,2,1,0)),
                       ('socket.connect',(sock,('127.0.0.1',7496))),
                       ('socket.connect',(other,('127.0.0.1',7496))),
                       ('socket.getaddrinfo',('localhost',7496,0,0,0)),
                       ('socket.bind',(sock,('127.0.0.1',0)))]:
        with pytest.raises(binding._Refused):
            permit.audit(event,args)


@pytest.mark.parametrize('address',[('localhost',7496),('127.0.0.1',7497),('8.8.8.8',7496)])
def test_one_shot_native_permit_refuses_any_other_endpoint(address):
    binding=load_binding(); permit=binding._NativeSocketPermit(binding._NATIVE_PERMIT_TOKEN)
    sock=object();permit.audit('socket.__new__',(sock,2,1,0))
    with pytest.raises(binding._Refused):
        permit.audit('socket.connect',(sock,address))


def test_one_shot_native_permit_expiry_and_unissued_token_fail_closed(monkeypatch):
    binding=load_binding()
    with pytest.raises(binding._Refused):
        binding._NativeSocketPermit(object())
    clock=[100.0];monkeypatch.setattr(binding,'_now',lambda:clock[0])
    permit=binding._NativeSocketPermit(binding._NATIVE_PERMIT_TOKEN)
    clock[0]=111.0
    with pytest.raises(binding._Refused):
        permit.audit('socket.__new__',(object(),2,1,0))


def test_one_shot_child_entry_without_authority_is_sanitized_and_cannot_connect():
    proc=subprocess.run([sys.executable,'-I','-S','-B',str(MODULE),'--ibkr-handshake-worker'],
        input=b'{"activation":true}',capture_output=True,timeout=5)
    assert proc.returncode==0
    result=json.loads(proc.stdout)
    assert result['status']=='BLOCKED'
    assert result['server_version']==0 and result['initialization_envelopes']==0
    assert proc.stderr==b''


def test_one_shot_launcher_uses_volatile_pipe_and_fixed_isolated_child(one_shot_fixture,monkeypatch):
    binding, _, gate, key, host, context, _, _=one_shot_fixture
    captured={}
    receipt={'status':'VERIFIED_HANDSHAKE','reason':'NONE','sdk_version':'1051.1',
        'server_version':213,'accounts_seen':True,'id_seen':True,'cleanup_verified':True,
        'initialization_envelopes':2,'failure_site':'NONE'}
    class Child:
        returncode=0
        def communicate(self,input=None,timeout=None):
            captured['input']=input;captured['timeout']=timeout
            return json.dumps(receipt).encode(),b''
        def poll(self):return 0
        def wait(self,timeout=None):return 0
    def spawn(args,**kwargs):
        captured['args']=args;captured['kwargs']=kwargs
        return Child()
    monkeypatch.setattr(subprocess,'Popen',spawn)
    result=binding._launch_handshake_worker(gate,host,context)
    assert result==receipt
    assert captured['args'][1:4]==['-I','-S','-B']
    assert captured['args'][-1]=='--ibkr-handshake-worker'
    assert key not in repr(captured['args'])+repr(captured['kwargs'])
    assert captured['kwargs']['stdin']==subprocess.PIPE
    assert 0 < captured['timeout'] <= 28
    assert set(json.loads(captured['input'])) == {'activation','host_evidence','context'}
    assert key.encode() not in captured['input']


def test_one_shot_launcher_timeout_kills_only_its_child_and_never_retries(one_shot_fixture,monkeypatch):
    binding, _, gate, key, host, context, _, _=one_shot_fixture
    children=[]
    class Child:
        returncode=None
        killed=False
        def communicate(self,input=None,timeout=None):
            raise subprocess.TimeoutExpired('SYNTHETIC_PRIVATE_CANARY',timeout)
        def poll(self):return self.returncode
        def kill(self):self.killed=True;self.returncode=-9
        def wait(self,timeout=None):return self.returncode
    def spawn(*args,**kwargs):
        child=Child();children.append(child);return child
    monkeypatch.setattr(subprocess,'Popen',spawn)
    result=binding._launch_handshake_worker(gate,host,context)
    assert result['status']=='BLOCKED' and result['reason']=='DEADLINE_EXCEEDED'
    assert len(children)==1 and children[0].killed
    assert 'SYNTHETIC_PRIVATE_CANARY' not in repr(result)


def test_one_shot_launcher_parent_identity_survives_windows_redirector(one_shot_fixture,monkeypatch):
    binding, _, gate, key, host, context, _, _=one_shot_fixture
    original=subprocess.Popen
    parent_ids=[]
    receipt={'status':'BLOCKED','reason':'ACTIVATION_REFUSED','sdk_version':'1051.1',
        'server_version':0,'accounts_seen':False,'id_seen':False,'cleanup_verified':False,
        'initialization_envelopes':0}
    class ReceiptChild:
        returncode=0
        def communicate(self,input=None,timeout=None):return json.dumps(receipt).encode(),b''
        def poll(self):return 0
        def wait(self,timeout=None):return 0
    def spawn(args,**kwargs):
        child=original([args[0],'-I','-S','-B','-c','import os;print(os.getppid())'],
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        output,error=child.communicate(timeout=5)
        assert child.returncode==0 and error==b''
        parent_ids.append(int(output))
        return ReceiptChild()
    monkeypatch.setattr(subprocess,'Popen',spawn)
    binding._launch_handshake_worker(gate,host,context)
    assert parent_ids==[os.getpid()]


def test_one_shot_unissued_worker_guard_cannot_be_consumed():
    binding=load_binding()
    context=binding.SdkProbe().execution_context()
    assert binding._consume_attempt_guard(context) is False


def test_one_shot_raw_worker_bootstrap_is_consumed_across_fresh_processes():
    binding=load_binding()
    context=binding.SdkProbe().execution_context()
    assert binding._attempt_guard_create(context) is True
    code = (
        "import importlib.util,json;"
        "s=importlib.util.spec_from_file_location('offline_guard',"+repr(str(MODULE))+");"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        "c=json.loads("+repr(json.dumps(context))+");"
        "print(json.dumps(m._consume_attempt_guard(c)))"
    )
    results=[]
    for _ in range(2):
        proc=subprocess.run([sys._base_executable,'-I','-S','-B','-c',code],
                            capture_output=True,timeout=5)
        assert proc.returncode==0 and proc.stderr==b''
        results.append(json.loads(proc.stdout))
    assert results==[True,False]
    assert binding._attempt_guard_create(context) is True
    assert binding._consume_attempt_guard(context) is False


def test_one_shot_failed_launch_burns_worker_bootstrap(one_shot_fixture,monkeypatch):
    binding, _, gate, key, host, context, _, _=one_shot_fixture
    def fail(*args,**kwargs):raise OSError('SYNTHETIC_PRIVATE_CANARY')
    monkeypatch.setattr(subprocess,'Popen',fail)
    result=binding._launch_handshake_worker(gate,host,context)
    assert result['status']=='BLOCKED'
    assert binding._consume_attempt_guard(context) is False
    assert 'SYNTHETIC_PRIVATE_CANARY' not in repr(result)


# Current TWS launcher release label includes its vendor suffix.
def test_one_shot_authority_accepts_current_tws_release_build(one_shot_fixture):
    binding, probe, gate, key, host, context, trust, sign = one_shot_fixture
    host['tws_build'] = '10.51.1b'
    sign()
    assert binding._authorize_handshake(gate, host, context) is True
    assert probe._consumed is False
    assert (context['parent_pid'], context['nonce']) not in binding._CONSUMED_CONTEXTS


def test_one_shot_release_build_change_requires_new_signature(one_shot_fixture):
    binding, _, gate, key, host, context, _, _ = one_shot_fixture
    host['tws_build'] = '10.51.1b'
    assert binding._authorize_handshake(gate, host, context) is False


@pytest.mark.parametrize('build', [
    '10.51.1bb', '10.51.1b extra', '10.51.1b\n', '1051.1b',
    'latest (10.51.1b)', '10.51.1b;run', '10.51.1B',
])
def test_one_shot_release_build_rejects_malformed_labels_even_when_signed(
        one_shot_fixture, build):
    binding, _, gate, key, host, context, _, sign = one_shot_fixture
    host['tws_build'] = build
    sign()
    assert binding._authorize_handshake(gate, host, context) is False


def synthetic_p256_signer(binding):
    # Public, fixed scalar 1 fixture; never used as an owner key.
    import ctypes
    api = binding._CngP256()
    x = bytes.fromhex('6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296')
    y = bytes.fromhex('4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5')
    public = struct.pack('<II', 0x31534345, 32) + x + y
    private = bytearray(struct.pack('<II', 0x32534345, 32) + x + y + bytes(31) + b'\x01')
    handle = ctypes.c_void_p()
    buf = (ctypes.c_ubyte * len(private)).from_buffer(private)
    try:
        api.check(api.dll.BCryptImportKeyPair(api.provider, None, 'ECCPRIVATEBLOB',
            ctypes.byref(handle), buf, len(private), 0))
        return binding._P256OwnerKey(api, handle, public)
    except BaseException:
        api.close()
        raise
    finally:
        private[:] = bytes(len(private))
        del buf
        private.clear()


def test_scoped_trust_p256_native_signature_and_public_only_verification():
    binding = load_binding()
    assert hasattr(binding, '_CngP256'), 'Approved P256 backend is missing'
    signer = synthetic_p256_signer(binding)
    try:
        digest = bytes(range(32))
        signature = signer.sign_digest(digest)
        assert len(signature) == 64
        assert binding._verify_p256(signer.public_blob, digest, signature) is True
        assert binding._verify_p256(signer.public_blob, bytes(32), signature) is False
        assert binding._verify_p256(signer.public_blob, digest, signature[:-1]) is False
        assert binding._verify_p256(b'invalid', digest, signature) is False
    finally:
        signer.close()
    with pytest.raises(ValueError):
        signer.sign_digest(bytes(32))


def test_scoped_trust_raw_secret_inputs_are_refused_before_attempt(monkeypatch):
    binding = load_binding()
    probe = binding.SdkProbe()
    monkeypatch.setattr(binding, '_authorize_handshake', lambda *a, **k: True)
    monkeypatch.setattr(binding, '_launch_handshake_worker',
                        lambda *a, **k: pytest.fail('worker launched'))
    result = probe.probe(activation={}, owner_key='SYNTHETIC_NOT_AN_OWNER_KEY', host_evidence={})
    assert result['status'] == 'BLOCKED'
    assert probe._consumed is False


def test_scoped_trust_owner_session_requires_local_terminal_before_generation(monkeypatch):
    binding = load_binding()
    assert hasattr(binding, '_owner_key_session_main'), 'Owner session is missing'
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: False)
    assert binding._owner_key_session_main() == 2


@pytest.mark.parametrize('mutation', [
    'scope_packet','scope_action','scope_path','algorithm','global_identity',
    'fingerprint','public_fingerprint','bool_version','unprovisioned','missing_signature',
])
def test_scoped_trust_rejects_cross_scope_or_unactivated_metadata(activation_fixture, mutation):
    binding, gate, _, trust, sign = activation_fixture
    if mutation == 'scope_packet': trust['scope']['packet_id'] = 'UNRELATED'
    elif mutation == 'scope_action': trust['scope']['allowed_actions'].append('ORDERS')
    elif mutation == 'scope_path': trust['scope']['allowed_paths'].append('RISK_POLICY.md')
    elif mutation == 'algorithm': trust['signature_algorithm'] = 'HMAC_SHA256'
    elif mutation == 'global_identity': gate['approval_evidence']['key_id'] = 'AIOS-HUMAN-OWNER-PRIMARY-V1'
    elif mutation == 'fingerprint': gate['approval_evidence']['key_fingerprint_sha256'] = '0' * 64
    elif mutation == 'public_fingerprint': trust['keys'][0]['key_fingerprint_sha256'] = '0' * 64
    elif mutation == 'bool_version': gate['approval_evidence']['key_version'] = True
    elif mutation == 'unprovisioned': trust.update(state='UNPROVISIONED',current_key_version=0,keys=[])
    elif mutation == 'missing_signature': gate['approval_evidence'].pop('approval_signature_base64')
    if mutation not in ('missing_signature',): sign()
    assert binding.SdkProbe().readiness(activation=gate)['status'] == 'BLOCKED'


def test_scoped_trust_disk_metadata_is_public_and_default_blocked():
    import hashlib
    binding = load_binding()
    trust = binding._owner_trust()
    assert binding._owner_verifier().validate_trust_metadata(trust) == []
    for record in trust['keys']:
        assert record['key_id'] == binding._IBKR_OWNER_KEY_ID
        public = binding._public_p256_blob(record['public_key_blob_base64'])
        assert hashlib.sha256(public).hexdigest() == record['key_fingerprint_sha256']
    assert trust['scope'] == binding._ibkr_trust_scope()
    assert binding.SdkProbe().probe()['status'] == 'BLOCKED'
    assert binding.SdkProbe().readiness(activation={})['status'] == 'BLOCKED'


def test_scoped_trust_signer_cannot_be_serialized_or_used_from_another_process(monkeypatch):
    import pickle
    binding = load_binding()
    signer = synthetic_p256_signer(binding)
    try:
        with pytest.raises(TypeError): pickle.dumps(signer)
        monkeypatch.setattr(os, 'getpid', lambda: signer._pid + 1)
        with pytest.raises(ValueError): signer.sign_digest(bytes(32))
    finally:
        signer.close()


@pytest.mark.parametrize('confirmed', [True, False])
def test_owner_key_session_one_local_ceremony_and_cleanup_without_grant(
        monkeypatch, capsys, confirmed):
    import builtins
    import msvcrt
    from types import SimpleNamespace
    binding = load_binding()
    calls = {'generate':0, 'sign':0, 'verify':0, 'close':0}
    signer = synthetic_p256_signer(binding)
    class FixtureSigner:
        public_blob = signer.public_blob
        key_version = binding._IBKR_CEREMONY_KEY_VERSION
        def sign_digest(self, digest):
            calls['sign'] += 1
            return signer.sign_digest(digest)
        def close(self):
            calls['close'] += 1
            signer.close()
    def generate():
        calls['generate'] += 1
        return FixtureSigner()
    verify = binding._verify_p256
    def verify_once(*args):
        calls['verify'] += 1
        return verify(*args)
    monkeypatch.setattr(binding._P256OwnerKey,'generate',generate)
    monkeypatch.setattr(binding,'_verify_p256',verify_once)
    monkeypatch.setattr(sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(sys.stdout,'isatty',lambda:True)
    monkeypatch.setattr(sys,'flags',SimpleNamespace(isolated=True,no_site=True))
    monkeypatch.setattr(sys,'dont_write_bytecode',True)
    monkeypatch.setattr(builtins,'input',lambda *_: 'GENERATE IBKR OWNER KEY' if confirmed else 'NO')
    chars=iter('EXIT\r')
    monkeypatch.setattr(msvcrt,'kbhit',lambda:True)
    monkeypatch.setattr(msvcrt,'getwch',lambda:next(chars))
    monkeypatch.setattr(binding.time,'sleep',lambda *_:None)
    monkeypatch.setattr(binding,'_launch_handshake_worker',lambda *a:pytest.fail('worker'))
    monkeypatch.setattr(Path,'write_bytes',lambda *a:pytest.fail('write'))
    monkeypatch.setattr(Path,'write_text',lambda *a:pytest.fail('write'))
    try:
        assert binding._owner_key_session_main() == (0 if confirmed else 2)
        output=capsys.readouterr().out
        if confirmed:
            receipt=json.JSONDecoder().raw_decode(output)[0]
            assert set(receipt)=={'KEY IDENTITY FOUND','SIGNING CHANNEL FOUND',
                'SYNTHETIC SIGNATURE VERIFIED','PUBLIC FINGERPRINT','SECRET PERSISTED'}
            assert receipt['SYNTHETIC SIGNATURE VERIFIED']=='YES'
            assert receipt['SECRET PERSISTED']=='NO'
            assert calls=={'generate':1,'sign':1,'verify':1,'close':1}
        else:
            assert output==''
            assert calls=={'generate':0,'sign':0,'verify':0,'close':0}
    finally:
        signer.close()


def test_one_shot_master_client_must_remain_blank_even_with_new_signature(one_shot_fixture):
    binding, _, gate, _, host, context, _, sign = one_shot_fixture
    host['master_api_client_id_blank'] = False
    sign()
    assert binding._authorize_handshake(gate, host, context) is False


def test_scoped_trust_future_owner_signs_public_grant_with_retained_key(one_shot_fixture):
    binding, _, gate, _, host, context, _, sign = one_shot_fixture
    import copy
    # Recover the fixed scalar fixture signer only for this synthetic test.
    signer=synthetic_p256_signer(binding)
    try:
        candidate=copy.deepcopy(gate)
        candidate['approval_evidence']['approval_signature_base64']=''
        candidate['approval_evidence']['canonical_payload_sha256']=''
        signed=binding._owner_sign_handshake_grant(signer,
            {'activation':candidate,'host_evidence':host,'context':context})
        assert binding._authorize_handshake(signed,host,context) is True
        assert not binding._CONSUMED_CONTEXTS
    finally:
        signer.close()


@pytest.mark.parametrize('mutation',['unprovisioned','mismatched_public','stale_host','no_lease'])
def test_scoped_trust_owner_signing_refuses_before_signing(one_shot_fixture,monkeypatch,mutation):
    import copy,base64
    binding, _, gate, _, host, context, trust, _ = one_shot_fixture
    candidate=copy.deepcopy(gate)
    candidate['approval_evidence']['approval_signature_base64']=''
    candidate['approval_evidence']['canonical_payload_sha256']=''
    class Signer:
        key_version=1
        public_blob=base64.b64decode(trust['keys'][0]['public_key_blob_base64'])
        def sign_digest(self,*args):pytest.fail('signing before qualification')
    if mutation=='unprovisioned':trust.update(state='UNPROVISIONED',keys=[],current_key_version=0)
    elif mutation=='mismatched_public':Signer.public_blob=b'INVALID'
    elif mutation=='stale_host':host['expires_at_utc']='2026-10-13T15:00:00Z'
    elif mutation=='no_lease':monkeypatch.setattr(binding,'_handshake_lock_current',lambda:False)
    with pytest.raises(ValueError):
        binding._owner_sign_handshake_grant(Signer(),
            {'activation':candidate,'host_evidence':host,'context':context})


def test_one_shot_new_execution_lease_requires_new_signature(one_shot_fixture,monkeypatch):
    binding, _, gate, _, host, context, _, _ = one_shot_fixture
    monkeypatch.setattr(binding,'_handshake_lease_hash',lambda:'f'*64)
    assert binding._authorize_handshake(gate,host,context) is False


def test_scoped_trust_owner_retains_key_across_reviewed_public_activation(
        activation_fixture, monkeypatch):
    import base64,hashlib
    binding, _, _, trust, _ = activation_fixture
    trust['environment']='PRODUCTION'
    public=base64.b64decode(trust['keys'][0]['public_key_blob_base64'])
    trust_raw=(json.dumps(trust,indent=2)+'\n').encode()
    trust_digest=hashlib.sha256(trust_raw).hexdigest()
    original_raw=MODULE.read_bytes()
    reviewed_raw=original_raw.replace(binding._TRUST_SHA.encode(),trust_digest.encode())
    reviewed_digest=hashlib.sha256(reviewed_raw).hexdigest()
    original_read=Path.read_bytes
    trust_path=MODULE.parents[2]/binding._IBKR_TRUST_PATH
    def read(path):
        if path==MODULE:return reviewed_raw
        if path==trust_path:return trust_raw
        return original_read(path)
    monkeypatch.setattr(Path,'read_bytes',read)
    class RetainedSigner:
        public_blob=public
        key_version=1
    active=binding._owner_load_active_signing_binding(RetainedSigner(),trust_digest,reviewed_digest)
    assert active._TRUST_SHA==trust_digest
    assert active._owner_trust()['state']=='ACTIVE'
    assert binding._TRUST_SHA != trust_digest
    monkeypatch.setattr(active,'_handshake_lease_hash',lambda:'e'*64)
    assert 'IBKR_TRUST_SHA256='+trust_digest in active._handshake_chain({}, {})
    with pytest.raises(ValueError):
        binding._owner_load_active_signing_binding(RetainedSigner(),trust_digest,'0'*64)


def test_scoped_trust_public_pin_refuses_unreviewed_or_unprovisioned_disk_metadata():
    import hashlib
    binding=load_binding()
    class Signer:
        key_version=1
        public_blob=b'UNPROVISIONED'
    raw=(MODULE.parents[2]/binding._IBKR_TRUST_PATH).read_bytes()
    with pytest.raises(ValueError):
        binding._owner_load_active_signing_binding(Signer(),
            hashlib.sha256(raw).hexdigest(),hashlib.sha256(MODULE.read_bytes()).hexdigest())


def test_owner_key_session_public_input_obeys_deadline_and_size(monkeypatch):
    import msvcrt
    binding=load_binding()
    clock=[100.0]
    monkeypatch.setattr(binding,'_now',lambda:clock[0])
    monkeypatch.setattr(msvcrt,'kbhit',lambda:False)
    monkeypatch.setattr(binding.time,'sleep',lambda *_:clock.__setitem__(0,clock[0]+1))
    with pytest.raises(ValueError):
        binding._owner_console_line(102,10)
    assert clock[0]==102
    monkeypatch.setattr(msvcrt,'kbhit',lambda:True)
    chars=iter('xxx\r')
    monkeypatch.setattr(msvcrt,'getwch',lambda:next(chars))
    with pytest.raises(ValueError):
        binding._owner_console_line(110,2)


def test_owner_key_session_buffered_public_packet_does_not_spend_grant_lifetime(monkeypatch):
    import msvcrt
    binding=load_binding()
    packet='x'*3000
    chars=iter(packet+'\r')
    monkeypatch.setattr(binding,'_now',lambda:100.0)
    monkeypatch.setattr(msvcrt,'kbhit',lambda:True)
    monkeypatch.setattr(msvcrt,'getwch',lambda:next(chars))
    monkeypatch.setattr(binding.time,'sleep',lambda *_:pytest.fail('buffered paste delayed'))
    assert binding._owner_console_line(101.0,32768)==packet


def test_scoped_trust_activated_public_pin_loads_without_private_key_or_authority():
    import hashlib
    binding=load_binding()
    trust=binding._owner_trust()
    assert trust['state']=='ACTIVE'
    assert trust['current_key_version']==10
    record=next(x for x in trust['keys'] if x['status']=='ACTIVE')
    assert record['key_fingerprint_sha256']=='05c4c25df8ebf7bdd8e02f7de7c051d4b86ee815f6fd523c64895cfc2a9f76a8'
    assert trust['keys'][0]['status']=='REVOKED'
    assert trust['keys'][1]['status']=='REVOKED'
    assert trust['keys'][2]['status']=='REVOKED'
    assert trust['keys'][3]['status']=='REVOKED'
    assert trust['keys'][4]['status']=='REVOKED'
    assert trust['keys'][5]['status']=='REVOKED'
    assert trust['keys'][6]['status']=='REVOKED'
    assert trust['keys'][7]['status']=='REVOKED'
    assert trust['keys'][8]['status']=='REVOKED'
    class PublicOnly:
        key_version=10
        public_blob=binding._public_p256_blob(record['public_key_blob_base64'])
    active=binding._owner_load_active_signing_binding(PublicOnly(),binding._TRUST_SHA,
        hashlib.sha256(MODULE.read_bytes()).hexdigest())
    assert active._owner_trust()['state']=='ACTIVE'
    assert active.SdkProbe().probe()['status']=='BLOCKED'
    assert active._authorize_handshake({}, {}, {}) is False


@pytest.mark.parametrize('attempt_unapproved_commands',[False,True])
def test_v6_rotation_owner_proof_status_and_close_are_explicit(monkeypatch,capsys,attempt_unapproved_commands):
    # Preserve the historical version6 ceremony independent of current rotation.
    import builtins,msvcrt
    from types import SimpleNamespace
    binding=load_binding()
    monkeypatch.setattr(binding,'_IBKR_CEREMONY_KEY_VERSION',6)
    signer=synthetic_p256_signer(binding)
    calls={'generate':0,'sign':0,'verify':0,'close':0}
    class Candidate:
        public_blob=signer.public_blob
        key_version=6
        def sign_digest(self,digest):
            calls['sign']+=1
            return signer.sign_digest(digest)
        def close(self):
            calls['close']+=1
            signer.close()
    def generate():
        calls['generate']+=1
        return Candidate()
    monkeypatch.setattr(binding._P256OwnerKey,'generate',generate)
    monkeypatch.setattr(sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(sys.stdout,'isatty',lambda:True)
    monkeypatch.setattr(sys,'flags',SimpleNamespace(isolated=True,no_site=True))
    monkeypatch.setattr(sys,'dont_write_bytecode',True)
    monkeypatch.setattr(builtins,'input',lambda *_:'GENERATE IBKR OWNER KEY')
    commands='STATUS\rEXIT\r'
    if attempt_unapproved_commands:
        import hashlib
        commands=('PIN PUBLIC TRUST '+binding._TRUST_SHA+' '+hashlib.sha256(MODULE.read_bytes()).hexdigest()+
            '\rSIGN IBKR GRANT\rGENERATE IBKR OWNER KEY\rSTATUS\rEXIT\r')
    chars=iter(commands)
    monkeypatch.setattr(msvcrt,'kbhit',lambda:True)
    monkeypatch.setattr(msvcrt,'getwch',lambda:next(chars))
    monkeypatch.setattr(binding.time,'sleep',lambda *_:None)
    real_verify=binding._verify_p256
    def verify_once(*args):
        calls['verify']+=1
        return real_verify(*args)
    monkeypatch.setattr(binding,'_verify_p256',verify_once)
    monkeypatch.setattr(binding,'_launch_handshake_worker',lambda *a:pytest.fail('worker during preparation'))
    monkeypatch.setattr(Path,'write_text',lambda *a,**k:pytest.fail('unapproved file write'))
    monkeypatch.setattr(Path,'write_bytes',lambda *a,**k:pytest.fail('unapproved file write'))
    try:
        assert binding._owner_key_session_main()==0
        output=capsys.readouterr().out
        receipt=json.JSONDecoder().raw_decode(output)[0]
        assert receipt['PUBLIC FINGERPRINT']['key_version']==6
        assert 'OWNER_SESSION_ACTIVE' in output
        assert 'OWNER_STATUS' in output and 'PUBLIC_PIN_PENDING' in output
        assert 'OWNER_KEY_SESSION_CLOSED' in output
        assert calls=={'generate':1,'sign':1,'verify':1,'close':1}
        assert 'SIGNED_PUBLIC_GRANT' not in output
        assert 'PUBLIC_TRUST_PINNED_IN_OWNER_PROCESS' not in output
        if attempt_unapproved_commands:
            assert 'PUBLIC_PIN_REFUSED' in output
            assert 'OWNER_COMMAND_REFUSED' in output
    finally:
        signer.close()


def test_v2_rotation_retained_signer_accepts_approved_version2(one_shot_fixture):
    import copy
    binding, _, gate, _, host, context, trust, sign=one_shot_fixture
    signer=synthetic_p256_signer(binding)
    class Candidate:
        public_blob=signer.public_blob
        key_version=2
        def sign_digest(self,digest):return signer.sign_digest(digest)
    trust['current_key_version']=2
    trust['keys'][0]['key_version']=2
    gate['approval_evidence']['key_version']=2
    sign()
    candidate=copy.deepcopy(gate)
    candidate['approval_evidence']['canonical_payload_sha256']=''
    candidate['approval_evidence']['approval_signature_base64']=''
    try:
        result=binding._owner_sign_handshake_grant(Candidate(),
            {'activation':candidate,'host_evidence':host,'context':context})
        assert result['approval_evidence']['key_version']==2
        assert binding._authorize_handshake(result,host,context) is True
    finally:
        signer.close()


def test_v2_rotation_pending_signer_cannot_pin_version1_public_trust(
        activation_fixture,monkeypatch):
    import base64,hashlib
    binding, _, _, trust, _=activation_fixture
    trust['environment']='PRODUCTION'
    trust_raw=(json.dumps(trust,indent=2)+'\n').encode()
    digest=hashlib.sha256(trust_raw).hexdigest()
    source=MODULE.read_bytes().replace(binding._TRUST_SHA.encode(),digest.encode())
    original=Path.read_bytes
    trust_path=MODULE.parents[2]/binding._IBKR_TRUST_PATH
    def read(path):
        if path==MODULE:return source
        if path==trust_path:return trust_raw
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',read)
    class Candidate:
        public_blob=base64.b64decode(trust['keys'][0]['public_key_blob_base64'])
        key_version=2
    assert json.loads(trust_raw)['current_key_version']==1
    with pytest.raises(ValueError,match='SIGNING_REFUSED'):
        binding._owner_load_active_signing_binding(Candidate(),digest,
            hashlib.sha256(source).hexdigest())


def test_v2_rotation_escape_clears_hidden_partial_command(monkeypatch):
    import msvcrt
    binding=load_binding()
    chars=iter('PARTIAL\x1bSTATUS\r')
    monkeypatch.setattr(binding,'_now',lambda:100)
    monkeypatch.setattr(msvcrt,'kbhit',lambda:True)
    monkeypatch.setattr(msvcrt,'getwch',lambda:next(chars))
    monkeypatch.setattr(binding.time,'sleep',lambda *_:pytest.fail('buffered input delayed'))
    assert binding._owner_console_line(110,160)=='STATUS'


@pytest.mark.parametrize('version',[True,False,0,-1,'2',None])
def test_v2_rotation_rejects_nonpositive_or_noninteger_owner_version(activation_fixture,version):
    binding, _, _, trust, _=activation_fixture
    class Candidate:
        key_version=version
    with pytest.raises(ValueError):
        binding._owner_active_version(Candidate(),trust)


def test_v2_rotation_boolean_current_version_cannot_verify_scoped_signature(activation_fixture):
    binding, gate, _, trust, _=activation_fixture
    trust['current_key_version']=True
    assert binding.SdkProbe().readiness(activation=gate)['status']=='BLOCKED'


@pytest.mark.parametrize('input_end,expected,reason',[
    ('EXIT\r',0,'OWNER_EXIT'),
    ('\x03',2,'INTERRUPTED'),
    ('x'*161+'\rEXIT\r',0,'OWNER_EXIT'),
])
def test_v2_rotation_owner_channel_closes_without_second_command(
        monkeypatch,capsys,input_end,expected,reason):
    import builtins,msvcrt
    from types import SimpleNamespace
    binding=load_binding()
    signer=synthetic_p256_signer(binding)
    calls={'sign':0,'close':0}
    class Candidate:
        public_blob=signer.public_blob
        key_version=binding._IBKR_CEREMONY_KEY_VERSION
        def sign_digest(self,digest):
            calls['sign']+=1
            return signer.sign_digest(digest)
        def close(self):
            calls['close']+=1
            signer.close()
    monkeypatch.setattr(binding._P256OwnerKey,'generate',lambda:Candidate())
    monkeypatch.setattr(sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(sys.stdout,'isatty',lambda:True)
    monkeypatch.setattr(sys,'flags',SimpleNamespace(isolated=True,no_site=True))
    monkeypatch.setattr(sys,'dont_write_bytecode',True)
    monkeypatch.setattr(builtins,'input',lambda *_:'GENERATE IBKR OWNER KEY')
    chars=iter(input_end)
    monkeypatch.setattr(msvcrt,'kbhit',lambda:True)
    monkeypatch.setattr(msvcrt,'getwch',lambda:next(chars))
    monkeypatch.setattr(binding.time,'sleep',lambda *_:None)
    try:
        assert binding._owner_key_session_main()==expected
        output=capsys.readouterr().out
        assert 'OWNER_KEY_SESSION_CLOSED: '+reason in output
        assert 'SIGNED_PUBLIC_GRANT' not in output
        assert calls=={'sign':1,'close':1}
    finally:
        signer.close()


def test_v2_rotation_extended_key_prefix_alone_cannot_bypass_deadline(monkeypatch):
    import msvcrt
    binding=load_binding()
    clock=[100.0]
    chars=iter('\x00')
    availability=iter([True,False,False,False])
    monkeypatch.setattr(binding,'_now',lambda:clock[0])
    monkeypatch.setattr(msvcrt,'kbhit',lambda:next(availability))
    monkeypatch.setattr(msvcrt,'getwch',lambda:next(chars))
    monkeypatch.setattr(binding.time,'sleep',lambda *_:clock.__setitem__(0,clock[0]+1))
    with pytest.raises(ValueError):
        binding._owner_console_line(102,160)
    assert clock[0]==102


def test_console_recovery_long_public_paste_keeps_same_signer(monkeypatch,capsys):
    import builtins,msvcrt
    from types import SimpleNamespace
    binding=load_binding()
    signer=synthetic_p256_signer(binding)
    calls={'generate':0,'sign':0,'close':0}
    class Candidate:
        public_blob=signer.public_blob
        key_version=binding._IBKR_CEREMONY_KEY_VERSION
        def sign_digest(self,digest):
            calls['sign']+=1
            return signer.sign_digest(digest)
        def close(self):
            calls['close']+=1
            signer.close()
    def generate():
        calls['generate']+=1
        return Candidate()
    monkeypatch.setattr(binding._P256OwnerKey,'generate',generate)
    monkeypatch.setattr(sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(sys.stdout,'isatty',lambda:True)
    monkeypatch.setattr(sys,'flags',SimpleNamespace(isolated=True,no_site=True))
    monkeypatch.setattr(sys,'dont_write_bytecode',True)
    monkeypatch.setattr(builtins,'input',lambda *_:'GENERATE IBKR OWNER KEY')
    long_command='PIN PUBLIC TRUST '+'0'*64+' '+'1'*64+' Reply only with the returned status. Keep this session open. No SIGN command.'
    chars=iter(long_command+'\rSTATUS\rEXIT\r')
    monkeypatch.setattr(msvcrt,'kbhit',lambda:True)
    monkeypatch.setattr(msvcrt,'getwch',lambda:next(chars))
    monkeypatch.setattr(binding.time,'sleep',lambda *_:pytest.fail('buffered input delayed'))
    monkeypatch.setattr(binding,'_owner_load_active_signing_binding',lambda *a:pytest.fail('partial pin executed'))
    monkeypatch.setattr(binding,'_launch_handshake_worker',lambda *a:pytest.fail('worker'))
    try:
        assert binding._owner_key_session_main()==0
        output=capsys.readouterr().out
        assert 'OWNER_COMMAND_REFUSED_INPUT_LIMIT' in output
        assert 'OWNER_STATUS' in output
        assert 'OWNER_KEY_SESSION_CLOSED: OWNER_EXIT' in output
        assert calls=={'generate':1,'sign':1,'close':1}
    finally:
        signer.close()


def test_console_recovery_overflow_stays_rejected_through_escape(monkeypatch):
    import msvcrt
    binding=load_binding()
    chars=list('x'*161+'\x1bSTATUS\r')
    monkeypatch.setattr(binding,'_now',lambda:100)
    monkeypatch.setattr(msvcrt,'kbhit',lambda:bool(chars))
    monkeypatch.setattr(msvcrt,'getwch',lambda:chars.pop(0))
    with pytest.raises(binding._OwnerConsoleOverflow):
        binding._owner_console_line(110,160)
    assert chars==[]


def test_console_recovery_overflow_without_newline_still_expires(monkeypatch):
    import msvcrt
    binding=load_binding()
    chars=list('x'*161)
    clock=[100.0]
    monkeypatch.setattr(binding,'_now',lambda:clock[0])
    monkeypatch.setattr(msvcrt,'kbhit',lambda:bool(chars))
    monkeypatch.setattr(msvcrt,'getwch',lambda:chars.pop(0))
    monkeypatch.setattr(binding.time,'sleep',lambda *_:clock.__setitem__(0,clock[0]+1))
    with pytest.raises(binding._OwnerConsoleExpired):
        binding._owner_console_line(102,160)
    assert clock[0]==102


def test_console_recovery_grant_json_overflow_still_closes_without_signing(monkeypatch,capsys):
    import builtins,msvcrt
    from types import SimpleNamespace
    binding=load_binding()
    signer=synthetic_p256_signer(binding)
    closed=[]
    class Candidate:
        public_blob=signer.public_blob
        key_version=binding._IBKR_CEREMONY_KEY_VERSION
        def sign_digest(self,digest):return signer.sign_digest(digest)
        def close(self):closed.append(True);signer.close()
    monkeypatch.setattr(binding._P256OwnerKey,'generate',lambda:Candidate())
    monkeypatch.setattr(sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(sys.stdout,'isatty',lambda:True)
    monkeypatch.setattr(sys,'flags',SimpleNamespace(isolated=True,no_site=True))
    monkeypatch.setattr(sys,'dont_write_bytecode',True)
    monkeypatch.setattr(builtins,'input',lambda *_:'GENERATE IBKR OWNER KEY')
    commands='PIN PUBLIC TRUST '+'0'*64+' '+'1'*64+'\rSIGN IBKR GRANT\r'+'x'*32769+'\r'
    chars=iter(commands)
    monkeypatch.setattr(msvcrt,'kbhit',lambda:True)
    monkeypatch.setattr(msvcrt,'getwch',lambda:next(chars))
    monkeypatch.setattr(binding.time,'sleep',lambda *_:pytest.fail('buffered paste delayed'))
    def forbidden(*args):pytest.fail('grant signing attempted')
    monkeypatch.setattr(binding,'_owner_load_active_signing_binding',
        lambda *a:SimpleNamespace(_owner_sign_handshake_grant=forbidden))
    try:
        assert binding._owner_key_session_main()==2
        output=capsys.readouterr().out
        assert 'OWNER_KEY_SESSION_CLOSED: INPUT_LIMIT' in output
        assert 'SIGNED_PUBLIC_GRANT' not in output
        assert closed==[True]
    finally:
        signer.close()


def test_v3_rotation_pending_signer_cannot_pin_active_version2(
        activation_fixture,monkeypatch):
    import base64,hashlib
    binding, _, _, trust, _=activation_fixture
    trust['environment']='PRODUCTION'
    trust['current_key_version']=2
    trust['keys'][0]['key_version']=2
    trust_raw=json.dumps(trust,indent=2).encode()
    digest=hashlib.sha256(trust_raw).hexdigest()
    source=MODULE.read_bytes().replace(binding._TRUST_SHA.encode(),digest.encode())
    original=Path.read_bytes
    trust_path=MODULE.parents[2]/binding._IBKR_TRUST_PATH
    def read(path):
        if path==MODULE:return source
        if path==trust_path:return trust_raw
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',read)
    class Candidate:
        public_blob=base64.b64decode(trust['keys'][0]['public_key_blob_base64'])
        key_version=3
    assert json.loads(trust_raw)['current_key_version']==2
    with pytest.raises(ValueError,match='SIGNING_REFUSED'):
        binding._owner_load_active_signing_binding(Candidate(),digest,
            hashlib.sha256(source).hexdigest())


def test_v3_rotation_retained_signer_supports_future_approved_version3(one_shot_fixture):
    import copy
    binding, _, gate, _, host, context, trust, sign=one_shot_fixture
    signer=synthetic_p256_signer(binding)
    class Candidate:
        public_blob=signer.public_blob
        key_version=3
        def sign_digest(self,digest):return signer.sign_digest(digest)
    trust['current_key_version']=3
    trust['keys'][0]['key_version']=3
    gate['approval_evidence']['key_version']=3
    sign()
    candidate=copy.deepcopy(gate)
    candidate['approval_evidence']['canonical_payload_sha256']=''
    candidate['approval_evidence']['approval_signature_base64']=''
    try:
        result=binding._owner_sign_handshake_grant(Candidate(),
            {'activation':candidate,'host_evidence':host,'context':context})
        assert result['approval_evidence']['key_version']==3
        assert binding._authorize_handshake(result,host,context) is True
    finally:
        signer.close()


def test_v5_rotation_pending_signer_cannot_pin_active_version4(
        activation_fixture,monkeypatch):
    import base64,hashlib
    binding, _, _, trust, _=activation_fixture
    trust['environment']='PRODUCTION'
    trust['current_key_version']=4
    trust['keys'][0]['key_version']=4
    trust_raw=json.dumps(trust,indent=2).encode()
    digest=hashlib.sha256(trust_raw).hexdigest()
    source=MODULE.read_bytes().replace(binding._TRUST_SHA.encode(),digest.encode())
    original=Path.read_bytes
    trust_path=MODULE.parents[2]/binding._IBKR_TRUST_PATH
    def read(path):
        if path==MODULE:return source
        if path==trust_path:return trust_raw
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',read)
    class Candidate:
        public_blob=base64.b64decode(trust['keys'][0]['public_key_blob_base64'])
        key_version=5
    assert json.loads(trust_raw)['current_key_version']==4
    with pytest.raises(ValueError,match='SIGNING_REFUSED'):
        binding._owner_load_active_signing_binding(Candidate(),digest,
            hashlib.sha256(source).hexdigest())



def test_v5_rotation_retained_signer_supports_future_approved_version5(one_shot_fixture):
    import copy
    binding, _, gate, _, host, context, trust, sign=one_shot_fixture
    signer=synthetic_p256_signer(binding)
    class Candidate:
        public_blob=signer.public_blob
        key_version=5
        def sign_digest(self,digest):return signer.sign_digest(digest)
    trust['current_key_version']=5
    trust['keys'][0]['key_version']=5
    gate['approval_evidence']['key_version']=5
    sign()
    candidate=copy.deepcopy(gate)
    candidate['approval_evidence']['canonical_payload_sha256']=''
    candidate['approval_evidence']['approval_signature_base64']=''
    try:
        result=binding._owner_sign_handshake_grant(Candidate(),
            {'activation':candidate,'host_evidence':host,'context':context})
        assert result['approval_evidence']['key_version']==5
        assert binding._authorize_handshake(result,host,context) is True
    finally:
        signer.close()


def test_failure_receipt_reader_error_retains_negotiated_version():
    result = run_case(version=213, mutation='reader_error')
    assert result['status'] == 'BLOCKED'
    assert result['reason'] == 'UNEXPECTED_ERROR'
    assert result['server_version'] == 213
    assert 1 <= result['initialization_envelopes'] <= 2
    assert result['cleanup_verified']


def test_failure_receipt_truncated_frame_preserves_deadline():
    result = run_case(version=213, mutation='truncated_frame')
    assert result['status'] == 'BLOCKED'
    assert result['reason'] == 'DEADLINE_EXCEEDED'
    assert result['server_version'] == 213
    assert result['cleanup_verified']


def test_failure_receipt_cleanup_failure_remains_dominant():
    result = run_case(version=213, mutation='close_error')
    assert result['status'] == 'BLOCKED'
    assert result['reason'] == 'CLEANUP_UNVERIFIED'
    assert result['server_version'] == 213
    assert not result['cleanup_verified']


def test_failure_receipt_before_negotiation_stays_zero():
    result = run_case(version=213, mutation='connect_error')
    assert result['status'] == 'BLOCKED'
    assert result['server_version'] == 0
    assert not result['accounts_seen'] and not result['id_seen']
    assert result['cleanup_verified']


def test_failure_receipt_preserves_partial_callback_presence():
    result = run_case(version=213, mutation='missing_accounts_after_callback')
    assert result['status'] == 'BLOCKED'
    assert result['server_version'] == 213
    assert not result['accounts_seen'] and result['id_seen']
    assert result['cleanup_verified']


def test_failure_receipt_first_wire_refusal_survives_sdk_translation():
    binding = load_binding()
    gate = binding._WireGate()
    with pytest.raises(binding._Refused, match='DEADLINE_EXCEEDED'):
        gate.refuse('DEADLINE_EXCEEDED')
    with pytest.raises(binding._Refused, match='DEADLINE_EXCEEDED'):
        gate.refuse('UNEXPECTED_ERROR')
    assert gate.reason == 'DEADLINE_EXCEEDED'
    assert gate.revoked


@pytest.mark.parametrize('mutation,site', [
    ('','NONE'),
    ('connect_error','SOCKET_CONNECT'),
    ('send_error','SOCKET_SEND'),
    ('start_api_error','SOCKET_SEND'),
    ('runtime_pin_tamper','SDK_RUNTIME'),
    ('seam_tamper','SDK_SEAM'),
    ('partial_send','SOCKET_SEND'),
    ('negotiation_extra','NEGOTIATION_SHAPE'),
    ('oversized_frame','INGRESS_LENGTH_OR_BUDGET'),
    ('unknown_inbound','STARTUP_MESSAGE_CLASS'),
    ('unknown_protobuf','PROTOBUF_SHAPE'),
    ('reader_error','READER_OR_DECODER'),
    ('truncated_frame','DEADLINE'),
    ('close_error','CLEANUP'),
])
def test_failure_site_reproduces_without_broker(mutation,site):
    result=run_case(version=213,mutation=mutation)
    assert result['failure_site']==site
    assert result['failure_site'] in load_binding()._PUBLIC_FAILURE_SITES
    assert CANARY not in json.dumps(result)
    assert result['status']==('VERIFIED_OFFLINE' if not mutation else 'BLOCKED')


def test_failure_site_first_refusal_stays_fixed():
    binding=load_binding();gate=binding._WireGate()
    with pytest.raises(binding._Refused):
        gate.refuse('DEADLINE_EXCEEDED',site='DEADLINE')
    with pytest.raises(binding._Refused):
        gate.refuse('UNEXPECTED_ERROR',site='READER_OR_DECODER')
    assert gate.reason=='DEADLINE_EXCEEDED' and gate.failure_site=='DEADLINE'
    assert gate.revoked


@pytest.mark.parametrize('site',[CANARY,True,None,132999,[],{},'SOCKET_CONNECT:'+CANARY])
def test_failure_site_decoder_rejects_private_or_foreign_types(site):
    binding=load_binding()
    result={'status':'BLOCKED','reason':'WIRE_REFUSED','sdk_version':'1051.1',
        'server_version':213,'accounts_seen':False,'id_seen':False,
        'cleanup_verified':True,'initialization_envelopes':2,'failure_site':site}
    answer=binding._decode_handshake_receipt(json.dumps(result).encode(),0)
    assert answer['status']=='BLOCKED' and answer['reason']=='WORKER_REFUSED'
    assert answer['failure_site']=='UNKNOWN'
    assert CANARY not in json.dumps(answer)


def test_failure_site_current_receipt_is_strict_and_legacy_not_promoted():
    binding=load_binding()
    result={'status':'VERIFIED_HANDSHAKE','reason':'NONE','sdk_version':'1051.1',
        'server_version':213,'accounts_seen':True,'id_seen':True,
        'cleanup_verified':True,'initialization_envelopes':2,'failure_site':'NONE'}
    assert binding._decode_handshake_receipt(json.dumps(result).encode(),0)==result
    result['failure_site']='SOCKET_CONNECT'
    assert binding._decode_handshake_receipt(json.dumps(result).encode(),0)['reason']=='WORKER_REFUSED'
    del result['failure_site']
    assert binding._decode_handshake_receipt(json.dumps(result).encode(),0)['reason']=='WORKER_REFUSED'


def test_failure_site_direct_unknown_label_never_echoed():
    binding=load_binding();gate=binding._WireGate()
    with pytest.raises(binding._Refused) as caught:
        gate.refuse(site=CANARY)
    assert gate.failure_site=='UNKNOWN' and caught.value.failure_site=='UNKNOWN'
    assert CANARY not in str(caught.value)


def test_failure_site_legacy_shape_is_classified_without_values():
    binding=load_binding();gate=binding._WireGate();gate.version=194
    with pytest.raises(binding._Refused):
        gate.validate(bytearray(b'15\x001\x00'+CANARY.encode()+b'\x00EXTRA\x00'))
    assert gate.failure_site=='LEGACY_STARTUP_SHAPE'
    assert CANARY not in gate.failure_site

def test_failure_site_egress_refusal_is_classified_and_revoked():
    binding=load_binding();gate=binding._WireGate()
    with pytest.raises(binding._Refused):
        gate.outgoing(b'UNAPPROVED_SYNTHETIC_OPERATION')
    assert gate.failure_site=='EGRESS_ENVELOPE' and gate.revoked

def test_failure_site_authority_remains_blocked():
    binding=load_binding();result=binding._handshake_blocked()
    assert result['status']=='BLOCKED' and result['failure_site']=='AUTHORITY'
    assert binding.SdkProbe().probe()['status']=='BLOCKED'


@pytest.mark.parametrize('mutation,reason,site',[
    ('delayed_unknown_protobuf','WIRE_REFUSED','PROTOBUF_SHAPE'),
    ('reader_wire_before_decoder','WIRE_REFUSED','PROTOBUF_SHAPE'),
    ('first_recv_error','UNEXPECTED_ERROR','READER_OR_DECODER'),
    ('first_recv_os_error','UNEXPECTED_ERROR','READER_OR_DECODER'),
])
def test_failure_site_review_deterministic_regressions(mutation,reason,site):
    result=run_case(version=213,mutation=mutation)
    assert result['status']=='BLOCKED'
    assert result['reason']==reason and result['failure_site']==site
    assert result['cleanup_verified']


def test_failure_site_shared_recorder_preserves_main_then_reader():
    binding=load_binding();gate=binding._WireGate();main_recorded=threading.Event()
    record=gate.record_failure
    def later_reader():
        assert main_recorded.wait(2)
        record('WIRE_REFUSED',site='PROTOBUF_SHAPE')
    thread=threading.Thread(target=later_reader);thread.start()
    record('UNEXPECTED_ERROR',site='READER_OR_DECODER')
    main_recorded.set();thread.join(2)
    assert not thread.is_alive()
    assert gate.reason=='UNEXPECTED_ERROR' and gate.failure_site=='READER_OR_DECODER'



@pytest.mark.parametrize('mutation', ['local_close_os_error','local_close_eof'])
def test_reader_local_close_after_paired_startup_is_clean(mutation):
    result = run_case(226, mutation)
    assert result['accounts_seen'] and result['id_seen'] and result['cleanup_verified']
    assert result['status'] == 'VERIFIED_OFFLINE'
    assert result['reason'] == 'NONE' and result['failure_site'] == 'NONE'

@pytest.mark.parametrize('mutation', ['pre_close_os_error','local_close_runtime_error'])
def test_reader_real_fault_is_not_hidden_by_local_close(mutation):
    result = run_case(226, mutation)
    assert result['status'] == 'BLOCKED'
    assert result['reason'] == 'UNEXPECTED_ERROR'
    assert result['failure_site'] == 'READER_OR_DECODER'
    assert result['cleanup_verified']


@pytest.mark.parametrize('mutation', ['delayed_pre_stop_os_error','delayed_pre_stop_eof'])
def test_reader_fault_before_stop_remains_blocked_when_handler_is_delayed(mutation):
    result = run_case(226, mutation)
    assert result['status'] == 'BLOCKED'
    assert result['reason'] == 'UNEXPECTED_ERROR'
    assert result['failure_site'] == 'READER_OR_DECODER'
    assert result['cleanup_verified']


def test_reader_stall_uses_one_cleanup_budget_and_remains_unverified():
    result = run_case(226, 'reader_stalls_until_close')
    assert result['status'] == 'BLOCKED'
    assert result['reason'] == 'CLEANUP_UNVERIFIED'
    assert result['failure_site'] == 'CLEANUP'
    assert result['cleanup_verified'] is False


@pytest.mark.parametrize('mutation,reason,site', [
    ('trailing_fragment_notice','NONE','NONE'),
    ('trailing_fragment_unknown','WIRE_REFUSED','STARTUP_MESSAGE_CLASS'),
    ('trailing_fragment_oversized','WIRE_REFUSED','INGRESS_LENGTH_OR_BUDGET'),
    ('trailing_fragment_truncated','DEADLINE_EXCEEDED','DEADLINE'),
])
def test_shutdown_finishes_already_received_fragment_before_result(mutation,reason,site):
    result = run_case(226, mutation)
    assert result['accounts_seen'] and result['id_seen']
    assert result['cleanup_verified']
    assert result['status'] == ('VERIFIED_OFFLINE' if reason == 'NONE' else 'BLOCKED')
    assert result['reason'] == reason and result['failure_site'] == site
