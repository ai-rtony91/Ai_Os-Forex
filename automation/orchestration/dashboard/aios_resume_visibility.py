"""Public read model of the existing verified resume owner; never an authority.

The isolated CLI writes JSON to stdout only. It does not publish a second head,
activate a reader/worker, recover an attempt or supply native admission context.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).absolute().parents[3]
OWNER_PATH = ROOT / 'automation/orchestration/aios_resume_state.py'
OWNER_SHA256 = 'ce0881237141570ff36680f620cc1c7f132efb044858f590f8a2851e987b219f'
SOURCE_PATH = 'Reports/aios_resume/AIOS_RESUME_STATE_latest.json'
SCHEMA = 'AIOS_PUBLIC_RESUME_VISIBILITY.v1'
TTL_SECONDS = 60
_OWNER = None


def load_owner():
    global _OWNER
    raw = OWNER_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != OWNER_SHA256:
        raise ValueError('canonical_owner_source_changed')
    if _OWNER is None:
        spec = importlib.util.spec_from_file_location('wp08_verified_resume_owner', OWNER_PATH)
        _OWNER = importlib.util.module_from_spec(spec)
        exec(compile(raw, str(OWNER_PATH), 'exec'), _OWNER.__dict__)
    return _OWNER


def public_id(value):
    return value if type(value) is str and re.fullmatch(r'[A-Za-z0-9_.:/ -]{1,160}', value) else 'UNKNOWN'


def unknown(reason='verification_unavailable'):
    return {'schema': SCHEMA, 'repo_root': str(ROOT), 'source_path': SOURCE_PATH,
            'source_owner_sha256': OWNER_SHA256, 'reader_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'integrity': 'UNKNOWN', 'checkpoint_id': None, 'result': 'UNKNOWN',
            'reason_code': public_id(reason), 'goal': 'UNKNOWN', 'selected_action': 'UNKNOWN',
            'task_id': 'UNKNOWN', 'next_component': 'UNKNOWN', 'resume_ready': False,
            'accepted_at': None, 'freshness': {'current': False, 'expires_at': None, 'ttl_seconds': TTL_SECONDS},
            'authority_state': 'EVIDENCE_ONLY', 'approval_required': True,
            'execution_allowed': False, 'mutation_allowed': False, 'worker_state': 'UNKNOWN',
            'next_safe_action': 'Review checkpoint evidence; protected actions require separate approval.'}


def read_public_resume(repo_root=ROOT, *, now=None, admitted_context=None,
                       native_admission_reader=None, expected_request=None):
    value = unknown()
    try:
        if Path(repo_root).resolve() != ROOT.resolve():
            raise ValueError('canonical_selected_owner_mismatch')
        owner = load_owner()
        # The actual verifier checks archive/pending/attempt/completion and
        # current source/input identities under its existing publication lock.
        # Native identity without its trusted admission reader fails UNKNOWN;
        # no fabricated context, recovery, caller PASS or JS rehash is used.
        if any(item is not None for item in (admitted_context, native_admission_reader, expected_request)):
            if admitted_context is None or not callable(native_admission_reader) or expected_request is None:
                raise ValueError('native_admission_reader_required')
            state = owner.load_native_requirement(ROOT, output_dir=owner.DEFAULT_OUTPUT_DIR,
                expected_request=expected_request, admitted_context=admitted_context,
                native_admission_reader=native_admission_reader)
            if state is None:
                raise ValueError('native_accepted_requirement_unavailable')
            expected_schema = 'AIOS_NATIVE_PUBLICATION.v1'
        else:
            state = owner.load_resume_state(ROOT)
            expected_schema = owner.SCHEMA
        if state.get('schema') != expected_schema or state.get('safety') != owner.safety_flags():
            raise ValueError('canonical_public_contract_invalid')
        stamp = state.get('generated_at_utc')
        accepted = datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        observed = now or datetime.now(timezone.utc)
        age = (observed - accepted).total_seconds()
        result = public_id(state.get('result'))
        identity = state['publication']['execution_identity']
        value.update(integrity='VERIFIED', checkpoint_id=state['checkpoint_id'], result=result,
                     reason_code=public_id(state.get('resume_reason_code')), goal=public_id(state.get('goal')),
                     selected_action=public_id(state.get('selected_action')), task_id=public_id(identity.get('task_id')),
                     next_component=public_id(state.get('next_build_plan', {}).get('next_component')),
                     resume_ready=state.get('resume_ready') is True, accepted_at=stamp,
                     freshness={'current': 0 <= age <= TTL_SECONDS,
                                'expires_at': (accepted + timedelta(seconds=TTL_SECONDS)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                                'ttl_seconds': TTL_SECONDS})
        if age < 0:
            value['reason_code'] = 'acceptance_time_in_future'
    except (OSError, ValueError, TypeError, KeyError, ImportError, AttributeError) as error:
        reason = str(error)
        value['reason_code'] = reason if re.fullmatch(r'[a-z_]{1,120}', reason) else 'verification_unavailable'
    return value


def main():
    print(json.dumps(read_public_resume(), sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
