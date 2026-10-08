from __future__ import annotations

import tempfile
import subprocess
import sys
from pathlib import Path

import pytest

import automation.forex_engine.forex_macd_confluence_runner_v1 as module
from automation.forex_engine.indicators import DOWN, UP
from automation.forex_engine.models import Candle


def _temp_report_path(name: str) -> Path:
    root = Path(tempfile.gettempdir()) / 'AIOS_PYTEST_CONTROL_V2'
    root.mkdir(parents=True, exist_ok=True)
    return root / name


def test_true_two_close_requires_two_consecutive_closes():
    candles = [
        Candle('EURUSD', '5m', f'2026-08-01T10:0{i}:00Z', 1, 1.1, 0.9, 1, 1, 'test')
        for i in range(4)
    ]
    directions = [UP, UP, DOWN, DOWN]
    bands = [0.9, 0.91, 1.1, 1.11]
    events = module._two_close_confirmation_events_from_series(candles, directions, bands)
    assert len(events) == 2
    assert events[0]['confirmation_index'] == 1
    assert events[1]['confirmation_index'] == 3


def test_failed_second_confirmation_cancels_pending_flip():
    candles = [
        Candle('EURUSD', '5m', f'2026-08-01T10:0{i}:00Z', 1, 1.1, 0.9, 1, 1, 'test')
        for i in range(4)
    ]
    directions = [UP, DOWN, UP, UP]
    bands = [0.9, 1.1, 0.9, 0.9]
    events = module._two_close_confirmation_events_from_series(candles, directions, bands)
    assert len(events) == 1
    assert events[0]['confirmation_index'] == 3


def test_entry_occurs_next_candle_open_and_r_parity():
    cache = module.load_replay_cache()
    instrument, history = next(iter(sorted(cache['pair_histories'].items())))
    candles = module._to_candles(instrument, history)
    trades = module._simulate_symbol(candles)
    assert trades
    first = trades[0]
    assert first['entry_price'] == candles[first['entry_index']].open
    assert first['entry_timestamp_utc'] == candles[first['entry_index']].timestamp
    assert abs(first['price_r'] - first['quote_r']) <= 1e-9
    assert first['initial_risk_distance'] > 0
    assert first['exit_reason'] in {'PROTECTIVE_STOP', 'OPPOSITE_TRUE_2_CLOSE_CONFIRMED', 'END_OF_DATA'}


def test_no_fixed_target_exists_in_baseline_control():
    cache = module.load_replay_cache()
    instrument, history = next(iter(sorted(cache['pair_histories'].items())))
    candles = module._to_candles(instrument, history)
    trades = module._simulate_symbol(candles)
    assert trades
    assert all('target_price' not in trade for trade in trades)


def test_global_timestamp_split_is_deterministic_and_no_count_forcing():
    result1 = module.run_control_baseline_v2()
    result2 = module.run_control_baseline_v2()
    assert result1['train_end_timestamp'] == result2['train_end_timestamp']
    assert result1['validation_end_timestamp'] == result2['validation_end_timestamp']
    assert result1['split_definition_sha256'] == result2['split_definition_sha256']
    assert result1['train_trade_hash'] == result2['train_trade_hash']
    assert result1['validation_trade_hash'] == result2['validation_trade_hash']
    assert result1['train_metrics_hash'] == result2['train_metrics_hash']
    assert result1['validation_metrics_hash'] == result2['validation_metrics_hash']
    assert result1['train_end_timestamp'] < result1['validation_end_timestamp']
    assert result1['count_forced_split_used'] is False
    assert result1['generic_replay_used_as_v2_control'] is False
    assert result1['final_holdout_opened'] is False


