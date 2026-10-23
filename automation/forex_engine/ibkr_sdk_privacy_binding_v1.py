"""Pinned SDK binding with separately signed, bounded one-shot activation.

The vendor SDK contains trading methods. This facade exposes none. Its private
socket boundary permits only the two initialization envelopes, and the current
worker denies native sockets unless a separate exact handshake grant and
current policy, host and packet-lock qualification pass. Defaults remain blocked.
"""
import hashlib
import contextlib
import io
import importlib.metadata
import importlib.util
from datetime import datetime, timezone
import re
import json
import logging
import os
from pathlib import Path
import queue
import struct
import sys
import time
import threading

_ROOT = Path('C:/AIOS_Tooling/IBKR/M6_SDK_OFFLINE_1051_1_V1')
_SITE = _ROOT / 'runtime-env/Lib/site-packages'
_RUNTIME_PIN_SHA = 'a791097eb5641672fca20077f88460e917137bcbc7b32f2e15c805cc026358b9'
_now = time.monotonic
_PUBLIC_REASONS = frozenset({'NONE', 'CONNECTION_AUTHORITY_UNAVAILABLE', 'RUNTIME_REFUSED',
    'SDK_SEAM_REFUSED', 'ENDPOINT_REFUSED', 'WIRE_REFUSED', 'DEADLINE_EXCEEDED',
    'UNEXPECTED_ERROR', 'QUEUE_REFUSED', 'CLEANUP_UNVERIFIED', 'NETWORK_REFUSED', 'ACTIVATION_REFUSED', 'WORKER_REFUSED',
    'ATTEMPT_ALREADY_CONSUMED'})


_PUBLIC_FAILURE_SITES = frozenset({'NONE','UNKNOWN','AUTHORITY','SDK_RUNTIME',
    'SDK_SEAM','SOCKET_CONNECT','SOCKET_SEND','NEGOTIATION_SHAPE',
    'INGRESS_LENGTH_OR_BUDGET','EGRESS_ENVELOPE','STARTUP_MESSAGE_CLASS',
    'PROTOBUF_SHAPE','LEGACY_STARTUP_SHAPE','READER_OR_DECODER','DEADLINE','CLEANUP'})


class SdkProbe:
    """Default-disabled facade; one separately signed handshake per context."""
    __slots__ = ('_context', '_consumed', '_mutex')

    def __init__(self):
        self._context = None
        self._consumed = False
        self._mutex = threading.RLock()

    def execution_context(self):
        """Nonsecret volatile challenge for a future owner-signed grant."""
        with self._mutex:
            if self._context is None:
                self._context = {'schema':'IBKR_EXECUTION_CONTEXT.v1',
                    'parent_pid':os.getpid(), 'nonce':os.urandom(32).hex(),
                    'created_at_utc':_utc_now().isoformat()}
            return dict(self._context)

    def readiness(self, *, activation=None, owner_key=None):
        if activation is None and owner_key is None:
            return {'status':'BLOCKED', 'reason':'CONNECTION_AUTHORITY_UNAVAILABLE'}
        return _activation_preflight(activation, owner_key)

    def probe(self, *, activation=None, owner_key=None, host_evidence=None):
        if activation is None and owner_key is None and host_evidence is None:
            return self.readiness()
        if owner_key is not None:
            return _handshake_blocked('ACTIVATION_REFUSED')
        try:
            with self._mutex:
                if self._consumed:
                    return _handshake_blocked('ATTEMPT_ALREADY_CONSUMED')
                context = self.execution_context()
                if not _authorize_handshake(activation, host_evidence, context):
                    return _handshake_blocked('ACTIVATION_REFUSED')
                with _CONTEXT_MUTEX:
                    identity = (context['parent_pid'], context['nonce'])
                    if identity in _CONSUMED_CONTEXTS:
                        return _handshake_blocked('ATTEMPT_ALREADY_CONSUMED')
                    _CONSUMED_CONTEXTS.add(identity)
                self._consumed = True
            return _launch_handshake_worker(activation, host_evidence, context)
        except BaseException:
            return _handshake_blocked('UNEXPECTED_ERROR')
        finally:
            activation = owner_key = host_evidence = None

    def disconnect(self):
        return {'status':'DISCONNECTED'}


_PREFLIGHT_REPO = Path('C:/Dev/Ai.Os')
_PREFLIGHT_MODULE = 'automation/forex_engine/ibkr_sdk_privacy_binding_v1.py'
_PREFLIGHT_PACKET = 'PKT-EAST-FOREX-IBKR-FIRST-READ-ONLY-HANDSHAKE-V1'
_RISK_SHA = 'f4a261c4d59c7ba05ce88760343895ab40c292aba7531f5db17071df641d6402'
_PRIVACY_SHA = 'a667db0c649626a2f628ff0efcc46345c0b3630a39bc6db92d9e41b4ed309b7e'
_TRUST_SHA = 'a58efe1c65e95db1332b7cda1b4d962cc4f18d70c8c95fa32606804817efa6a8'
_AUTHORITY_PINS = {
    'automation/validators/aios_approval_authority_integrity_validator.py':
        '8110b59d6d46405a43ddcb8db4d6d0e26010f3e638fc40182f83146e07348351',
    'automation/validators/aios_approval_contract_v2.py':
        '9e4d4d2378c3cc918331b9f9bf11cb6c80575f17e4179dfb608000f647d17bf9',
}
_PREFLIGHT_BLOCKED = ['broker','credentials','historical_requests','market_data',
                      'orders','account_requests','portfolio_requests','streaming']


def _utc_now():
    return datetime.now(timezone.utc)


def _activation_plain(value, depth=0):
    if depth > 4:
        return False
    kind = type(value)
    if kind is str:
        return len(value) <= 256
    if kind in (int, bool):
        return True
    if kind is list:
        return len(value) <= 16 and all(_activation_plain(x, depth + 1) for x in value)
    if kind is dict:
        return len(value) <= 24 and all(type(k) is str and len(k) <= 64
                                      and _activation_plain(v, depth + 1) for k,v in value.items())
    return False


def _owner_trust():
    # Public trust metadata only. No key store, environment or credential loader.
    path = _PREFLIGHT_REPO / _IBKR_TRUST_PATH
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _TRUST_SHA:
        raise ValueError('ACTIVATION_REFUSED')
    trust = json.loads(raw.decode('utf-8-sig'))
    if trust.get('scope') != _ibkr_trust_scope() or trust.get('signature_algorithm') != _IBKR_SIGNATURE_ALGORITHM:
        raise ValueError('ACTIVATION_REFUSED')
    return trust


def _owner_verifier():
    for name, digest in _AUTHORITY_PINS.items():
        if hashlib.sha256((_PREFLIGHT_REPO / name).read_bytes()).hexdigest() != digest:
            raise ValueError('ACTIVATION_REFUSED')
    path = _PREFLIGHT_REPO / 'automation/validators/aios_approval_authority_integrity_validator.py'
    name = '_ibkr_owner_preflight_authority'
    if name in sys.modules:
        raise ValueError('ACTIVATION_REFUSED')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _preflight_chain():
    module_path = _PREFLIGHT_REPO / _PREFLIGHT_MODULE
    if Path(__file__).resolve() != module_path.resolve():
        raise ValueError('ACTIVATION_REFUSED')
    for name, digest in (('RISK_POLICY.md', _RISK_SHA),
                         ('automation/forex_engine/ibkr_connection_probe_v1.py', _PRIVACY_SHA)):
        if hashlib.sha256((_PREFLIGHT_REPO / name).read_bytes()).hexdigest() != digest:
            raise ValueError('ACTIVATION_REFUSED')
    return ['IBKR_PREFLIGHT_ONLY_V1',
            'BINDING_SHA256=' + hashlib.sha256(module_path.read_bytes()).hexdigest(),
            'RUNTIME_SHA256=' + _RUNTIME_PIN_SHA,
            'RISK_POLICY_SHA256=' + _RISK_SHA, 'PRIVACY_SHA256=' + _PRIVACY_SHA,
            'READ_ONLY_LOOPBACK_127.0.0.1:7496_CLIENT132',
            'NO_BROKER_CONNECTION_OR_REQUESTS']


