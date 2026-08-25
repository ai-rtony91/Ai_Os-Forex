from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from automation.forex_engine import forex_new_oos_data_acquisition_v1 as module


def _root() -> Path:
    root = Path(tempfile.gettempdir()) / 'AIOS_NEW_OOS_DATA_ACQUISITION_V1'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _context(instruments=('EUR_USD',), required=2):
    instruments = sorted(instruments)
    return {
        'v1_end_timestamp': module.V1_END_TIMESTAMP,
        'v1_unique_timestamp_count': required,
        'v1_per_instrument_raw_counts': {item: required for item in instruments},
        'target_instruments': instruments,
        'target_universe_sha256': module._fingerprint(instruments),
        'original_cache_file_sha256': 'cache',
    }


def _candle(timestamp, *, complete=True, close='1.1'):
    return {
        'time': timestamp,
        'complete': complete,
        'volume': 10,
        'mid': {'o': '1.0', 'h': '1.2', 'l': '0.9', 'c': close},
    }


def _payload(instrument, candles):
    return {'instrument': instrument, 'granularity': 'M5', 'candles': candles}


def _guard(path: Path):
    path.write_text(json.dumps({
        'schema': 'AIOS_FOREX_FINAL_HOLDOUT_ACCESS_GUARD_V1',
        'datasets': {'FINAL_HOLDOUT_V1': {
            'dataset_id': 'FINAL_HOLDOUT_V1', 'dataset_fingerprint': 'v1',
            'status': 'SPENT_CONTAMINATED', 'first_access_utc': None,
            'access_count': 2, 'spent': True, 'contaminated': True,
            'reason': 'TEST', 'source_packet': 'TEST',
        }},
    }), encoding='utf-8')


class FakeClient:
    environment = 'practice'

    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def observation_candles(self, instrument, **kwargs):
        self.calls.append((instrument, kwargs))
        return self.payloads[instrument]


def test_sanitizer_rejects_incomplete_pre_v1_and_v1_end_but_accepts_new():
    payload = _payload('EUR_USD', [
        _candle('2026-08-21T19:45:00.000000000Z'),
        _candle(module.V1_END_TIMESTAMP),
        _candle('2026-08-21T19:55:00.000000000Z', complete=False),
        _candle('2026-08-21T20:00:00.000000000Z'),
    ])
    rows, failures = module.sanitize_observation_response('EUR_USD', payload)
    assert [row['timestamp_utc'] for row in rows] == ['2026-08-21T20:00:00.000000000Z']
    assert failures == {'incomplete': 1, 'pre_v1': 2, 'invalid': 0}
    assert set(rows[0]) == module.RAW_KEYS


def test_accumulator_deduplicates_and_conflict_fails_closed():
    context = _context()
    row = module.sanitize_observation_response(
        'EUR_USD', _payload('EUR_USD', [_candle('2026-08-21T20:00:00.000000000Z')])
    )[0][0]
    accumulator = module.merge_sanitized_candles(module._empty_accumulator(context), [row, row])
    assert accumulator['per_instrument_counts']['EUR_USD'] == 1
    with pytest.raises(ValueError, match='^RAW_DATA_CONFLICT$'):
        module.merge_sanitized_candles(accumulator, [dict(row, close=1.15)])


def test_insufficient_synthetic_acquisition_never_reserves_or_runs_strategy():
    root = _root()
    paths = [root / name for name in ('insufficient_acc.json', 'insufficient_guard.json', 'insufficient_result.json')]
    for path in paths:
        path.unlink(missing_ok=True)
    _guard(paths[1])
    context = _context(required=2)
    client = FakeClient({'EUR_USD': _payload('EUR_USD', [_candle('2026-08-21T20:00:00.000000000Z')])})
    result = module.acquire_with_client(
        client, context, accumulator_path=paths[0], guard_path=paths[1], result_path=paths[2], source_head='TEST'
    )
    assert client.calls == [('EUR_USD', {'granularity': 'M5', 'count': 500, 'price': 'M'})]
    assert result['oanda_environment'] == 'practice' and result['oanda_get_only'] is True
    assert result['account_endpoint_calls'] == 0 and result['non_get_calls'] == 0
    assert result['final_holdout_v2_reserved'] is False
    assert result['final_holdout_v2_strategy_executed'] is False
    assert result['final_holdout_v2_metrics_read'] is False
    assert not any(key.lower().endswith('_r') for key in json.loads(paths[0].read_text()) if key != 'v1_end_timestamp')


def test_sufficient_synthetic_data_reserves_earliest_window_at_access_zero():
    root = _root()
    paths = [root / name for name in ('sufficient_acc.json', 'sufficient_guard.json', 'sufficient_result.json')]
    for path in paths:
        path.unlink(missing_ok=True)
    _guard(paths[1])
    context = _context(('EUR_USD', 'GBP_USD'), required=2)
    timestamps = ['2026-08-21T20:00:00.000000000Z', '2026-08-21T20:05:00.000000000Z']
    client = FakeClient({item: _payload(item, [_candle(ts) for ts in timestamps]) for item in context['target_instruments']})
    result = module.acquire_with_client(
        client, context, accumulator_path=paths[0], guard_path=paths[1], result_path=paths[2], source_head='TEST'
    )
    guard = json.loads(paths[1].read_text(encoding='utf-8'))
    assert result['final_holdout_v2_reserved'] is True
    assert result['final_holdout_v2_access_count'] == 0
    assert result['final_holdout_v2_start_timestamp'] == timestamps[0]
    assert result['final_holdout_v2_end_timestamp'] == timestamps[-1]
    assert guard['datasets']['FINAL_HOLDOUT_V2']['status'] == 'RESERVED_UNTOUCHED'
    assert guard['datasets']['FINAL_HOLDOUT_V2']['access_count'] == 0
    assert result['credentials_persisted'] is False and result['credentials_printed'] is False


def test_live_environment_is_rejected_before_any_call():
    client = FakeClient({})
    client.environment = 'live'
    root = _root()
    with pytest.raises(ValueError, match='^PRACTICE_ENVIRONMENT_REQUIRED$'):
        module.acquire_with_client(
            client, _context(), accumulator_path=root/'live_acc.json', guard_path=root/'live_guard.json',
            result_path=root/'live_result.json', source_head='TEST'
        )
    assert client.calls == []