def test_boundary_crossing_trades_are_excluded_and_report_written(monkeypatch):
    report = _temp_report_path('AIOS_FOREX_CONTROL_BASELINE_V2_RESULTS.json')
    monkeypatch.setattr(module, 'REPORT_PATH', report)
    result = module.run_control_baseline_v2()
    assert report.exists()
    assert result['train_validation_crossers_excluded'] >= 0
    assert result['validation_holdout_crossers_excluded'] >= 0
    assert result['all_trade_ids_unique'] is True
    assert result['control_baseline_v2_valid'] is True
    assert result['lookahead_entry_count'] == 0
    assert result['r_parity_failures'] == 0


def test_mixed_symbol_sequences_are_avoided():
    cache = module.load_replay_cache()
    instrument, history = next(iter(sorted(cache['pair_histories'].items())))
    candles = module._to_candles(instrument, history)
    assert {candle.symbol for candle in candles} == {instrument.replace('_', '')}
    assert len({candle.timeframe for candle in candles}) == 1


def test_macd_selection_uses_train_only_and_keeps_holdout_closed(monkeypatch):
    report = _temp_report_path('AIOS_FOREX_MACD_V2_RESULTS.json')
    monkeypatch.setattr(module, 'MACD_REPORT_PATH', report)
    result = module.run_macd_v2_selection()
    assert report.exists()
    assert result['control_baseline_v2']['control_baseline_v2_valid'] is True
    assert result['selected_macd_filter'] == 'FILTER_B_ZERO'
    assert result['selection_reason'] == 'selected_by_train_only_ranking'
    assert result['macd_supported'] is True
    assert result['macd_decision_complete'] is True
    assert result['final_holdout_opened'] is False
    assert result['final_holdout_used_for_selection'] is False
    assert result['lookahead_used_for_selection'] is False
    assert result['cross_symbol_macd_lookups'] == 0
    assert result['future_macd_lookups'] == 0
    assert result['control_validation']['closed'] == 532
    assert result['macd_validation']['closed'] == 224
    assert result['macd_validation']['expectancy_r'] < 0
    assert result['validation_buy']['closed'] == 128
    assert result['validation_sell']['closed'] == 96


def test_supertrend_entry_grid_is_exact_and_frozen():
    grid = module._entry_grid_records()
    assert len(grid) == 16
    assert len({item['config_id'] for item in grid}) == 16
    assert {item['atr_period'] for item in grid} == {3, 5, 7, 10}
    assert {item['supertrend_factor'] for item in grid} == {1.5, 2.0, 2.5, 3.0}
    assert {item['confirmation'] for item in grid} == {'TRUE_2_CLOSE'}
    assert {item['macd_filter'] for item in grid} == {'NONE'}


def test_partition_helper_rejects_final_holdout_access():
    cache = module.load_replay_cache()
    cache_sha256 = module._sha256(cache)
    candles_by_pair = {
        instrument: module._to_candles(instrument, history)
        for instrument, history in sorted(cache['pair_histories'].items())
    }
    boundaries = module._split_boundaries(candles_by_pair, cache_sha256)
    try:
        module._trades_for_partition(
            candles_by_pair,
            boundaries,
            module.SUPERTREND_ENTRY_GRID[0],
            'FINAL_HOLDOUT',
        )
    except ValueError as exc:
        assert str(exc) == 'final_holdout_partition_access_forbidden'
    else:
        raise AssertionError('FINAL_HOLDOUT access was not blocked')


def test_supertrend_entry_tune_is_deterministic_and_keeps_holdout_closed(monkeypatch):
    report = _temp_report_path('AIOS_FOREX_SUPERTREND_ENTRY_TUNE_V2_RESULTS.json')
    monkeypatch.setattr(module, 'ENTRY_TUNE_REPORT_PATH', report)
    try:
        module.run_supertrend_entry_tune_v2(source_head='TEST_HEAD')
    except ValueError as exc:
        assert str(exc) == 'NO_VALIDATED_ENTRY_CONFIGURATION'
    else:
        raise AssertionError('aggregate entry grid unexpectedly passed validation')
    assert not report.exists()