def _activation_preflight(activation, owner_key):
    """Verify an expiring owner signature; grant no transport capability.

    Only public signatures are admitted. Private owner signing material is
    refused and never transported to a worker.
    Readiness is repeatable: no approval, nonce or connection-attempt state is
    consumed. Genuine execution requires a separate handshake grant and never follows
    from preflight readiness. TEST_ONLY trust can produce only a FIXTURE_ONLY result.
    """
    refused = {'status':'BLOCKED','reason':'ACTIVATION_REFUSED','connection_authorized':False}
    try:
        if type(activation) is not dict or not _activation_plain(activation):
            return refused
        if owner_key is not None:
            return refused
        fields = {'schema','approval_gate_id','packet_id','requested_action','requested_mode',
                  'allowed_paths','blocked_paths','validator_chain','approval_status',
                  'approved_by_human','approval_timestamp_utc','expires_at_utc','approval_evidence'}
        if set(activation) != fields or activation['schema'] != 'AIOS_HUMAN_OWNER_APPROVAL_PAYLOAD.v1':
            return refused
        if (activation['packet_id'] != _PREFLIGHT_PACKET
                or activation['requested_action'] != 'IBKR_READ_ONLY_PREFLIGHT'
                or activation['requested_mode'] != 'APPLY'
                or activation['approval_status'] != 'approved_for_apply'
                or activation['approved_by_human'] is not True
                or activation['allowed_paths'] != [_PREFLIGHT_MODULE]
                or activation['blocked_paths'] != _PREFLIGHT_BLOCKED
                or activation['validator_chain'] != _preflight_chain()):
            return refused
        evidence = activation['approval_evidence']
        if type(evidence) is not dict or set(evidence) != {
                'type','canonical_payload_schema','approval_nonce','key_id','key_version',
                'key_fingerprint_sha256','canonical_payload_sha256','approval_signature_base64'}:
            return refused
        trust = _owner_trust()
        fixture = trust.get('environment') == 'TEST_ONLY'
        prefix = 'FIXTURE_ONLY_IBKR_PREFLIGHT_' if fixture else 'IBKR_PREFLIGHT_'
        if not re.fullmatch(prefix + '[0-9a-f]{32}', activation['approval_gate_id']):
            return refused
        if fixture != evidence['approval_nonce'].startswith('FIXTURE_ONLY_'):
            return refused
        if type(evidence['key_version']) is not int or evidence['key_version'] <= 0:
            return refused
        now = _utc_now()
        approved = datetime.fromisoformat(activation['approval_timestamp_utc'].replace('Z','+00:00'))
        expiry = datetime.fromisoformat(activation['expires_at_utc'].replace('Z','+00:00'))
        if (approved.tzinfo is None or expiry.tzinfo is None
                or approved.utcoffset().total_seconds() != 0 or expiry.utcoffset().total_seconds() != 0
                or not approved <= now < expiry or not 0 < (expiry-approved).total_seconds() <= 300):
            return refused
        if not _verify_scoped_approval(activation, trust, allow_test_trust=fixture):
            return refused
        before = list(sys.path)
        try:
            _validate_runtime()
        finally:
            sys.path[:] = before
        return {'status':'READY_FIXTURE_PREFLIGHT_ONLY' if fixture else 'READY_PREFLIGHT_ONLY',
                'reason':'NONE','authorization_kind':'FIXTURE_ONLY' if fixture else 'OWNER_VERIFIED',
                'connection_authorized':False}
    except BaseException:
        # Foreign diagnostics and signing material never leave the boundary.
        return refused
    finally:
        owner_key = None
        activation = None


class _Refused(Exception):
    def __init__(self, reason='WIRE_REFUSED', *, site='UNKNOWN'):
        super().__init__(reason if reason in _PUBLIC_REASONS else 'UNEXPECTED_ERROR')
        self.failure_site = site if type(site) is str and site in _PUBLIC_FAILURE_SITES and site != 'NONE' else 'UNKNOWN'


def _check_endpoint(host, port, client_id):
    if type(host) is not str or host != '127.0.0.1' or type(port) is not int or port != 7496 or type(client_id) is not int or client_id != 132:
        raise ValueError('ENDPOINT_REFUSED')


