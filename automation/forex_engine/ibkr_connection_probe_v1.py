"""FIXTURE_ONLY IBKR startup privacy contract. No genuine transport exists.

This bounded model neither imports the SDK nor grants connection permission.
Synthetic framing is a conservative subset of the reviewed 1051.1 shapes, not
a vendor protocol implementation. It has no logger, writer, credential loader,
IPC sender, account cache, network, platform launcher, or application requests.
Owned bytearrays are overwritten; Python/OS/TWS forensic erasure is unverified.
SDK logging, process isolation and host assurance require a separate binding.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from datetime import datetime, timezone

__all__ = [
    'PrivacyBoundaryError', 'validate_connection_plan',
    'classify_connection_readiness', 'fixture_initialization_envelopes',
    'FixtureConnectionLifecycleTransport', 'replay_connection_fixture',
    'validate_public_receipt',
]

_LIMITS = {
    'max_attempts': 1, 'max_elapsed_seconds': 30,
    'startup_timeout_seconds': 10, 'cleanup_timeout_seconds': 2,
    'max_retries': 0, 'max_reconnects': 0,
    'max_input_bytes': 65536, 'max_frame_bytes': 8192,
    'max_queue_frames': 16, 'max_notice_frames': 16,
}
_CONTROLS = frozenset((
    'outputs_armed', 'no_file_logging', 'no_telemetry', 'no_debugger',
    'no_sitecustomize', 'host_dump_verified', 'paging_verified',
    'hibernation_verified', 'platform_logging_verified',
))
_PLAN_KEYS = frozenset(_LIMITS) | frozenset((
    'schema', 'evidence_kind', 'profile', 'privacy_policy', 'host', 'port',
    'client_id', 'environment', 'read_only_api', 'client_id_fresh',
    'master_client_id', 'expires_at_utc', 'source_pins', 'privacy_controls', 'grant',
))
_ERRORS = frozenset((
    'NONE', 'BLOCKED_PLAN', 'BLOCKED_TRANSPORT', 'BLOCKED_REUSE',
    'BLOCKED_TIME', 'BLOCKED_SEND', 'BLOCKED_FRAME', 'BLOCKED_LIMIT',
    'BLOCKED_STARTUP', 'BLOCKED_TERMINAL', 'DISCONNECT_UNVERIFIED',
))
# Bounded, volatile public anti-replay state only. No account/data cache,
# serialization, persistence, real human grant or cross-process authority.
_USED_FIXTURE_GRANTS = set()


class PrivacyBoundaryError(ValueError):
    """Constant error only. Never interpolate or attach a foreign payload."""


def _bad(code='BLOCKED_PLAN'):
    raise PrivacyBoundaryError(code)


def _plain(value, depth=0):
    """Reject foreign types before equality, repr, JSON or attribute access."""
    if depth > 4:
        return False
    t = type(value)
    if t is str:
        return len(value) <= 128
    if t is bool or value is None:
        return True
    if t is int:
        return -(1 << 63) <= value < (1 << 63)
    if t is float:
        return math.isfinite(value)
    if t is dict:
        return len(value) <= 32 and all(
            type(k) is str and len(k) <= 64 and _plain(v, depth + 1)
            for k, v in value.items()
        )
    return False


def _hash_shape(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_connection_plan(plan, now_utc):
    """Validate a public synthetic plan; return a detached public-only copy.

    The fixture fingerprint is alteration detection, not a signed human grant.
    Source/platform/host flags are invented fixture facts, never real evidence.
    """
    if type(plan) is not dict or not _plain(plan) or set(plan) != _PLAN_KEYS:
        _bad()
    expected = {
        'schema': 'AIOS_IBKR_CONNECTION_PLAN.v1', 'evidence_kind': 'FIXTURE_ONLY',
        'profile': 'OFFLINE_PRIVACY_FIXTURE', 'privacy_policy': 'FIXTURE_MINIMAL_STARTUP_V1',
        'host': '127.0.0.1', 'port': 7497, 'client_id': 132,
        'environment': 'FIXTURE_PAPER', 'read_only_api': True, 'client_id_fresh': True,
    }
    for key, value in (expected | _LIMITS).items():
        if type(plan[key]) is not type(value) or plan[key] != value:
            _bad()
    if type(plan['master_client_id']) is not int or not 0 <= plan['master_client_id'] <= 2147483647 or plan['master_client_id'] == 132:
        _bad()
    controls = plan['privacy_controls']
    if type(controls) is not dict or set(controls) != _CONTROLS or any(v is not True for v in controls.values()):
        _bad()
    pins = plan['source_pins']
    if type(pins) is not dict or set(pins) != {'evidence_kind', 'sdk_version', 'sdk_source_sha256', 'dependency_sha256', 'platform_version'}:
        _bad()
    if pins['evidence_kind'] != 'FIXTURE_ONLY' or pins['sdk_version'] != 'FIXTURE_VERSION' or pins['platform_version'] != 'FIXTURE_VERSION':
        _bad()
    if not _hash_shape(pins['sdk_source_sha256']) or not _hash_shape(pins['dependency_sha256']):
        _bad()
    grant = plan['grant']
    if type(grant) is not dict or set(grant) != {'evidence_kind', 'grant_id', 'used', 'plan_sha256'}:
        _bad()
    grant_id = grant['grant_id']
    if grant['evidence_kind'] != 'FIXTURE_ONLY' or type(grant_id) is not str or not grant_id.startswith('FIXTURE_ONLY_GRANT_') or not _hash_shape(grant_id[19:] + '0' * 32) or grant['used'] is not False or not _hash_shape(grant['plan_sha256']):
        _bad()
    body = {**{k: v for k, v in plan.items() if k != 'grant'},
            'grant': {k: v for k, v in grant.items() if k != 'plan_sha256'}}
    if hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest() != grant['plan_sha256']:
        _bad()
    valid = False
    expiry = None
    if type(now_utc) is datetime and now_utc.tzinfo is timezone.utc and type(plan['expires_at_utc']) is str:
        try:
            expiry = datetime.fromisoformat(plan['expires_at_utc'].replace('Z', '+00:00'))
            valid = expiry.tzinfo is not None and expiry.utcoffset().total_seconds() == 0 and now_utc < expiry
        except (ValueError, OverflowError):
            pass
    if not valid:
        _bad()
    copy = json.loads(json.dumps(plan, allow_nan=False))
    return copy


def classify_connection_readiness(snapshot):
    """No snapshot can authorize genuine SDK construction or connection."""
    strict = (type(snapshot) is dict and _plain(snapshot)
              and snapshot.get('profile') == 'STANDARD_IBKR_SDK'
              and snapshot.get('no_account_data') is True)
    return {
        'status': 'BLOCKED', 'real_connection_authorized': False,
        'error_code': 'BLOCKED_AUTOMATIC_PRIVATE_STARTUP' if strict else 'BLOCKED_INCOMPLETE_READINESS',
    }


def _frame(payload):
    return struct.pack('!I', len(payload)) + payload


def fixture_initialization_envelopes(server_version):
    """Public synthetic envelope constants. Never transmitted by this module."""
    if type(server_version) is not int or not 100 <= server_version <= 226:
        _bad('BLOCKED_TRANSPORT')
    initial = b'API\0' + _frame(b'v100..226')
    if server_version >= 213:
        start = _frame(struct.pack('!I', 271) + b'\x08\x84\x01\x12\x00')
    elif server_version >= 201:
        start = _frame(struct.pack('!I', 71) + b'2\x00132\x00\x00')
    else:
        start = _frame(b'71\x002\x00132\x00\x00')
    return initial, start


def _wipe(buffer):
    for i in range(len(buffer)):
        buffer[i] = 0


def _digits(buffer, start, end, maximum=2147483647, negative_one=False):
    if negative_one and end - start == 2 and buffer[start] == 45 and buffer[start + 1] == 49:
        return -1
    if end <= start or end - start > 10:
        _bad('BLOCKED_FRAME')
    value = 0
    for i in range(start, end):
        digit = buffer[i] - 48
        if not 0 <= digit <= 9:
            _bad('BLOCKED_FRAME')
        value = value * 10 + digit
        if value > maximum:
            _bad('BLOCKED_FRAME')
    return value


def _varint(buffer, cursor, end):
    value = 0
    for shift in range(0, 70, 7):
        if cursor >= end:
            _bad('BLOCKED_FRAME')
        byte = buffer[cursor]; cursor += 1
        if shift == 63 and byte > 1:
            _bad('BLOCKED_FRAME')
        value |= (byte & 127) << shift
        if byte < 128:
            if shift and byte == 0:
                _bad('BLOCKED_FRAME')
            return value, cursor
    _bad('BLOCKED_FRAME')


def _proto_fields(buffer, start, end, shape):
    fields = {}
    cursor = start
    while cursor < end:
        key, cursor = _varint(buffer, cursor, end)
        tag, wire = key >> 3, key & 7
        if tag not in shape or tag in fields or shape[tag] != wire:
            _bad('BLOCKED_FRAME')
        if wire == 0:
            value, cursor = _varint(buffer, cursor, end)
            fields[tag] = value
        else:
            length, cursor = _varint(buffer, cursor, end)
            if length > end - cursor:
                _bad('BLOCKED_FRAME')
            # Retain indices only, never copy/decode a private string.
            fields[tag] = (cursor, cursor + length)
            cursor += length
    return fields


def _legacy_fields(buffer, start, end):
    fields = []
    cursor = start
    for i in range(start, end):
        if buffer[i] == 0:
            fields.append((cursor, i)); cursor = i + 1
            if len(fields) > 6:
                _bad('BLOCKED_FRAME')
    if cursor != end:
        _bad('BLOCKED_FRAME')
    return fields


def _nonempty_ascii(buffer, region):
    start, end = region
    return end > start and all(32 <= buffer[i] <= 126 for i in range(start, end))


class FixtureConnectionLifecycleTransport:
    """Single-use, sealed, in-memory fixture owner; never an SDK/client/socket.

    Accepted bytearrays transfer model ownership and are overwritten on every
    terminal path. Callers may hold views to verify this limited guarantee.
    There is no business callback or generic dispatch seam.
    """
    __slots__ = (
        '_chunks', '_pending', '_server', '_cleanup_ok', '_sent', '_armed',
        '_used', '_closed', '_revoked', '_error', '_accounts', '_next',
        '_notices', '_input', '_forms', '_semantic', '_cleared',
    )

    def __init__(self, chunks, server_version, cleanup_verified=True):
        if type(chunks) is not list or len(chunks) > 16 or type(cleanup_verified) is not bool:
            _bad('BLOCKED_TRANSPORT')
        if any(type(c) is not bytearray for c in chunks) or sum(len(c) for c in chunks) > 65536:
            _bad('BLOCKED_LIMIT')
        fixture_initialization_envelopes(server_version)
        self._chunks = list(chunks)
        self._pending = bytearray()
        self._server = server_version
        self._cleanup_ok = cleanup_verified
        self._sent = []
        self._armed = self._used = self._closed = self._revoked = False
        self._error = 'NONE'
        self._accounts = self._next = False
        self._notices = self._input = self._forms = self._semantic = 0
        self._cleared = True

    def __repr__(self):
        return '<FIXTURE_ONLY privacy transport>'

    def __reduce_ex__(self, protocol):
        _bad('BLOCKED_TRANSPORT')

    @property
    def sent_envelopes(self):
        return tuple(self._sent)

    @property
    def revoked(self):
        return self._revoked

    @property
    def closed(self):
        return self._closed

    @property
    def pending_bytes(self):
        return len(self._pending)

    @property
    def retained_input_chunks(self):
        return len(self._chunks)

    @property
    def callback_forms_processed(self):
        return self._forms

    @property
    def semantic_startup_frames(self):
        return self._semantic

    def send_envelope(self, envelope):
        # Final model sender: exact bytes, order, source shape, lease and count.
        expected = fixture_initialization_envelopes(self._server)
        if not self._armed or self._revoked or type(envelope) is not bytes or len(self._sent) >= 2 or envelope != expected[len(self._sent)]:
            self._error = 'BLOCKED_SEND'
            _ORIGINAL_CLEANUP(self)
            return False
        self._sent.append(envelope)
        return True

    def _decode(self, start, end):
        buffer = self._pending
        if self._server >= 201:
            if end - start < 4:
                _bad('BLOCKED_FRAME')
            kind = struct.unpack_from('!I', buffer, start)[0]; start += 4
        else:
            stop = start
            while stop < end and buffer[stop] != 0:
                stop += 1
            kind = _digits(buffer, start, stop)
            start = stop + 1
        is_proto = kind >= 200
        semantic = kind - 200 if is_proto else kind
        if semantic not in (4, 9, 15) or is_proto and self._server < 207:
            _bad('BLOCKED_FRAME')
        if is_proto:
            shape = {1: 2} if semantic == 15 else {1: 0} if semantic == 9 else {1: 0, 2: 0, 3: 0, 4: 2, 5: 2}
            fields = _proto_fields(buffer, start, end, shape)
            if semantic == 15:
                if set(fields) != {1} or not _nonempty_ascii(buffer, fields[1]):
                    _bad('BLOCKED_FRAME')
            elif semantic == 9:
                if set(fields) != {1} or fields[1] > 2147483647:
                    _bad('BLOCKED_FRAME')
            else:
                if fields.get(1, (1 << 64) - 1) != (1 << 64) - 1 or fields.get(3) not in (2104, 2106, 2158):
                    _bad('BLOCKED_FRAME')
                if 2 in fields and fields[2] > (1 << 63) - 1 or 5 in fields and fields[5][0] != fields[5][1]:
                    _bad('BLOCKED_FRAME')
        else:
            fields = _legacy_fields(buffer, start, end)
            if semantic in (9, 15):
                if len(fields) != 2 or _digits(buffer, *fields[0]) != 1:
                    _bad('BLOCKED_FRAME')
                if semantic == 9:
                    _digits(buffer, *fields[1])
                elif not _nonempty_ascii(buffer, fields[1]):
                    _bad('BLOCKED_FRAME')
            else:
                if len(fields) != 4 or _digits(buffer, *fields[0]) != 2 or _digits(buffer, *fields[1], negative_one=True) != -1 or _digits(buffer, *fields[2]) not in (2104, 2106, 2158):
                    _bad('BLOCKED_FRAME')
        # Model both protobuf callback forms without any private argument,
        # callback object, default EWrapper logger, or premature message Clear.
        self._forms += 2 if is_proto else 1
        if semantic == 15:
            if self._accounts:
                _bad('BLOCKED_FRAME')
            self._accounts = True; self._semantic += 1
        elif semantic == 9:
            if self._next:
                _bad('BLOCKED_FRAME')
            self._next = True; self._semantic += 1
        else:
            self._notices += 1
            if self._notices > 16:
                _bad('BLOCKED_LIMIT')

    def ingest(self, chunk):
        if type(chunk) is not bytearray:
            self._error = 'BLOCKED_FRAME'; _ORIGINAL_CLEANUP(self)
            return False
        if not self._armed or self._revoked:
            _wipe(chunk)
            self._error = 'BLOCKED_TERMINAL'; _ORIGINAL_CLEANUP(self)
            return False
        self._input += len(chunk)
        if self._input > 65536:
            _wipe(chunk)
            self._error = 'BLOCKED_LIMIT'; _ORIGINAL_CLEANUP(self)
            return False
        self._pending.extend(chunk); _wipe(chunk)
        processed = 0
        failure = None
        try:
            while len(self._pending) >= 4:
                size = struct.unpack_from('!I', self._pending)[0]
                if not 0 < size <= 8192:
                    _bad('BLOCKED_FRAME')
                if len(self._pending) < 4 + size:
                    break
                processed += 1
                if processed > 16:
                    _bad('BLOCKED_LIMIT')
                self._decode(4, 4 + size)
                for i in range(4 + size):
                    self._pending[i] = 0
                del self._pending[:4 + size]
                if self._accounts and self._next:
                    self._revoked = self._closed = True
                    if self._pending:
                        _bad('BLOCKED_TERMINAL')
                    break
        except PrivacyBoundaryError as error:
            failure = error.args[0] if type(error.args[0]) is str and error.args[0] in _ERRORS else 'BLOCKED_FRAME'
        if failure is not None:
            self._error = failure; _ORIGINAL_CLEANUP(self)
            return False
        return True

    def _cleanup(self):
        # Original slot descriptors bypass an injected __getattribute__ or
        # replaced class property. Revoke first; always drop owned references.
        _set_slot(self, '_revoked', True); _set_slot(self, '_closed', True)
        _set_slot(self, '_armed', False)
        cleared = _slot(self, '_cleared') is True
        pending, chunks = _slot(self, '_pending'), _slot(self, '_chunks')
        buffers = [pending]
        if type(chunks) is list:
            buffers.extend(chunks)
        else:
            cleared = False
        for buffer in buffers:
            if type(buffer) is not bytearray:
                cleared = False
                continue
            try:
                _wipe(buffer)
            except Exception:
                cleared = False
        _set_slot(self, '_pending', bytearray())
        _set_slot(self, '_chunks', [])
        _set_slot(self, '_input', 0)
        _set_slot(self, '_cleared', cleared)
        if not cleared:
            _set_slot(self, '_cleanup_ok', False)


_ORIGINAL_CLEANUP = FixtureConnectionLifecycleTransport._cleanup
_CLASS_PINS = dict(vars(FixtureConnectionLifecycleTransport))
_SLOT_PINS = {name: _CLASS_PINS[name] for name in FixtureConnectionLifecycleTransport.__slots__}


def _slot(transport, name):
    return _SLOT_PINS[name].__get__(transport, FixtureConnectionLifecycleTransport)


def _set_slot(transport, name, value):
    _SLOT_PINS[name].__set__(transport, value)


def _intact():
    namespace = vars(FixtureConnectionLifecycleTransport)
    return set(namespace) == set(_CLASS_PINS) and all(namespace[name] is member for name, member in _CLASS_PINS.items())


def _receipt(transport=None, error='BLOCKED_PLAN'):
    known = type(transport) is FixtureConnectionLifecycleTransport
    accounts = _slot(transport, '_accounts') is True if known else False
    next_seen = _slot(transport, '_next') is True if known else False
    cleared = known and _slot(transport, '_cleared') is True
    cleaned = bool(cleared and _slot(transport, '_cleanup_ok') is True and _slot(transport, '_closed') is True)
    complete = bool(known and accounts and next_seen and cleaned and error == 'NONE')
    if known and not cleaned:
        error = 'DISCONNECT_UNVERIFIED'
    status = 'MODEL_COMPLETE' if complete else 'DISCONNECT_UNVERIFIED' if error == 'DISCONNECT_UNVERIFIED' else 'BLOCKED'
    return {
        'schema': 'AIOS_IBKR_CONNECTION_PROBE_RECEIPT.v1', 'evidence_kind': 'FIXTURE_ONLY',
        'status': status, 'error_code': error,
        'modeled_lifecycle_complete': complete, 'real_connection_verified': False,
        'source_admitted': False, 'paper_ready': False, 'live_ready': False,
        'managed_accounts_seen': accounts, 'next_valid_id_seen': next_seen,
        'cleanup_verified': bool(cleaned), 'owned_mutable_buffers_cleared': bool(cleared),
        'forensic_erasure_verified': False,
        'initialization_envelopes': len(_slot(transport, '_sent')) if known else 0,
        'forbidden_envelopes': 0, 'genuine_effects': 0,
    }


def replay_connection_fixture(plan, transport, timeline, now_utc):
    """One finite fixture run; sanitize failures and always revoke/clean up.

    Every run consumes a distinct public synthetic grant, even on failure.
    Reusing the same transport or grant/copy is refused in this model context.
    This does not implement genuine signatures, process isolation or deadlines.
    """
    known = type(transport) is FixtureConnectionLifecycleTransport
    error = 'BLOCKED_PLAN'
    try:
        valid = validate_connection_plan(plan, now_utc)
        error = 'BLOCKED_TRANSPORT'
        if known and _intact():
            grant_id = valid['grant']['grant_id']
            if transport._used or transport._revoked or grant_id in _USED_FIXTURE_GRANTS:
                error = 'BLOCKED_REUSE'
            elif len(_USED_FIXTURE_GRANTS) >= 64:
                error = 'BLOCKED_LIMIT'
            else:
                transport._used = True
                _USED_FIXTURE_GRANTS.add(grant_id)
                error = 'NONE'
                good_time = type(timeline) is list and len(timeline) == len(transport._chunks)
                previous = 0.0
                for value in timeline if type(timeline) is list and len(timeline) <= 16 else ():
                    # Range first: math.isfinite converts huge integers to float.
                    if type(value) not in (int, float) or not previous <= value <= 10 or not math.isfinite(value):
                        good_time = False
                        break
                    previous = value
                expiry = datetime.fromisoformat(valid['expires_at_utc'].replace('Z', '+00:00'))
                if (expiry - now_utc).total_seconds() <= previous + 2:
                    good_time = False
                if not good_time:
                    error = 'BLOCKED_TIME'
                else:
                    transport._armed = True
                    for envelope in fixture_initialization_envelopes(transport._server):
                        if not transport.send_envelope(envelope):
                            error = 'BLOCKED_SEND'
                            break
                    if error == 'NONE':
                        for chunk in tuple(transport._chunks):
                            if not transport.ingest(chunk):
                                error = transport._error
                                break
                        if error == 'NONE' and (transport._pending or not transport._accounts or not transport._next):
                            error = 'BLOCKED_STARTUP'
    except PrivacyBoundaryError:
        # Never forward exception objects, args, text, cause, context or locals.
        error = 'BLOCKED_PLAN'
    except Exception:
        error = 'BLOCKED_TRANSPORT'
    finally:
        if known:
            _ORIGINAL_CLEANUP(transport)
    return _receipt(transport if known else None, error)


_PUBLIC_DEFAULT = _receipt()
_PUBLIC_KEYS = frozenset(_PUBLIC_DEFAULT)


def validate_public_receipt(receipt):
    """Strict scalar allowlist; no default serializer or foreign repr hook."""
    if type(receipt) is not dict or len(receipt) != len(_PUBLIC_KEYS) or any(type(k) is not str for k in receipt) or set(receipt) != _PUBLIC_KEYS:
        _bad('BLOCKED_TRANSPORT')
    for key, default in _PUBLIC_DEFAULT.items():
        if type(receipt[key]) is not type(default):
            _bad('BLOCKED_TRANSPORT')
    if receipt['schema'] != _PUBLIC_DEFAULT['schema'] or receipt['evidence_kind'] != 'FIXTURE_ONLY':
        _bad('BLOCKED_TRANSPORT')
    if receipt['status'] not in ('MODEL_COMPLETE', 'BLOCKED', 'DISCONNECT_UNVERIFIED') or receipt['error_code'] not in _ERRORS:
        _bad('BLOCKED_TRANSPORT')
    for key in ('real_connection_verified', 'source_admitted', 'paper_ready', 'live_ready', 'forensic_erasure_verified'):
        if receipt[key] is not False:
            _bad('BLOCKED_TRANSPORT')
    if not 0 <= receipt['initialization_envelopes'] <= 2 or receipt['forbidden_envelopes'] != 0 or receipt['genuine_effects'] != 0:
        _bad('BLOCKED_TRANSPORT')
    complete = receipt['status'] == 'MODEL_COMPLETE'
    if receipt['modeled_lifecycle_complete'] is not complete:
        _bad('BLOCKED_TRANSPORT')
    if complete and not (receipt['cleanup_verified'] and receipt['owned_mutable_buffers_cleared'] and receipt['managed_accounts_seen'] and receipt['next_valid_id_seen'] and receipt['error_code'] == 'NONE' and receipt['initialization_envelopes'] == 2):
        _bad('BLOCKED_TRANSPORT')
    if not complete and receipt['error_code'] == 'NONE':
        _bad('BLOCKED_TRANSPORT')
    if receipt['status'] == 'DISCONNECT_UNVERIFIED' and (receipt['cleanup_verified'] or receipt['error_code'] != 'DISCONNECT_UNVERIFIED'):
        _bad('BLOCKED_TRANSPORT')
    return dict(receipt)