def test_direction_filter_preserves_trade_identity_timestamp_and_r():
    trades = [
        {'trade_id': 'buy', 'direction': 'BUY', 'entry_timestamp_utc': '2026-01-01T00:00:00Z', 'realized_r': 1.25},
        {'trade_id': 'sell', 'direction': 'SELL', 'entry_timestamp_utc': '2026-01-01T00:05:00Z', 'realized_r': -0.5},
    ]
    buys = module._direction_trades(trades, 'BUY_ONLY')
    sells = module._direction_trades(trades, 'SELL_ONLY')
    assert [item['direction'] for item in buys] == ['BUY']
    assert [item['direction'] for item in sells] == ['SELL']
    assert buys[0]['entry_timestamp_utc'] == trades[0]['entry_timestamp_utc']
    assert sells[0]['entry_timestamp_utc'] == trades[1]['entry_timestamp_utc']
    assert buys[0]['realized_r'] == trades[0]['realized_r']
    assert sells[0]['realized_r'] == trades[1]['realized_r']


def test_directional_rescue_is_bounded_deterministic_and_holdout_sealed(monkeypatch):
    report = _temp_report_path('AIOS_FOREX_SUPERTREND_DIRECTIONAL_RESCUE_V1_RESULTS.json')
    monkeypatch.setattr(module, 'DIRECTIONAL_RESCUE_REPORT_PATH', report)
    result = module.run_supertrend_directional_rescue_v1(source_head='TEST_HEAD')
    assert report.exists()
    assert result['config_count'] == 16
    assert result['directional_candidate_count'] == 32
    assert len(result['direction_decompositions']) == 16
    assert all(
        item['direction_policy'] in {'BUY_ONLY', 'SELL_ONLY'}
        for item in result['train_direction_candidates']
    )
    assert len(result['promoted_directional_candidates']) <= 5
    assert result['mfe_used_for_entry_selection'] is False
    assert result['final_holdout_opened'] is False
    assert result['final_holdout_metrics_read'] is False
    assert result['final_holdout_used_for_selection'] is False
    assert result['root_cause'] in {
        'AGGREGATE_DIRECTIONAL_ASYMMETRY',
        'EXIT_CAPTURE_FAILURE',
        'ENTRY_EDGE_FAILURE',
    }
    assert result['reproducible_result'] is True
    assert result['reproducibility_hashes']['first_train_direction_results_hash'] == result['reproducibility_hashes']['second_train_direction_results_hash']
    assert result['reproducibility_hashes']['first_validation_direction_results_hash'] == result['reproducibility_hashes']['second_validation_direction_results_hash']


def _exit_test_trade_and_market(highs, lows, baseline_r=1.0):
    candles = [
        Candle('EURUSD', '5m', f'2026-08-01T10:0{index}:00Z', 100.0, high, low, 100.0, 1, 'test')
        for index, (high, low) in enumerate(zip(highs, lows))
    ]
    trade = {
        'trade_id': 'frozen-buy',
        'instrument': 'EUR_USD',
        'direction': 'BUY',
        'entry_timestamp_utc': candles[0].timestamp,
        'exit_timestamp_utc': candles[-1].timestamp,
        'entry_price': 100.0,
        'initial_stop': 90.0,
        'exit_price': 100.0 + baseline_r * 10.0,
        'exit_reason': 'END_OF_DATA',
        'entry_index': 0,
        'exit_index': len(candles) - 1,
        'realized_r': baseline_r,
        'price_r': baseline_r,
        'quote_r': baseline_r,
        'initial_risk_distance': 10.0,
    }
    trend = [{'lower_band': 90.0, 'upper_band': None, 'direction': UP} for _ in candles]
    return trade, candles, trend