def _validate_runtime():
    """Authenticate the complete isolated installation before an SDK import."""
    pin = (_ROOT / 'manifests/M7_RUNTIME_PIN.json').read_bytes()
    if hashlib.sha256(pin).hexdigest() != _RUNTIME_PIN_SHA or sys.version_info[:3] != (3, 12, 10):
        raise _Refused('RUNTIME_REFUSED')
    manifest = json.loads(pin)
    expected = {r['path']:r['sha256'] for r in manifest['files']}
    actual = {}
    for path in _SITE.rglob('*'):
        if path.is_file():
            if path.is_symlink() or path.suffix.lower() in ('.pth','.pyc','.exe','.pyd','.so','.dll','.bat','.cmd','.ps1'):
                raise _Refused('RUNTIME_REFUSED')
            actual[path.relative_to(_SITE).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise _Refused('RUNTIME_REFUSED')
    if str(_SITE) not in sys.path:
        sys.path.insert(0, str(_SITE))
    packages = {d.metadata['Name']:d.version for d in importlib.metadata.distributions(path=[str(_SITE)])}
    if packages != {'ibapi':'1051.1', 'protobuf':'5.29.5'}:
        raise _Refused('RUNTIME_REFUSED')


def _arm_private_boundary(permit=None):
    if not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode:
        raise _Refused('RUNTIME_REFUSED')
    logging.disable(sys.maxsize)
    logging.getLogger().handlers.clear()
    logging.lastResort = None
    # A separate process is required: this audit hook is deliberately irreversible.
    allowed = (_ROOT.resolve(), Path(__file__).resolve().parent,
               Path(sys.base_prefix).resolve(), Path(sys.base_exec_prefix).resolve())
    def audit(event, args):
        if event.startswith('socket.'):
            if type(permit) is not _NativeSocketPermit:
                raise _Refused('NETWORK_REFUSED')
            permit.audit(event, args)
            return
        if event in ('urllib.Request','http.client.connect'):
            raise _Refused('NETWORK_REFUSED')
        if event in ('subprocess.Popen','os.system','os.posix_spawn','os.spawn') or event.startswith('os.exec'):
            raise _Refused('UNEXPECTED_ERROR')
        if event == 'open':
            path, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if writing:
                raise _Refused('UNEXPECTED_ERROR')
            if isinstance(path, (str, bytes)):
                resolved = Path(os.fsdecode(path)).resolve()
                if not any(resolved.is_relative_to(root) for root in allowed) or resolved.name.lower() == '.env':
                    raise _Refused('UNEXPECTED_ERROR')
        if event in ('os.remove','os.rmdir','os.mkdir','os.rename','os.chmod','os.utime','os.link','os.symlink'):
            raise _Refused('UNEXPECTED_ERROR')
    sys.addaudithook(audit)


def _envelope(payload):
    return struct.pack('!I', len(payload)) + payload


def _initialization(version):
    if version >= 213:
        # Official createStartApiRequestProto omits empty optionalCapabilities.
        return _envelope((271).to_bytes(4, 'big') + b'\x08\x84\x01')
    payload = (71).to_bytes(4, 'big') if version >= 201 else b'71\0'
    return _envelope(payload + b'2\0' + b'132\0\0')


def _varint(data, offset):
    value = 0
    for index in range(10):
        if offset >= len(data):
            raise _Refused()
        byte = data[offset]; offset += 1
        value |= (byte & 127) << (7 * index)
        if byte < 128:
            if (index and byte == 0) or (index == 9 and byte > 1):
                raise _Refused()
            return value, offset
    raise _Refused()


def _flat_proto(data, allowed):
    fields = {}; offset = 0
    try:
        while offset < len(data):
            key, offset = _varint(data, offset)
            tag, wire = key >> 3, key & 7
            if tag not in allowed or allowed[tag] != wire or tag in fields:
                raise _Refused()
            if wire == 0:
                value, offset = _varint(data, offset)
                fields[tag] = value
            elif wire == 2:
                size, offset = _varint(data, offset)
                if size > 4096 or offset + size > len(data):
                    raise _Refused()
                value = data[offset:offset + size]; offset += size
                fields[tag] = value
                try:
                    bytes(value).decode('utf-8')
                except UnicodeError:
                    raise _Refused() from None
            else:
                raise _Refused()
        return fields
    except BaseException:
        _wipe_fields(fields)
        raise


def _wipe(value):
    if isinstance(value, bytearray):
        value[:] = b'\0' * len(value)
        value.clear()


def _wipe_fields(fields):
    for value in fields.values() if isinstance(fields, dict) else fields:
        _wipe(value)
    fields.clear()


class _WireGate:
    """Bounded ingress and exact two-envelope egress, before SDK decoding."""
    def __init__(self):
        self.deadline = _now() + 10
        self.buffer = bytearray()
        self.version = 0
        self.received = 0
        self.sent = 0
        self.required = set()
        self.notices = 0
        self.reason = 'NONE'
        self.failure_site = 'NONE'
        self._failure_lock = threading.RLock()
        self.revoked = False

    def record_failure(self, reason='WIRE_REFUSED', *, site='UNKNOWN'):
        # Reader/main failures share one atomic, fixed-public first-failure pair.
        reason = reason if type(reason) is str and reason in _PUBLIC_REASONS and reason != 'NONE' else 'UNEXPECTED_ERROR'
        site = site if type(site) is str and site in _PUBLIC_FAILURE_SITES and site != 'NONE' else 'UNKNOWN'
        with self._failure_lock:
            if self.reason == 'NONE':
                self.reason = reason; self.failure_site = site
            self.revoked = True
            return self.reason, self.failure_site

    def refuse(self, reason='WIRE_REFUSED', *, site='UNKNOWN'):
        reason, site = self.record_failure(reason, site=site)
        raise _Refused(reason, site=site)

    def remaining(self):
        remaining = self.deadline - _now()
        if remaining <= 0:
            self.refuse('DEADLINE_EXCEEDED', site='DEADLINE')
        return remaining

    def outgoing(self, data):
        self.remaining()
        if self.revoked or self.sent >= 2:
            self.refuse(site='EGRESS_ENVELOPE')
        expected = b'API\0' + _envelope(b'v100..226') if self.sent == 0 else _initialization(self.version)
        if type(data) is not bytes or data != expected or (self.sent == 1 and self.version == 0):
            self.refuse(site='EGRESS_ENVELOPE')
        self.sent += 1

    def feed(self, data):
        if type(data) is not bytes or len(data) > 4096:
            self.refuse(site='INGRESS_LENGTH_OR_BUDGET')
        self.received += len(data)
        if self.received > 65536 or len(self.buffer) + len(data) > 12288:
            self.refuse(site='INGRESS_LENGTH_OR_BUDGET')
        self.buffer.extend(data)

    def take(self):
        if len(self.buffer) < 4:
            return None
        size = int.from_bytes(self.buffer[:4], 'big')
        if size == 0 or size > 8192:
            self.refuse(site='INGRESS_LENGTH_OR_BUDGET')
        if len(self.buffer) < size + 4:
            return None
        payload = self.buffer[4:size + 4]
        self.buffer[:size + 4] = b'\0' * (size + 4)
        del self.buffer[:size + 4]
        fields = []
        try:
            if self.version == 0:
                fields = payload.split(b'\0')
                if len(fields) != 3 or fields[-1] or not fields[0].isdigit() or not fields[1] or len(fields[1]) > 256:
                    self.refuse(site='NEGOTIATION_SHAPE')
                version = int(fields[0])
                if not 100 <= version <= 226:
                    self.refuse(site='NEGOTIATION_SHAPE')
                self.version = version
            else:
                self.validate(payload)
            return payload
        except BaseException:
            payload[:] = b'\0' * len(payload)
            payload.clear()
            raise
        finally:
            _wipe_fields(fields)

    def validate(self, payload):
        if self.version >= 201:
            if len(payload) < 4:
                self.refuse(site='STARTUP_MESSAGE_CLASS')
            message_id = int.from_bytes(payload[:4], 'big'); body = payload[4:]
        else:
            split = payload.find(0)
            if split < 1 or not payload[:split].isdigit():
                self.refuse(site='STARTUP_MESSAGE_CLASS')
            message_id = int(payload[:split]); body = payload[split + 1:]
        try:
            self._validate_body(body, message_id)
        finally:
            _wipe(body)

    def _validate_body(self, body, message_id):
        fields = {}
        try:
            if self.version >= 213:
                if message_id not in (209, 215, 204):
                    self.refuse(site='STARTUP_MESSAGE_CLASS')
                if message_id in (209, 215):
                    fields = _flat_proto(body, {1:0 if message_id == 209 else 2})
                    if set(fields) != {1} or (message_id == 209 and fields[1] > 2147483647) or (message_id == 215 and not fields[1]):
                        self.refuse(site='STARTUP_MESSAGE_CLASS')
                else:
                    fields = _flat_proto(body, {1:0, 2:0, 3:0, 4:2, 5:2})
                    # Global notices use int32 -1, sign-extended to a ten-byte varint.
                    if fields.get(1, 18446744073709551615) != 18446744073709551615 or fields.get(3) not in (2104, 2106, 2158) or fields.get(5, b''):
                        self.refuse(site='STARTUP_MESSAGE_CLASS')
                message_id -= 200
            else:
                if message_id not in (9, 15, 4) or not body.endswith(b'\0'):
                    self.refuse(site='LEGACY_STARTUP_SHAPE')
                fields = body.split(b'\0')[:-1]
                if message_id in (9, 15):
                    if len(fields) != 2 or fields[0] != b'1' or not fields[1] or len(fields[1]) > 4096:
                        self.refuse(site='LEGACY_STARTUP_SHAPE')
                    if message_id == 9 and (not fields[1].isdigit() or int(fields[1]) > 2147483647):
                        self.refuse(site='LEGACY_STARTUP_SHAPE')
                else:
                    offset = 0 if self.version >= 194 else 1
                    expected = offset + 3 + int(self.version >= 166) + int(self.version >= 194)
                    if len(fields) != expected or (offset and fields[0] != b'2') or fields[offset] != b'-1' or fields[offset + 1] not in (b'2104', b'2106', b'2158'):
                        self.refuse(site='LEGACY_STARTUP_SHAPE')
                    if self.version >= 166 and fields[offset + 3]:
                        self.refuse(site='LEGACY_STARTUP_SHAPE')
                    if self.version >= 194 and (not fields[-1].isdigit() or len(fields[-1]) > 20):
                        self.refuse(site='LEGACY_STARTUP_SHAPE')
            if message_id in (9, 15):
                if message_id in self.required:
                    self.refuse(site='STARTUP_MESSAGE_CLASS')
                self.required.add(message_id)
            else:
                self.notices += 1
                if self.notices > 16:
                    self.refuse('QUEUE_REFUSED', site='STARTUP_MESSAGE_CLASS')
        except _Refused as error:
            if self.reason == 'NONE':
                self.refuse(str(error), site='PROTOBUF_SHAPE' if self.version >= 213 else 'LEGACY_STARTUP_SHAPE')
            raise
        finally:
            _wipe_fields(fields)

    def clear(self):
        self.revoked = True
        self.buffer[:] = b'\0' * len(self.buffer)
        self.buffer.clear()


def _verify_seams(client_module, reader_module, decoder_module, connection_module):
    for module, cls, methods in ((client_module, client_module.EClient, ('connect','startApi','sendMsg','sendMsgProtoBuf')),
        (reader_module, reader_module.EReader, ('__init__','run')),
        (connection_module, connection_module.Connection, ('connect','sendMsg','recvMsg')),
        (decoder_module, decoder_module.Decoder, ('interpret','processProtoBuf'))):
        for name in methods:
            method = getattr(cls, name, None)
            if not callable(method) or getattr(method, '__module__', None) != module.__name__ or Path(method.__code__.co_filename).resolve() != Path(module.__file__).resolve():
                raise _Refused('SDK_SEAM_REFUSED')


def _verify_loaded_origins():
    for name, module in tuple(sys.modules.items()):
        if name == 'ibapi' or name.startswith('ibapi.') or name == 'google.protobuf' or name.startswith('google.protobuf.'):
            path = getattr(module, '__file__', None)
            stem = _SITE.joinpath(*name.split('.'))
            if path is None or Path(path).resolve() not in (stem.with_suffix('.py').resolve(), (stem/'__init__.py').resolve()):
                raise _Refused('RUNTIME_REFUSED')


class _DiscardText(io.TextIOBase):
    @property
    def encoding(self):
        return 'utf-8'

    def write(self, text):
        return len(text)


def _run_private(socket_factory, *, permit=None):
    with contextlib.redirect_stdout(_DiscardText()), contextlib.redirect_stderr(_DiscardText()):
        return _run_sdk(socket_factory, permit=permit)


def _run_sdk(socket_factory, *, permit=None):
    """Reuse the bounded SDK engine; injected fixtures have no native permit.

    A genuine permit is created only in the independently authorized child.
    Injection alone never supplies broker or source-admission authority.
    """
    result = {'status':'BLOCKED', 'reason':'RUNTIME_REFUSED', 'sdk_version':'1051.1',
        'server_version':0, 'accounts_seen':False, 'id_seen':False,
        'cleanup_verified':False, 'initialization_envelopes':0, 'failure_site':'SDK_RUNTIME'}
    gate = _WireGate(); client = None; captured_reader = None; captured_conn = None
    q = queue.Queue(maxsize=16); wrapper = None; stage = 'AUTHORITY'
    local_reader_stop = threading.Event()
    try:
        if permit is not None and type(permit) is not _NativeSocketPermit:
            raise _Refused('NETWORK_REFUSED')
        _arm_private_boundary(permit)
        stage = 'SDK_RUNTIME'
        _validate_runtime()
        import ibapi
        import google.protobuf
        from google.protobuf.internal import api_implementation
        from ibapi import client as cm, connection as cnm, reader as rm, decoder as dm, comm
        from ibapi.wrapper import EWrapper
        if ibapi.get_version_string() != '1051.1' or google.protobuf.__version__ != '5.29.5' or api_implementation.Type() != 'python':
            raise _Refused('RUNTIME_REFUSED')
        _verify_loaded_origins()
        stage = 'SDK_SEAM'
        _verify_seams(cm, rm, dm, cnm)

        class PrivateWrapper(EWrapper):
            def __init__(self):
                self.accounts_seen = False; self.id_seen = False; self.protos = []
            def managedAccounts(self, accounts):
                self.accounts_seen = True
            def nextValidId(self, order_id):
                self.id_seen = True
            def managedAccountsProtoBuf(self, proto):
                self.protos.append(proto)
            def nextValidIdProtoBuf(self, proto):
                self.protos.append(proto)
            def errorProtoBuf(self, proto):
                self.protos.append(proto)
            def error(self, req_id, error_time, code, text, advanced=''):
                if code not in (2104,2106,2158) or advanced:
                    gate.refuse('UNEXPECTED_ERROR', site=stage)
            def connectAck(self):
                pass
            def connectionClosed(self):
                pass
            def clear(self):
                for proto in self.protos:
                    proto.Clear()
                self.protos.clear()

        class BoundedConnection(cnm.Connection):
            def connect(self):
                nonlocal captured_conn
                captured_conn = self
                _check_endpoint(self.host, self.port, 132)
                try:
                    self.socket = socket_factory()
                    self.socket.settimeout(gate.remaining())
                    self.socket.connect((self.host, self.port))
                except _Refused as error:
                    gate.refuse(str(error), site=error.failure_site if error.failure_site != 'UNKNOWN' else 'SOCKET_CONNECT')
                except BaseException:
                    gate.refuse('UNEXPECTED_ERROR', site='SOCKET_CONNECT')
            def sendMsg(self, data):
                gate.outgoing(data)
                if self.socket is None:
                    gate.refuse(site='SOCKET_SEND')
                try:
                    self.socket.settimeout(gate.remaining())
                    count = self.socket.send(data)
                except _Refused as error:
                    gate.refuse(str(error), site=error.failure_site if error.failure_site != 'UNKNOWN' else 'SOCKET_SEND')
                except BaseException:
                    gate.refuse('UNEXPECTED_ERROR', site='SOCKET_SEND')
                if count != len(data):
                    gate.refuse(site='SOCKET_SEND')
                return count
            def recvMsg(self):
                while self.socket is not None and not gate.revoked:
                    # Finish any frame already owned before honoring local stop.
                    if local_reader_stop.is_set() and not gate.buffer:
                        return b''
                    gate.remaining()
                    payload = gate.take()
                    if payload is not None:
                        try:
                            return _envelope(bytes(payload))
                        finally:
                            payload[:] = b'\0' * len(payload); payload.clear()
                    try:
                        self.socket.settimeout(min(0.1, gate.remaining()))
                        data = self.socket.recv(4096)
                    except TimeoutError:
                        continue
                    except _Refused as error:
                        gate.refuse(str(error), site=error.failure_site if error.failure_site != 'UNKNOWN' else 'READER_OR_DECODER')
                    except BaseException:
                        gate.refuse('UNEXPECTED_ERROR', site='READER_OR_DECODER')
                    if not data:
                        gate.refuse('UNEXPECTED_ERROR', site='READER_OR_DECODER')
                    gate.feed(data)
                return b''

        class BoundedReader(rm.EReader):
            def __init__(self, conn, msg_queue):
                nonlocal captured_reader
                super().__init__(conn, msg_queue)
                self.daemon = True
                captured_reader = self
            def run(self):
                try:
                    while self.conn.isConnected() and not gate.revoked:
                        data = self.conn.recvMsg()
                        if not data:
                            break
                        payload = bytearray(data[4:])
                        try:
                            self.msg_queue.put_nowait(payload)
                        except queue.Full:
                            payload[:] = b'\0' * len(payload); payload.clear()
                            gate.refuse('QUEUE_REFUSED', site='READER_OR_DECODER')
                except _Refused as error:
                    gate.record_failure(str(error), site=error.failure_site if error.failure_site != 'UNKNOWN' else 'READER_OR_DECODER')
                except BaseException:
                    gate.record_failure('UNEXPECTED_ERROR', site='READER_OR_DECODER')

        # Only this short-lived process is patched; vendor source remains intact.
        cm.Connection = BoundedConnection; rm.EReader = BoundedReader
        wrapper = PrivateWrapper(); client = cm.EClient(wrapper); client.msg_queue = q
        stage = 'SOCKET_CONNECT'
        client.connect('127.0.0.1', 7496, 132)
        stage = 'READER_OR_DECODER'
        captured_reader = client.reader
        client.connTime = None
        while not (wrapper.accounts_seen and wrapper.id_seen and q.empty()):
            gate.remaining()
            if gate.reason != 'NONE':
                raise _Refused(gate.reason, site=gate.failure_site)
            try:
                payload = q.get(timeout=min(0.01, gate.remaining()))
            except queue.Empty:
                continue
            try:
                data = bytes(payload)
                if gate.version >= 201:
                    message_id = int.from_bytes(data[:4], 'big'); body = data[4:]
                else:
                    index = data.index(b'\0'); message_id = int(data[:index]); body = data[index + 1:]
                if message_id > 200:
                    client.decoder.processProtoBuf(body, message_id - 200)
                else:
                    client.decoder.interpret(comm.read_fields(body), message_id)
            finally:
                wrapper.clear()
                payload[:] = b'\0' * len(payload); payload.clear()
        if permit is not None and not permit.connected:
            raise _Refused('NETWORK_REFUSED')
        result.update(status='VERIFIED_OFFLINE' if permit is None else 'VERIFIED_HANDSHAKE', reason='NONE', server_version=gate.version,
                      accounts_seen=wrapper.accounts_seen, id_seen=wrapper.id_seen, failure_site='NONE')
    except _Refused as error:
        reason, site = gate.record_failure(str(error), site=error.failure_site if error.failure_site != 'UNKNOWN' else stage)
        result.update(reason=reason, failure_site=site)
    except BaseException:
        reason, site = gate.record_failure('UNEXPECTED_ERROR', site=stage)
        result.update(reason=reason, failure_site=site)
    finally:
        cleanup_deadline = time.monotonic() + 2
        local_reader_stop.set()
        cleanup = True
        # Normal receives have a <=0.1s timeout. Stop the reader before closing
        # its socket, retaining genuine errors and time for a bounded fallback.
        if captured_reader is not None:
            try:
                captured_reader.join(timeout=max(0, min(1, cleanup_deadline-time.monotonic())))
                if captured_reader.is_alive():
                    cleanup = False
            except BaseException:
                cleanup = False
        # The reader may validate already-received fragments during its bounded
        # join. Revoke before forced close; genuine faults still remain failures.
        gate.revoked = True
        if captured_conn is not None:
            try:
                captured_conn.disconnect()
            except BaseException:
                cleanup = False
            finally:
                # Detach even when close throws; teardown uncertainty stays BLOCKED.
                captured_conn.socket = None
        if client is not None:
            try:
                client.disconnect()
            except BaseException:
                cleanup = False
        if captured_reader is not None:
            try:
                captured_reader.join(timeout=max(0, cleanup_deadline-time.monotonic()))
                if captured_reader.is_alive():
                    cleanup = False
            except BaseException:
                cleanup = False
        # Preserve the primary failure; residual bytes are not a diagnosis.
        if gate.reason != 'NONE':
            result.update(status='BLOCKED', reason=gate.reason, failure_site=gate.failure_site)
        if gate.buffer and result['reason'] == 'NONE':
            result.update(status='BLOCKED', reason='WIRE_REFUSED', failure_site='INGRESS_LENGTH_OR_BUDGET')
        # Capture only approved scalar observations before clearing owned objects.
        result.update(server_version=gate.version,
                      accounts_seen=wrapper is not None and wrapper.accounts_seen,
                      id_seen=wrapper is not None and wrapper.id_seen)
        gate.clear()
        while not q.empty():
            payload = q.get_nowait(); payload[:] = b'\0' * len(payload); payload.clear()
        if wrapper is not None:
            wrapper.clear(); wrapper.__dict__.clear()
        if client is not None:
            client.__dict__.clear()
        if captured_reader is not None and not captured_reader.is_alive():
            captured_reader.conn = None; captured_reader.msg_queue = None
        result['initialization_envelopes'] = gate.sent
        result['cleanup_verified'] = cleanup
        if not cleanup:
            result.update(status='BLOCKED', reason='CLEANUP_UNVERIFIED', failure_site='CLEANUP')
    return result

# A preflight grant never creates this separately verified execution authority.
_HANDSHAKE_BLOCKED = ['credentials','historical_requests','market_data','orders',
    'account_requests','portfolio_requests','positions','scanners','news','streaming',
    'retry','reconnect']
_CONTEXT_MUTEX = threading.Lock()
_CONSUMED_CONTEXTS = set()
_NATIVE_PERMIT_TOKEN = object()
_HANDSHAKE_LOCK = 'LOCK_EAST_FOREX_IBKR_FIRST_READ_ONLY_HANDSHAKE_OCC132'
_HANDSHAKE_BRANCH = 'codex/forex-edge-autopilot-20261008'
_HANDSHAKE_HEAD = '5af6206681c90c6e8fb32db0834a91739d694957'


def _handshake_blocked(reason='ACTIVATION_REFUSED'):
    site = ('CLEANUP' if reason == 'CLEANUP_UNVERIFIED' else
            'DEADLINE' if reason == 'DEADLINE_EXCEEDED' else
            'AUTHORITY' if reason in ('ACTIVATION_REFUSED','NETWORK_REFUSED',
                'CONNECTION_AUTHORITY_UNAVAILABLE','ATTEMPT_ALREADY_CONSUMED') else 'UNKNOWN')
    return {'status':'BLOCKED','reason':reason,
        'sdk_version':'1051.1','server_version':0,'accounts_seen':False,
        'id_seen':False,'cleanup_verified':False,'initialization_envelopes':0,'failure_site':site}


def _canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _utc_timestamp(value):
    if type(value) is not str:
        raise _Refused('ACTIVATION_REFUSED')
    result = datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise _Refused('ACTIVATION_REFUSED')
    return result


def _handshake_lock_current():
    """Read only the canonical handshake lease and exact current Git identity."""
    root = _PREFLIGHT_REPO
    head = (root/'.git/HEAD').read_text().strip()
    if head != 'ref: refs/heads/' + _HANDSHAKE_BRANCH:
        return False
    ref = root/'.git/refs/heads'/ _HANDSHAKE_BRANCH
    if ref.is_file():
        commit = ref.read_text().strip()
    else:
        entries = (root/'.git/packed-refs').read_text().splitlines()
        commit = next((x.split(' ',1)[0] for x in entries
                       if x.endswith(' refs/heads/' + _HANDSHAKE_BRANCH)), '')
    if commit != _HANDSHAKE_HEAD:
        return False
    reg = json.loads((root/'automation/orchestration/locks/FILE_LOCK_REGISTRY.json').read_text(encoding='utf-8-sig'))
    matches = [x for x in reg['locks'] if x.get('lock_id') == _HANDSHAKE_LOCK
               and x.get('status') == 'ACTIVE']
    if len(matches) != 1:
        return False
    lock = matches[0]
    return (lock.get('worker_id') == 'EAST_OCC_132'
        and lock.get('packet_id') == _PREFLIGHT_PACKET
        and set(lock.get('claimed_paths',[])) == {'RISK_POLICY.md',_PREFLIGHT_MODULE,
            'tests/forex_engine/test_ibkr_sdk_privacy_binding_v1.py', _IBKR_TRUST_PATH}
        and _utc_timestamp(lock['created_at_utc']) <= _utc_now()
        < _utc_timestamp(lock['expires_at_utc']))


def _handshake_lease_hash():
    reg=json.loads((_PREFLIGHT_REPO/'automation/orchestration/locks/FILE_LOCK_REGISTRY.json').read_text(encoding='utf-8-sig'))
    matches=[x for x in reg['locks'] if x.get('lock_id')==_HANDSHAKE_LOCK and x.get('status')=='ACTIVE']
    if len(matches)!=1:raise ValueError('ACTIVATION_REFUSED')
    return _canonical_hash(matches[0])


def _handshake_chain(context, host):
    preflight = _preflight_chain()
    return ['IBKR_ONE_SHOT_HANDSHAKE_V1', *preflight[1:5],
        'IBKR_TRUST_SHA256=' + _TRUST_SHA, 'EXECUTION_LEASE_SHA256=' + _handshake_lease_hash(),
        'HOST_EVIDENCE_SHA256=' + _canonical_hash(host),
        'EXECUTION_CONTEXT_SHA256=' + _canonical_hash(context),
        'READ_ONLY_LOOPBACK_127.0.0.1:7496_CLIENT132',
        'MAX_ATTEMPTS=1_STARTUP10_CLEANUP2_WATCHDOG30',
        'NO_BUSINESS_REQUESTS_RETRY_RECONNECT','STOP_AFTER_DISCONNECT']


def _qualify_handshake_context(context, host, now, expected_pid):
    if type(context) is not dict or set(context) != {
            'schema','parent_pid','nonce','created_at_utc'}:
        return False
    if (context['schema'] != 'IBKR_EXECUTION_CONTEXT.v1'
            or type(context['parent_pid']) is not int
            or context['parent_pid'] != expected_pid
            or type(context['nonce']) is not str
            or re.fullmatch('[0-9a-f]{64}',context['nonce']) is None
            or not 0 <= (now-_utc_timestamp(context['created_at_utc'])).total_seconds() <= 300):
        return False
    flags = {'tws_running','paper_logged_in','read_only_api','localhost_only',
             'auto_binding_blocked_for_client132','master_api_client_id_blank','client132_unused_nonmaster',
             'owner_host_storage_risk_accepted'}
    fields = flags | {'schema','qualified_at_utc','expires_at_utc','port','client_id',
                      'tws_build','storage_controls'}
    if type(host) is not dict or set(host) != fields or not _activation_plain(host):
        return False
    if (host['schema'] != 'IBKR_HOST_QUALIFICATION.v1'
            or any(host[x] is not True for x in flags)
            or type(host['port']) is not int or host['port'] != 7496
            or type(host['client_id']) is not int or host['client_id'] != 132
            or type(host['tws_build']) is not str
            or re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,3}){1,3}[a-z]?',host['tws_build']) is None
            or not 0 <= (now-_utc_timestamp(host['qualified_at_utc'])).total_seconds() <= 300
            or not now < _utc_timestamp(host['expires_at_utc'])):
        return False
    controls = host['storage_controls']
    return (type(controls) is dict and set(controls) == {
        'paging','dumps','crash_handlers','hibernation','debugger_telemetry','vendor_logs'}
        and all(x in ('DISABLED_OR_EXCLUDED','OWNER_ACCEPTED_RESIDUAL_RISK')
                for x in controls.values()))


