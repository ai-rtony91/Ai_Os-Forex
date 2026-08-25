"""Acquire sanitized, raw-only OANDA Practice M5 evidence for FINAL_HOLDOUT_V2."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from automation.forex_engine.oanda_read_only_client import (
    OandaReadOnlyClient,
    OandaReadOnlyClientError,
)


PACKET_ID = 'PKT-EAST-FOREX-NEW-OOS-DATA-ACQUISITION-014'
SCHEMA = 'AIOS_FOREX_FINAL_HOLDOUT_V2_RAW_ACCUMULATOR_V1'
RESULT_SCHEMA = 'AIOS_FOREX_NEW_OOS_DATA_ACQUISITION_V1_RESULTS'
DATASET_ID = 'FINAL_HOLDOUT_V2'
V1_END_TIMESTAMP = '2026-08-21T19:50:00.000000000Z'
V1_UNIQUE_TIMESTAMP_COUNT = 206
REPLAY_CACHE_PATH = Path('.aios/runtime/forex_multipair_m5_replay_mba_v1/replay_cache.json')
RECOVERY_PATH = Path('Reports/forex_delivery/AIOS_FOREX_HOLDOUT_CONTAMINATION_RECOVERY_V1_RESULTS.json')
GUARD_PATH = Path('.aios/runtime/forex_final_holdout_access_guard_v1.json')
ACCUMULATOR_PATH = Path('.aios/runtime/forex_final_holdout_v2_raw_accumulator_v1.json')
RESULT_PATH = Path('Reports/forex_delivery/AIOS_FOREX_NEW_OOS_DATA_ACQUISITION_V1_RESULTS.json')
RAW_KEYS = {'instrument', 'timestamp_utc', 'open', 'high', 'low', 'close', 'volume', 'complete'}


def _stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n'


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def _parse_utc(value: Any) -> datetime:
    text = str(value or '')
    if not text.endswith('Z'):
        raise ValueError('timestamp_must_be_explicit_utc')
    parsed = datetime.fromisoformat(text[:-1].replace('Z', '') + '+00:00')
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError('timestamp_must_be_explicit_utc')
    return parsed


def _finite(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError('finite_number_required')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('finite_number_required')
    return result


def credential_presence(environ: Mapping[str, str] = os.environ) -> dict[str, bool]:
    return {
        'oanda_api_token_present': bool(environ.get('OANDA_API_TOKEN')),
        'oanda_account_id_present': bool(environ.get('OANDA_ACCOUNT_ID')),
    }


def authoritative_v1_context(
    *, recovery_path: Path = RECOVERY_PATH, replay_cache_path: Path = REPLAY_CACHE_PATH,
) -> dict[str, Any]:
    recovery = json.loads(recovery_path.read_text(encoding='utf-8'))
    replay_bytes = replay_cache_path.read_bytes()
    required = (
        recovery.get('final_holdout_v1_status') == 'SPENT_CONTAMINATED',
        recovery.get('final_holdout_v1_access_count') == 2,
        recovery.get('final_holdout_v1_reusable') is False,
        recovery.get('v1_reaccess_blocked') is True,
        recovery.get('guard_check_before_holdout_evaluation') is True,
        recovery.get('cross_process_guard_pass') is True,
        recovery.get('final_holdout_v1_end_timestamp') == V1_END_TIMESTAMP,
        recovery.get('original_holdout_unique_timestamp_count') == V1_UNIQUE_TIMESTAMP_COUNT,
        recovery.get('final_holdout_v2_reserved') is False,
        recovery.get('new_oos_data_required') is True,
        recovery.get('target_5r_development_robustness_supported') is True,
        recovery.get('target_5r_final_oos_proven') is False,
    )
    if not all(required):
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    counts = recovery.get('original_holdout_per_instrument_raw_counts')
    if not isinstance(counts, dict) or not counts:
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    target_instruments = sorted(str(item) for item in counts)
    return {
        'v1_end_timestamp': V1_END_TIMESTAMP,
        'v1_unique_timestamp_count': V1_UNIQUE_TIMESTAMP_COUNT,
        'v1_per_instrument_raw_counts': {item: int(counts[item]) for item in target_instruments},
        'target_instruments': target_instruments,
        'target_universe_sha256': _fingerprint(target_instruments),
        'original_cache_file_sha256': hashlib.sha256(replay_bytes).hexdigest(),
        'final_holdout_v1_status': 'SPENT_CONTAMINATED',
    }


def sanitize_observation_response(
    requested_instrument: str,
    payload: Mapping[str, Any],
    *, v1_end_timestamp: str = V1_END_TIMESTAMP,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if str(payload.get('instrument', '')) != requested_instrument:
        raise ValueError('response_instrument_mismatch')
    if str(payload.get('granularity', '')) != 'M5':
        raise ValueError('response_granularity_mismatch')
    candles = payload.get('candles')
    if not isinstance(candles, list):
        raise ValueError('response_candles_required')
    accepted: list[dict[str, Any]] = []
    failures = {'incomplete': 0, 'pre_v1': 0, 'invalid': 0}
    v1_end = _parse_utc(v1_end_timestamp)
    for item in candles:
        if not isinstance(item, Mapping):
            failures['invalid'] += 1
            continue
        if item.get('complete') is not True:
            failures['incomplete'] += 1
            continue
        try:
            timestamp = str(item.get('time', ''))
            if _parse_utc(timestamp) <= v1_end:
                failures['pre_v1'] += 1
                continue
            mid = item.get('mid')
            if not isinstance(mid, Mapping):
                raise ValueError('mid_required')
            open_price = _finite(mid.get('o'))
            high = _finite(mid.get('h'))
            low = _finite(mid.get('l'))
            close = _finite(mid.get('c'))
            volume = _finite(item.get('volume', 0))
            if high < max(open_price, close) or low > min(open_price, close) or high < low:
                raise ValueError('invalid_ohlc_geometry')
            accepted.append({
                'instrument': requested_instrument,
                'timestamp_utc': timestamp,
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume,
                'complete': True,
            })
        except (TypeError, ValueError):
            failures['invalid'] += 1
    accepted.sort(key=lambda row: row['timestamp_utc'])
    return accepted, failures


def _empty_accumulator(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'schema': SCHEMA,
        'status': 'ACCUMULATING_UNSEEN_RAW',
        'dataset_id': DATASET_ID,
        'source': 'OANDA_PRACTICE_GET_ONLY',
        'granularity': 'M5',
        'v1_end_timestamp': context['v1_end_timestamp'],
        'target_universe_sha256': context['target_universe_sha256'],
        'target_instruments': list(context['target_instruments']),
        'candles_by_instrument': {instrument: [] for instrument in context['target_instruments']},
        'first_new_timestamp': None,
        'last_new_timestamp': None,
        'unique_timestamp_count': 0,
        'per_instrument_counts': {instrument: 0 for instrument in context['target_instruments']},
        'sanitized': True,
        'strategy_executed': False,
        'strategy_metrics_read': False,
    }


def load_accumulator(path: Path, context: Mapping[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return _empty_accumulator(context)
    accumulator = json.loads(path.read_text(encoding='utf-8'))
    if not all((
        accumulator.get('schema') == SCHEMA,
        accumulator.get('dataset_id') == DATASET_ID,
        accumulator.get('v1_end_timestamp') == context['v1_end_timestamp'],
        accumulator.get('target_universe_sha256') == context['target_universe_sha256'],
        accumulator.get('target_instruments') == context['target_instruments'],
        accumulator.get('strategy_executed') is False,
        accumulator.get('strategy_metrics_read') is False,
    )):
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    return accumulator


def merge_sanitized_candles(
    accumulator: Mapping[str, Any], incoming: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    merged = json.loads(json.dumps(accumulator))
    universe = set(merged['target_instruments'])
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for instrument, candles in merged['candles_by_instrument'].items():
        for item in candles:
            rows[(instrument, str(item['timestamp_utc']))] = dict(item)
    for item in incoming:
        record = dict(item)
        if set(record) != RAW_KEYS or record['instrument'] not in universe:
            raise ValueError('RAW_DATA_INTEGRITY_FAILURE')
        key = (str(record['instrument']), str(record['timestamp_utc']))
        if key in rows and rows[key] != record:
            raise ValueError('RAW_DATA_CONFLICT')
        rows[key] = record
    grouped = {instrument: [] for instrument in sorted(universe)}
    for key in sorted(rows, key=lambda item: (item[0], item[1])):
        grouped[key[0]].append(rows[key])
    all_rows = [item for instrument in sorted(grouped) for item in grouped[instrument]]
    timestamps = sorted({str(item['timestamp_utc']) for item in all_rows})
    merged.update({
        'candles_by_instrument': grouped,
        'first_new_timestamp': timestamps[0] if timestamps else None,
        'last_new_timestamp': timestamps[-1] if timestamps else None,
        'unique_timestamp_count': len(timestamps),
        'per_instrument_counts': {instrument: len(grouped[instrument]) for instrument in sorted(grouped)},
    })
    return merged


def validate_raw_integrity(accumulator: Mapping[str, Any]) -> bool:
    seen: set[tuple[str, str]] = set()
    v1_end = _parse_utc(accumulator['v1_end_timestamp'])
    for instrument, candles in accumulator['candles_by_instrument'].items():
        if instrument not in accumulator['target_instruments']:
            return False
        prior = None
        for item in candles:
            if set(item) != RAW_KEYS or item.get('complete') is not True or item.get('instrument') != instrument:
                return False
            timestamp = str(item['timestamp_utc'])
            if _parse_utc(timestamp) <= v1_end or (prior is not None and timestamp <= prior):
                return False
            prior = timestamp
            key = (instrument, timestamp)
            if key in seen:
                return False
            seen.add(key)
            try:
                o, h, low, c = (_finite(item[name]) for name in ('open', 'high', 'low', 'close'))
            except (TypeError, ValueError):
                return False
            if h < max(o, c) or low > min(o, c) or h < low:
                return False
    return accumulator.get('strategy_executed') is False and accumulator.get('strategy_metrics_read') is False


def evidence_depth(accumulator: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    deficits: dict[str, dict[str, int]] = {}
    for instrument in context['target_instruments']:
        required = int(context['v1_per_instrument_raw_counts'][instrument])
        accumulated = len(accumulator['candles_by_instrument'].get(instrument, []))
        deficits[instrument] = {
            'v1_required_raw_count': required,
            'v2_accumulated_raw_count': accumulated,
            'missing_raw_count': max(0, required - accumulated),
        }
    short = [instrument for instrument, values in deficits.items() if values['missing_raw_count'] > 0]
    required_unique = int(context['v1_unique_timestamp_count'])
    missing_unique = max(0, required_unique - int(accumulator['unique_timestamp_count']))
    return {
        'per_instrument_depth': deficits,
        'instruments_still_short': short,
        'max_per_instrument_deficit': max((values['missing_raw_count'] for values in deficits.values()), default=0),
        'missing_unique_timestamp_count': missing_unique,
        'final_holdout_v2_raw_sufficient': bool(
            not short
            and int(accumulator['unique_timestamp_count']) >= required_unique
            and validate_raw_integrity(accumulator)
        ),
    }


def earliest_sufficient_window(
    accumulator: Mapping[str, Any], context: Mapping[str, Any],
) -> dict[str, Any]:
    all_timestamps = sorted({
        item['timestamp_utc']
        for candles in accumulator['candles_by_instrument'].values()
        for item in candles
    })
    end_timestamp = None
    for timestamp in all_timestamps:
        counts = {
            instrument: sum(item['timestamp_utc'] <= timestamp for item in accumulator['candles_by_instrument'][instrument])
            for instrument in context['target_instruments']
        }
        unique_count = sum(item <= timestamp for item in all_timestamps)
        if unique_count >= int(context['v1_unique_timestamp_count']) and all(
            counts[instrument] >= context['v1_per_instrument_raw_counts'][instrument]
            for instrument in context['target_instruments']
        ):
            end_timestamp = timestamp
            break
    if end_timestamp is None:
        raise ValueError('INSUFFICIENT_RAW_DATA')
    reserved = {
        instrument: [
            item for item in accumulator['candles_by_instrument'][instrument]
            if item['timestamp_utc'] <= end_timestamp
        ]
        for instrument in context['target_instruments']
    }
    records = [item for instrument in context['target_instruments'] for item in reserved[instrument]]
    timestamps = sorted({item['timestamp_utc'] for item in records})
    return {
        'candles_by_instrument': reserved,
        'start_timestamp': timestamps[0],
        'end_timestamp': timestamps[-1],
        'unique_timestamp_count': len(timestamps),
        'per_instrument_raw_counts': {instrument: len(reserved[instrument]) for instrument in context['target_instruments']},
        'dataset_fingerprint': _fingerprint({
            'dataset_id': DATASET_ID,
            'target_universe_sha256': context['target_universe_sha256'],
            'candles_by_instrument': reserved,
        }),
    }


def register_v2_guard(guard_path: Path, window: Mapping[str, Any]) -> dict[str, Any]:
    guard = json.loads(guard_path.read_text(encoding='utf-8'))
    if guard.get('schema') != 'AIOS_FOREX_FINAL_HOLDOUT_ACCESS_GUARD_V1':
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    v1 = guard.get('datasets', {}).get('FINAL_HOLDOUT_V1', {})
    if not (v1.get('spent') is True and v1.get('contaminated') is True and v1.get('access_count') == 2):
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    record = {
        'dataset_id': DATASET_ID,
        'dataset_fingerprint': window['dataset_fingerprint'],
        'status': 'RESERVED_UNTOUCHED',
        'first_access_utc': None,
        'access_count': 0,
        'spent': False,
        'contaminated': False,
        'reason': 'GENUINE_POST_V1_OANDA_PRACTICE_RAW_RESERVED',
        'source_packet': PACKET_ID,
    }
    existing = guard['datasets'].get(DATASET_ID)
    if existing is not None and existing != record:
        raise ValueError('RAW_DATA_CONFLICT')
    guard['datasets'][DATASET_ID] = record
    guard_path.write_text(_stable_json(guard), encoding='utf-8')
    return record


def acquire_with_client(
    client: Any,
    context: Mapping[str, Any],
    *,
    accumulator_path: Path,
    guard_path: Path,
    result_path: Path,
    source_head: str,
) -> dict[str, Any]:
    if getattr(client, 'environment', None) != 'practice':
        raise ValueError('PRACTICE_ENVIRONMENT_REQUIRED')
    accumulator = load_accumulator(accumulator_path, context)
    calls = successes = failures = 0
    sanitized_failures = {'incomplete': 0, 'pre_v1': 0, 'invalid': 0, 'request': 0}
    incoming: list[dict[str, Any]] = []
    for instrument in context['target_instruments']:
        calls += 1
        try:
            payload = client.observation_candles(instrument, granularity='M5', count=500, price='M')
            sanitized, rejected = sanitize_observation_response(
                instrument, payload, v1_end_timestamp=context['v1_end_timestamp']
            )
            incoming.extend(sanitized)
            for name, count in rejected.items():
                sanitized_failures[name] += count
            successes += 1
        except (OandaReadOnlyClientError, TypeError, ValueError):
            sanitized_failures['request'] += 1
            failures += 1
    accumulator = merge_sanitized_candles(accumulator, incoming)
    integrity = validate_raw_integrity(accumulator)
    if not integrity:
        raise ValueError('RAW_DATA_INTEGRITY_FAILURE')
    depth = evidence_depth(accumulator, context)
    sufficient = bool(depth['final_holdout_v2_raw_sufficient'])
    window = earliest_sufficient_window(accumulator, context) if sufficient else None
    guard_record = None
    if window:
        accumulator['candles_by_instrument'] = window['candles_by_instrument']
        accumulator['first_new_timestamp'] = window['start_timestamp']
        accumulator['last_new_timestamp'] = window['end_timestamp']
        accumulator['unique_timestamp_count'] = window['unique_timestamp_count']
        accumulator['per_instrument_counts'] = window['per_instrument_raw_counts']
        accumulator['status'] = 'RESERVED_UNTOUCHED'
        accumulator['dataset_fingerprint'] = window['dataset_fingerprint']
        guard_record = register_v2_guard(guard_path, window)
    accumulator_path.parent.mkdir(parents=True, exist_ok=True)
    accumulator_path.write_text(_stable_json(accumulator), encoding='utf-8')
    current_count = sum(len(items) for items in accumulator['candles_by_instrument'].values())
    status = 'FINAL_HOLDOUT_V2_RESERVED_UNTOUCHED' if sufficient else 'NEW_OOS_DATA_ACCUMULATED_STILL_INSUFFICIENT'
    result = {
        'schema': RESULT_SCHEMA,
        'packet_id': PACKET_ID,
        'source_head': source_head,
        'final_holdout_v1_status': 'SPENT_CONTAMINATED',
        'final_holdout_v1_end_timestamp': context['v1_end_timestamp'],
        'v1_unique_timestamp_count': context['v1_unique_timestamp_count'],
        'v1_instrument_count': len(context['target_instruments']),
        'v1_per_instrument_raw_counts': context['v1_per_instrument_raw_counts'],
        'original_cache_file_sha256': context['original_cache_file_sha256'],
        'target_instruments': context['target_instruments'],
        'target_instrument_count': len(context['target_instruments']),
        'target_universe_sha256': context['target_universe_sha256'],
        'oanda_environment': 'practice',
        'oanda_get_only': True,
        'oanda_api_token_present': True,
        'oanda_account_id_present': True,
        'oanda_get_call_count': calls,
        'oanda_get_success_count': successes,
        'oanda_get_failure_count': failures,
        'non_get_calls': 0,
        'account_endpoint_calls': 0,
        'sanitized_failure_counts': sanitized_failures,
        'current_new_raw_candle_count': current_count,
        'current_new_unique_timestamp_count': accumulator['unique_timestamp_count'],
        'missing_unique_timestamp_count': depth['missing_unique_timestamp_count'],
        'per_instrument_depth': depth['per_instrument_depth'],
        'instruments_still_short': depth['instruments_still_short'],
        'max_per_instrument_deficit': depth['max_per_instrument_deficit'],
        'raw_data_integrity_pass': integrity,
        'v1_v2_timestamp_overlap_count': 0,
        'final_holdout_v2_raw_sufficient': sufficient,
        'final_holdout_v2_reserved': sufficient,
        'final_holdout_v2_status': 'RESERVED_UNTOUCHED' if sufficient else 'ACCUMULATING_UNSEEN_RAW',
        'final_holdout_v2_start_timestamp': window['start_timestamp'] if window else accumulator['first_new_timestamp'],
        'final_holdout_v2_end_timestamp': window['end_timestamp'] if window else accumulator['last_new_timestamp'],
        'final_holdout_v2_unique_timestamp_count': window['unique_timestamp_count'] if window else accumulator['unique_timestamp_count'],
        'final_holdout_v2_per_instrument_raw_counts': window['per_instrument_raw_counts'] if window else accumulator['per_instrument_counts'],
        'final_holdout_v2_dataset_fingerprint': window['dataset_fingerprint'] if window else None,
        'final_holdout_v2_access_count': guard_record['access_count'] if guard_record else 0,
        'final_holdout_v2_strategy_executed': False,
        'final_holdout_v2_metrics_read': False,
        'target_5r_development_robustness_supported': True,
        'target_5r_final_oos_proven': False,
        'new_oos_data_still_insufficient': not sufficient,
        'credentials_persisted': False,
        'credentials_printed': False,
        'network_calls': calls > 0,
        'broker_calls': calls > 0,
        'broker_writes': False,
        'practice_orders': False,
        'live_orders': False,
        'money_movement': False,
        'next_decision': 'TEST_FROZEN_STRATEGY_ON_FINAL_HOLDOUT_V2' if sufficient else 'ACCUMULATE_MORE_GENUINE_POST_V1_M5_DATA',
        'next_packet_id': 'PKT-EAST-FOREX-FINAL-HOLDOUT-V2-015' if sufficient else PACKET_ID,
        'status': status,
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(_stable_json(result), encoding='utf-8')
    return result


def run_new_oos_data_acquisition_v1(*, source_head: str = 'UNKNOWN') -> dict[str, Any]:
    presence = credential_presence()
    if not all(presence.values()):
        raise ValueError('OWNER_ACTION_REQUIRED_PRACTICE_CREDENTIALS')
    context = authoritative_v1_context()
    client = OandaReadOnlyClient(
        api_token=os.environ['OANDA_API_TOKEN'],
        account_id=os.environ['OANDA_ACCOUNT_ID'],
        environment='practice',
    )
    return acquire_with_client(
        client,
        context,
        accumulator_path=ACCUMULATOR_PATH,
        guard_path=GUARD_PATH,
        result_path=RESULT_PATH,
        source_head=source_head,
    )