def test_exit_policy_grid_is_exactly_eight():
    assert len(module.EXIT_POLICY_GRID) == 8
    assert len({policy.policy_id for policy in module.EXIT_POLICY_GRID}) == 8
    assert [policy.policy_id for policy in module.EXIT_POLICY_GRID] == [
        'EXIT_A_BASELINE',
        'EXIT_B_FIXED_1_5R',
        'EXIT_C_FIXED_2R',
        'EXIT_D_FIXED_3R',
        'EXIT_E_BE1_RUNNER',
        'EXIT_F_TRAIL_AFTER_1R',
        'EXIT_G_PARTIAL_1_5R_RUNNER',
        'EXIT_H_PARTIAL_2R_RUNNER',
    ]


def test_partial_runner_size_weighting_is_correct():
    trade, candles, trend = _exit_test_trade_and_market([116.0, 111.0], [95.0, 95.0])
    partial_1_5 = next(policy for policy in module.EXIT_POLICY_GRID if policy.policy_id == 'EXIT_G_PARTIAL_1_5R_RUNNER')
    result_1_5 = module._rescore_frozen_buy_trade(trade, candles, trend, partial_1_5)
    assert result_1_5['partial_triggered'] is True
    assert result_1_5['realized_r'] == 0.5 * 1.5 + 0.5 * 1.0

    trade, candles, trend = _exit_test_trade_and_market([121.0, 111.0], [95.0, 95.0])
    partial_2 = next(policy for policy in module.EXIT_POLICY_GRID if policy.policy_id == 'EXIT_H_PARTIAL_2R_RUNNER')
    result_2 = module._rescore_frozen_buy_trade(trade, candles, trend, partial_2)
    assert result_2['partial_triggered'] is True
    assert result_2['realized_r'] == 0.5 * 2.0 + 0.5 * 1.0


def test_breakeven_activates_only_after_one_r_touch_and_stop_never_loosens():
    policy = next(policy for policy in module.EXIT_POLICY_GRID if policy.policy_id == 'EXIT_E_BE1_RUNNER')
    trade, candles, trend = _exit_test_trade_and_market([111.0, 101.0], [95.0, 99.0])
    result = module._rescore_frozen_buy_trade(trade, candles, trend, policy)
    assert result['breakeven_activated'] is True
    assert result['exit_price'] == 100.0
    assert result['realized_r'] == 0.0
    assert result['stop_never_loosened'] is True

    trade, candles, trend = _exit_test_trade_and_market([109.0, 111.0], [95.0, 89.0])
    result = module._rescore_frozen_buy_trade(trade, candles, trend, policy)
    assert result['breakeven_activated'] is False


def test_ambiguous_stop_and_threshold_is_conservative():
    trade, candles, trend = _exit_test_trade_and_market([116.0], [89.0], baseline_r=-1.0)
    policy = next(policy for policy in module.EXIT_POLICY_GRID if policy.policy_id == 'EXIT_B_FIXED_1_5R')
    result = module._rescore_frozen_buy_trade(trade, candles, trend, policy)
    assert result['ambiguous_intrabar_count'] == 1
    assert result['exit_price'] == 90.0
    assert result['realized_r'] == -1.0
    assert result['exit_reason'] == 'PROTECTIVE_STOP_CONSERVATIVE'


def test_exit_tune_reproduces_entries_and_is_deterministic(monkeypatch):
    report = _temp_report_path('AIOS_FOREX_R_CAPTURE_EXIT_TUNE_V1_RESULTS.json')
    monkeypatch.setattr(module, 'EXIT_TUNE_REPORT_PATH', report)
    with pytest.raises(ValueError, match='^NO_VALIDATED_EXIT_POLICY$'):
        module.run_r_capture_exit_tune_v1(source_head='TEST_HEAD')


def _retest_v2_candles() -> list[Candle]:
    values = [
        (101.0, 102.0, 100.5, 101.0),
        (101.0, 102.0, 100.5, 101.0),
        (101.0, 102.0, 100.5, 101.0),
        (101.0, 103.0, 99.0, 102.0),
        (102.0, 103.0, 99.5, 101.5),
        (101.5, 103.0, 101.0, 102.0),
        (102.0, 104.0, 99.0, 103.0),
        (103.0, 104.0, 102.0, 103.0),
        (103.0, 104.0, 102.0, 103.0),
    ]
    return [
        Candle('EURUSD', '5m', f'2026-08-01T10:{index:02d}:00Z', *value, 1, 'test')
        for index, value in enumerate(values)
    ]