def _handshake_candidate(activation, host, context, *, expected_pid):
    """Shared non-signature qualification; never issues a transport capability."""
    try:
        if type(activation) is not dict or not _activation_plain(activation):
            return False
        now = _utc_now()
        if not _qualify_handshake_context(context,host,now,expected_pid):
            return False
        fields = {'schema','approval_gate_id','packet_id','requested_action','requested_mode',
            'allowed_paths','blocked_paths','validator_chain','approval_status',
            'approved_by_human','approval_timestamp_utc','expires_at_utc','approval_evidence'}
        if set(activation) != fields:
            return False
        if (activation['schema'] != 'AIOS_HUMAN_OWNER_APPROVAL_PAYLOAD.v1'
                or type(activation['approval_gate_id']) is not str
                or re.fullmatch('IBKR_HANDSHAKE_[0-9a-f]{32}',activation['approval_gate_id']) is None
                or activation['packet_id'] != _PREFLIGHT_PACKET
                or activation['requested_action'] != 'IBKR_READ_ONLY_HANDSHAKE'
                or activation['requested_mode'] != 'APPLY'
                or activation['allowed_paths'] != [_PREFLIGHT_MODULE]
                or activation['blocked_paths'] != _HANDSHAKE_BLOCKED
                or activation['validator_chain'] != _handshake_chain(context,host)
                or activation['approval_status'] != 'approved_for_apply'
                or activation['approved_by_human'] is not True):
            return False
        approved = _utc_timestamp(activation['approval_timestamp_utc'])
        expiry = _utc_timestamp(activation['expires_at_utc'])
        if (not approved <= now < expiry
                or not 30 <= (expiry-now).total_seconds()
                or not 0 < (expiry-approved).total_seconds() <= 300
                or expiry > _utc_timestamp(host['expires_at_utc'])):
            return False
        trust = _owner_trust()
        if trust.get('environment') != 'PRODUCTION' or trust.get('state') != 'ACTIVE':
            return False
        evidence = activation['approval_evidence']
        if type(evidence) is not dict or set(evidence) != {
                'type','canonical_payload_schema','approval_nonce','key_id','key_version',
                'key_fingerprint_sha256','canonical_payload_sha256','approval_signature_base64'}:
            return False
        if type(evidence['approval_nonce']) is not str or evidence['approval_nonce'].startswith('FIXTURE_ONLY'):
            return False
        if not _handshake_lock_current():
            return False
        before = list(sys.path)
        try:
            _validate_runtime()
        finally:
            sys.path[:] = before
        return (_utc_now() < expiry and (expiry-_utc_now()).total_seconds() >= 30)
    except BaseException:
        return False
    finally:
        activation = None