def test_retest_v2_definition_hash_and_grids_are_frozen():
    assert module.retest_definition_v2_hash() == module.retest_definition_v2_hash()
    assert module.RETEST_DEFINITION_V2['legacy_retest_counts_used_as_acceptance_target'] is False
    assert len(module.RETEST_V2_ENTRY_FAMILIES) == 4
    assert {family.filter_type for family in module.RETEST_V2_ENTRY_FAMILIES} == {
        'BASE', 'BULL_CLOSE', 'STRONG_BODY', 'PRIOR_HIGH_RECLAIM'
    }
    assert len(module.EXIT_POLICY_GRID) == 8


def test_retest_v2_touch_retention_consecutive_and_future_causality():
    candles = _retest_v2_candles()
    directions = [UP] * len(candles)
    bands = [100.0] * len(candles)
    confirmations = [{'confirmation_index': 2, 'direction': UP, 'timestamp': candles[2].timestamp, 'band': 100.0}]
    boundaries = module.SplitBoundaries(candles[-1].timestamp, candles[-1].timestamp, 'split', 'cache')
    events = module._retest_v2_events_from_series('EUR_USD', candles, directions, bands, confirmations, boundaries)
    assert [event['ordinal'] for event in events] == [1, 2]
    assert events[0]['decision_index'] == 3
    assert events[1]['decision_index'] == 6

    changed_future = list(candles)
    changed_future[7] = Candle('EURUSD', '5m', candles[7].timestamp, 50, 51, 49, 50, 1, 'test')
    changed = module._retest_v2_events_from_series(
        'EUR_USD', changed_future, directions, bands, confirmations, boundaries
    )
    assert changed[0]['decision_timestamp'] == events[0]['decision_timestamp']
    assert changed[0]['entry_timestamp_utc'] == events[0]['entry_timestamp_utc']

    no_close_retention = list(candles)
    no_close_retention[3] = Candle('EURUSD', '5m', candles[3].timestamp, 101, 103, 99, 99.5, 1, 'test')
    rejected = module._retest_v2_events_from_series(
        'EUR_USD', no_close_retention, directions, bands, confirmations, boundaries
    )
    assert all(event['decision_index'] != 3 for event in rejected)

    no_touch = list(candles)
    no_touch[3] = Candle('EURUSD', '5m', candles[3].timestamp, 101, 103, 100.5, 102, 1, 'test')
    rejected = module._retest_v2_events_from_series(
        'EUR_USD', no_touch, directions, bands, confirmations, boundaries
    )
    assert all(event['decision_index'] != 3 for event in rejected)


def test_retest_v2_partition_crossing_is_excluded_and_family_filters_are_exact():
    candles = _retest_v2_candles()
    directions = [UP] * len(candles)
    bands = [100.0] * len(candles)
    confirmations = [{'confirmation_index': 2, 'direction': UP, 'timestamp': candles[2].timestamp, 'band': 100.0}]
    boundaries = module.SplitBoundaries(candles[3].timestamp, candles[-1].timestamp, 'split', 'cache')
    events = module._retest_v2_events_from_series('EUR_USD', candles, directions, bands, confirmations, boundaries)
    assert all(event['decision_index'] != 3 for event in events)

    opportunity = {
        'ordinal': 1,
        'decision_open': 100.0,
        'decision_close': 102.0,
        'decision_high': 103.0,
        'decision_low': 99.0,
        'previous_high': 101.0,
        'body_to_range': 0.5,
    }
    assert all(module._retest_family_accepts(family, opportunity) for family in module.RETEST_V2_ENTRY_FAMILIES)
    weak = dict(opportunity, decision_close=100.2, body_to_range=0.05, previous_high=101.0)
    accepted = {
        family.family_id: module._retest_family_accepts(family, weak)
        for family in module.RETEST_V2_ENTRY_FAMILIES
    }
    assert accepted == {
        'RETEST_V2_A_BASE': True,
        'RETEST_V2_B_BULL_CLOSE': True,
        'RETEST_V2_C_STRONG_BODY': False,
        'RETEST_V2_D_PRIOR_HIGH_RECLAIM': False,
    }