def _authorize_handshake(activation, host, context, *, worker=False):
    try:
        expected_pid = os.getppid() if worker else os.getpid()
        return (_handshake_candidate(activation, host, context, expected_pid=expected_pid)
                and _verify_scoped_approval(activation, _owner_trust()))
    except BaseException:
        return False


class _NativeSocketPermit:
    """Private-worker capability: one exact native create and one literal connect."""
    __slots__ = ('socket','connected','deadline')
    def __init__(self, token):
        if token is not _NATIVE_PERMIT_TOKEN:
            raise _Refused('NETWORK_REFUSED')
        self.socket = None
        self.connected = False
        self.deadline = _now() + 10

    def audit(self, event, args):
        if _now() >= self.deadline:
            raise _Refused('DEADLINE_EXCEEDED')
        if event == 'socket.__new__' and self.socket is None:
            sock,family,kind,protocol = args
            if (family,kind,protocol) != (2,1,0):
                raise _Refused('NETWORK_REFUSED')
            self.socket = sock
            return
        if event == 'socket.connect' and len(args) == 2:
            sock,address = args
            if sock is self.socket and not self.connected and address == ('127.0.0.1',7496):
                self.connected = True
                return
        raise _Refused('NETWORK_REFUSED')

    def clear(self):
        self.socket = None
        self.deadline = 0


def _decode_handshake_receipt(data, returncode):
    refused = _handshake_blocked('WORKER_REFUSED')
    try:
        if returncode != 0 or type(data) is not bytes or len(data) > 1024:
            return refused
        result = json.loads(data)
        expected = {'status','reason','sdk_version','server_version','accounts_seen',
                    'id_seen','cleanup_verified','initialization_envelopes','failure_site'}
        if type(result) is not dict or set(result) != expected:
            return refused
        if (result['status'] not in ('VERIFIED_HANDSHAKE','BLOCKED')
                or result['reason'] not in _PUBLIC_REASONS
                or result['sdk_version'] != '1051.1'
                or type(result['failure_site']) is not str
                or result['failure_site'] not in _PUBLIC_FAILURE_SITES
                or type(result['server_version']) is not int
                or not 0 <= result['server_version'] <= 226
                or type(result['initialization_envelopes']) is not int
                or not 0 <= result['initialization_envelopes'] <= 2
                or any(type(result[x]) is not bool for x in
                       ('accounts_seen','id_seen','cleanup_verified'))):
            return refused
        if result['status'] == 'VERIFIED_HANDSHAKE' and (
                result['reason'] != 'NONE' or result['failure_site'] != 'NONE'
                or not 100 <= result['server_version'] <= 226
                or result['initialization_envelopes'] != 2 or not all(result[x] for x in
                    ('accounts_seen','id_seen','cleanup_verified'))):
            return refused
        if result['status'] == 'BLOCKED' and (result['reason'] == 'NONE' or result['failure_site'] == 'NONE'):
            return refused
        return result
    except BaseException:
        return refused



_ATTEMPT_API = None
_ATTEMPT_MUTEX = threading.Lock()
# Hold handles until the initiating process exits; closing the last handle must
# never reset a consumed bootstrap while that same process can replay its grant.
_PROCESS_ATTEMPT_HANDLES = {}


def _attempt_api():
    global _ATTEMPT_API
    if os.name != 'nt':
        raise _Refused('RUNTIME_REFUSED')
    if _ATTEMPT_API is None:
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32',use_last_error=True)
        api.CreateSemaphoreW.argtypes = [ctypes.c_void_p,wintypes.LONG,wintypes.LONG,wintypes.LPCWSTR]
        api.CreateSemaphoreW.restype = wintypes.HANDLE
        api.OpenSemaphoreW.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR]
        api.OpenSemaphoreW.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        _ATTEMPT_API = api
    return _ATTEMPT_API


def _attempt_guard_name(context):
    return 'Local\\AIOS_IBKR_ONE_SHOT_' + _canonical_hash(context)


def _attempt_guard_create(context):
    """Create once in the parent, never rearm an existing named OS permit."""
    try:
        import ctypes
        name = _attempt_guard_name(context)
        with _ATTEMPT_MUTEX:
            if name in _PROCESS_ATTEMPT_HANDLES:
                return True
            api = _attempt_api()
            ctypes.set_last_error(0)
            handle = api.CreateSemaphoreW(None,1,1,name)
            if not handle:
                return False
            if ctypes.get_last_error() == 183:  # foreign/preexisting ownership
                api.CloseHandle(handle)
                return False
            _PROCESS_ATTEMPT_HANDLES[name] = handle
        return True
    except BaseException:
        return False


def _consume_attempt_guard(context):
    """A worker opens (never creates) and atomically consumes one parent permit."""
    handle = None
    try:
        api = _attempt_api()
        handle = api.OpenSemaphoreW(0x00100000,False,_attempt_guard_name(context))
        return bool(handle) and api.WaitForSingleObject(handle,0) == 0
    except BaseException:
        return False
    finally:
        if handle:
            api.CloseHandle(handle)