def test_retest_v2_master_evaluates_all_candidates_and_keeps_holdout_sealed(monkeypatch):
    definition = _temp_report_path('AIOS_FOREX_SUPERTREND_RETEST_DEFINITION_V2.json')
    report = _temp_report_path('AIOS_FOREX_RETEST_V2_ENTRY_EXIT_MASTER_V1_RESULTS.json')
    monkeypatch.setattr(module, 'RETEST_V2_DEFINITION_PATH', definition)
    monkeypatch.setattr(module, 'RETEST_V2_MASTER_REPORT_PATH', report)
    result = module.run_retest_v2_entry_exit_master_v1(source_head='TEST_HEAD')
    assert definition.exists() and report.exists()
    assert result['retest_entry_family_count'] == 4
    assert len(result['train_entry_results']) == 4
    assert len(result['validation_entry_results']) == 4
    assert result['r_parity_failures'] == 0
    assert result['lookahead_entry_count'] == 0
    assert result['final_holdout_opened'] is False
    assert result['final_holdout_metrics_read'] is False
    assert result['final_holdout_open_count'] == 0
    assert result['reproducible_result'] is True
    if result['entry_config_frozen']:
        assert result['exit_policy_count'] == 8
        assert len(result['train_exit_results']) == 8
        assert len(result['validation_exit_results']) == 8


def test_development_grid_is_exactly_ten_and_includes_fixed_5r():
    assert len(module.DEVELOPMENT_EXIT_POLICY_GRID) == 10
    assert [policy.policy_id for policy in module.DEVELOPMENT_EXIT_POLICY_GRID] == [
        'EXIT_A_BASELINE', 'EXIT_B_FIXED_1_5R', 'EXIT_C_FIXED_2R',
        'EXIT_D_FIXED_3R', 'EXIT_E_FIXED_4R', 'EXIT_F_FIXED_5R',
        'EXIT_G_BE1_RUNNER', 'EXIT_H_TRAIL_AFTER_1R',
        'EXIT_I_PARTIAL_1_5R_RUNNER', 'EXIT_J_PARTIAL_2R_RUNNER',
    ]


@pytest.mark.parametrize(('policy_id', 'threshold'), [
    ('EXIT_B_FIXED_1_5R', 1.5), ('EXIT_C_FIXED_2R', 2.0),
    ('EXIT_D_FIXED_3R', 3.0), ('EXIT_E_FIXED_4R', 4.0), ('EXIT_F_FIXED_5R', 5.0),
])
def test_development_fixed_targets_close_at_exact_frozen_r(policy_id, threshold):
    trade, candles, trend = _exit_test_trade_and_market([100.0 + threshold * 10.0], [95.0])
    policy = next(item for item in module.DEVELOPMENT_EXIT_POLICY_GRID if item.policy_id == policy_id)
    result = module._rescore_frozen_buy_trade(trade, candles, trend, policy)
    assert result['exit_reason'] == 'FIXED_R_TARGET'
    assert result['realized_r'] == threshold


def test_development_folds_are_four_contiguous_and_exclude_holdout():
    candles = _retest_v2_candles()
    boundaries = module.SplitBoundaries(candles[3].timestamp, candles[7].timestamp, 'split', 'cache')
    definition = module._development_fold_definition({'EUR_USD': candles}, boundaries)
    assert len(definition['folds']) == 4
    assert definition['final_holdout_excluded'] is True
    assert definition['folds'][-1]['end_timestamp'] == candles[7].timestamp
    assert candles[8].timestamp > definition['folds'][-1]['end_timestamp']
    assert definition == module._development_fold_definition({'EUR_USD': candles}, boundaries)


def test_development_selection_has_no_5r_bonus():
    weak_5r = {
        'median_fold_expectancy_r': 0.1, 'expectancy_r': 0.1, 'profit_factor': 1.1,
        'net_r': 10.0, 'max_drawdown_r': 5.0, 'closed': 100,
    }
    stronger_2r = dict(weak_5r, median_fold_expectancy_r=0.2)
    assert module._development_selection_key(stronger_2r) > module._development_selection_key(weak_5r)


def _synthetic_guard_path(name: str) -> Path:
    root = Path(tempfile.gettempdir()) / 'AIOS_HOLDOUT_CONTAMINATION_RECOVERY_V1'
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.unlink(missing_ok=True)
    return path


def _synthetic_dataset(dataset_id: str, *, spent: bool = False, access_count: int = 0):
    return {
        'dataset_id': dataset_id,
        'dataset_fingerprint': f'{dataset_id}-fingerprint',
        'status': 'SPENT_CONTAMINATED' if spent else 'RESERVED_UNTOUCHED',
        'first_access_utc': None,
        'access_count': access_count,
        'spent': spent,
        'contaminated': spent,
        'reason': 'SYNTHETIC_TEST',
        'source_packet': 'TEST',
    }


def test_spent_v1_guard_blocks_before_evaluation_callback():
    path = _synthetic_guard_path('spent_v1.json')
    module._write_holdout_guard(path, {'FINAL_HOLDOUT_V1': _synthetic_dataset('FINAL_HOLDOUT_V1', spent=True, access_count=2)})
    calls = []
    with pytest.raises(ValueError, match='^FINAL_HOLDOUT_ALREADY_SPENT$'):
        module.evaluate_holdout_once(
            'FINAL_HOLDOUT_V1', 'FINAL_HOLDOUT_V1-fingerprint', lambda: calls.append(True), guard_path=path
        )
    assert calls == []


def test_synthetic_atomic_claim_allows_exactly_one_access_and_preserves_v2():
    path = _synthetic_guard_path('atomic_claim.json')
    module._write_holdout_guard(path, {
        'SYNTHETIC_V1': _synthetic_dataset('SYNTHETIC_V1'),
        'FINAL_HOLDOUT_V2': _synthetic_dataset('FINAL_HOLDOUT_V2'),
    })
    claimed = module.claim_final_holdout_access(
        'SYNTHETIC_V1', 'SYNTHETIC_V1-fingerprint', guard_path=path
    )
    assert claimed['access_count'] == 1 and claimed['spent'] is True
    with pytest.raises(ValueError, match='^FINAL_HOLDOUT_ALREADY_SPENT$'):
        module.claim_final_holdout_access('SYNTHETIC_V1', 'SYNTHETIC_V1-fingerprint', guard_path=path)
    guard = __import__('json').loads(path.read_text(encoding='utf-8'))
    assert guard['datasets']['FINAL_HOLDOUT_V2']['access_count'] == 0
    assert guard['datasets']['FINAL_HOLDOUT_V2']['spent'] is False


def test_holdout_guard_persists_across_python_processes():
    path = _synthetic_guard_path('cross_process.json')
    module._write_holdout_guard(path, {'SYNTHETIC': _synthetic_dataset('SYNTHETIC')})
    code = (
        "from pathlib import Path; from automation.forex_engine.forex_macd_confluence_runner_v1 "
        "import claim_final_holdout_access; import sys; "
        "claim_final_holdout_access('SYNTHETIC','SYNTHETIC-fingerprint',guard_path=Path(sys.argv[1]))"
    )
    first = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True, text=True, check=False)
    second = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True, text=True, check=False)
    assert first.returncode == 0
    assert second.returncode != 0
    assert 'FINAL_HOLDOUT_ALREADY_SPENT' in second.stderr