def _launch_handshake_worker(activation, host, context):
    """Public signed authority in anonymous pipes; no private key is accepted."""
    import subprocess
    child = None
    payload = bytearray()
    deadline = _now() + 30
    result = _handshake_blocked('WORKER_REFUSED')
    try:
        if not _attempt_guard_create(context):
            return result
        payload.extend(json.dumps({'activation':activation,
            'host_evidence':host,'context':context},separators=(',',':')).encode())
        if len(payload) > 32768:
            return result
        env = {'SystemRoot':os.environ.get('SystemRoot','C:\\Windows'),
            'PYTHONDONTWRITEBYTECODE':'1',
            'PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION':'python'}
        child = subprocess.Popen([sys._base_executable,'-I','-S','-B',str(Path(__file__).resolve()),
            '--ibkr-handshake-worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,env=env,cwd=str(_ROOT))
        output,_ = child.communicate(input=bytes(payload),timeout=max(0.01,deadline-_now()-2))
        result = _decode_handshake_receipt(output,child.returncode)
        output = None
    except subprocess.TimeoutExpired:
        result = _handshake_blocked('DEADLINE_EXCEEDED')
    except BaseException:
        result = _handshake_blocked('WORKER_REFUSED')
    finally:
        _wipe(payload)
        _consume_attempt_guard(context)
        activation = host = context = None
        if child is not None:
            try:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=max(0.01,min(2,deadline-_now())))
                for stream in (getattr(child,'stdin',None),getattr(child,'stdout',None)):
                    if stream is not None:
                        stream.close()
            except BaseException:
                result = _handshake_blocked('CLEANUP_UNVERIFIED')
    return result


def _handshake_worker_main():
    """No enabling environment flag; the child independently verifies authority."""
    result = _handshake_blocked('ACTIVATION_REFUSED')
    raw = bytearray()
    packet = {}
    permit = None
    try:
        if not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode:
            raise _Refused('RUNTIME_REFUSED')
        logging.disable(sys.maxsize)
        logging.getLogger().handlers.clear()
        logging.lastResort = None
        with contextlib.redirect_stdout(_DiscardText()), contextlib.redirect_stderr(_DiscardText()):
            raw.extend(sys.stdin.buffer.read(32769))
            if len(raw) > 32768:
                raise _Refused('ACTIVATION_REFUSED')
            packet = json.loads(raw)
            if type(packet) is not dict or set(packet) != {
                    'activation','host_evidence','context'}:
                raise _Refused('ACTIVATION_REFUSED')
            if not _authorize_handshake(packet['activation'],
                    packet['host_evidence'],packet['context'],worker=True):
                raise _Refused('ACTIVATION_REFUSED')
            if not _consume_attempt_guard(packet['context']):
                raise _Refused('ATTEMPT_ALREADY_CONSUMED')
            packet.clear()
            _wipe(raw)
            import socket
            permit = _NativeSocketPermit(_NATIVE_PERMIT_TOKEN)
            result = _run_private(lambda:socket.socket(socket.AF_INET,socket.SOCK_STREAM),permit=permit)
    except _Refused as error:
        result = _handshake_blocked(str(error))
    except BaseException:
        result = _handshake_blocked('UNEXPECTED_ERROR')
    finally:
        if isinstance(packet,dict):
            packet.clear()
        _wipe(raw)
        if permit is not None:
            permit.clear()
    # The only stdout write occurs after private worker cleanup.
    result = _decode_handshake_receipt(json.dumps(result).encode(),0)
    sys.stdout.write(json.dumps(result,separators=(',',':')))
    sys.stdout.flush()



# IBKR-only asymmetric authority. Private CNG keys never leave their process.
_IBKR_OWNER_KEY_ID = 'AIOS-HUMAN-OWNER-IBKR-HANDSHAKE-V1'
_IBKR_SIGNATURE_ALGORITHM = 'ECDSA_P256_SHA256'
_IBKR_CEREMONY_KEY_VERSION = 10
_IBKR_TRUST_PATH = 'automation/forex_engine/ibkr_handshake_owner_trust_v1.json'


def _ibkr_trust_scope():
    return {'packet_id':_PREFLIGHT_PACKET,
            'allowed_actions':['IBKR_READ_ONLY_PREFLIGHT','IBKR_READ_ONLY_HANDSHAKE'],
            'allowed_paths':[_PREFLIGHT_MODULE]}


class _CngP256:
    def __init__(self):
        if os.name != 'nt':
            raise ValueError('CNG_REFUSED')
        import ctypes
        self.c = ctypes
        self.provider = ctypes.c_void_p()
        self.dll = ctypes.WinDLL('bcrypt.dll', winmode=0x00000800)
        H = ctypes.c_void_p; U = ctypes.c_ulong; P = ctypes.POINTER(ctypes.c_ubyte)
        specs = {
            'BCryptOpenAlgorithmProvider':([ctypes.POINTER(H),ctypes.c_wchar_p,ctypes.c_wchar_p,U],ctypes.c_long),
            'BCryptCloseAlgorithmProvider':([H,U],ctypes.c_long),
            'BCryptGenerateKeyPair':([H,ctypes.POINTER(H),U,U],ctypes.c_long),
            'BCryptFinalizeKeyPair':([H,U],ctypes.c_long),
            'BCryptDestroyKey':([H],ctypes.c_long),
            'BCryptExportKey':([H,H,ctypes.c_wchar_p,P,U,ctypes.POINTER(U),U],ctypes.c_long),
            'BCryptImportKeyPair':([H,H,ctypes.c_wchar_p,ctypes.POINTER(H),P,U,U],ctypes.c_long),
            'BCryptSignHash':([H,H,P,U,P,U,ctypes.POINTER(U),U],ctypes.c_long),
            'BCryptVerifySignature':([H,H,P,U,P,U,U],ctypes.c_long),
        }
        for name,(args,ret) in specs.items():
            method = getattr(self.dll,name); method.argtypes=args; method.restype=ret
        self.check(self.dll.BCryptOpenAlgorithmProvider(
            ctypes.byref(self.provider),'ECDSA_P256',None,0))

    @staticmethod
    def check(status):
        if status < 0:
            raise ValueError('CNG_REFUSED')

    def buffer(self, value):
        return (self.c.c_ubyte * len(value)).from_buffer_copy(value)

    def close(self):
        if self.provider:
            self.dll.BCryptCloseAlgorithmProvider(self.provider,0)
            self.provider = self.c.c_void_p()


class _P256OwnerKey:
    __slots__ = ('_api','_handle','public_blob','key_version','_pid','_closed')

    def __init__(self, api, handle, public_blob, *, key_version=1):
        if type(key_version) is not int or key_version<=0:
            raise ValueError('SIGNER_REFUSED')
        self.key_version=key_version
        self._api=api; self._handle=handle; self.public_blob=public_blob
        self._pid=os.getpid(); self._closed=False

    def __repr__(self):
        return '<IBKR owner signer: private material stays in this process>'

    def __reduce__(self):
        raise TypeError('SIGNER_NOT_EXPORTABLE')

    @classmethod
    def generate(cls):
        api=_CngP256(); c=api.c; handle=c.c_void_p()
        try:
            api.check(api.dll.BCryptGenerateKeyPair(api.provider,c.byref(handle),256,0))
            api.check(api.dll.BCryptFinalizeKeyPair(handle,0))
            size=c.c_ulong()
            api.check(api.dll.BCryptExportKey(handle,None,'ECCPUBLICBLOB',None,0,c.byref(size),0))
            if size.value != 72:
                raise ValueError('CNG_REFUSED')
            public=(c.c_ubyte * 72)()
            api.check(api.dll.BCryptExportKey(handle,None,'ECCPUBLICBLOB',public,72,c.byref(size),0))
            return cls(api,handle,bytes(public),key_version=_IBKR_CEREMONY_KEY_VERSION)
        except BaseException:
            if handle:api.dll.BCryptDestroyKey(handle)
            api.close()
            raise

    def sign_digest(self, digest):
        if self._closed or self._pid!=os.getpid() or type(digest) is not bytes or len(digest)!=32:
            raise ValueError('SIGNER_REFUSED')
        api=self._api; c=api.c; signature=(c.c_ubyte * 64)(); size=c.c_ulong()
        api.check(api.dll.BCryptSignHash(self._handle,None,api.buffer(digest),32,
                                        signature,64,c.byref(size),0))
        if size.value != 64:raise ValueError('SIGNER_REFUSED')
        return bytes(signature)

    def close(self):
        if not self._closed:
            self._closed=True
            if self._handle:self._api.dll.BCryptDestroyKey(self._handle)
            self._handle=self._api.c.c_void_p()
            self._api.close()


def _public_p256_blob(value):
    import base64
    if type(value) is not str:
        raise ValueError('SIGNATURE_REFUSED')
    raw=base64.b64decode(value,validate=True)
    if len(raw)!=72 or raw[:8]!=struct.pack('<II',0x31534345,32):
        raise ValueError('SIGNATURE_REFUSED')
    return raw


def _verify_p256(public_blob, digest, signature):
    api=None; key=None
    try:
        if (type(public_blob) is not bytes or len(public_blob)!=72
                or public_blob[:8]!=struct.pack('<II',0x31534345,32)
                or type(digest) is not bytes or len(digest)!=32
                or type(signature) is not bytes or len(signature)!=64):
            return False
        api=_CngP256(); c=api.c; key=c.c_void_p()
        api.check(api.dll.BCryptImportKeyPair(api.provider,None,'ECCPUBLICBLOB',
            c.byref(key),api.buffer(public_blob),72,0))
        return api.dll.BCryptVerifySignature(key,None,api.buffer(digest),32,
                                             api.buffer(signature),64,0)==0
    except BaseException:
        return False
    finally:
        if api is not None:
            if key:api.dll.BCryptDestroyKey(key)
            api.close()


def _verify_scoped_approval(activation, trust, *, allow_test_trust=False):
    import base64
    import hmac
    try:
        verifier=_owner_verifier()
        if (trust.get('scope')!=_ibkr_trust_scope()
                or trust.get('signature_algorithm')!=_IBKR_SIGNATURE_ALGORITHM
                or verifier.validate_trust_metadata(trust,allow_test_trust=allow_test_trust)
                or trust.get('state')!='ACTIVE'
                or type(trust.get('current_key_version')) is not int
                or trust['current_key_version']<=0):
            return False
        evidence=activation['approval_evidence']
        if type(evidence) is not dict or set(evidence)!={
            'type','canonical_payload_schema','approval_nonce','key_id','key_version',
            'key_fingerprint_sha256','canonical_payload_sha256','approval_signature_base64'}:
            return False
        if (evidence['type']!=_IBKR_SIGNATURE_ALGORITHM
                or evidence['canonical_payload_schema']!=verifier.PAYLOAD_SCHEMA
                or type(evidence['approval_nonce']) is not str or not evidence['approval_nonce']
                or evidence['key_id']!=_IBKR_OWNER_KEY_ID
                or type(evidence['key_version']) is not int):
            return False
        record,error=verifier._trusted_key_record(trust,evidence['key_id'],evidence['key_version'])
        if error or record is None or type(record['key_version']) is not int:return False
        public=_public_p256_blob(record['public_key_blob_base64'])
        fingerprint=hashlib.sha256(public).hexdigest()
        if (not hmac.compare_digest(fingerprint,record['key_fingerprint_sha256'])
                or not hmac.compare_digest(fingerprint,evidence['key_fingerprint_sha256'])):
            return False
        digest=hashlib.sha256(verifier.canonical_payload(activation).encode('utf-8')).digest()
        if not hmac.compare_digest(digest.hex(),evidence['canonical_payload_sha256']):return False
        signature=base64.b64decode(evidence['approval_signature_base64'],validate=True)
        return _verify_p256(public,digest,signature)
    except BaseException:
        return False



def _owner_active_version(signer, trust):
    version=getattr(signer,'key_version',None)
    current=trust.get('current_key_version')
    if type(version) is not int or version<=0 or type(current) is not int or version!=current:
        raise ValueError('SIGNING_REFUSED')
    return version


def _owner_sign_handshake_grant(signer, packet):
    # Future human-initiated signing only; this method never launches a worker.
    import base64
    if type(packet) is not dict or set(packet) != {'activation','host_evidence','context'}:
        raise ValueError('SIGNING_REFUSED')
    activation=packet['activation']; host=packet['host_evidence']; context=packet['context']
    if not _activation_plain(activation) or not _activation_plain(host) or not _activation_plain(context):
        raise ValueError('SIGNING_REFUSED')
    trust=_owner_trust()
    if trust.get('state')!='ACTIVE' or trust.get('environment')!='PRODUCTION':
        raise ValueError('SIGNING_REFUSED')
    verifier=_owner_verifier()
    if verifier.validate_trust_metadata(trust):
        raise ValueError('SIGNING_REFUSED')
    version=_owner_active_version(signer,trust)
    record,error=verifier._trusted_key_record(trust,_IBKR_OWNER_KEY_ID,version)
    if (error or record is None or type(record['key_version']) is not int
            or _public_p256_blob(record['public_key_blob_base64'])!=signer.public_blob):
        raise ValueError('SIGNING_REFUSED')
    fingerprint=hashlib.sha256(signer.public_blob).hexdigest()
    if record['key_fingerprint_sha256']!=fingerprint:
        raise ValueError('SIGNING_REFUSED')
    evidence=activation.get('approval_evidence')
    if (type(evidence) is not dict or set(evidence)!={
            'type','canonical_payload_schema','approval_nonce','key_id','key_version',
            'key_fingerprint_sha256','canonical_payload_sha256','approval_signature_base64'}
            or evidence['type']!=_IBKR_SIGNATURE_ALGORITHM
            or evidence['canonical_payload_schema']!=verifier.PAYLOAD_SCHEMA
            or evidence['key_id']!=_IBKR_OWNER_KEY_ID or type(evidence['key_version']) is not int
            or evidence['key_version']!=version or evidence['key_fingerprint_sha256']!=fingerprint
            or evidence['approval_signature_base64']!='' or evidence['canonical_payload_sha256']!=''):
        raise ValueError('SIGNING_REFUSED')
    # Context is supplied publicly by the future execution parent. Both parent
    # and worker independently enforce its actual OS PID at admission.
    if (type(context.get('parent_pid')) is not int or context['parent_pid']<=0
            or not _handshake_candidate(activation,host,context,expected_pid=context['parent_pid'])):
        raise ValueError('SIGNING_REFUSED')
    digest=hashlib.sha256(verifier.canonical_payload(activation).encode('utf-8')).digest()
    evidence['canonical_payload_sha256']=digest.hex()
    evidence['approval_signature_base64']=base64.b64encode(signer.sign_digest(digest)).decode('ascii')
    if not _verify_scoped_approval(activation,trust):
        raise ValueError('SIGNING_REFUSED')
    return activation



def _owner_load_active_signing_binding(signer, trust_digest, binding_digest):
    # The owner explicitly pins public, reviewed activation hashes in the same
    # terminal. Reload only verified source bytes; the native private handle
    # remains in this process and is never serialized.
    for value in (trust_digest,binding_digest):
        if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None:
            raise ValueError('PUBLIC_PIN_REFUSED')
    path=_PREFLIGHT_REPO/_PREFLIGHT_MODULE
    raw=path.read_bytes()
    trust_raw=(_PREFLIGHT_REPO/_IBKR_TRUST_PATH).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=binding_digest or hashlib.sha256(trust_raw).hexdigest()!=trust_digest:
        raise ValueError('PUBLIC_PIN_REFUSED')
    spec=importlib.util.spec_from_file_location('_ibkr_owner_reviewed_binding',path)
    module=importlib.util.module_from_spec(spec)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    if module._TRUST_SHA!=trust_digest:
        raise ValueError('PUBLIC_PIN_REFUSED')
    trust=module._owner_trust()
    verifier=module._owner_verifier()
    if (trust.get('state')!='ACTIVE' or trust.get('environment')!='PRODUCTION'
            or verifier.validate_trust_metadata(trust)):
        raise ValueError('PUBLIC_PIN_REFUSED')
    version=_owner_active_version(signer,trust)
    record,error=verifier._trusted_key_record(trust,_IBKR_OWNER_KEY_ID,version)
    if (error or record is None or type(record['key_version']) is not int
            or module._public_p256_blob(record['public_key_blob_base64'])!=signer.public_blob
            or record['key_fingerprint_sha256']!=hashlib.sha256(signer.public_blob).hexdigest()):
        raise ValueError('PUBLIC_PIN_REFUSED')
    return module



class _OwnerConsoleExpired(ValueError):
    pass


class _OwnerConsoleOverflow(ValueError):
    pass


def _owner_console_line(deadline, limit):
    import msvcrt
    line=''
    extended_suffix=False
    overflow=False
    while _now()<deadline:
        if msvcrt.kbhit():
            char=msvcrt.getwch()
            if extended_suffix:
                extended_suffix=False
                continue
            if char=='\x03':raise KeyboardInterrupt
            if char in ('\r','\n'):
                if overflow:raise _OwnerConsoleOverflow('INPUT_LIMIT')
                return line
            if overflow:continue
            if char=='\x1b':line=''
            elif char=='\b':line=line[:-1]
            elif char in ('\x00','\xe0'):
                extended_suffix=True
            else:
                if len(line)>=limit:
                    overflow=True
                else:
                    line+=char
            continue
        time.sleep(0.05)
    raise _OwnerConsoleExpired('SESSION_EXPIRED')


def _owner_key_session_main():
    # Only the human's interactive terminal can enter this ceremony.
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return 2
    if not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode:
        return 2
    signer=None
    close_reason='REFUSED'
    try:
        if input('Type GENERATE IBKR OWNER KEY to start one local ceremony: ')!='GENERATE IBKR OWNER KEY':
            return 2
        signer=_P256OwnerKey.generate()
        if type(signer.key_version) is not int or signer.key_version!=_IBKR_CEREMONY_KEY_VERSION:
            raise ValueError('SIGNER_REFUSED')
        import base64
        public=signer.public_blob
        challenge=b'AIOS_IBKR_OWNER_KEY_PROOF_V1\0'+os.urandom(32)
        digest=hashlib.sha256(challenge).digest()
        signature=signer.sign_digest(digest)
        verified=_verify_p256(public,digest,signature)
        receipt={'KEY IDENTITY FOUND':'YES','SIGNING CHANNEL FOUND':'YES',
                 'SYNTHETIC SIGNATURE VERIFIED':'YES' if verified else 'NO',
                 'PUBLIC FINGERPRINT':{'algorithm':_IBKR_SIGNATURE_ALGORITHM,
                    'key_id':_IBKR_OWNER_KEY_ID,'key_version':signer.key_version,
                    'fingerprint_sha256':hashlib.sha256(public).hexdigest(),
                    'public_key_blob_base64':base64.b64encode(public).decode('ascii')},
                 'SECRET PERSISTED':'NO'}
        print(json.dumps(receipt,indent=2),flush=True)
        if not verified:return 2
        deadline=_now()+45*60
        signing_used=False
        active_binding=None
        print('OWNER_SESSION_ACTIVE: keep this process open for fingerprint review.',flush=True)
        print('Public command input is hidden. STATUS reports readiness; EXIT discards the key.',flush=True)
        while _now()<deadline:
            print('OWNER COMMAND (hidden input)> ',end='',flush=True)
            try:
                line=_owner_console_line(deadline,160)
            except _OwnerConsoleOverflow:
                print('\nOWNER_COMMAND_REFUSED_INPUT_LIMIT',flush=True)
                continue
            print('',flush=True)
            command=line.strip().upper()
            if not command:continue
            if command=='EXIT':
                close_reason='OWNER_EXIT'
                return 0
            if command=='STATUS':
                state='PUBLIC_PIN_ACTIVE' if active_binding is not None else 'PUBLIC_PIN_PENDING'
                print('OWNER_STATUS: key_version='+str(signer.key_version)+' '+state+
                      ' seconds_remaining='+str(max(0,int(deadline-_now()))),flush=True)
                continue
            if command.startswith('PIN PUBLIC TRUST ') and active_binding is None:
                try:
                    parts=line.strip().split()
                    if len(parts)!=5:raise ValueError('PUBLIC_PIN_REFUSED')
                    active_binding=_owner_load_active_signing_binding(signer,parts[3],parts[4])
                    print('PUBLIC_TRUST_PINNED_IN_OWNER_PROCESS',flush=True)
                except (KeyboardInterrupt,EOFError):
                    raise
                except BaseException:
                    print('PUBLIC_PIN_REFUSED',flush=True)
                continue
            if command=='SIGN IBKR GRANT' and not signing_used and active_binding is not None:
                signing_used=True
                try:
                    print('Paste one public grant/context/host JSON:',flush=True)
                    text=_owner_console_line(deadline,32768)
                    if _now()>=deadline:raise _OwnerConsoleExpired('SESSION_EXPIRED')
                    grant=active_binding._owner_sign_handshake_grant(signer,json.loads(text))
                    print(json.dumps({'SIGNED_PUBLIC_GRANT':grant}),flush=True)
                except (KeyboardInterrupt,EOFError,_OwnerConsoleExpired,_OwnerConsoleOverflow):
                    raise
                except BaseException:
                    print('SIGNING_REFUSED',flush=True)
                continue
            print('OWNER_COMMAND_REFUSED',flush=True)
        close_reason='EXPIRED'
        return 0
    except _OwnerConsoleExpired:
        close_reason='EXPIRED'
        return 0
    except _OwnerConsoleOverflow:
        close_reason='INPUT_LIMIT'
        return 2
    except (KeyboardInterrupt,EOFError):
        close_reason='INTERRUPTED'
        return 2
    except BaseException:
        close_reason='ERROR'
        print('OWNER_KEY_SESSION_BLOCKED',flush=True)
        return 2
    finally:
        if signer is not None:
            try:
                signer.close()
            except BaseException:
                print('OWNER_KEY_CLEANUP_UNVERIFIED',flush=True)
            else:
                print('OWNER_KEY_SESSION_CLOSED: '+close_reason,flush=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['--ibkr-handshake-worker']:
        _handshake_worker_main()
    elif sys.argv[1:] == ['--ibkr-owner-key-session']:
        raise SystemExit(_owner_key_session_main())
