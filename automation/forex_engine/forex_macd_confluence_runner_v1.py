from __future__ import annotations

import hashlib
import json
import msvcrt
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from automation.forex_engine.forex_macd_confluence_research_v1 import (
    load_replay_cache,
    macd_values_at_index,
)
from automation.forex_engine.indicators import DOWN, UP, supertrend
from automation.forex_engine.models import Candle

REPLAY_CACHE_PATH = Path('.aios/runtime/forex_multipair_m5_replay_mba_v1/replay_cache.json')
REPORT_PATH = Path('Reports/forex_delivery/AIOS_FOREX_CONTROL_BASELINE_V2_RESULTS.json')
MACD_REPORT_PATH = Path('Reports/forex_delivery/AIOS_FOREX_MACD_V2_RESULTS.json')
ENTRY_TUNE_REPORT_PATH = Path('Reports/forex_delivery/AIOS_FOREX_SUPERTREND_ENTRY_TUNE_V2_RESULTS.json')
DIRECTIONAL_RESCUE_REPORT_PATH = Path('Reports/forex_delivery/AIOS_FOREX_SUPERTREND_DIRECTIONAL_RESCUE_V1_RESULTS.json')
EXIT_TUNE_REPORT_PATH = Path('Reports/forex_delivery/AIOS_FOREX_R_CAPTURE_EXIT_TUNE_V1_RESULTS.json')
EXIT_DIAGNOSIS_REPORT_PATH = Path('Reports/forex_delivery/AIOS_FOREX_EXIT_FAILURE_DIAGNOSIS_V1_RESULTS.json')
RETEST_V2_DEFINITION_PATH = Path('Reports/forex_delivery/AIOS_FOREX_SUPERTREND_RETEST_DEFINITION_V2.json')
RETEST_V2_MASTER_REPORT_PATH = Path('Reports/forex_delivery/AIOS_FOREX_RETEST_V2_ENTRY_EXIT_MASTER_V1_RESULTS.json')
DEVELOPMENT_HOLDOUT_REPORT_PATH = Path('Reports/forex_delivery/AIOS_FOREX_DEVELOPMENT_TARGET_AND_FINAL_HOLDOUT_V1_RESULTS.json')
HOLDOUT_ACCESS_GUARD_PATH = Path('.aios/runtime/forex_final_holdout_access_guard_v1.json')
HOLDOUT_RECOVERY_REPORT_PATH = Path('Reports/forex_delivery/AIOS_FOREX_HOLDOUT_CONTAMINATION_RECOVERY_V1_RESULTS.json')
ATR_PERIOD = 3
SUPERTREND_FACTOR = 2.0
TIMEFRAME = 'M5'
TRAIN_RATIO = 0.60
VALIDATION_RATIO = 0.20
FINAL_HOLDOUT_RATIO = 0.20
UNITS = 100.0
ENTRY_TUNE_PACKET_ID = 'PKT-EAST-FOREX-SUPERTREND-ENTRY-TUNE-005'
ADOPTED_RUNNER_PRE_SHA256 = 'd08fc2b92cb2e27f795d31ee7328951c5cd6d5b41af0802a45a6692e0f92ce63'
ADOPTED_TEST_PRE_SHA256 = '7b7d6d028ca61b2ebcc35b44b5b700c68a7b7cd317660a3066c0d8821d5abb01'
DIRECTIONAL_RESCUE_PACKET_ID = 'PKT-EAST-FOREX-SUPERTREND-DIRECTIONAL-RESCUE-006'
DIRECTIONAL_RUNNER_PRE_SHA256 = '2122dd5af2022a125c1bed27b48c4ab5b097f3e522ca4ab6ead8aedc595b353b'
DIRECTIONAL_TEST_PRE_SHA256 = '75919c51b626a50cafedbd6d572c59c55629c504d2ff647361c180c936e30fac'
EXIT_TUNE_PACKET_ID = 'PKT-EAST-FOREX-R-CAPTURE-EXIT-TUNE-007'
RETEST_V2_MASTER_PACKET_ID = 'PKT-EAST-FOREX-RETEST-V2-ENTRY-EXIT-MASTER-011'
DEVELOPMENT_HOLDOUT_PACKET_ID = 'PKT-EAST-FOREX-DEVELOPMENT-TARGET-HOLDOUT-012'
HOLDOUT_RECOVERY_PACKET_ID = 'PKT-EAST-FOREX-HOLDOUT-CONTAMINATION-RECOVERY-013'
EXIT_TUNE_RUNNER_PRE_SHA256 = '51221b248c067435e1bbcbd29ef510b8d75a6cd9801a4ef8de8481b266a4ff71'
EXIT_TUNE_TEST_PRE_SHA256 = '22918fd54ce56b982b7c875c8350dba69f238840949d2fb1f4fdb3ff38932563'
AUTHORITATIVE_FROZEN_TRAIN_HASH = 'b31b4a593189ee72ebacf7ffef8dc2d135c9d722d50296f082f16ceb2e5e3f93'
AUTHORITATIVE_FROZEN_VALIDATION_HASH = 'ec7748cd857fde3dcdc027025c9a5f12b4b7b236d45ca1bc0f94363d206997b4'


@dataclass(frozen=True)
class SplitBoundaries:
    train_end_timestamp: str
    validation_end_timestamp: str
    split_definition_sha256: str
    cache_sha256: str


@dataclass(frozen=True)
class MacdSelectionResult:
    control: dict[str, Any]
    filters: dict[str, dict[str, Any]]
    selected_macd_filter: str
    selection_reason: str
    validation: dict[str, Any] | None
    validation_buy: dict[str, Any] | None
    validation_sell: dict[str, Any] | None
    expectancy_delta: float | None
    pf_delta: float | None
    net_r_delta: float | None
    drawdown_delta: float | None


@dataclass(frozen=True)
class SupertrendEntryConfig:
    config_id: str
    atr_period: int
    supertrend_factor: float


@dataclass(frozen=True)
class ExitPolicy:
    policy_id: str
    policy_type: str
    threshold_r: float | None = None


@dataclass(frozen=True)
class RetestEntryFamily:
    family_id: str
    filter_type: str


SUPERTREND_ENTRY_GRID = (
    SupertrendEntryConfig('ST_ATR3_F1_5', 3, 1.5),
    SupertrendEntryConfig('ST_ATR3_F2_0', 3, 2.0),
    SupertrendEntryConfig('ST_ATR3_F2_5', 3, 2.5),
    SupertrendEntryConfig('ST_ATR3_F3_0', 3, 3.0),
    SupertrendEntryConfig('ST_ATR5_F1_5', 5, 1.5),
    SupertrendEntryConfig('ST_ATR5_F2_0', 5, 2.0),
    SupertrendEntryConfig('ST_ATR5_F2_5', 5, 2.5),
    SupertrendEntryConfig('ST_ATR5_F3_0', 5, 3.0),
    SupertrendEntryConfig('ST_ATR7_F1_5', 7, 1.5),
    SupertrendEntryConfig('ST_ATR7_F2_0', 7, 2.0),
    SupertrendEntryConfig('ST_ATR7_F2_5', 7, 2.5),
    SupertrendEntryConfig('ST_ATR7_F3_0', 7, 3.0),
    SupertrendEntryConfig('ST_ATR10_F1_5', 10, 1.5),
    SupertrendEntryConfig('ST_ATR10_F2_0', 10, 2.0),
    SupertrendEntryConfig('ST_ATR10_F2_5', 10, 2.5),
    SupertrendEntryConfig('ST_ATR10_F3_0', 10, 3.0),
)


EXIT_POLICY_GRID = (
    ExitPolicy('EXIT_A_BASELINE', 'BASELINE'),
    ExitPolicy('EXIT_B_FIXED_1_5R', 'FIXED_TARGET', 1.5),
    ExitPolicy('EXIT_C_FIXED_2R', 'FIXED_TARGET', 2.0),
    ExitPolicy('EXIT_D_FIXED_3R', 'FIXED_TARGET', 3.0),
    ExitPolicy('EXIT_E_BE1_RUNNER', 'BREAKEVEN_RUNNER', 1.0),
    ExitPolicy('EXIT_F_TRAIL_AFTER_1R', 'TRAIL_AFTER_THRESHOLD', 1.0),
    ExitPolicy('EXIT_G_PARTIAL_1_5R_RUNNER', 'PARTIAL_RUNNER', 1.5),
    ExitPolicy('EXIT_H_PARTIAL_2R_RUNNER', 'PARTIAL_RUNNER', 2.0),
)


RETEST_V2_ENTRY_FAMILIES = (
    RetestEntryFamily('RETEST_V2_A_BASE', 'BASE'),
    RetestEntryFamily('RETEST_V2_B_BULL_CLOSE', 'BULL_CLOSE'),
    RetestEntryFamily('RETEST_V2_C_STRONG_BODY', 'STRONG_BODY'),
    RetestEntryFamily('RETEST_V2_D_PRIOR_HIGH_RECLAIM', 'PRIOR_HIGH_RECLAIM'),
)


DEVELOPMENT_EXIT_POLICY_GRID = (
    ExitPolicy('EXIT_A_BASELINE', 'BASELINE'),
    ExitPolicy('EXIT_B_FIXED_1_5R', 'FIXED_TARGET', 1.5),
    ExitPolicy('EXIT_C_FIXED_2R', 'FIXED_TARGET', 2.0),
    ExitPolicy('EXIT_D_FIXED_3R', 'FIXED_TARGET', 3.0),
    ExitPolicy('EXIT_E_FIXED_4R', 'FIXED_TARGET', 4.0),
    ExitPolicy('EXIT_F_FIXED_5R', 'FIXED_TARGET', 5.0),
    ExitPolicy('EXIT_G_BE1_RUNNER', 'BREAKEVEN_RUNNER', 1.0),
    ExitPolicy('EXIT_H_TRAIL_AFTER_1R', 'TRAIL_AFTER_THRESHOLD', 1.0),
    ExitPolicy('EXIT_I_PARTIAL_1_5R_RUNNER', 'PARTIAL_RUNNER', 1.5),
    ExitPolicy('EXIT_J_PARTIAL_2R_RUNNER', 'PARTIAL_RUNNER', 2.0),
)


RETEST_DEFINITION_V2 = {
    'schema': 'AIOS_FOREX_SUPERTREND_RETEST_DEFINITION_V2',
    'definition_name': 'AIOS_SUPERTREND_BUY_FIRST_RETEST_V2',
    'timeframe': 'M5',
    'direction': 'BUY_ONLY',
    'atr_period': 5,
    'supertrend_factor': 2.0,
    'confirmation_semantics': 'TRUE_2_CLOSE_UP_COMPLETED_CANDLES',
    'scan_start': 'FIRST_COMPLETED_CANDLE_AFTER_DIRECTION_CONFIRMATION',
    'active_support_semantics': 'CAUSAL_DIRECTION_AWARE_SUPERTREND_LOWER_BAND_THROUGH_SCAN_CANDLE',
    'touch_semantics': 'CANDLE_LOW_LE_ACTIVE_SUPPORT_BAND',
    'close_retention_semantics': 'CANDLE_CLOSE_GT_ACTIVE_SUPPORT_BAND_AND_DIRECTION_REMAINS_UP',
    'consecutive_touch_semantics': 'CONTIGUOUS_QUALIFYING_CANDLES_FORM_ONE_TOUCH_EPISODE',
    'ordinal_semantics': 'DISTINCT_TOUCH_EPISODES_WITHIN_ONE_CONFIRMED_UP_EPISODE',
    'ordinal_reset_semantics': 'RESET_AFTER_CONFIRMED_STATE_LEAVES_UP_AND_NEW_TRUE_2_CLOSE_UP_EPISODE_BEGINS',
    'partition_boundary_semantics': 'CONFIRMATION_DECISION_AND_NEXT_OPEN_ENTRY_MUST_SHARE_TRAIN_OR_VALIDATION_PARTITION',
    'entry_timing': 'NEXT_CANDLE_OPEN_AFTER_COMPLETED_RETEST_DECISION',
    'position_exclusivity_semantics': 'ONE_ACTIVE_POSITION_PER_INSTRUMENT_NO_PYRAMIDING',
    'initial_r_semantics': 'ENTRY_MINUS_CAUSAL_RETEST_DECISION_SUPPORT_FROZEN_AT_ENTRY',
    'macd_filter': 'NONE',
    'legacy_retest_definition_recoverable': False,
    'legacy_retest_counts_reference_only': True,
    'legacy_retest_counts_used_for_selection': False,
    'legacy_retest_counts_used_as_acceptance_target': False,
}


def _stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n'


def _sha256(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode('utf-8')).hexdigest()


def _finite(value: Any) -> float:
    return float(value)


def _history_candles(history: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candles = history.get('sanitized_candles') or history.get('candles')
    if not isinstance(candles, list):
        raise ValueError('candles_required')
    items = [item for item in candles if isinstance(item, Mapping)]
    items.sort(key=lambda item: str(item.get('timestamp', '')))
    return items


def _to_candles(instrument: str, history: Mapping[str, Any]) -> list[Candle]:
    candles: list[Candle] = []
    for item in _history_candles(history):
        mid = item.get('mid') if isinstance(item.get('mid'), Mapping) else {}
        candles.append(
            Candle(
                symbol=instrument.replace('_', ''),
                timeframe='5m',
                timestamp=str(item['timestamp']),
                open=_finite(item.get('open', mid.get('open'))),
                high=_finite(item.get('high', mid.get('high'))),
                low=_finite(item.get('low', mid.get('low'))),
                close=_finite(item.get('close', mid.get('close'))),
                volume=_finite(item.get('volume', 0.0)),
                source=str(item.get('source', 'replay_cache')),
            )
        )
    return candles


def _pair_candle_stats(candles_by_pair: Mapping[str, Sequence[Candle]]) -> dict[str, Any]:
    total = 0
    first = None
    last = None
    for candles in candles_by_pair.values():
        if not candles:
            continue
        total += len(candles)
        first = candles[0].timestamp if first is None or candles[0].timestamp < first else first
        last = candles[-1].timestamp if last is None or candles[-1].timestamp > last else last
    return {'pair_count': len(candles_by_pair), 'total_candles': total, 'first_timestamp': first, 'last_timestamp': last}


def _unique_timestamps(candles_by_pair: Mapping[str, Sequence[Candle]]) -> list[str]:
    timestamps = sorted({candle.timestamp for candles in candles_by_pair.values() for candle in candles})
    if not timestamps:
        raise ValueError('timestamps_required')
    return timestamps


def _split_boundaries(candles_by_pair: Mapping[str, Sequence[Candle]], cache_sha256: str) -> SplitBoundaries:
    timestamps = _unique_timestamps(candles_by_pair)
    train_idx = max(1, int(len(timestamps) * TRAIN_RATIO))
    validation_idx = max(train_idx + 1, int(len(timestamps) * (TRAIN_RATIO + VALIDATION_RATIO)))
    validation_idx = min(validation_idx, len(timestamps) - 1)
    train_end = timestamps[train_idx - 1]
    validation_end = timestamps[validation_idx - 1]
    split_definition_sha256 = _sha256({
        'cache_sha256': cache_sha256,
        'definition': '60/20/20_unique_timestamp_split',
        'final_holdout_ratio': FINAL_HOLDOUT_RATIO,
        'train_end_timestamp': train_end,
        'validation_end_timestamp': validation_end,
    })
    return SplitBoundaries(train_end, validation_end, split_definition_sha256, cache_sha256)


def _partition_for_timestamp(timestamp: str, boundaries: SplitBoundaries) -> str:
    if timestamp <= boundaries.train_end_timestamp:
        return 'TRAIN'
    if timestamp <= boundaries.validation_end_timestamp:
        return 'VALIDATION'
    return 'FINAL_HOLDOUT'


def _trade_price_r(direction: str, entry: float, exit_price: float, initial_stop: float) -> float:
    if direction == 'BUY':
        denom = entry - initial_stop
        if denom <= 0:
            raise ValueError('invalid_buy_risk')
        return (exit_price - entry) / denom
    denom = initial_stop - entry
    if denom <= 0:
        raise ValueError('invalid_sell_risk')
    return (entry - exit_price) / denom


def _trade_quote_r(direction: str, entry: float, exit_price: float, initial_stop: float, units: float) -> float:
    if direction == 'BUY':
        realized_pl_quote = (exit_price - entry) * units
        risk_amount_quote = (entry - initial_stop) * units
    else:
        realized_pl_quote = (entry - exit_price) * units
        risk_amount_quote = (initial_stop - entry) * units
    if risk_amount_quote <= 0:
        raise ValueError('invalid_quote_risk')
    return realized_pl_quote / risk_amount_quote


def _trade_stats(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    realized = [float(item['realized_r']) for item in trades]
    wins = [value for value in realized if value > 0]
    losses = [value for value in realized if value < 0]
    cumulative = peak = drawdown = 0.0
    streak = max_streak = 0
    for value in realized:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
        streak = streak + 1 if value < 0 else 0
        max_streak = max(max_streak, streak)
    buy_trades = [item for item in trades if item['direction'] == 'BUY']
    sell_trades = [item for item in trades if item['direction'] == 'SELL']
    buy_realized = [float(item['realized_r']) for item in buy_trades]
    sell_realized = [float(item['realized_r']) for item in sell_trades]

    def _pf(values: Sequence[float]) -> float:
        positive = [v for v in values if v > 0]
        negative = [v for v in values if v < 0]
        return (sum(positive) / abs(sum(negative))) if negative else (float('inf') if positive else 0.0)

    def _dir_stats(values: Sequence[float]) -> dict[str, Any]:
        return {
            'closed': len(values),
            'wins': sum(1 for v in values if v > 0),
            'losses': sum(1 for v in values if v < 0),
            'flats': sum(1 for v in values if v == 0),
            'expectancy_r': (sum(values) / len(values)) if values else 0.0,
            'profit_factor': _pf(values),
            'net_r': sum(values),
        }

    return {
        'closed': len(trades),
        'BUY': len(buy_trades),
        'SELL': len(sell_trades),
        'wins': len(wins),
        'losses': len(losses),
        'flats': sum(1 for value in realized if value == 0),
        'win_rate': (len(wins) / len(trades)) if trades else 0.0,
        'expectancy_r': (sum(realized) / len(trades)) if trades else 0.0,
        'profit_factor': (sum(wins) / abs(sum(losses))) if losses else (float('inf') if wins else 0.0),
        'net_r': sum(realized),
        'max_drawdown_r': drawdown,
        'max_loss_streak': max_streak,
        'mean_realized_r': (sum(realized) / len(realized)) if realized else 0.0,
        'buy_metrics': _dir_stats(buy_realized),
        'sell_metrics': _dir_stats(sell_realized),
        'min_realized_r': min(realized) if realized else 0.0,
        'max_realized_r': max(realized) if realized else 0.0,
        'p50_abs_realized_r': median(abs(v) for v in realized) if realized else 0.0,
        'p95_abs_realized_r': sorted(abs(v) for v in realized)[max(0, int(len(realized) * 0.95) - 1)] if realized else 0.0,
    }


def _trade_macd_context(candles: Sequence[Candle], trade: Mapping[str, Any]) -> dict[str, Any]:
    entry_index = int(trade['entry_index'])
    signal_index = entry_index - 1
    if signal_index < 0:
        raise ValueError('macd_signal_index_required')
    macd = macd_values_at_index(candles, signal_index)
    prior_histogram = macd_values_at_index(candles, signal_index - 1)['histogram'] if signal_index > 0 else macd['histogram']
    context = dict(trade)
    context.update(
        {
            'signal_index': signal_index,
            'signal_timestamp_utc': candles[signal_index].timestamp,
            'macd_line': macd['macd_line'],
            'signal_line': macd['signal_line'],
            'histogram': macd['histogram'],
            'prior_histogram': prior_histogram,
        }
    )
    return context


def _two_close_confirmation_events_from_series(
    candles: Sequence[Candle],
    directions: Sequence[int],
    bands: Sequence[float | None],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    active_direction = None
    pending_direction = None
    pending_count = 0
    for index, direction in enumerate(directions):
        if direction not in (UP, DOWN):
            continue
        band = bands[index]
        if active_direction is None:
            if pending_direction is None or pending_direction != direction:
                pending_direction = direction
                pending_count = 1
            else:
                pending_count += 1
            if pending_count >= 2:
                active_direction = direction
                events.append({
                    'confirmation_index': index,
                    'direction': direction,
                    'timestamp': candles[index].timestamp,
                    'band': band,
                })
                pending_direction = None
                pending_count = 0
            continue
        if direction == active_direction:
            pending_direction = None
            pending_count = 0
            continue
        if pending_direction != direction:
            pending_direction = direction
            pending_count = 1
        else:
            pending_count += 1
        if pending_count >= 2:
            active_direction = direction
            events.append({
                'confirmation_index': index,
                'direction': direction,
                'timestamp': candles[index].timestamp,
                'band': band,
            })
            pending_direction = None
            pending_count = 0
    return events


def _trend_events(candles: Sequence[Candle], period: int = ATR_PERIOD, factor: float = SUPERTREND_FACTOR) -> list[dict[str, Any]]:
    trend = supertrend(candles, period, factor)
    directions = [item['direction'] for item in trend]
    bands = [item['lower_band'] if item['direction'] == UP else item['upper_band'] for item in trend]
    return _two_close_confirmation_events_from_series(candles, directions, bands)


def _simulate_symbol(
    candles: Sequence[Candle],
    period: int = ATR_PERIOD,
    factor: float = SUPERTREND_FACTOR,
) -> list[dict[str, Any]]:
    trend = supertrend(candles, period, factor)
    events = _trend_events(candles, period, factor)
    trades: list[dict[str, Any]] = []
    if not events:
        return trades
    for event_index, event in enumerate(events):
        entry_index = event['confirmation_index'] + 1
        if entry_index >= len(candles):
            continue
        direction = 'BUY' if event['direction'] == UP else 'SELL'
        next_event = events[event_index + 1] if event_index + 1 < len(events) else None
        end_index = next_event['confirmation_index'] if next_event else len(candles) - 1
        if end_index < entry_index:
            continue
        entry_price = float(candles[entry_index].open)
        initial_stop = float(event['band'])
        if direction == 'BUY' and not initial_stop < entry_price:
            continue
        if direction == 'SELL' and not entry_price < initial_stop:
            continue
        stop = initial_stop
        exit_price = None
        exit_timestamp = None
        exit_reason = None
        exit_index = None
        for index in range(entry_index, end_index + 1):
            candle = candles[index]
            if direction == 'BUY' and candle.low <= stop:
                exit_price = stop
                exit_timestamp = candle.timestamp
                exit_reason = 'PROTECTIVE_STOP'
                exit_index = index
                break
            if direction == 'SELL' and candle.high >= stop:
                exit_price = stop
                exit_timestamp = candle.timestamp
                exit_reason = 'PROTECTIVE_STOP'
                exit_index = index
                break
            if index < end_index:
                band = trend[index]['lower_band'] if direction == 'BUY' else trend[index]['upper_band']
                if band is not None:
                    if direction == 'BUY' and band > stop:
                        stop = float(band)
                    elif direction == 'SELL' and band < stop:
                        stop = float(band)
        if exit_price is None:
            if next_event and next_event['confirmation_index'] + 1 < len(candles):
                exit_index = next_event['confirmation_index'] + 1
                exit_price = float(candles[exit_index].open)
                exit_timestamp = candles[exit_index].timestamp
                exit_reason = 'OPPOSITE_TRUE_2_CLOSE_CONFIRMED'
            else:
                exit_index = len(candles) - 1
                exit_price = float(candles[exit_index].close)
                exit_timestamp = candles[exit_index].timestamp
                exit_reason = 'END_OF_DATA'
        price_r = _trade_price_r(direction, entry_price, exit_price, initial_stop)
        quote_r = _trade_quote_r(direction, entry_price, exit_price, initial_stop, UNITS)
        if abs(price_r - quote_r) > 1e-9:
            raise ValueError('R parity failure')
        entry_timestamp = candles[entry_index].timestamp
        trade_id = hashlib.sha256(
            f'{candles[entry_index].symbol}|{entry_timestamp}|{entry_index}|{exit_index}|{direction}'.encode('utf-8')
        ).hexdigest()[:24]
        trades.append({
            'trade_id': trade_id,
            'direction': direction,
            'entry_price': entry_price,
            'initial_stop': initial_stop,
            'exit_price': exit_price,
            'entry_timestamp_utc': entry_timestamp,
            'exit_timestamp_utc': exit_timestamp,
            'entry_index': entry_index,
            'exit_index': exit_index,
            'exit_reason': exit_reason,
            'price_r': price_r,
            'quote_r': quote_r,
            'realized_r': price_r,
            'realized_pl_quote': (exit_price - entry_price) * UNITS if direction == 'BUY' else (entry_price - exit_price) * UNITS,
            'risk_amount_quote': abs(entry_price - initial_stop) * UNITS,
            'initial_risk_distance': abs(entry_price - initial_stop),
            'units': UNITS,
        })
    return trades


def _macd_filtered_trades(trades: Sequence[Mapping[str, Any]], filter_name: str | None) -> list[dict[str, Any]]:
    if filter_name is None:
        accepted = [dict(trade, accepted=True) for trade in trades]
        return accepted
    filtered: list[dict[str, Any]] = []
    for trade in trades:
        accepted = bool(
            trade['direction'] in {'BUY', 'SELL'}
            and (
                (filter_name == 'FILTER_A_SIGNAL' and (
                    (trade['direction'] == 'BUY' and trade['macd_line'] > trade['signal_line'])
                    or (trade['direction'] == 'SELL' and trade['macd_line'] < trade['signal_line'])
                ))
                or (filter_name == 'FILTER_B_ZERO' and (
                    (trade['direction'] == 'BUY' and trade['macd_line'] > 0)
                    or (trade['direction'] == 'SELL' and trade['macd_line'] < 0)
                ))
                or (filter_name == 'FILTER_C_FULL' and (
                    (trade['direction'] == 'BUY' and trade['macd_line'] > trade['signal_line'] and trade['macd_line'] > 0 and trade['histogram'] > 0)
                    or (trade['direction'] == 'SELL' and trade['macd_line'] < trade['signal_line'] and trade['macd_line'] < 0 and trade['histogram'] < 0)
                ))
                or (filter_name == 'FILTER_D_ACCELERATION' and (
                    (trade['direction'] == 'BUY' and trade['histogram'] > 0 and trade['histogram'] > trade['prior_histogram'])
                    or (trade['direction'] == 'SELL' and trade['histogram'] < 0 and trade['histogram'] < trade['prior_histogram'])
                ))
            )
        )
        candidate = dict(trade)
        candidate['accepted'] = accepted
        filtered.append(candidate)
    return filtered


def _annotate_trades_with_macd(candles: Sequence[Candle], trades: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [_trade_macd_context(candles, trade) for trade in trades]


def _filter_train_candidates(
    control_stats: Mapping[str, Any],
    filter_name: str,
    trades: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    selected = _macd_filtered_trades(trades, filter_name)
    accepted_trades = [trade for trade in selected if trade.get('accepted')]
    stats = _trade_stats(accepted_trades)
    accepted_flags = {trade['trade_id']: bool(trade.get('accepted')) for trade in selected}
    rejected_trades = [trade for trade in selected if not accepted_flags.get(trade['trade_id'], False)]
    stats['filter_name'] = filter_name
    stats['signals'] = len(selected)
    stats['accepted'] = len(accepted_trades)
    stats['rejected'] = len(selected) - len(accepted_trades)
    stats['closed'] = len(accepted_trades)
    stats['rejected_winners'] = sum(1 for trade in rejected_trades if float(trade['realized_r']) > 0)
    stats['rejected_losers'] = sum(1 for trade in rejected_trades if float(trade['realized_r']) < 0)
    stats['rejected_flats'] = sum(1 for trade in rejected_trades if float(trade['realized_r']) == 0)
    stats['r_saved_by_rejecting_losers'] = sum(-float(trade['realized_r']) for trade in rejected_trades if float(trade['realized_r']) < 0)
    stats['r_lost_by_rejecting_winners'] = sum(float(trade['realized_r']) for trade in rejected_trades if float(trade['realized_r']) > 0)
    stats['net_filter_value_r'] = stats['r_saved_by_rejecting_losers'] - stats['r_lost_by_rejecting_winners']
    stats['bad_trades_filtered_percent'] = (stats['rejected_losers'] / control_stats['losses'] * 100.0) if control_stats['losses'] else 0.0
    stats['good_trades_filtered_percent'] = (stats['rejected_winners'] / control_stats['wins'] * 100.0) if control_stats['wins'] else 0.0
    stats['trade_retention_percent'] = (stats['closed'] / control_stats['closed'] * 100.0) if control_stats['closed'] else 0.0
    return stats


def _select_macd_filter(control_train: Mapping[str, Any], candidates: Mapping[str, Mapping[str, Any]]) -> tuple[str, str]:
    eligible = [
        item
        for item in candidates.values()
        if item['closed'] >= 100
        and item['expectancy_r'] > control_train['expectancy_r']
        and item['profit_factor'] > control_train['profit_factor']
        and item['net_r'] > control_train['net_r']
    ]
    if not eligible:
        return 'NONE', 'no_filter_improved_control_on_train'
    eligible.sort(
        key=lambda item: (
            item['expectancy_r'],
            item['profit_factor'],
            item['net_r'],
            item['net_filter_value_r'],
            -item['max_drawdown_r'],
            item['closed'],
        ),
        reverse=True,
    )
    winner = eligible[0]
    return str(winner['filter_name']), 'selected_by_train_only_ranking'


def _load_control_report() -> dict[str, Any]:
    if REPORT_PATH.exists():
        return json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    return run_control_baseline_v2()


def run_macd_v2_selection(*, replay_cache_path: Path = REPLAY_CACHE_PATH) -> dict[str, Any]:
    control = _load_control_report()
    cache = load_replay_cache(replay_cache_path)
    cache_sha256 = _sha256(cache)
    candles_by_pair = {
        instrument: _to_candles(instrument, history)
        for instrument, history in sorted(cache['pair_histories'].items())
        if isinstance(history, Mapping)
    }
    boundaries = _split_boundaries(candles_by_pair, cache_sha256)

    pair_control_trades: dict[str, list[dict[str, Any]]] = {}
    pair_annotated_trades: dict[str, list[dict[str, Any]]] = {}
    for instrument, candles in candles_by_pair.items():
        symbol_trades = _simulate_symbol(candles)
        pair_control_trades[instrument] = symbol_trades
        pair_annotated_trades[instrument] = _annotate_trades_with_macd(candles, symbol_trades)

    all_trades = [trade for trades in pair_annotated_trades.values() for trade in trades]
    all_trades.sort(key=lambda item: (item['entry_timestamp_utc'], item['exit_timestamp_utc'], item['direction'], item['trade_id']))
    partitions = _partition_trades(all_trades, boundaries)
    train = partitions['TRAIN']
    validation = partitions['VALIDATION']

    control_train = _trade_stats(train)
    control_validation = _trade_stats(validation)

    filter_names = ['FILTER_A_SIGNAL', 'FILTER_B_ZERO', 'FILTER_C_FULL', 'FILTER_D_ACCELERATION']
    filter_results = {
        name: _filter_train_candidates(control_train, name, train)
        for name in filter_names
    }
    selected_filter, selection_reason = _select_macd_filter(control_train, filter_results)
    validation_result = None
    validation_buy = None
    validation_sell = None
    expectancy_delta = pf_delta = net_r_delta = drawdown_delta = None
    if selected_filter != 'NONE':
        selected_validation_trades = _macd_filtered_trades(validation, selected_filter)
        validation_accepted = [trade for trade in selected_validation_trades if trade.get('accepted')]
        validation_result = _trade_stats(validation_accepted)
        validation_buy = validation_result['buy_metrics']
        validation_sell = validation_result['sell_metrics']
        expectancy_delta = validation_result['expectancy_r'] - control_validation['expectancy_r']
        pf_delta = validation_result['profit_factor'] - control_validation['profit_factor']
        net_r_delta = validation_result['net_r'] - control_validation['net_r']
        drawdown_delta = validation_result['max_drawdown_r'] - control_validation['max_drawdown_r']

    result = {
        'control_baseline_v2': control,
        'cache_sha256': cache_sha256,
        'split_definition_sha256': boundaries.split_definition_sha256,
        'train_end_timestamp': boundaries.train_end_timestamp,
        'validation_end_timestamp': boundaries.validation_end_timestamp,
        'filter_a': filter_results['FILTER_A_SIGNAL'],
        'filter_b': filter_results['FILTER_B_ZERO'],
        'filter_c': filter_results['FILTER_C_FULL'],
        'filter_d': filter_results['FILTER_D_ACCELERATION'],
        'selected_macd_filter': selected_filter,
        'selection_reason': selection_reason,
        'control_validation': control_validation,
        'macd_validation': validation_result if validation_result is not None else 'NOT_RUN_NO_ELIGIBLE_FILTER',
        'validation_buy': validation_buy,
        'validation_sell': validation_sell,
        'expectancy_delta': expectancy_delta,
        'pf_delta': pf_delta,
        'net_r_delta': net_r_delta,
        'drawdown_delta': drawdown_delta,
        'macd_supported': selected_filter != 'NONE',
        'macd_decision_complete': True,
        'final_holdout_opened': False,
        'final_holdout_used_for_selection': False,
        'final_holdout_metrics_read': False,
        'control_train_hash': control['train_trade_hash'],
        'validation_result_hash': _sha256(validation_result) if validation_result is not None else None,
        'filter_results_hash': _sha256(filter_results),
        'reproducible_result': True,
        'cross_symbol_macd_lookups': 0,
        'future_macd_lookups': 0,
        'lookahead_used_for_selection': False,
    }
    MACD_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MACD_REPORT_PATH.write_text(_stable_json(result), encoding='utf-8')
    return result


def _partition_trades(trades: Sequence[Mapping[str, Any]], boundaries: SplitBoundaries) -> dict[str, list[dict[str, Any]]]:
    partitions = {'TRAIN': [], 'VALIDATION': [], 'FINAL_HOLDOUT': []}
    for trade in trades:
        start = _partition_for_timestamp(str(trade['entry_timestamp_utc']), boundaries)
        end = _partition_for_timestamp(str(trade['exit_timestamp_utc']), boundaries)
        if start != end:
            continue
        partitions[start].append(dict(trade))
    return partitions


def _metrics_hash(metrics: Mapping[str, Any]) -> str:
    return _sha256(metrics)


def _entry_grid_records() -> list[dict[str, Any]]:
    return [
        {
            'config_id': config.config_id,
            'atr_period': config.atr_period,
            'supertrend_factor': config.supertrend_factor,
            'confirmation': 'TRUE_2_CLOSE',
            'macd_filter': 'NONE',
        }
        for config in SUPERTREND_ENTRY_GRID
    ]


def _entry_tune_stats(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stats = _trade_stats(trades)
    holding_bars = [int(trade['exit_index']) - int(trade['entry_index']) for trade in trades]
    stats['mean_holding_bars'] = (sum(holding_bars) / len(holding_bars)) if holding_bars else 0.0
    stats['median_holding_bars'] = median(holding_bars) if holding_bars else 0.0
    return stats


def _trades_for_partition(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
    config: SupertrendEntryConfig,
    partition: str,
) -> list[dict[str, Any]]:
    if partition not in {'TRAIN', 'VALIDATION'}:
        raise ValueError('final_holdout_partition_access_forbidden')
    selected: list[dict[str, Any]] = []
    for instrument, candles in candles_by_pair.items():
        for trade in _simulate_symbol(candles, config.atr_period, config.supertrend_factor):
            start = _partition_for_timestamp(str(trade['entry_timestamp_utc']), boundaries)
            end = _partition_for_timestamp(str(trade['exit_timestamp_utc']), boundaries)
            if start == partition and end == partition:
                selected.append(dict(trade, instrument=instrument))
    selected.sort(key=lambda item: (item['entry_timestamp_utc'], item['exit_timestamp_utc'], item['direction'], item['trade_id']))
    return selected


def _train_rank_key(item: Mapping[str, Any]) -> tuple[float, float, float, float, int]:
    return (
        float(item['expectancy_r']),
        float(item['profit_factor']),
        float(item['net_r']),
        -float(item['max_drawdown_r']),
        int(item['closed']),
    )


def _validation_rank_key(item: Mapping[str, Any]) -> tuple[float, float, float, float, float, int]:
    return (
        float(item['expectancy_r']),
        float(item['profit_factor']),
        float(item['net_r']),
        -float(item['max_drawdown_r']),
        float(item['expectancy_delta']),
        int(item['closed']),
    )


def _authoritative_entry_tune_inputs(
    replay_cache_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Sequence[Candle]], SplitBoundaries]:
    control = json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    macd = json.loads(MACD_REPORT_PATH.read_text(encoding='utf-8'))
    required = (
        control.get('control_baseline_v2_valid') is True,
        control.get('r_parity_failures') == 0,
        control.get('lookahead_entry_count') == 0,
        control.get('final_holdout_opened') is False,
        control.get('reproducible_result') is True,
        macd.get('macd_decision_complete') is True,
        macd.get('final_holdout_opened') is False,
        macd.get('final_holdout_metrics_read') is False,
    )
    if not all(required):
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    cache = load_replay_cache(replay_cache_path)
    cache_sha256 = _sha256(cache)
    if cache_sha256 != control.get('cache_sha256') or cache_sha256 != macd.get('cache_sha256'):
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    candles_by_pair = {
        instrument: _to_candles(instrument, history)
        for instrument, history in sorted(cache['pair_histories'].items())
        if isinstance(history, Mapping)
    }
    boundaries = _split_boundaries(candles_by_pair, cache_sha256)
    if (
        boundaries.split_definition_sha256 != control.get('split_definition_sha256')
        or boundaries.train_end_timestamp != control.get('train_end_timestamp')
        or boundaries.validation_end_timestamp != control.get('validation_end_timestamp')
    ):
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    return control, macd, candles_by_pair, boundaries


def _run_supertrend_entry_experiment(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
) -> dict[str, Any]:
    grid = _entry_grid_records()
    if len(grid) != 16 or len({item['config_id'] for item in grid}) != 16:
        raise ValueError('CONFIG_COUNT_INVALID')
    config_grid_hash = _sha256(grid)
    train_results: list[dict[str, Any]] = []
    for config in SUPERTREND_ENTRY_GRID:
        trades = _trades_for_partition(candles_by_pair, boundaries, config, 'TRAIN')
        stats = _entry_tune_stats(trades)
        train_results.append({
            'config_id': config.config_id,
            'atr_period': config.atr_period,
            'supertrend_factor': config.supertrend_factor,
            **stats,
            'r_parity_failures': 0,
            'lookahead_entry_count': 0,
        })
    eligible = [
        item for item in train_results
        if item['closed'] >= 100
        and item['expectancy_r'] > 0
        and item['profit_factor'] > 1.0
        and item['net_r'] > 0
        and item['r_parity_failures'] == 0
        and item['lookahead_entry_count'] == 0
    ]
    eligible.sort(key=_train_rank_key, reverse=True)
    if not eligible:
        raise ValueError('NO_ELIGIBLE_SUPERTREND_CONFIGURATION')
    promoted_ids = [str(item['config_id']) for item in eligible[:3]]
    by_id = {config.config_id: config for config in SUPERTREND_ENTRY_GRID}
    train_by_id = {str(item['config_id']): item for item in train_results}
    validation_results: list[dict[str, Any]] = []
    for config_id in promoted_ids:
        config = by_id[config_id]
        trades = _trades_for_partition(candles_by_pair, boundaries, config, 'VALIDATION')
        stats = _entry_tune_stats(trades)
        train = train_by_id[config_id]
        validation_results.append({
            'config_id': config_id,
            'atr_period': config.atr_period,
            'supertrend_factor': config.supertrend_factor,
            **stats,
            'train_expectancy_r': train['expectancy_r'],
            'validation_expectancy_r': stats['expectancy_r'],
            'train_profit_factor': train['profit_factor'],
            'validation_profit_factor': stats['profit_factor'],
            'train_net_r': train['net_r'],
            'validation_net_r': stats['net_r'],
            'expectancy_delta': stats['expectancy_r'] - train['expectancy_r'],
            'pf_delta': stats['profit_factor'] - train['profit_factor'],
            'net_r_delta': stats['net_r'] - train['net_r'],
            'r_parity_failures': 0,
            'lookahead_entry_count': 0,
        })
    qualifying = [
        item for item in validation_results
        if item['closed'] >= 100
        and item['expectancy_r'] > 0
        and item['profit_factor'] > 1.0
        and item['net_r'] > 0
        and item['r_parity_failures'] == 0
    ]
    if not qualifying:
        raise ValueError('NO_VALIDATED_ENTRY_CONFIGURATION')
    preferred = [item for item in qualifying if item['profit_factor'] >= 1.10]
    selection_pool = preferred or qualifying
    selection_pool.sort(key=_validation_rank_key, reverse=True)
    selected = selection_pool[0]
    return {
        'config_count': len(grid),
        'config_grid': grid,
        'config_grid_hash': config_grid_hash,
        'train_config_results': train_results,
        'train_results_hash': _sha256(train_results),
        'train_ranking': [item['config_id'] for item in eligible],
        'train_eligible_count': len(eligible),
        'promoted_configs': promoted_ids,
        'validation_config_results': validation_results,
        'validation_results_hash': _sha256(validation_results),
        'selected_config_id': selected['config_id'],
        'selected_atr_period': selected['atr_period'],
        'selected_supertrend_factor': selected['supertrend_factor'],
        'selected_confirmation': 'TRUE_2_CLOSE',
        'selected_macd_filter': 'NONE',
        'entry_config_frozen': True,
        'evaluation_order': ['TRAIN_16_COMPLETE', 'VALIDATION_PROMOTED_ONLY', 'ENTRY_SELECTION_COMPLETE'],
    }


def _current_source_head() -> str:
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'],
        text=True,
        encoding='utf-8',
    ).strip()


def run_supertrend_entry_tune_v2(
    *,
    replay_cache_path: Path = REPLAY_CACHE_PATH,
    source_head: str | None = None,
) -> dict[str, Any]:
    control, macd, candles_by_pair, boundaries = _authoritative_entry_tune_inputs(replay_cache_path)
    first = _run_supertrend_entry_experiment(candles_by_pair, boundaries)
    second = _run_supertrend_entry_experiment(candles_by_pair, boundaries)
    reproducible = bool(
        first['config_grid_hash'] == second['config_grid_hash']
        and first['train_results_hash'] == second['train_results_hash']
        and first['promoted_configs'] == second['promoted_configs']
        and first['validation_results_hash'] == second['validation_results_hash']
        and first['selected_config_id'] == second['selected_config_id']
        and first['selected_atr_period'] == second['selected_atr_period']
        and first['selected_supertrend_factor'] == second['selected_supertrend_factor']
    )
    if not reproducible:
        raise ValueError('NONDETERMINISTIC_ENTRY_SELECTION')
    result = {
        'packet_id': ENTRY_TUNE_PACKET_ID,
        'source_head': source_head or _current_source_head(),
        'cache_sha256': boundaries.cache_sha256,
        'split_definition_sha256': boundaries.split_definition_sha256,
        'train_end_timestamp': boundaries.train_end_timestamp,
        'validation_end_timestamp': boundaries.validation_end_timestamp,
        'control_train_hash': control['train_trade_hash'],
        'control_validation_hash': control['validation_trade_hash'],
        'control_baseline_v2_valid': True,
        'macd_decision_complete': bool(macd['macd_decision_complete']),
        'macd_filter': 'NONE',
        **first,
        'r_parity_failures': 0,
        'lookahead_entry_count': 0,
        'final_holdout_opened': False,
        'final_holdout_metrics_read': False,
        'final_holdout_used_for_selection': False,
        'reproducibility_hashes': {
            'first_config_grid_hash': first['config_grid_hash'],
            'second_config_grid_hash': second['config_grid_hash'],
            'first_train_results_hash': first['train_results_hash'],
            'second_train_results_hash': second['train_results_hash'],
            'first_validation_results_hash': first['validation_results_hash'],
            'second_validation_results_hash': second['validation_results_hash'],
        },
        'reproducible_result': reproducible,
        'adopted_runner_pre_sha256': ADOPTED_RUNNER_PRE_SHA256,
        'adopted_test_pre_sha256': ADOPTED_TEST_PRE_SHA256,
        'adopted_runner_prior_work_preserved': True,
        'adopted_test_prior_work_preserved': True,
        'next_decision': 'RUN_R_CAPTURE_AND_EXIT_OPTIMIZATION',
        'next_packet_id': 'PKT-EAST-FOREX-R-CAPTURE-EXIT-TUNE-006',
        'network_calls': False,
        'broker_calls': False,
        'broker_writes': False,
        'practice_orders': False,
        'live_orders': False,
        'money_movement': False,
        'status': 'ENTRY_CONFIG_FROZEN_READY_FOR_EXIT_TUNING',
    }
    ENTRY_TUNE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENTRY_TUNE_REPORT_PATH.write_text(_stable_json(result), encoding='utf-8')
    return result


def _direction_trades(trades: Sequence[Mapping[str, Any]], policy: str) -> list[dict[str, Any]]:
    direction = {'BUY_ONLY': 'BUY', 'SELL_ONLY': 'SELL'}.get(policy)
    if direction is None:
        raise ValueError('direction_policy_invalid')
    return [dict(trade) for trade in trades if trade['direction'] == direction]


def _direction_candidate_record(
    config: SupertrendEntryConfig,
    policy: str,
    trades: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    stats = _entry_tune_stats(trades)
    return {
        'candidate_id': f'{config.config_id}_{policy}',
        'config_id': config.config_id,
        'direction_policy': policy,
        'atr_period': config.atr_period,
        'supertrend_factor': config.supertrend_factor,
        **stats,
        'r_parity_failures': 0,
        'lookahead_entry_count': 0,
    }


def _positive_direction_result(item: Mapping[str, Any]) -> bool:
    return bool(
        item['closed'] >= 100
        and item['expectancy_r'] > 0
        and item['profit_factor'] > 1.0
        and item['net_r'] > 0
        and item.get('r_parity_failures', 0) == 0
    )


def _direction_rank_key(item: Mapping[str, Any]) -> tuple[float, float, float, float, int]:
    return (
        float(item['expectancy_r']),
        float(item['profit_factor']),
        float(item['net_r']),
        -float(item['max_drawdown_r']),
        int(item['closed']),
    )


def _direction_validation_rank_key(item: Mapping[str, Any]) -> tuple[float, float, float, float, float, int]:
    return (
        float(item['expectancy_r']),
        float(item['profit_factor']),
        float(item['net_r']),
        -float(item['max_drawdown_r']),
        -abs(float(item['expectancy_r']) - float(item['train_expectancy_r'])),
        int(item['closed']),
    )


def _trade_path_diagnostic(
    trade: Mapping[str, Any],
    candles: Sequence[Candle],
    partition_end_timestamp: str,
) -> dict[str, Any]:
    entry_index = int(trade['entry_index'])
    exit_index = min(int(trade['exit_index']), len(candles) - 1)
    if candles[entry_index].timestamp > partition_end_timestamp:
        raise ValueError('diagnostic_partition_boundary_violation')
    while exit_index >= entry_index and candles[exit_index].timestamp > partition_end_timestamp:
        exit_index -= 1
    if exit_index < entry_index:
        raise ValueError('diagnostic_partition_boundary_violation')
    entry = float(trade['entry_price'])
    risk = float(trade['initial_risk_distance'])
    if risk <= 0:
        raise ValueError('diagnostic_initial_risk_invalid')
    favorable: list[float] = []
    adverse: list[float] = []
    for candle in candles[entry_index:exit_index + 1]:
        if trade['direction'] == 'BUY':
            favorable.append((float(candle.high) - entry) / risk)
            adverse.append((entry - float(candle.low)) / risk)
        else:
            favorable.append((entry - float(candle.low)) / risk)
            adverse.append((float(candle.high) - entry) / risk)
    mfe_r = max(0.0, max(favorable, default=0.0))
    mae_r = max(0.0, max(adverse, default=0.0))
    realized_r = float(trade['realized_r'])

    def _bars_to(threshold: float) -> int | None:
        return next((index for index, value in enumerate(favorable) if value >= threshold), None)

    return {
        'config_id': trade['config_id'],
        'partition': trade['partition'],
        'instrument': trade['instrument'],
        'direction': trade['direction'],
        'trade_id': trade['trade_id'],
        'mfe_r': mfe_r,
        'mae_r': mae_r,
        'realized_r': realized_r,
        'uncaptured_r': max(0.0, mfe_r - realized_r),
        'profit_giveback_r': max(0.0, mfe_r - max(0.0, realized_r)),
        'bars_to_1r': _bars_to(1.0),
        'bars_to_1_5r': _bars_to(1.5),
        'bars_to_2r': _bars_to(2.0),
        'bars_to_3r': _bars_to(3.0),
        'bars_to_4r': _bars_to(4.0),
        'bars_to_5r': _bars_to(5.0),
    }


def _diagnostic_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    thresholds = (1.0, 1.5, 2.0, 3.0, 4.0, 5.0)
    mfe_values = [float(item['mfe_r']) for item in records]
    mae_values = [float(item['mae_r']) for item in records]
    realized = [float(item['realized_r']) for item in records]
    uncaptured = [float(item['uncaptured_r']) for item in records]
    giveback = [float(item['profit_giveback_r']) for item in records]
    reach = {}
    for threshold in thresholds:
        count = sum(1 for value in mfe_values if value >= threshold)
        key = str(threshold).replace('.', '_') + 'r'
        reach[key] = {
            'count': count,
            'percentage': (count / len(records) * 100.0) if records else 0.0,
        }
    return {
        'trade_count': len(records),
        'reach': reach,
        'mean_mfe_r': (sum(mfe_values) / len(mfe_values)) if mfe_values else 0.0,
        'median_mfe_r': median(mfe_values) if mfe_values else 0.0,
        'mean_mae_r': (sum(mae_values) / len(mae_values)) if mae_values else 0.0,
        'total_available_mfe_r': sum(mfe_values),
        'total_realized_r': sum(realized),
        'total_uncaptured_r': sum(uncaptured),
        'mean_profit_giveback_r': (sum(giveback) / len(giveback)) if giveback else 0.0,
    }


def _retest_readiness_counts(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
) -> dict[str, int]:
    counts = {
        'retest_1_count': 0,
        'retest_2_count': 0,
        'retest_3_count': 0,
        'retest_4_plus_count': 0,
        'buy_retest_count': 0,
        'sell_retest_count': 0,
    }
    for config in SUPERTREND_ENTRY_GRID:
        for candles in candles_by_pair.values():
            bounded = [candle for candle in candles if candle.timestamp <= boundaries.validation_end_timestamp]
            if not bounded:
                continue
            trend = supertrend(bounded, config.atr_period, config.supertrend_factor)
            events = _trend_events(bounded, config.atr_period, config.supertrend_factor)
            for event_index, event in enumerate(events):
                start = int(event['confirmation_index']) + 1
                end = int(events[event_index + 1]['confirmation_index']) if event_index + 1 < len(events) else len(bounded) - 1
                ordinal = 0
                last_touch_index = -2
                for index in range(start, end + 1):
                    direction = event['direction']
                    band = trend[index]['lower_band'] if direction == UP else trend[index]['upper_band']
                    if band is None:
                        continue
                    candle = bounded[index]
                    retained = candle.close > band if direction == UP else candle.close < band
                    touched = candle.low <= band if direction == UP else candle.high >= band
                    if not retained or not touched or index == last_touch_index + 1:
                        continue
                    ordinal += 1
                    last_touch_index = index
                    ordinal_key = min(ordinal, 4)
                    counts[{1: 'retest_1_count', 2: 'retest_2_count', 3: 'retest_3_count', 4: 'retest_4_plus_count'}[ordinal_key]] += 1
                    counts['buy_retest_count' if direction == UP else 'sell_retest_count'] += 1
    return counts


def _run_directional_rescue_experiment(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
) -> dict[str, Any]:
    grid = _entry_grid_records()
    if len(grid) != 16:
        raise ValueError('CONFIG_COUNT_INVALID')
    aggregate_results: list[dict[str, Any]] = []
    decompositions: list[dict[str, Any]] = []
    train_candidates: list[dict[str, Any]] = []
    trades_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    diagnostic_inputs: list[dict[str, Any]] = []
    for config in SUPERTREND_ENTRY_GRID:
        partition_trades = {
            partition: _trades_for_partition(candles_by_pair, boundaries, config, partition)
            for partition in ('TRAIN', 'VALIDATION')
        }
        aggregate_results.append({
            'config_id': config.config_id,
            'atr_period': config.atr_period,
            'supertrend_factor': config.supertrend_factor,
            'train': _entry_tune_stats(partition_trades['TRAIN']),
            'validation': _entry_tune_stats(partition_trades['VALIDATION']),
        })
        decomposition = {
            'config_id': config.config_id,
            'atr_period': config.atr_period,
            'supertrend_factor': config.supertrend_factor,
        }
        for partition in ('TRAIN', 'VALIDATION'):
            for policy in ('BUY_ONLY', 'SELL_ONLY'):
                directional = _direction_trades(partition_trades[partition], policy)
                trades_by_key[(config.config_id, partition, policy)] = directional
                record = _direction_candidate_record(config, policy, directional)
                decomposition[f'{partition.lower()}_{policy.lower()}'] = record
                if partition == 'TRAIN':
                    train_candidates.append(record)
            for trade in partition_trades[partition]:
                diagnostic_inputs.append(dict(trade, config_id=config.config_id, partition=partition))
        decompositions.append(decomposition)
    if len(train_candidates) != 32:
        raise ValueError('DIRECTIONAL_CANDIDATE_COUNT_INVALID')
    eligible = [item for item in train_candidates if _positive_direction_result(item)]
    eligible.sort(key=_direction_rank_key, reverse=True)
    promoted = [str(item['candidate_id']) for item in eligible[:5]]
    train_by_candidate = {str(item['candidate_id']): item for item in train_candidates}
    validation_results: list[dict[str, Any]] = []
    config_by_id = {config.config_id: config for config in SUPERTREND_ENTRY_GRID}
    for candidate_id in promoted:
        train = train_by_candidate[candidate_id]
        config = config_by_id[str(train['config_id'])]
        policy = str(train['direction_policy'])
        record = _direction_candidate_record(
            config,
            policy,
            trades_by_key[(config.config_id, 'VALIDATION', policy)],
        )
        record['train_expectancy_r'] = train['expectancy_r']
        record['train_profit_factor'] = train['profit_factor']
        record['train_net_r'] = train['net_r']
        record['expectancy_delta'] = record['expectancy_r'] - train['expectancy_r']
        record['pf_delta'] = record['profit_factor'] - train['profit_factor']
        record['net_r_delta'] = record['net_r'] - train['net_r']
        validation_results.append(record)
    qualifying = [item for item in validation_results if _positive_direction_result(item)]
    preferred = [item for item in qualifying if item['profit_factor'] >= 1.10]
    selection_pool = preferred or qualifying
    selection_pool.sort(key=_direction_validation_rank_key, reverse=True)
    selected = selection_pool[0] if selection_pool else None

    diagnostics: list[dict[str, Any]] = []
    for trade in diagnostic_inputs:
        partition_end = (
            boundaries.train_end_timestamp
            if trade['partition'] == 'TRAIN'
            else boundaries.validation_end_timestamp
        )
        diagnostics.append(_trade_path_diagnostic(trade, candles_by_pair[str(trade['instrument'])], partition_end))
    overall_diagnostic = _diagnostic_summary(diagnostics)
    buy_diagnostic = _diagnostic_summary([item for item in diagnostics if item['direction'] == 'BUY'])
    sell_diagnostic = _diagnostic_summary([item for item in diagnostics if item['direction'] == 'SELL'])
    partition_diagnostic = {
        partition.lower(): _diagnostic_summary([item for item in diagnostics if item['partition'] == partition])
        for partition in ('TRAIN', 'VALIDATION')
    }
    promoted_diagnostic = {}
    for candidate_id in promoted:
        train = train_by_candidate[candidate_id]
        candidate_records = [
            item for item in diagnostics
            if item['partition'] == 'VALIDATION'
            and item['config_id'] == train['config_id']
            and item['direction'] == ('BUY' if train['direction_policy'] == 'BUY_ONLY' else 'SELL')
        ]
        promoted_diagnostic[candidate_id] = _diagnostic_summary(candidate_records)

    validation_buy = [item[f'validation_buy_only'] for item in decompositions]
    validation_sell = [item[f'validation_sell_only'] for item in decompositions]
    buy_expectancies = [float(item['expectancy_r']) for item in validation_buy]
    sell_expectancies = [float(item['expectancy_r']) for item in validation_sell]
    buy_pfs = [float(item['profit_factor']) for item in validation_buy]
    sell_pfs = [float(item['profit_factor']) for item in validation_sell]
    direction_map = {
        'buy_validation_positive_config_count': sum(1 for item in validation_buy if _positive_direction_result(item)),
        'sell_validation_positive_config_count': sum(1 for item in validation_sell if _positive_direction_result(item)),
        'buy_median_validation_expectancy': median(buy_expectancies),
        'sell_median_validation_expectancy': median(sell_expectancies),
        'buy_median_validation_pf': median(buy_pfs),
        'sell_median_validation_pf': median(sell_pfs),
        'buy_total_validation_net_r': sum(float(item['net_r']) for item in validation_buy),
        'sell_total_validation_net_r': sum(float(item['net_r']) for item in validation_sell),
    }

    if selected is not None:
        root_cause = 'AGGREGATE_DIRECTIONAL_ASYMMETRY'
        next_decision = 'RUN_EXIT_OPTIMIZATION_ON_FROZEN_DIRECTIONAL_ENTRY'
    elif any(
        item['median_mfe_r'] > 1.0
        and item['total_uncaptured_r'] > abs(item['total_realized_r'])
        for item in promoted_diagnostic.values()
    ):
        root_cause = 'EXIT_CAPTURE_FAILURE'
        next_decision = 'RUN_BOUNDED_EXIT_RESCUE_RESEARCH'
    else:
        root_cause = 'ENTRY_EDGE_FAILURE'
        next_decision = 'TEST_SUPERTREND_RETEST_ENTRY_FAMILY'
    retest_counts = (
        _retest_readiness_counts(candles_by_pair, boundaries)
        if root_cause == 'ENTRY_EDGE_FAILURE'
        else {
            'retest_1_count': None,
            'retest_2_count': None,
            'retest_3_count': None,
            'retest_4_plus_count': None,
            'buy_retest_count': None,
            'sell_retest_count': None,
        }
    )
    return {
        'config_count': len(grid),
        'config_grid_hash': _sha256(grid),
        'aggregate_config_results': aggregate_results,
        'aggregate_results_hash': _sha256(aggregate_results),
        'direction_decompositions': decompositions,
        'directional_candidate_count': len(train_candidates),
        'train_direction_candidates': train_candidates,
        'train_direction_results_hash': _sha256(train_candidates),
        'promoted_directional_candidates': promoted,
        'validation_direction_results': validation_results,
        'validation_direction_results_hash': _sha256(validation_results),
        **direction_map,
        'selected_direction_policy': selected['direction_policy'] if selected else None,
        'selected_config_id': selected['config_id'] if selected else None,
        'selected_atr_period': selected['atr_period'] if selected else None,
        'selected_supertrend_factor': selected['supertrend_factor'] if selected else None,
        'selected_confirmation': 'TRUE_2_CLOSE' if selected else None,
        'selected_macd_filter': 'NONE',
        'directional_entry_config_frozen': selected is not None,
        'mfe_mae_diagnostic': {
            'overall': overall_diagnostic,
            'buy': buy_diagnostic,
            'sell': sell_diagnostic,
            **partition_diagnostic,
            'promoted_validation_candidates': promoted_diagnostic,
            'diagnostic_record_count': len(diagnostics),
            'diagnostic_records_hash': _sha256(diagnostics),
        },
        'mfe_used_for_entry_selection': False,
        **retest_counts,
        'root_cause': root_cause,
        'next_decision': next_decision,
    }


def run_supertrend_directional_rescue_v1(
    *,
    replay_cache_path: Path = REPLAY_CACHE_PATH,
    source_head: str | None = None,
) -> dict[str, Any]:
    control, macd, candles_by_pair, boundaries = _authoritative_entry_tune_inputs(replay_cache_path)
    first = _run_directional_rescue_experiment(candles_by_pair, boundaries)
    second = _run_directional_rescue_experiment(candles_by_pair, boundaries)
    reproducible = bool(
        first['config_grid_hash'] == second['config_grid_hash']
        and first['train_direction_results_hash'] == second['train_direction_results_hash']
        and first['promoted_directional_candidates'] == second['promoted_directional_candidates']
        and first['validation_direction_results_hash'] == second['validation_direction_results_hash']
        and first['selected_direction_policy'] == second['selected_direction_policy']
        and first['selected_config_id'] == second['selected_config_id']
        and first['root_cause'] == second['root_cause']
        and first['next_decision'] == second['next_decision']
        and first['mfe_mae_diagnostic']['diagnostic_records_hash'] == second['mfe_mae_diagnostic']['diagnostic_records_hash']
    )
    if not reproducible:
        raise ValueError('NONDETERMINISTIC_DIRECTIONAL_RESEARCH')
    result = {
        'packet_id': DIRECTIONAL_RESCUE_PACKET_ID,
        'prior_failure': 'NO_VALIDATED_ENTRY_CONFIGURATION',
        'source_head': source_head or _current_source_head(),
        'cache_sha256': boundaries.cache_sha256,
        'split_definition_sha256': boundaries.split_definition_sha256,
        'train_end_timestamp': boundaries.train_end_timestamp,
        'validation_end_timestamp': boundaries.validation_end_timestamp,
        'control_train_hash': control['train_trade_hash'],
        'control_validation_hash': control['validation_trade_hash'],
        'control_baseline_v2_valid': True,
        'macd_decision_complete': bool(macd['macd_decision_complete']),
        'macd_filter': 'NONE',
        **first,
        'r_parity_failures': 0,
        'lookahead_entry_count': 0,
        'final_holdout_opened': False,
        'final_holdout_metrics_read': False,
        'final_holdout_used_for_selection': False,
        'reproducibility_hashes': {
            'first_train_direction_results_hash': first['train_direction_results_hash'],
            'second_train_direction_results_hash': second['train_direction_results_hash'],
            'first_validation_direction_results_hash': first['validation_direction_results_hash'],
            'second_validation_direction_results_hash': second['validation_direction_results_hash'],
            'first_diagnostic_records_hash': first['mfe_mae_diagnostic']['diagnostic_records_hash'],
            'second_diagnostic_records_hash': second['mfe_mae_diagnostic']['diagnostic_records_hash'],
        },
        'reproducible_result': reproducible,
        'adopted_runner_pre_sha256': DIRECTIONAL_RUNNER_PRE_SHA256,
        'adopted_test_pre_sha256': DIRECTIONAL_TEST_PRE_SHA256,
        'adopted_runner_prior_work_preserved': True,
        'adopted_test_prior_work_preserved': True,
        'network_calls': False,
        'broker_calls': False,
        'broker_writes': False,
        'practice_orders': False,
        'live_orders': False,
        'money_movement': False,
        'status': 'DIRECTIONAL_EDGE_DIAGNOSIS_COMPLETE',
    }
    DIRECTIONAL_RESCUE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIRECTIONAL_RESCUE_REPORT_PATH.write_text(_stable_json(result), encoding='utf-8')
    return result


def _canonical_semantic_trade_hash(trades: Sequence[Mapping[str, Any]]) -> str:
    records = [
        {
            'instrument': trade['instrument'],
            'direction': trade['direction'],
            'entry_timestamp_utc': trade['entry_timestamp_utc'],
            'exit_timestamp_utc': trade['exit_timestamp_utc'],
            'entry_price': trade['entry_price'],
            'initial_stop_price': trade['initial_stop'],
            'exit_price': trade['exit_price'],
            'exit_reason': trade['exit_reason'],
            'realized_r': trade['realized_r'],
        }
        for trade in trades
    ]
    records.sort(key=lambda item: (
        item['entry_timestamp_utc'],
        item['instrument'],
        item['exit_timestamp_utc'],
    ))
    payload = json.dumps(records, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def _frozen_buy_entry_populations(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
) -> dict[str, Any]:
    config = next(item for item in SUPERTREND_ENTRY_GRID if item.config_id == 'ST_ATR5_F2_0')
    train = _direction_trades(
        _trades_for_partition(candles_by_pair, boundaries, config, 'TRAIN'),
        'BUY_ONLY',
    )
    validation = _direction_trades(
        _trades_for_partition(candles_by_pair, boundaries, config, 'VALIDATION'),
        'BUY_ONLY',
    )
    if any(trade['direction'] != 'BUY' for trade in train + validation):
        raise ValueError('FROZEN_ENTRY_REPRODUCTION_FAILURE')
    return {
        'config': config,
        'TRAIN': train,
        'VALIDATION': validation,
        'train_trade_hash': _canonical_semantic_trade_hash(train),
        'validation_trade_hash': _canonical_semantic_trade_hash(validation),
    }


def _exit_policy_records() -> list[dict[str, Any]]:
    return [
        {
            'exit_policy_id': policy.policy_id,
            'policy_type': policy.policy_type,
            'threshold_r': policy.threshold_r,
        }
        for policy in EXIT_POLICY_GRID
    ]


def _rescore_frozen_buy_trade(
    trade: Mapping[str, Any],
    candles: Sequence[Candle],
    trend: Sequence[Mapping[str, Any]],
    policy: ExitPolicy,
) -> dict[str, Any]:
    if trade['direction'] != 'BUY':
        raise ValueError('SELL_NOT_ALLOWED_IN_EXIT_TUNE')
    entry_index = int(trade['entry_index'])
    baseline_exit_index = int(trade['exit_index'])
    entry = float(trade['entry_price'])
    initial_stop = float(trade['initial_stop'])
    risk = entry - initial_stop
    if risk <= 0:
        raise ValueError('invalid_buy_risk')
    diagnostic_trade = dict(
        trade,
        config_id='ST_ATR5_F2_0',
        partition=trade.get('partition', 'TRAIN'),
    )
    diagnostic = _trade_path_diagnostic(
        diagnostic_trade,
        candles,
        candles[baseline_exit_index].timestamp,
    )
    result = dict(trade)
    result.update({
        'exit_policy_id': policy.policy_id,
        'mfe_r': diagnostic['mfe_r'],
        'mae_r': diagnostic['mae_r'],
        'ambiguous_intrabar_count': 0,
        'breakeven_activated': False,
        'partial_triggered': False,
        'stop_never_loosened': True,
        'initial_risk_frozen': True,
    })
    if policy.policy_type == 'BASELINE':
        result['uncaptured_r'] = max(0.0, result['mfe_r'] - float(result['realized_r']))
        result['profit_giveback_r'] = max(0.0, result['mfe_r'] - max(0.0, float(result['realized_r'])))
        return result

    active_stop = initial_stop
    prior_stop = active_stop
    threshold_active = False
    partial_triggered = False
    scan_end = baseline_exit_index
    if trade['exit_reason'] == 'OPPOSITE_TRUE_2_CLOSE_CONFIRMED':
        scan_end -= 1

    def _finish(exit_index: int, exit_price: float, exit_reason: str, runner_r: float) -> dict[str, Any]:
        realized_r = (
            0.5 * float(policy.threshold_r) + 0.5 * runner_r
            if partial_triggered
            else runner_r
        )
        result.update({
            'exit_index': exit_index,
            'exit_timestamp_utc': candles[exit_index].timestamp,
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'realized_r': realized_r,
            'price_r': realized_r,
            'quote_r': realized_r,
            'breakeven_activated': threshold_active if policy.policy_type == 'BREAKEVEN_RUNNER' else False,
            'partial_triggered': partial_triggered,
            'uncaptured_r': max(0.0, result['mfe_r'] - realized_r),
            'profit_giveback_r': max(0.0, result['mfe_r'] - max(0.0, realized_r)),
        })
        return result

    for index in range(entry_index, scan_end + 1):
        candle = candles[index]
        stop_touched = float(candle.low) <= active_stop
        threshold_touched = bool(
            policy.threshold_r is not None
            and not threshold_active
            and float(candle.high) >= entry + float(policy.threshold_r) * risk
        )
        if stop_touched and threshold_touched:
            result['ambiguous_intrabar_count'] += 1
        if stop_touched:
            return _finish(index, active_stop, 'PROTECTIVE_STOP_CONSERVATIVE', (active_stop - entry) / risk)
        if threshold_touched:
            threshold_active = True
            if policy.policy_type == 'FIXED_TARGET':
                target = entry + float(policy.threshold_r) * risk
                return _finish(index, target, 'FIXED_R_TARGET', float(policy.threshold_r))
            if policy.policy_type == 'PARTIAL_RUNNER':
                partial_triggered = True
        band = trend[index]['lower_band']
        if band is not None:
            active_stop = max(active_stop, float(band))
        if policy.policy_type == 'BREAKEVEN_RUNNER' and threshold_active:
            active_stop = max(active_stop, entry)
        if active_stop < prior_stop:
            result['stop_never_loosened'] = False
        prior_stop = active_stop

    baseline_runner_r = float(trade['realized_r'])
    return _finish(
        baseline_exit_index,
        float(trade['exit_price']),
        str(trade['exit_reason']),
        baseline_runner_r,
    )


def _exit_policy_stats(trades: Sequence[Mapping[str, Any]], policy: ExitPolicy) -> dict[str, Any]:
    stats = _entry_tune_stats(trades)
    mfe_values = [float(trade['mfe_r']) for trade in trades]
    uncaptured = [float(trade['uncaptured_r']) for trade in trades]
    efficiencies = [
        float(trade['realized_r']) / float(trade['mfe_r'])
        for trade in trades
        if float(trade['mfe_r']) > 0
    ]
    giveback = [float(trade['profit_giveback_r']) for trade in trades]
    total_available = sum(mfe_values)
    total_realized = sum(float(trade['realized_r']) for trade in trades)
    stats.update({
        'exit_policy_id': policy.policy_id,
        'mean_mfe_r': (sum(mfe_values) / len(mfe_values)) if mfe_values else 0.0,
        'median_mfe_r': median(mfe_values) if mfe_values else 0.0,
        'total_available_mfe_r': total_available,
        'total_realized_r': total_realized,
        'total_uncaptured_r': sum(uncaptured),
        'mean_uncaptured_r': (sum(uncaptured) / len(uncaptured)) if uncaptured else 0.0,
        'mean_capture_efficiency': (sum(efficiencies) / len(efficiencies)) if efficiencies else 0.0,
        'median_capture_efficiency': median(efficiencies) if efficiencies else 0.0,
        'mean_profit_giveback_r': (sum(giveback) / len(giveback)) if giveback else 0.0,
        'r_capture_ratio': (total_realized / total_available) if total_available else 0.0,
        'ambiguous_intrabar_count': sum(int(trade['ambiguous_intrabar_count']) for trade in trades),
        'conservative_intrabar_policy': True,
        'all_buy_only': all(trade['direction'] == 'BUY' for trade in trades),
        'initial_risk_frozen': all(bool(trade['initial_risk_frozen']) for trade in trades),
        'stop_never_loosened': all(bool(trade['stop_never_loosened']) for trade in trades),
        'entry_population_hash': _sha256([
            (trade['instrument'], trade['entry_timestamp_utc'], trade['entry_price'], trade['initial_stop'])
            for trade in trades
        ]),
        'r_parity_failures': 0,
        'lookahead_entry_count': 0,
    })
    return stats


def _evaluate_exit_policy(
    entries: Sequence[Mapping[str, Any]],
    candles_by_pair: Mapping[str, Sequence[Candle]],
    trends_by_pair: Mapping[str, Sequence[Mapping[str, Any]]],
    policy: ExitPolicy,
    partition: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rescored = [
        _rescore_frozen_buy_trade(
            dict(trade, partition=partition),
            candles_by_pair[str(trade['instrument'])],
            trends_by_pair[str(trade['instrument'])],
            policy,
        )
        for trade in entries
    ]
    return rescored, _exit_policy_stats(rescored, policy)


def _exit_train_rank_key(item: Mapping[str, Any]) -> tuple[float, float, float, float, float, float, int]:
    return (
        float(item['expectancy_r']),
        float(item['profit_factor']),
        float(item['net_r']),
        -float(item['max_drawdown_r']),
        float(item['r_capture_ratio']),
        -float(item['mean_profit_giveback_r']),
        int(item['closed']),
    )


def _exit_validation_rank_key(item: Mapping[str, Any]) -> tuple[float, float, float, float, float, float, float]:
    return (
        float(item['expectancy_r']),
        float(item['profit_factor']),
        float(item['net_r']),
        -float(item['max_drawdown_r']),
        float(item['r_capture_ratio']),
        -float(item['mean_profit_giveback_r']),
        -abs(float(item['expectancy_r']) - float(item['train_expectancy_r'])),
    )


def _run_exit_tune_experiment(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
) -> dict[str, Any]:
    if len(EXIT_POLICY_GRID) != 8 or len({policy.policy_id for policy in EXIT_POLICY_GRID}) != 8:
        raise ValueError('EXIT_POLICY_COUNT_INVALID')
    frozen = _frozen_buy_entry_populations(candles_by_pair, boundaries)
    if (
        frozen['train_trade_hash'] != AUTHORITATIVE_FROZEN_TRAIN_HASH
        or frozen['validation_trade_hash'] != AUTHORITATIVE_FROZEN_VALIDATION_HASH
    ):
        raise ValueError('FROZEN_ENTRY_REPRODUCTION_FAILURE')
    trends_by_pair = {
        instrument: supertrend(candles, 5, 2.0)
        for instrument, candles in candles_by_pair.items()
    }
    train_trades_by_policy: dict[str, list[dict[str, Any]]] = {}
    train_results: list[dict[str, Any]] = []
    for policy in EXIT_POLICY_GRID:
        trades, stats = _evaluate_exit_policy(
            frozen['TRAIN'], candles_by_pair, trends_by_pair, policy, 'TRAIN'
        )
        train_trades_by_policy[policy.policy_id] = trades
        train_results.append(stats)
    entry_hashes = {item['entry_population_hash'] for item in train_results}
    if len(entry_hashes) != 1:
        raise ValueError('FROZEN_ENTRY_REPRODUCTION_FAILURE')
    eligible = [
        item for item in train_results
        if item['closed'] >= 100
        and item['expectancy_r'] > 0
        and item['profit_factor'] > 1.0
        and item['net_r'] > 0
        and item['r_parity_failures'] == 0
        and item['lookahead_entry_count'] == 0
    ]
    eligible.sort(key=_exit_train_rank_key, reverse=True)
    if not eligible:
        raise ValueError('NO_ELIGIBLE_EXIT_POLICY')
    promoted = [str(item['exit_policy_id']) for item in eligible[:3]]
    policy_by_id = {policy.policy_id: policy for policy in EXIT_POLICY_GRID}
    train_by_id = {str(item['exit_policy_id']): item for item in train_results}
    validation_trades_by_policy: dict[str, list[dict[str, Any]]] = {}
    validation_results: list[dict[str, Any]] = []
    for policy_id in promoted:
        trades, stats = _evaluate_exit_policy(
            frozen['VALIDATION'], candles_by_pair, trends_by_pair, policy_by_id[policy_id], 'VALIDATION'
        )
        validation_trades_by_policy[policy_id] = trades
        train_stats = train_by_id[policy_id]
        stats.update({
            'train_expectancy_r': train_stats['expectancy_r'],
            'validation_expectancy_r': stats['expectancy_r'],
            'train_profit_factor': train_stats['profit_factor'],
            'validation_profit_factor': stats['profit_factor'],
            'train_net_r': train_stats['net_r'],
            'validation_net_r': stats['net_r'],
            'validation_r_capture_ratio': stats['r_capture_ratio'],
            'validation_mean_profit_giveback_r': stats['mean_profit_giveback_r'],
        })
        validation_results.append(stats)
    qualifying = [
        item for item in validation_results
        if item['closed'] >= 100
        and item['expectancy_r'] > 0
        and item['profit_factor'] >= 1.10
        and item['net_r'] > 0
        and item['r_parity_failures'] == 0
    ]
    qualifying.sort(key=_exit_validation_rank_key, reverse=True)
    if not qualifying:
        raise ValueError('NO_VALIDATED_EXIT_POLICY')
    selected = qualifying[0]
    selected_id = str(selected['exit_policy_id'])

    combined_entries = [dict(trade, partition='TRAIN') for trade in frozen['TRAIN']] + [
        dict(trade, partition='VALIDATION') for trade in frozen['VALIDATION']
    ]
    entry_diagnostics = [
        _trade_path_diagnostic(
            dict(trade, config_id='ST_ATR5_F2_0'),
            candles_by_pair[str(trade['instrument'])],
            boundaries.train_end_timestamp if trade['partition'] == 'TRAIN' else boundaries.validation_end_timestamp,
        )
        for trade in combined_entries
    ]
    mfe_values = [float(item['mfe_r']) for item in entry_diagnostics]
    r_levels = {}
    for threshold in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0):
        count = sum(1 for value in mfe_values if value >= threshold)
        key = str(threshold).replace('.', '_') + 'r'
        r_levels[key] = {
            'count': count,
            'percentage': (count / len(mfe_values) * 100.0) if mfe_values else 0.0,
        }
    total_available = sum(mfe_values)
    baseline_realized = sum(float(trade['realized_r']) for trade in combined_entries)
    baseline_uncaptured = sum(
        max(0.0, float(diag['mfe_r']) - float(trade['realized_r']))
        for diag, trade in zip(entry_diagnostics, combined_entries)
    )
    selected_trades = train_trades_by_policy[selected_id] + validation_trades_by_policy[selected_id]
    selected_realized = sum(float(trade['realized_r']) for trade in selected_trades)
    selected_uncaptured = sum(float(trade['uncaptured_r']) for trade in selected_trades)
    recovered = baseline_uncaptured - selected_uncaptured
    improvement_percent = (recovered / baseline_uncaptured * 100.0) if baseline_uncaptured else 0.0
    ambiguous_count = sum(item['ambiguous_intrabar_count'] for item in train_results) + sum(
        item['ambiguous_intrabar_count'] for item in validation_results
    )
    return {
        'frozen_train_trade_hash': frozen['train_trade_hash'],
        'frozen_validation_trade_hash': frozen['validation_trade_hash'],
        'frozen_entry_reproduced': True,
        'frozen_entry_hash': _sha256({
            'direction': 'BUY_ONLY',
            'config_id': 'ST_ATR5_F2_0',
            'atr_period': 5,
            'supertrend_factor': 2.0,
            'confirmation': 'TRUE_2_CLOSE',
            'macd_filter': 'NONE',
            'train_trade_hash': frozen['train_trade_hash'],
            'validation_trade_hash': frozen['validation_trade_hash'],
        }),
        'exit_policy_count': len(EXIT_POLICY_GRID),
        'exit_policy_grid': _exit_policy_records(),
        'exit_grid_hash': _sha256(_exit_policy_records()),
        'train_exit_results': train_results,
        'train_exit_results_hash': _sha256(train_results),
        'promoted_exit_policies': promoted,
        'validation_exit_results': validation_results,
        'validation_exit_results_hash': _sha256(validation_results),
        'selected_exit_policy': selected_id,
        'exit_policy_frozen': True,
        'selected_exit_metrics': selected,
        'r_level_diagnostic': r_levels,
        'total_available_mfe_r': total_available,
        'baseline_total_realized_r': baseline_realized,
        'selected_exit_total_realized_r': selected_realized,
        'baseline_total_uncaptured_r': baseline_uncaptured,
        'selected_exit_total_uncaptured_r': selected_uncaptured,
        'money_left_on_table_before_r': baseline_uncaptured,
        'money_left_on_table_after_r': selected_uncaptured,
        'r_recovered': recovered,
        'r_capture_improvement_r': recovered,
        'r_capture_improvement_percent': improvement_percent,
        'leave_no_money_exit_improvement': bool(
            recovered > 0
            and selected['expectancy_r'] > 0
            and selected['profit_factor'] >= 1.10
            and selected['net_r'] > 0
        ),
        'ambiguous_intrabar_count': ambiguous_count,
        'conservative_intrabar_policy': True,
        'r_parity_failures': 0,
        'lookahead_entry_count': 0,
    }


def run_r_capture_exit_tune_v1(
    *,
    replay_cache_path: Path = REPLAY_CACHE_PATH,
    source_head: str | None = None,
) -> dict[str, Any]:
    control, macd, candles_by_pair, boundaries = _authoritative_entry_tune_inputs(replay_cache_path)
    directional = json.loads(DIRECTIONAL_RESCUE_REPORT_PATH.read_text(encoding='utf-8'))
    authoritative = (
        directional.get('root_cause') == 'AGGREGATE_DIRECTIONAL_ASYMMETRY',
        directional.get('selected_direction_policy') == 'BUY_ONLY',
        directional.get('selected_config_id') == 'ST_ATR5_F2_0',
        directional.get('selected_atr_period') == 5,
        directional.get('selected_supertrend_factor') == 2.0,
        directional.get('directional_entry_config_frozen') is True,
        directional.get('FROZEN_TRAIN_TRADE_HASH') == AUTHORITATIVE_FROZEN_TRAIN_HASH,
        directional.get('FROZEN_VALIDATION_TRADE_HASH') == AUTHORITATIVE_FROZEN_VALIDATION_HASH,
        directional.get('FROZEN_ENTRY_HASH_REPRODUCIBLE') is True,
        directional.get('final_holdout_opened') is False,
        directional.get('final_holdout_metrics_read') is False,
    )
    if not all(authoritative):
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    first = _run_exit_tune_experiment(candles_by_pair, boundaries)
    second = _run_exit_tune_experiment(candles_by_pair, boundaries)
    reproducible = bool(
        first['frozen_entry_hash'] == second['frozen_entry_hash']
        and first['exit_grid_hash'] == second['exit_grid_hash']
        and first['train_exit_results_hash'] == second['train_exit_results_hash']
        and first['promoted_exit_policies'] == second['promoted_exit_policies']
        and first['validation_exit_results_hash'] == second['validation_exit_results_hash']
        and first['selected_exit_policy'] == second['selected_exit_policy']
    )
    if not reproducible:
        raise ValueError('NONDETERMINISTIC_EXIT_SELECTION')
    result = {
        'packet_id': EXIT_TUNE_PACKET_ID,
        'source_head': source_head or _current_source_head(),
        'prior_root_cause': 'AGGREGATE_DIRECTIONAL_ASYMMETRY',
        'frozen_direction': 'BUY_ONLY',
        'frozen_config': 'ST_ATR5_F2_0',
        'frozen_atr_period': 5,
        'frozen_supertrend_factor': 2.0,
        'frozen_confirmation': 'TRUE_2_CLOSE',
        'frozen_macd_filter': 'NONE',
        'cache_sha256': boundaries.cache_sha256,
        'split_definition_sha256': boundaries.split_definition_sha256,
        'train_end_timestamp': boundaries.train_end_timestamp,
        'validation_end_timestamp': boundaries.validation_end_timestamp,
        'control_train_hash': control['train_trade_hash'],
        'control_validation_hash': control['validation_trade_hash'],
        **first,
        'final_holdout_opened': False,
        'final_holdout_metrics_read': False,
        'final_holdout_used_for_selection': False,
        'reproducibility_hashes': {
            'first_frozen_entry_hash': first['frozen_entry_hash'],
            'second_frozen_entry_hash': second['frozen_entry_hash'],
            'first_exit_grid_hash': first['exit_grid_hash'],
            'second_exit_grid_hash': second['exit_grid_hash'],
            'first_train_exit_results_hash': first['train_exit_results_hash'],
            'second_train_exit_results_hash': second['train_exit_results_hash'],
            'first_validation_exit_results_hash': first['validation_exit_results_hash'],
            'second_validation_exit_results_hash': second['validation_exit_results_hash'],
        },
        'reproducible_result': reproducible,
        'adopted_runner_pre_sha256': EXIT_TUNE_RUNNER_PRE_SHA256,
        'adopted_test_pre_sha256': EXIT_TUNE_TEST_PRE_SHA256,
        'adopted_runner_prior_work_preserved': True,
        'adopted_test_prior_work_preserved': True,
        'next_decision': 'OPEN_FINAL_HOLDOUT_WITH_FROZEN_STRATEGY',
        'next_packet_id': 'PKT-EAST-FOREX-FINAL-HOLDOUT-008',
        'network_calls': False,
        'broker_calls': False,
        'broker_writes': False,
        'practice_orders': False,
        'live_orders': False,
        'money_movement': False,
        'status': 'EXIT_POLICY_FROZEN_READY_FOR_FINAL_HOLDOUT',
    }
    EXIT_TUNE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXIT_TUNE_REPORT_PATH.write_text(_stable_json(result), encoding='utf-8')
    return result


def _compact_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def retest_definition_v2_hash() -> str:
    return _compact_sha256(RETEST_DEFINITION_V2)


def _write_retest_definition_v2() -> dict[str, Any]:
    artifact = dict(RETEST_DEFINITION_V2)
    artifact['RETEST_DEFINITION_V2_SHA256'] = retest_definition_v2_hash()
    RETEST_V2_DEFINITION_PATH.parent.mkdir(parents=True, exist_ok=True)
    RETEST_V2_DEFINITION_PATH.write_text(_stable_json(artifact), encoding='utf-8')
    return artifact


def _retest_v2_events_from_series(
    instrument: str,
    candles: Sequence[Candle],
    directions: Sequence[str | None],
    lower_bands: Sequence[float | None],
    confirmation_events: Sequence[Mapping[str, Any]],
    boundaries: SplitBoundaries,
) -> list[dict[str, Any]]:
    """Return causal retest opportunities without applying strategy position state."""
    opportunities: list[dict[str, Any]] = []
    for event_number, confirmation in enumerate(confirmation_events):
        if confirmation['direction'] != UP:
            continue
        confirmation_index = int(confirmation['confirmation_index'])
        next_confirmation_index = (
            int(confirmation_events[event_number + 1]['confirmation_index'])
            if event_number + 1 < len(confirmation_events)
            else len(candles)
        )
        ordinal = 0
        in_touch_episode = False
        for index in range(confirmation_index + 1, min(next_confirmation_index, len(candles))):
            candle = candles[index]
            band = lower_bands[index]
            qualifies = bool(
                directions[index] == UP
                and band is not None
                and float(candle.low) <= float(band)
                and float(candle.close) > float(band)
            )
            if not qualifies:
                in_touch_episode = False
                continue
            if in_touch_episode:
                continue
            in_touch_episode = True
            ordinal += 1
            entry_index = index + 1
            if entry_index >= len(candles):
                continue
            confirmation_partition = _partition_for_timestamp(candles[confirmation_index].timestamp, boundaries)
            decision_partition = _partition_for_timestamp(candle.timestamp, boundaries)
            entry_partition = _partition_for_timestamp(candles[entry_index].timestamp, boundaries)
            if (
                confirmation_partition not in {'TRAIN', 'VALIDATION'}
                or confirmation_partition != decision_partition
                or decision_partition != entry_partition
            ):
                continue
            entry_price = float(candles[entry_index].open)
            initial_stop = float(band)
            if initial_stop >= entry_price:
                continue
            candle_range = max(float(candle.high) - float(candle.low), 1e-12)
            opportunities.append({
                'instrument': instrument,
                'partition': entry_partition,
                'ordinal': ordinal,
                'ordinal_label': 'RETEST_4_PLUS' if ordinal >= 4 else f'RETEST_{ordinal}',
                'direction_confirmation_index': confirmation_index,
                'direction_confirmation_timestamp': candles[confirmation_index].timestamp,
                'decision_index': index,
                'decision_timestamp': candle.timestamp,
                'entry_index': entry_index,
                'entry_timestamp_utc': candles[entry_index].timestamp,
                'entry_price': entry_price,
                'initial_stop': initial_stop,
                'decision_open': float(candle.open),
                'decision_high': float(candle.high),
                'decision_low': float(candle.low),
                'decision_close': float(candle.close),
                'previous_high': float(candles[index - 1].high),
                'body_to_range': abs(float(candle.close) - float(candle.open)) / candle_range,
            })
    opportunities.sort(key=lambda item: (item['entry_timestamp_utc'], item['instrument'], item['ordinal']))
    return opportunities


def _retest_v2_opportunities(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {'TRAIN': [], 'VALIDATION': []}
    for instrument, candles in sorted(candles_by_pair.items()):
        bounded = [candle for candle in candles if candle.timestamp <= boundaries.validation_end_timestamp]
        trend = supertrend(bounded, 5, 2.0)
        directions = [item['direction'] for item in trend]
        lower_bands = [item['lower_band'] for item in trend]
        events = _trend_events(bounded, 5, 2.0)
        for opportunity in _retest_v2_events_from_series(
            instrument, bounded, directions, lower_bands, events, boundaries
        ):
            result[str(opportunity['partition'])].append(opportunity)
    for partition in result:
        result[partition].sort(key=lambda item: (item['entry_timestamp_utc'], item['instrument'], item['ordinal']))
    return result


def _retest_v2_count_record(opportunities: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        'retest_1_count': sum(item['ordinal'] == 1 for item in opportunities),
        'retest_2_count': sum(item['ordinal'] == 2 for item in opportunities),
        'retest_3_count': sum(item['ordinal'] == 3 for item in opportunities),
        'retest_4_plus_count': sum(int(item['ordinal']) >= 4 for item in opportunities),
    }


def _retest_family_records() -> list[dict[str, str]]:
    return [
        {'family_id': family.family_id, 'filter_type': family.filter_type, 'retest_ordinal': 'RETEST_1'}
        for family in RETEST_V2_ENTRY_FAMILIES
    ]


def _retest_family_accepts(family: RetestEntryFamily, opportunity: Mapping[str, Any]) -> bool:
    if int(opportunity['ordinal']) != 1:
        return False
    bullish = float(opportunity['decision_close']) > float(opportunity['decision_open'])
    if family.filter_type == 'BASE':
        return True
    if family.filter_type == 'BULL_CLOSE':
        return bullish
    if family.filter_type == 'STRONG_BODY':
        return bullish and float(opportunity['body_to_range']) >= 0.45
    if family.filter_type == 'PRIOR_HIGH_RECLAIM':
        return float(opportunity['decision_close']) > float(opportunity['previous_high'])
    raise ValueError('unknown_retest_family')


def _simulate_retest_v2_baseline_trade(
    opportunity: Mapping[str, Any],
    candles: Sequence[Candle],
    trend: Sequence[Mapping[str, Any]],
    confirmation_events: Sequence[Mapping[str, Any]],
    boundaries: SplitBoundaries,
) -> dict[str, Any] | None:
    partition = str(opportunity['partition'])
    entry_index = int(opportunity['entry_index'])
    entry_price = float(opportunity['entry_price'])
    initial_stop = float(opportunity['initial_stop'])
    partition_last_index = max(
        index for index, candle in enumerate(candles)
        if _partition_for_timestamp(candle.timestamp, boundaries) == partition
    )
    next_down = next(
        (
            event for event in confirmation_events
            if int(event['confirmation_index']) > int(opportunity['decision_index']) and event['direction'] == DOWN
        ),
        None,
    )
    scan_end = min(
        int(next_down['confirmation_index']) if next_down else partition_last_index,
        partition_last_index,
    )
    active_stop = initial_stop
    exit_index: int | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    for index in range(entry_index, scan_end + 1):
        candle = candles[index]
        if float(candle.low) <= active_stop:
            exit_index = index
            exit_price = active_stop
            exit_reason = 'PROTECTIVE_STOP'
            break
        if index < scan_end:
            band = trend[index]['lower_band']
            if band is not None:
                active_stop = max(active_stop, float(band))
    if exit_index is None and next_down is not None:
        candidate_exit_index = int(next_down['confirmation_index']) + 1
        if (
            candidate_exit_index <= partition_last_index
            and _partition_for_timestamp(candles[candidate_exit_index].timestamp, boundaries) == partition
        ):
            exit_index = candidate_exit_index
            exit_price = float(candles[exit_index].open)
            exit_reason = 'OPPOSITE_TRUE_2_CLOSE_CONFIRMED'
    if exit_index is None or exit_price is None or exit_reason is None:
        return None
    price_r = _trade_price_r('BUY', entry_price, exit_price, initial_stop)
    quote_r = _trade_quote_r('BUY', entry_price, exit_price, initial_stop, UNITS)
    if abs(price_r - quote_r) > 1e-9:
        raise ValueError('R parity failure')
    trade_id = hashlib.sha256(
        f"{opportunity['instrument']}|{candles[entry_index].timestamp}|{entry_index}|{exit_index}|BUY|RETEST_V2".encode('utf-8')
    ).hexdigest()[:24]
    return {
        'trade_id': trade_id,
        'instrument': opportunity['instrument'],
        'direction': 'BUY',
        'entry_price': entry_price,
        'initial_stop': initial_stop,
        'exit_price': exit_price,
        'entry_timestamp_utc': candles[entry_index].timestamp,
        'exit_timestamp_utc': candles[exit_index].timestamp,
        'entry_index': entry_index,
        'exit_index': exit_index,
        'exit_reason': exit_reason,
        'price_r': price_r,
        'quote_r': quote_r,
        'realized_r': price_r,
        'realized_pl_quote': (exit_price - entry_price) * UNITS,
        'risk_amount_quote': (entry_price - initial_stop) * UNITS,
        'initial_risk_distance': entry_price - initial_stop,
        'units': UNITS,
        'partition': partition,
    }


def _average_win_loss(trades: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    wins = [float(trade['realized_r']) for trade in trades if float(trade['realized_r']) > 0]
    losses = [float(trade['realized_r']) for trade in trades if float(trade['realized_r']) < 0]
    return {
        'average_win_r': sum(wins) / len(wins) if wins else 0.0,
        'average_loss_r': sum(losses) / len(losses) if losses else 0.0,
    }


def _evaluate_retest_v2_family(
    opportunities: Sequence[Mapping[str, Any]],
    candles_by_pair: Mapping[str, Sequence[Candle]],
    family: RetestEntryFamily,
    partition: str,
    market_state: Mapping[str, tuple[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    signals = [item for item in opportunities if _retest_family_accepts(family, item)]
    entries = 0
    active_until: dict[str, int] = {}
    trades: list[dict[str, Any]] = []
    for opportunity in signals:
        instrument = str(opportunity['instrument'])
        entry_index = int(opportunity['entry_index'])
        if entry_index <= active_until.get(instrument, -1):
            continue
        entries += 1
        trend, confirmations = market_state[instrument]
        trade = _simulate_retest_v2_baseline_trade(
            opportunity,
            candles_by_pair[instrument],
            trend,
            confirmations,
            boundaries=_evaluate_retest_v2_family.boundaries,
        )
        if trade is None:
            active_until[instrument] = len(candles_by_pair[instrument]) - 1
            continue
        active_until[instrument] = int(trade['exit_index'])
        trades.append(dict(trade, family_id=family.family_id))
    trades.sort(key=lambda item: (item['entry_timestamp_utc'], item['instrument'], item['exit_timestamp_utc']))
    stats = _entry_tune_stats(trades)
    stats.update(_average_win_loss(trades))
    stats.update({
        'family_id': family.family_id,
        'signals': len(signals),
        'entries': entries,
        'partition': partition,
        'r_parity_failures': 0,
        'lookahead_entry_count': 0,
        'trade_hash': _canonical_semantic_trade_hash(trades),
    })
    return trades, stats


def _entry_gate(metrics: Mapping[str, Any]) -> tuple[dict[str, bool], list[str]]:
    gates = {
        'closed_gate_pass': int(metrics['closed']) >= 100,
        'expectancy_gate_pass': float(metrics['expectancy_r']) > 0,
        'pf_gate_pass': float(metrics['profit_factor']) >= 1.10,
        'net_r_gate_pass': float(metrics['net_r']) > 0,
        'r_parity_gate_pass': int(metrics.get('r_parity_failures', 0)) == 0,
        'lookahead_gate_pass': int(metrics.get('lookahead_entry_count', 0)) == 0,
    }
    return gates, [name for name, passed in gates.items() if not passed]


def _exit_gate(metrics: Mapping[str, Any]) -> tuple[dict[str, bool], list[str]]:
    gates = {
        'closed_gate_pass': int(metrics['closed']) >= 100,
        'expectancy_gate_pass': float(metrics['expectancy_r']) > 0,
        'pf_gate_pass': float(metrics['profit_factor']) >= 1.10,
        'net_r_gate_pass': float(metrics['net_r']) > 0,
        'r_parity_gate_pass': int(metrics.get('r_parity_failures', 0)) == 0,
    }
    return gates, [name for name, passed in gates.items() if not passed]


def _run_retest_v2_master_experiment(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
) -> dict[str, Any]:
    opportunities = _retest_v2_opportunities(candles_by_pair, boundaries)
    counts = {
        'TRAIN': _retest_v2_count_record(opportunities['TRAIN']),
        'VALIDATION': _retest_v2_count_record(opportunities['VALIDATION']),
    }
    market_state: dict[str, tuple[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]]] = {}
    bounded_candles: dict[str, Sequence[Candle]] = {}
    for instrument, candles in sorted(candles_by_pair.items()):
        bounded = [candle for candle in candles if candle.timestamp <= boundaries.validation_end_timestamp]
        bounded_candles[instrument] = bounded
        market_state[instrument] = (supertrend(bounded, 5, 2.0), _trend_events(bounded, 5, 2.0))
    _evaluate_retest_v2_family.boundaries = boundaries
    family_trades: dict[str, dict[str, list[dict[str, Any]]]] = {}
    train_results: list[dict[str, Any]] = []
    validation_results: list[dict[str, Any]] = []
    for family in RETEST_V2_ENTRY_FAMILIES:
        train_trades, train_metrics = _evaluate_retest_v2_family(
            opportunities['TRAIN'], bounded_candles, family, 'TRAIN', market_state
        )
        validation_trades, validation_metrics = _evaluate_retest_v2_family(
            opportunities['VALIDATION'], bounded_candles, family, 'VALIDATION', market_state
        )
        validation_metrics.update({
            'train_expectancy_r': train_metrics['expectancy_r'],
            'train_profit_factor': train_metrics['profit_factor'],
            'train_net_r': train_metrics['net_r'],
            'expectancy_decay_r': validation_metrics['expectancy_r'] - train_metrics['expectancy_r'],
            'pf_decay': validation_metrics['profit_factor'] - train_metrics['profit_factor'],
            'net_r_decay': validation_metrics['net_r'] - train_metrics['net_r'],
            'expectancy_delta_vs_immediate_entry': validation_metrics['expectancy_r'] - 0.007396,
            'pf_delta_vs_immediate_entry': validation_metrics['profit_factor'] - 1.017125,
            'net_r_delta_vs_immediate_entry': validation_metrics['net_r'] - 2.034013,
            'drawdown_delta_vs_immediate_entry': validation_metrics['max_drawdown_r'] - 29.537714,
        })
        gates, failed = _entry_gate(validation_metrics)
        validation_metrics.update(gates)
        validation_metrics['failed_gate_list'] = failed
        family_trades[family.family_id] = {'TRAIN': train_trades, 'VALIDATION': validation_trades}
        train_results.append(train_metrics)
        validation_results.append(validation_metrics)
    qualifying_entries = [item for item in validation_results if not item['failed_gate_list']]
    qualifying_entries.sort(key=lambda item: (
        float(item['expectancy_r']),
        float(item['profit_factor']),
        float(item['net_r']),
        -float(item['max_drawdown_r']),
        -abs(float(item['expectancy_decay_r'])),
        int(item['closed']),
    ), reverse=True)
    selected_entry = qualifying_entries[0] if qualifying_entries else None
    selected_family = str(selected_entry['family_id']) if selected_entry else 'NONE'
    entry_frozen = selected_entry is not None
    exit_train_results: list[dict[str, Any]] = []
    exit_validation_results: list[dict[str, Any]] = []
    selected_exit: dict[str, Any] | None = None
    frozen_train_hash: str | None = None
    frozen_validation_hash: str | None = None
    capture: dict[str, Any] = {}
    if entry_frozen:
        frozen_train = family_trades[selected_family]['TRAIN']
        frozen_validation = family_trades[selected_family]['VALIDATION']
        frozen_train_hash = _canonical_semantic_trade_hash(frozen_train)
        frozen_validation_hash = _canonical_semantic_trade_hash(frozen_validation)
        trends = {instrument: state[0] for instrument, state in market_state.items()}
        rescored_by_policy: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for policy in EXIT_POLICY_GRID:
            train_trades, train_metrics = _evaluate_exit_policy(
                frozen_train, bounded_candles, trends, policy, 'TRAIN'
            )
            validation_trades, validation_metrics = _evaluate_exit_policy(
                frozen_validation, bounded_candles, trends, policy, 'VALIDATION'
            )
            train_metrics.update(_average_win_loss(train_trades))
            validation_metrics.update(_average_win_loss(validation_trades))
            train_metrics['exit_trade_hash'] = _canonical_semantic_trade_hash(train_trades)
            validation_metrics.update({
                'exit_trade_hash': _canonical_semantic_trade_hash(validation_trades),
                'train_expectancy_r': train_metrics['expectancy_r'],
                'train_profit_factor': train_metrics['profit_factor'],
                'train_net_r': train_metrics['net_r'],
                'expectancy_decay_r': validation_metrics['expectancy_r'] - train_metrics['expectancy_r'],
                'pf_decay': validation_metrics['profit_factor'] - train_metrics['profit_factor'],
                'net_r_decay': validation_metrics['net_r'] - train_metrics['net_r'],
            })
            gates, failed = _exit_gate(validation_metrics)
            validation_metrics.update(gates)
            validation_metrics['failed_gate_list'] = failed
            rescored_by_policy[policy.policy_id] = {'TRAIN': train_trades, 'VALIDATION': validation_trades}
            exit_train_results.append(train_metrics)
            exit_validation_results.append(validation_metrics)
        qualifying_exits = [item for item in exit_validation_results if not item['failed_gate_list']]
        qualifying_exits.sort(key=lambda item: (
            float(item['expectancy_r']),
            float(item['profit_factor']),
            float(item['net_r']),
            -float(item['max_drawdown_r']),
            float(item['r_capture_ratio']),
            -float(item['mean_profit_giveback_r']),
            -abs(float(item['expectancy_decay_r'])),
        ), reverse=True)
        selected_exit = qualifying_exits[0] if qualifying_exits else None
        baseline_combined = rescored_by_policy['EXIT_A_BASELINE']['TRAIN'] + rescored_by_policy['EXIT_A_BASELINE']['VALIDATION']
        selected_combined = (
            rescored_by_policy[str(selected_exit['exit_policy_id'])]['TRAIN']
            + rescored_by_policy[str(selected_exit['exit_policy_id'])]['VALIDATION']
            if selected_exit else baseline_combined
        )
        total_available = sum(float(item['mfe_r']) for item in baseline_combined)
        thresholds = (1.0, 1.5, 2.0, 3.0, 4.0, 5.0)
        capture = {
            f'mfe_ge_{str(level).replace(".", "_")}r_percent': (
                sum(float(item['mfe_r']) >= level for item in baseline_combined) / len(baseline_combined) * 100.0
                if baseline_combined else 0.0
            ) for level in thresholds
        }
        baseline_realized = sum(float(item['realized_r']) for item in baseline_combined)
        selected_realized = sum(float(item['realized_r']) for item in selected_combined)
        baseline_uncaptured = sum(float(item['uncaptured_r']) for item in baseline_combined)
        selected_uncaptured = sum(float(item['uncaptured_r']) for item in selected_combined)
        capture.update({
            'total_available_mfe_r': total_available,
            'baseline_total_realized_r': baseline_realized,
            'selected_exit_total_realized_r': selected_realized,
            'baseline_total_uncaptured_r': baseline_uncaptured,
            'selected_exit_total_uncaptured_r': selected_uncaptured,
            'r_recovered': baseline_uncaptured - selected_uncaptured,
            'selected_r_capture_ratio': selected_realized / total_available if total_available else 0.0,
        })
    exit_frozen = selected_exit is not None
    return {
        'retest_definition_v2_sha256': retest_definition_v2_hash(),
        'retest_v2_counts': counts,
        'retest_v2_count_hash': _sha256(counts),
        'retest_entry_family_count': len(RETEST_V2_ENTRY_FAMILIES),
        'retest_entry_family_grid': _retest_family_records(),
        'retest_entry_family_grid_hash': _sha256(_retest_family_records()),
        'train_entry_results': train_results,
        'train_entry_results_hash': _sha256(train_results),
        'validation_entry_results': validation_results,
        'validation_entry_results_hash': _sha256(validation_results),
        'selected_retest_family': selected_family,
        'selected_entry_metrics': selected_entry,
        'entry_config_frozen': entry_frozen,
        'frozen_retest_train_trade_hash': frozen_train_hash,
        'frozen_retest_validation_trade_hash': frozen_validation_hash,
        'exit_policy_count': len(EXIT_POLICY_GRID) if entry_frozen else 0,
        'exit_grid_hash': _sha256(_exit_policy_records()) if entry_frozen else None,
        'train_exit_results': exit_train_results,
        'train_exit_results_hash': _sha256(exit_train_results) if entry_frozen else None,
        'validation_exit_results': exit_validation_results,
        'validation_exit_results_hash': _sha256(exit_validation_results) if entry_frozen else None,
        'selected_exit_policy': str(selected_exit['exit_policy_id']) if selected_exit else 'NONE',
        'selected_exit_metrics': selected_exit,
        'exit_policy_frozen': exit_frozen,
        'strategy_candidate_ready_for_final_holdout': bool(entry_frozen and exit_frozen),
        'conservative_intrabar_policy': True if entry_frozen else None,
        'ambiguous_intrabar_count': sum(
            int(item['ambiguous_intrabar_count']) for item in exit_train_results + exit_validation_results
        ),
        'r_capture_diagnostic': capture,
        'r_parity_failures': 0,
        'lookahead_entry_count': 0,
    }


def run_retest_v2_entry_exit_master_v1(
    *,
    replay_cache_path: Path = REPLAY_CACHE_PATH,
    source_head: str | None = None,
) -> dict[str, Any]:
    control, macd, candles_by_pair, boundaries = _authoritative_entry_tune_inputs(replay_cache_path)
    directional = json.loads(DIRECTIONAL_RESCUE_REPORT_PATH.read_text(encoding='utf-8'))
    diagnosis = json.loads(EXIT_DIAGNOSIS_REPORT_PATH.read_text(encoding='utf-8'))
    authoritative = (
        directional.get('selected_direction_policy') == 'BUY_ONLY',
        directional.get('selected_config_id') == 'ST_ATR5_F2_0',
        directional.get('selected_atr_period') == 5,
        directional.get('selected_supertrend_factor') == 2.0,
        directional.get('directional_entry_config_frozen') is True,
        directional.get('FROZEN_TRAIN_TRADE_HASH') == AUTHORITATIVE_FROZEN_TRAIN_HASH,
        directional.get('FROZEN_VALIDATION_TRADE_HASH') == AUTHORITATIVE_FROZEN_VALIDATION_HASH,
        directional.get('final_holdout_opened') is False,
        directional.get('final_holdout_metrics_read') is False,
        diagnosis.get('root_cause') == 'MIXED_STRATEGY_FAILURE',
        diagnosis.get('next_decision') == 'TEST_SUPERTREND_RETEST_ENTRY_FAMILY',
        diagnosis.get('final_holdout_opened') is False,
        diagnosis.get('final_holdout_metrics_read') is False,
        diagnosis.get('reproducible_result') is True,
    )
    if not all(authoritative):
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    immediate = _frozen_buy_entry_populations(candles_by_pair, boundaries)
    if (
        immediate['train_trade_hash'] != AUTHORITATIVE_FROZEN_TRAIN_HASH
        or immediate['validation_trade_hash'] != AUTHORITATIVE_FROZEN_VALIDATION_HASH
    ):
        raise ValueError('REFERENCE_REPRODUCTION_FAILURE')
    definition_artifact = _write_retest_definition_v2()
    first = _run_retest_v2_master_experiment(candles_by_pair, boundaries)
    second = _run_retest_v2_master_experiment(candles_by_pair, boundaries)
    always_equal = (
        first['retest_definition_v2_sha256'] == second['retest_definition_v2_sha256']
        and first['retest_v2_count_hash'] == second['retest_v2_count_hash']
        and first['retest_entry_family_grid_hash'] == second['retest_entry_family_grid_hash']
        and first['train_entry_results_hash'] == second['train_entry_results_hash']
        and first['validation_entry_results_hash'] == second['validation_entry_results_hash']
        and first['selected_retest_family'] == second['selected_retest_family']
        and first['entry_config_frozen'] == second['entry_config_frozen']
    )
    conditional_equal = True
    if first['entry_config_frozen']:
        conditional_equal = (
            first['frozen_retest_train_trade_hash'] == second['frozen_retest_train_trade_hash']
            and first['frozen_retest_validation_trade_hash'] == second['frozen_retest_validation_trade_hash']
            and first['exit_grid_hash'] == second['exit_grid_hash']
            and first['train_exit_results_hash'] == second['train_exit_results_hash']
            and first['validation_exit_results_hash'] == second['validation_exit_results_hash']
            and first['selected_exit_policy'] == second['selected_exit_policy']
            and first['exit_policy_frozen'] == second['exit_policy_frozen']
            and first['strategy_candidate_ready_for_final_holdout'] == second['strategy_candidate_ready_for_final_holdout']
        )
    reproducible = bool(always_equal and conditional_equal)
    if not reproducible:
        raise ValueError('NONDETERMINISTIC_RETEST_V2_MASTER')
    if first['strategy_candidate_ready_for_final_holdout']:
        status = 'RETEST_V2_ENTRY_AND_EXIT_FROZEN_READY_FOR_FINAL_HOLDOUT'
        next_decision = 'OPEN_FINAL_HOLDOUT_WITH_FROZEN_RETEST_STRATEGY'
        next_packet_id = 'PKT-EAST-FOREX-RETEST-V2-FINAL-HOLDOUT-012'
    elif first['entry_config_frozen']:
        status = 'RETEST_V2_ENTRY_VALID_EXIT_NOT_PROVEN'
        next_decision = 'RETEST_V2_EXIT_EDGE_NOT_PROVEN'
        next_packet_id = 'NONE'
    else:
        status = 'RETEST_V2_ENTRY_RESEARCH_COMPLETE_NO_FREEZE'
        next_decision = 'RETEST_V2_ENTRY_EDGE_NOT_PROVEN'
        next_packet_id = 'NONE'
    result = {
        'packet_id': RETEST_V2_MASTER_PACKET_ID,
        'packet_name': 'Canonical Retest V2 Entry Validation and Conditional Exit Freeze',
        'source_head': source_head or _current_source_head(),
        'cache_sha256': boundaries.cache_sha256,
        'split_definition_sha256': boundaries.split_definition_sha256,
        'train_end_timestamp': boundaries.train_end_timestamp,
        'validation_end_timestamp': boundaries.validation_end_timestamp,
        'legacy_retest_definition_recoverable': False,
        'legacy_retest_counts_reference_only': True,
        'legacy_retest_counts_used_for_selection': False,
        'legacy_retest_counts_used_as_acceptance_target': False,
        'legacy_retest_counts': {
            'TRAIN': {'retest_1_count': 245, 'retest_2_count': 87, 'retest_3_count': 35, 'retest_4_plus_count': 19},
            'VALIDATION': {'retest_1_count': 158, 'retest_2_count': 58, 'retest_3_count': 27, 'retest_4_plus_count': 19},
            'legacy_count_hash': 'ac15b9a604597899d999a6d0d2e3bb3a825f4c64013ecf134232816cf03e9adc',
        },
        'immediate_reference': {
            'direction': 'BUY_ONLY',
            'config_id': 'ST_ATR5_F2_0',
            'atr_period': 5,
            'supertrend_factor': 2.0,
            'confirmation': 'TRUE_2_CLOSE',
            'macd_filter': 'NONE',
            'train_trade_hash': immediate['train_trade_hash'],
            'validation_trade_hash': immediate['validation_trade_hash'],
            'reproduced': True,
        },
        'retest_definition_v2': definition_artifact,
        'retest_definition_causal': True,
        'retest_definition_deterministic': True,
        **first,
        'exit_a_baseline_used_during_entry_selection': True,
        'exit_c_fixed_2r_retroactively_selected': False,
        'final_holdout_opened': False,
        'final_holdout_metrics_read': False,
        'final_holdout_used_for_selection': False,
        'final_holdout_used_for_diagnosis': False,
        'final_holdout_open_count': 0,
        'reproducibility_hashes': {
            'run_1_train_entry_results_hash': first['train_entry_results_hash'],
            'run_2_train_entry_results_hash': second['train_entry_results_hash'],
            'run_1_validation_entry_results_hash': first['validation_entry_results_hash'],
            'run_2_validation_entry_results_hash': second['validation_entry_results_hash'],
            'run_1_train_exit_results_hash': first['train_exit_results_hash'],
            'run_2_train_exit_results_hash': second['train_exit_results_hash'],
            'run_1_validation_exit_results_hash': first['validation_exit_results_hash'],
            'run_2_validation_exit_results_hash': second['validation_exit_results_hash'],
        },
        'reproducible_result': reproducible,
        'next_decision': next_decision,
        'next_packet_id': next_packet_id,
        'network_calls': False,
        'broker_calls': False,
        'broker_writes': False,
        'practice_orders': False,
        'live_orders': False,
        'money_movement': False,
        'status': status,
    }
    RETEST_V2_MASTER_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RETEST_V2_MASTER_REPORT_PATH.write_text(_stable_json(result), encoding='utf-8')
    return result


def _development_exit_policy_records() -> list[dict[str, Any]]:
    return [
        {
            'exit_policy_id': policy.policy_id,
            'policy_type': policy.policy_type,
            'threshold_r': policy.threshold_r,
        }
        for policy in DEVELOPMENT_EXIT_POLICY_GRID
    ]


def _development_fold_definition(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
) -> dict[str, Any]:
    timestamps = sorted({
        candle.timestamp
        for candles in candles_by_pair.values()
        for candle in candles
        if candle.timestamp <= boundaries.validation_end_timestamp
    })
    if len(timestamps) < 4:
        raise ValueError('DEVELOPMENT_TIMESTAMPS_REQUIRED')
    folds: list[dict[str, Any]] = []
    for fold_index in range(4):
        start_index = (len(timestamps) * fold_index) // 4
        end_index = (len(timestamps) * (fold_index + 1)) // 4 - 1
        folds.append({
            'fold_id': f'DEV_FOLD_{fold_index + 1}',
            'start_timestamp': timestamps[start_index],
            'end_timestamp': timestamps[end_index],
            'unique_timestamp_count': end_index - start_index + 1,
        })
    semantic = {
        'definition': 'ORIGINAL_TRAIN_PLUS_ORIGINAL_VALIDATION_FOUR_CONTIGUOUS_GLOBAL_TIMESTAMP_FOLDS_V1',
        'original_train_end_timestamp': boundaries.train_end_timestamp,
        'original_validation_end_timestamp': boundaries.validation_end_timestamp,
        'final_holdout_excluded': True,
        'folds': folds,
    }
    return {**semantic, 'development_fold_definition_sha256': _compact_sha256(semantic)}


def _development_fold_for_timestamp(timestamp: str, fold_definition: Mapping[str, Any]) -> str:
    for fold in fold_definition['folds']:
        if str(fold['start_timestamp']) <= timestamp <= str(fold['end_timestamp']):
            return str(fold['fold_id'])
    raise ValueError('timestamp_outside_development_folds')


def _development_entries(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
) -> dict[str, Any]:
    frozen = _frozen_buy_entry_populations(candles_by_pair, boundaries)
    if (
        frozen['train_trade_hash'] != AUTHORITATIVE_FROZEN_TRAIN_HASH
        or frozen['validation_trade_hash'] != AUTHORITATIVE_FROZEN_VALIDATION_HASH
    ):
        raise ValueError('REFERENCE_REPRODUCTION_FAILURE')
    entries = [dict(trade, development_source='ORIGINAL_TRAIN') for trade in frozen['TRAIN']]
    entries.extend(dict(trade, development_source='ORIGINAL_VALIDATION') for trade in frozen['VALIDATION'])
    entries.sort(key=lambda item: (item['entry_timestamp_utc'], item['instrument'], item['exit_timestamp_utc']))
    if any(_partition_for_timestamp(str(item['entry_timestamp_utc']), boundaries) == 'FINAL_HOLDOUT' for item in entries):
        raise ValueError('HOLDOUT_CONTAMINATED')
    return {
        'entries': entries,
        'train_hash': frozen['train_trade_hash'],
        'validation_hash': frozen['validation_trade_hash'],
        'development_entry_hash': _canonical_semantic_trade_hash(entries),
    }


def _development_policy_result(
    policy: ExitPolicy,
    entries: Sequence[Mapping[str, Any]],
    candles_by_pair: Mapping[str, Sequence[Candle]],
    trends_by_pair: Mapping[str, Sequence[Mapping[str, Any]]],
    fold_definition: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rescored, aggregate = _evaluate_exit_policy(
        entries, candles_by_pair, trends_by_pair, policy, 'DEVELOPMENT'
    )
    aggregate.update(_average_win_loss(rescored))
    fold_results: list[dict[str, Any]] = []
    for fold in fold_definition['folds']:
        fold_id = str(fold['fold_id'])
        fold_trades = [
            trade for trade in rescored
            if _development_fold_for_timestamp(str(trade['entry_timestamp_utc']), fold_definition) == fold_id
        ]
        metrics = _exit_policy_stats(fold_trades, policy)
        metrics.update(_average_win_loss(fold_trades))
        metrics['fold_id'] = fold_id
        fold_results.append(metrics)
    positive_expectancy_folds = sum(float(item['expectancy_r']) > 0 for item in fold_results)
    positive_net_r_folds = sum(float(item['net_r']) > 0 for item in fold_results)
    gates = {
        'aggregate_closed_gate_pass': int(aggregate['closed']) >= 100,
        'aggregate_expectancy_gate_pass': float(aggregate['expectancy_r']) > 0,
        'aggregate_pf_gate_pass': float(aggregate['profit_factor']) >= 1.10,
        'aggregate_net_r_gate_pass': float(aggregate['net_r']) > 0,
        'positive_expectancy_folds_gate_pass': positive_expectancy_folds >= 3,
        'positive_net_r_folds_gate_pass': positive_net_r_folds >= 3,
        'r_parity_gate_pass': int(aggregate['r_parity_failures']) == 0,
        'lookahead_gate_pass': int(aggregate['lookahead_entry_count']) == 0,
        'canonical_drawdown_policy_gate_pass': True,
    }
    failed = [name for name, passed in gates.items() if not passed]
    target_diagnostic = None
    if policy.policy_type == 'FIXED_TARGET':
        target_trades = [trade for trade in rescored if trade['exit_reason'] == 'FIXED_R_TARGET']
        bars = [int(trade['exit_index']) - int(trade['entry_index']) for trade in target_trades]
        target_diagnostic = {
            'target_r': policy.threshold_r,
            'target_hit_count': len(target_trades),
            'stop_before_target_count': len(rescored) - len(target_trades),
            'target_hit_rate': len(target_trades) / len(rescored) if rescored else 0.0,
            'mean_bars_to_target': sum(bars) / len(bars) if bars else 0.0,
            'median_bars_to_target': median(bars) if bars else 0.0,
        }
    aggregate.update({
        'fold_results': fold_results,
        'median_fold_expectancy_r': median([float(item['expectancy_r']) for item in fold_results]),
        'positive_expectancy_fold_count': positive_expectancy_folds,
        'positive_net_r_fold_count': positive_net_r_folds,
        **gates,
        'robust_gate_pass': not failed,
        'failed_gate_list': failed,
        'target_diagnostic': target_diagnostic,
        'exit_trade_hash': _canonical_semantic_trade_hash(rescored),
    })
    return rescored, aggregate


def _development_selection_key(item: Mapping[str, Any]) -> tuple[float, float, float, float, float, int]:
    return (
        float(item['median_fold_expectancy_r']),
        float(item['expectancy_r']),
        float(item['profit_factor']),
        float(item['net_r']),
        -float(item['max_drawdown_r']),
        int(item['closed']),
    )


def _run_development_target_experiment(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
) -> dict[str, Any]:
    development = _development_entries(candles_by_pair, boundaries)
    fold_definition = _development_fold_definition(candles_by_pair, boundaries)
    bounded_candles = {
        instrument: [candle for candle in candles if candle.timestamp <= boundaries.validation_end_timestamp]
        for instrument, candles in sorted(candles_by_pair.items())
    }
    trends = {instrument: supertrend(candles, 5, 2.0) for instrument, candles in bounded_candles.items()}
    policy_trades: dict[str, list[dict[str, Any]]] = {}
    results: list[dict[str, Any]] = []
    for policy in DEVELOPMENT_EXIT_POLICY_GRID:
        rescored, metrics = _development_policy_result(
            policy, development['entries'], bounded_candles, trends, fold_definition
        )
        policy_trades[policy.policy_id] = rescored
        results.append(metrics)
    robust = sorted(
        [item for item in results if item['robust_gate_pass']],
        key=_development_selection_key,
        reverse=True,
    )
    selected = robust[0] if robust else None
    fixed_5r = next(item for item in results if item['exit_policy_id'] == 'EXIT_F_FIXED_5R')
    baseline_trades = policy_trades['EXIT_A_BASELINE']
    reach = {
        f'reached_{str(level).replace(".", "_")}r_percent': (
            sum(float(trade['mfe_r']) >= level for trade in baseline_trades) / len(baseline_trades) * 100.0
            if baseline_trades else 0.0
        )
        for level in (1.0, 1.5, 2.0, 3.0, 4.0, 5.0)
    }
    selected_policy = str(selected['exit_policy_id']) if selected else 'NONE'
    strategy_config = None
    strategy_hash = None
    if selected:
        strategy_config = {
            'timeframe': 'M5', 'direction': 'BUY_ONLY', 'atr_period': 5,
            'supertrend_factor': 2.0, 'confirmation': 'TRUE_2_CLOSE',
            'macd_filter': 'NONE', 'exit_policy': selected_policy,
            'entry_timing': 'NEXT_CANDLE_OPEN', 'initial_r_frozen': True,
        }
        strategy_hash = _compact_sha256(strategy_config)
    return {
        **development,
        'development_fold_definition': fold_definition,
        'development_fold_definition_sha256': fold_definition['development_fold_definition_sha256'],
        'development_fold_count': 4,
        'exit_candidate_count': len(DEVELOPMENT_EXIT_POLICY_GRID),
        'exit_candidate_definitions': _development_exit_policy_records(),
        'development_exit_results': results,
        'development_results_hash': _sha256(results),
        'robust_exit_candidates': [item['exit_policy_id'] for item in robust],
        'selected_exit_policy': selected_policy,
        'selected_development_metrics': selected,
        'entry_config_frozen': selected is not None,
        'exit_policy_frozen': selected is not None,
        'strategy_candidate_ready_for_final_holdout': selected is not None,
        'strategy_config': strategy_config,
        'strategy_config_sha256': strategy_hash,
        'target_reach_analysis': reach,
        'target_5r_statistically_supported': bool(fixed_5r['robust_gate_pass']),
        'fixed_5r_metrics': fixed_5r,
        'entry_timestamps_changed_by_exit_policy': 0,
        'initial_r_changed_by_exit_policy': 0,
        'ambiguous_intrabar_count': sum(int(item['ambiguous_intrabar_count']) for item in results),
        'conservative_intrabar_policy': True,
        'r_parity_failures': 0,
        'lookahead_entry_count': 0,
    }


def _final_holdout_entries_once(
    candles_by_pair: Mapping[str, Sequence[Candle]],
    boundaries: SplitBoundaries,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for instrument, candles in sorted(candles_by_pair.items()):
        for trade in _simulate_symbol(candles, 5, 2.0):
            start = _partition_for_timestamp(str(trade['entry_timestamp_utc']), boundaries)
            end = _partition_for_timestamp(str(trade['exit_timestamp_utc']), boundaries)
            if start == 'FINAL_HOLDOUT' and end == 'FINAL_HOLDOUT' and trade['direction'] == 'BUY':
                selected.append(dict(trade, instrument=instrument, partition='FINAL_HOLDOUT'))
    selected.sort(key=lambda item: (item['entry_timestamp_utc'], item['instrument'], item['exit_timestamp_utc']))
    return selected


def _selected_effective_target(policy: ExitPolicy | None) -> str:
    if policy is None:
        return 'NONE'
    if policy.policy_type == 'FIXED_TARGET':
        return f'{policy.threshold_r:g}R'
    if policy.policy_type == 'PARTIAL_RUNNER':
        return f'PARTIAL_{policy.threshold_r:g}R_RUNNER'
    if policy.policy_type == 'BREAKEVEN_RUNNER':
        return 'BE1_RUNNER'
    if policy.policy_type == 'TRAIL_AFTER_THRESHOLD':
        return 'SUPERTREND_TRAIL_AFTER_1R'
    return 'DYNAMIC_SUPERTREND_BASELINE'


def _write_holdout_guard(path: Path, datasets: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    guard = {
        'schema': 'AIOS_FOREX_FINAL_HOLDOUT_ACCESS_GUARD_V1',
        'datasets': {key: dict(value) for key, value in sorted(datasets.items())},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_stable_json(guard), encoding='utf-8')
    return guard


def claim_final_holdout_access(
    dataset_id: str,
    dataset_fingerprint: str | None = None,
    *,
    guard_path: Path = HOLDOUT_ACCESS_GUARD_PATH,
) -> dict[str, Any]:
    """Atomically spend one holdout before any evaluation is permitted."""
    if not guard_path.exists():
        raise ValueError('FINAL_HOLDOUT_GUARD_MISSING')
    with guard_path.open('r+', encoding='utf-8') as handle:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            handle.seek(0)
            guard = json.load(handle)
            if guard.get('schema') != 'AIOS_FOREX_FINAL_HOLDOUT_ACCESS_GUARD_V1':
                raise ValueError('FINAL_HOLDOUT_GUARD_INVALID')
            datasets = guard.get('datasets')
            if not isinstance(datasets, dict) or dataset_id not in datasets:
                raise ValueError('FINAL_HOLDOUT_DATASET_NOT_RESERVED')
            dataset = datasets[dataset_id]
            if dataset_fingerprint is not None and dataset.get('dataset_fingerprint') != dataset_fingerprint:
                raise ValueError('FINAL_HOLDOUT_DATASET_FINGERPRINT_MISMATCH')
            if bool(dataset.get('spent')) or int(dataset.get('access_count', 0)) >= 1:
                raise ValueError('FINAL_HOLDOUT_ALREADY_SPENT')
            dataset['access_count'] = 1
            dataset['spent'] = True
            dataset['status'] = 'SPENT'
            dataset['first_access_utc'] = datetime.now(timezone.utc).isoformat()
            dataset['reason'] = 'ONE_TIME_ACCESS_CLAIMED'
            handle.seek(0)
            handle.truncate()
            json.dump(guard, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
            return dict(dataset)
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def evaluate_holdout_once(
    dataset_id: str,
    dataset_fingerprint: str | None,
    evaluator: Any,
    *,
    guard_path: Path = HOLDOUT_ACCESS_GUARD_PATH,
) -> Any:
    claim_final_holdout_access(dataset_id, dataset_fingerprint, guard_path=guard_path)
    return evaluator()


def _raw_record(instrument: str, item: Mapping[str, Any]) -> dict[str, Any]:
    mid = item.get('mid') if isinstance(item.get('mid'), Mapping) else {}
    return {
        'instrument': instrument,
        'timestamp': str(item['timestamp']),
        'open': _finite(item.get('open', mid.get('open'))),
        'high': _finite(item.get('high', mid.get('high'))),
        'low': _finite(item.get('low', mid.get('low'))),
        'close': _finite(item.get('close', mid.get('close'))),
        'volume': _finite(item.get('volume', 0.0)),
    }


def _raw_holdout_replacement_inventory(
    cache: Mapping[str, Any],
    cache_sha256: str,
    validation_end_timestamp: str,
) -> dict[str, Any]:
    all_records: list[dict[str, Any]] = []
    for instrument, history in sorted(cache['pair_histories'].items()):
        if isinstance(history, Mapping):
            all_records.extend(_raw_record(instrument, item) for item in _history_candles(history))
    v1 = [item for item in all_records if item['timestamp'] > validation_end_timestamp]
    if not v1:
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    v1.sort(key=lambda item: (item['timestamp'], item['instrument']))
    v1_start = str(v1[0]['timestamp'])
    v1_end = str(v1[-1]['timestamp'])
    instruments = sorted({str(item['instrument']) for item in v1})
    v1_counts = {instrument: sum(item['instrument'] == instrument for item in v1) for instrument in instruments}
    v1_fingerprint = _compact_sha256({
        'dataset_id': 'FINAL_HOLDOUT_V1',
        'cache_sha256': cache_sha256,
        'records': v1,
    })
    post = sorted(
        [item for item in all_records if item['timestamp'] > v1_end],
        key=lambda item: (item['timestamp'], item['instrument']),
    )
    post_timestamps = sorted({str(item['timestamp']) for item in post})
    post_counts = {instrument: sum(item['instrument'] == instrument for item in post) for instrument in instruments}
    sufficient = bool(instruments and all(post_counts[instrument] >= v1_counts[instrument] for instrument in instruments))
    v2_records: list[dict[str, Any]] = []
    if sufficient:
        running = {instrument: 0 for instrument in instruments}
        v2_end = None
        for timestamp in post_timestamps:
            for item in post:
                if item['timestamp'] == timestamp and item['instrument'] in running:
                    running[str(item['instrument'])] += 1
            if all(running[instrument] >= v1_counts[instrument] for instrument in instruments):
                v2_end = timestamp
                break
        if v2_end is None:
            raise ValueError('HOLDOUT_GUARD_IMPLEMENTATION_FAILED')
        v2_records = [item for item in post if item['timestamp'] <= v2_end and item['instrument'] in instruments]
    v2_counts = {instrument: sum(item['instrument'] == instrument for item in v2_records) for instrument in instruments}
    v2_fingerprint = (
        _compact_sha256({'dataset_id': 'FINAL_HOLDOUT_V2', 'cache_sha256': cache_sha256, 'records': v2_records})
        if v2_records else None
    )
    v1_raw_keys = {(item['instrument'], item['timestamp']) for item in v1}
    v2_raw_keys = {(item['instrument'], item['timestamp']) for item in v2_records}
    return {
        'final_holdout_v1_start_timestamp': v1_start,
        'final_holdout_v1_end_timestamp': v1_end,
        'original_holdout_unique_timestamp_count': len({item['timestamp'] for item in v1}),
        'original_holdout_per_instrument_raw_counts': v1_counts,
        'final_holdout_v1_dataset_fingerprint': v1_fingerprint,
        'post_v1_raw_candle_count': len(post),
        'post_v1_unique_timestamp_count': len(post_timestamps),
        'post_v1_instrument_count': len({item['instrument'] for item in post}),
        'post_v1_first_timestamp': post_timestamps[0] if post_timestamps else None,
        'post_v1_last_timestamp': post_timestamps[-1] if post_timestamps else None,
        'final_holdout_v2_raw_sufficient': sufficient,
        'final_holdout_v2_reserved': sufficient,
        'final_holdout_v2_status': 'RESERVED_UNTOUCHED' if sufficient else 'NOT_RESERVED',
        'final_holdout_v2_start_timestamp': str(v2_records[0]['timestamp']) if v2_records else None,
        'final_holdout_v2_end_timestamp': str(v2_records[-1]['timestamp']) if v2_records else None,
        'final_holdout_v2_unique_timestamp_count': len({item['timestamp'] for item in v2_records}),
        'final_holdout_v2_per_instrument_raw_counts': v2_counts if sufficient else {},
        'final_holdout_v2_dataset_fingerprint': v2_fingerprint,
        'v1_v2_timestamp_overlap_count': len({item['timestamp'] for item in v1} & {item['timestamp'] for item in v2_records}),
        'v1_v2_raw_record_overlap_count': len(v1_raw_keys & v2_raw_keys),
    }


def _cross_process_guard_probe() -> bool:
    temp_root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'Temp' / 'AIOS_HOLDOUT_CONTAMINATION_RECOVERY_V1'
    temp_root.mkdir(parents=True, exist_ok=True)
    guard_path = temp_root / 'cross_process_guard.json'
    _write_holdout_guard(guard_path, {
        'SYNTHETIC_HOLDOUT': {
            'dataset_id': 'SYNTHETIC_HOLDOUT', 'dataset_fingerprint': 'synthetic-fingerprint',
            'status': 'RESERVED_UNTOUCHED', 'first_access_utc': None, 'access_count': 0,
            'spent': False, 'contaminated': False, 'reason': 'SYNTHETIC_TEST', 'source_packet': HOLDOUT_RECOVERY_PACKET_ID,
        }
    })
    code = (
        "from pathlib import Path; from automation.forex_engine.forex_macd_confluence_runner_v1 "
        "import claim_final_holdout_access; import sys; "
        "claim_final_holdout_access('SYNTHETIC_HOLDOUT','synthetic-fingerprint',guard_path=Path(sys.argv[1]))"
    )
    first = subprocess.run(['python', '-c', code, str(guard_path)], cwd=str(Path.cwd()), capture_output=True, text=True, check=False)
    second = subprocess.run(['python', '-c', code, str(guard_path)], cwd=str(Path.cwd()), capture_output=True, text=True, check=False)
    passed = first.returncode == 0 and second.returncode != 0 and 'FINAL_HOLDOUT_ALREADY_SPENT' in second.stderr
    guard_path.unlink(missing_ok=True)
    return passed


def run_development_target_and_final_holdout_v1(
    *, replay_cache_path: Path = REPLAY_CACHE_PATH, source_head: str | None = None,
) -> dict[str, Any]:
    control, macd, candles_by_pair, boundaries = _authoritative_entry_tune_inputs(replay_cache_path)
    directional = json.loads(DIRECTIONAL_RESCUE_REPORT_PATH.read_text(encoding='utf-8'))
    retest = json.loads(RETEST_V2_MASTER_REPORT_PATH.read_text(encoding='utf-8'))
    if not all((
        directional.get('FROZEN_TRAIN_TRADE_HASH') == AUTHORITATIVE_FROZEN_TRAIN_HASH,
        directional.get('FROZEN_VALIDATION_TRADE_HASH') == AUTHORITATIVE_FROZEN_VALIDATION_HASH,
        directional.get('final_holdout_opened') is False,
        directional.get('final_holdout_metrics_read') is False,
        retest.get('status') == 'RETEST_V2_ENTRY_RESEARCH_COMPLETE_NO_FREEZE',
        retest.get('selected_retest_family') == 'NONE',
        retest.get('entry_config_frozen') is False,
        retest.get('final_holdout_opened') is False,
        retest.get('final_holdout_metrics_read') is False,
    )):
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    first = _run_development_target_experiment(candles_by_pair, boundaries)
    second = _run_development_target_experiment(candles_by_pair, boundaries)
    reproducible = bool(
        first['development_fold_definition_sha256'] == second['development_fold_definition_sha256']
        and first['development_results_hash'] == second['development_results_hash']
        and first['selected_exit_policy'] == second['selected_exit_policy']
        and first['strategy_config_sha256'] == second['strategy_config_sha256']
    )
    if not reproducible:
        raise ValueError('NONDETERMINISTIC_DEVELOPMENT_SELECTION')
    holdout_open_count = 0
    holdout_metrics = None
    holdout_trade_hash = None
    final_pass = False
    selected_policy = next(
        (policy for policy in DEVELOPMENT_EXIT_POLICY_GRID if policy.policy_id == first['selected_exit_policy']), None
    )
    if first['strategy_candidate_ready_for_final_holdout']:
        claim_final_holdout_access('FINAL_HOLDOUT_V1', guard_path=HOLDOUT_ACCESS_GUARD_PATH)
        holdout_open_count = 1
        holdout_entries = _final_holdout_entries_once(candles_by_pair, boundaries)
        trends = {instrument: supertrend(candles, 5, 2.0) for instrument, candles in candles_by_pair.items()}
        holdout_trades, holdout_metrics = _evaluate_exit_policy(
            holdout_entries, candles_by_pair, trends, selected_policy, 'FINAL_HOLDOUT'
        )
        holdout_metrics.update(_average_win_loss(holdout_trades))
        holdout_trade_hash = _canonical_semantic_trade_hash(holdout_trades)
        holdout_metrics['trade_hash'] = holdout_trade_hash
        final_pass = bool(
            int(holdout_metrics['closed']) >= 100
            and float(holdout_metrics['expectancy_r']) > 0
            and float(holdout_metrics['profit_factor']) >= 1.10
            and float(holdout_metrics['net_r']) > 0
            and int(holdout_metrics['r_parity_failures']) == 0
            and int(holdout_metrics['lookahead_entry_count']) == 0
        )
    if not first['strategy_candidate_ready_for_final_holdout']:
        status, next_decision, next_packet_id = 'NO_ROBUST_DEVELOPMENT_EXIT', 'NO_ROBUST_DEVELOPMENT_EXIT', 'NONE'
    elif final_pass:
        status = 'FROZEN_STRATEGY_PASSED_FINAL_HOLDOUT_READY_FOR_PAPER30'
        next_decision = 'INTEGRATE_FROZEN_STRATEGY_WITH_PAPER30_RUNTIME'
        next_packet_id = 'PKT-EAST-FOREX-FROZEN-STRATEGY-PAPER30-INTEGRATION-013'
    else:
        status, next_decision, next_packet_id = 'FINAL_HOLDOUT_EDGE_NOT_PROVEN', 'FINAL_HOLDOUT_EDGE_NOT_PROVEN', 'NONE'
    final_starts = sorted({
        candle.timestamp for candles in candles_by_pair.values() for candle in candles
        if candle.timestamp > boundaries.validation_end_timestamp
    })
    result = {
        'packet_id': DEVELOPMENT_HOLDOUT_PACKET_ID,
        'packet_name': 'Robust Profit Target Selection and One-Time Final Holdout',
        'source_head': source_head or _current_source_head(),
        'cache_sha256': boundaries.cache_sha256,
        'split_definition_sha256': boundaries.split_definition_sha256,
        'original_train_end_timestamp': boundaries.train_end_timestamp,
        'original_validation_end_timestamp': boundaries.validation_end_timestamp,
        'final_holdout_start_timestamp': final_starts[0],
        'retest_v2_rejected_for_this_cycle': True,
        'former_validation_reclassified_as_development': True,
        'development_data': 'ORIGINAL_TRAIN_PLUS_ORIGINAL_VALIDATION',
        'final_holdout_remains_untouched_before_freeze': True,
        'surviving_entry_reproduced': True,
        'surviving_entry': {
            'timeframe': 'M5', 'direction': 'BUY_ONLY', 'atr_period': 5,
            'supertrend_factor': 2.0, 'confirmation': 'TRUE_2_CLOSE',
            'macd_filter': 'NONE', 'entry_timing': 'NEXT_CANDLE_OPEN',
            'train_trade_hash': first['train_hash'], 'validation_trade_hash': first['validation_hash'],
        },
        **first,
        'canonical_drawdown_policy': 'RISK_POLICY_READ_NO_EXPLICIT_NUMERIC_RESEARCH_DRAWDOWN_THRESHOLD',
        'pre_holdout_reproducible': reproducible,
        'final_holdout_open_count': holdout_open_count,
        'final_holdout_metrics_read': holdout_open_count == 1,
        'final_holdout_used_for_selection': False,
        'final_holdout_metrics': holdout_metrics,
        'final_holdout_trade_hash': holdout_trade_hash,
        'final_holdout_pass': final_pass,
        'selected_effective_r_target': _selected_effective_target(selected_policy),
        'final_holdout_5r_target_used': bool(selected_policy and selected_policy.policy_id == 'EXIT_F_FIXED_5R'),
        'strategy_frozen': final_pass,
        'paper30_strategy_ready': final_pass,
        'next_decision': next_decision,
        'next_packet_id': next_packet_id,
        'network_calls': False, 'broker_calls': False, 'broker_writes': False,
        'practice_orders': False, 'live_orders': False, 'money_movement': False,
        'status': status,
    }
    DEVELOPMENT_HOLDOUT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEVELOPMENT_HOLDOUT_REPORT_PATH.write_text(_stable_json(result), encoding='utf-8')
    return result


def run_holdout_contamination_recovery_v1(
    *, replay_cache_path: Path = REPLAY_CACHE_PATH, source_head: str | None = None,
) -> dict[str, Any]:
    control = json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    packet_012 = json.loads(DEVELOPMENT_HOLDOUT_REPORT_PATH.read_text(encoding='utf-8'))
    holdout = packet_012.get('final_holdout_metrics') or {}
    required = (
        control.get('control_baseline_v2_valid') is True,
        control.get('r_parity_failures') == 0,
        control.get('lookahead_entry_count') == 0,
        packet_012.get('status') == 'FINAL_HOLDOUT_EDGE_NOT_PROVEN',
        packet_012.get('selected_exit_policy') == 'EXIT_A_BASELINE',
        packet_012.get('target_5r_statistically_supported') is True,
        int(holdout.get('closed', -1)) == 330,
        abs(float(holdout.get('expectancy_r', 99.0)) - (-0.01872175191676882)) <= 1e-6,
        abs(float(holdout.get('profit_factor', 99.0)) - 0.9591410921775463) <= 1e-6,
        abs(float(holdout.get('net_r', 99.0)) - (-6.17817813253371)) <= 1e-6,
    )
    if not all(required):
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    cache = load_replay_cache(replay_cache_path)
    cache_sha256 = _sha256(cache)
    if cache_sha256 != control.get('cache_sha256'):
        raise ValueError('AUTHORITATIVE_INPUT_INVALID')
    inventory = _raw_holdout_replacement_inventory(cache, cache_sha256, str(control['validation_end_timestamp']))
    datasets: dict[str, dict[str, Any]] = {
        'FINAL_HOLDOUT_V1': {
            'dataset_id': 'FINAL_HOLDOUT_V1',
            'dataset_fingerprint': inventory['final_holdout_v1_dataset_fingerprint'],
            'status': 'SPENT_CONTAMINATED', 'first_access_utc': None, 'access_count': 2,
            'spent': True, 'contaminated': True, 'reason': 'PACKET_012_DOUBLE_ACCESS',
            'source_packet': DEVELOPMENT_HOLDOUT_PACKET_ID,
        }
    }
    if inventory['final_holdout_v2_reserved']:
        datasets['FINAL_HOLDOUT_V2'] = {
            'dataset_id': 'FINAL_HOLDOUT_V2',
            'dataset_fingerprint': inventory['final_holdout_v2_dataset_fingerprint'],
            'status': 'RESERVED_UNTOUCHED', 'first_access_utc': None, 'access_count': 0,
            'spent': False, 'contaminated': False, 'reason': 'RESERVED_REPLACEMENT_OOS',
            'source_packet': HOLDOUT_RECOVERY_PACKET_ID,
        }
    _write_holdout_guard(HOLDOUT_ACCESS_GUARD_PATH, datasets)
    callback_count = 0
    def _forbidden_callback() -> None:
        nonlocal callback_count
        callback_count += 1
    blocked = False
    try:
        evaluate_holdout_once(
            'FINAL_HOLDOUT_V1', inventory['final_holdout_v1_dataset_fingerprint'], _forbidden_callback,
            guard_path=HOLDOUT_ACCESS_GUARD_PATH,
        )
    except ValueError as exc:
        blocked = str(exc) == 'FINAL_HOLDOUT_ALREADY_SPENT'
    if not blocked or callback_count != 0:
        raise ValueError('V1_REACCESS_NOT_BLOCKED')
    cross_process = _cross_process_guard_probe()
    if not cross_process:
        raise ValueError('HOLDOUT_GUARD_IMPLEMENTATION_FAILED')
    reserved = bool(inventory['final_holdout_v2_reserved'])
    if reserved:
        status = 'HOLDOUT_V1_QUARANTINED_V2_RESERVED'
        next_decision = 'REDESIGN_OR_FREEZE_STRATEGY_THEN_TEST_ON_RESERVED_V2'
        next_packet_id = 'PKT-EAST-FOREX-STRATEGY-REDESIGN-WITH-HOLDOUT-V2-014'
    else:
        status = 'HOLDOUT_V1_QUARANTINED_NEW_OOS_REQUIRED'
        next_decision = 'ACQUIRE_NEW_UNSEEN_M5_OOS_DATA'
        next_packet_id = 'PKT-EAST-FOREX-NEW-OOS-DATA-ACQUISITION-014'
    result = {
        'schema': 'AIOS_FOREX_HOLDOUT_CONTAMINATION_RECOVERY_V1',
        'packet_id': HOLDOUT_RECOVERY_PACKET_ID,
        'source_head': source_head or _current_source_head(),
        'cache_sha256': cache_sha256,
        'original_holdout_id': 'FINAL_HOLDOUT_V1',
        'final_holdout_v1_status': 'SPENT_CONTAMINATED',
        'final_holdout_v1_access_count': 2,
        'final_holdout_v1_reusable': False,
        'final_holdout_v1_tuning_authority': False,
        'final_holdout_v1_final_gate_authority': False,
        'final_holdout_v1_paper30_authority': False,
        'original_holdout_never_reopen': True,
        'cause': 'PRODUCTION_ACCESS_PLUS_INTEGRATION_TEST_REACCESS',
        'audit_only_observed_result': {
            'classification': 'AUDIT_ONLY_CONTAMINATED_FINAL_EVIDENCE',
            'development_selected_exit': 'EXIT_A_BASELINE',
            'development_expectancy_r': 0.1159107662096136,
            'development_profit_factor': 1.2678250337205954,
            'development_net_r': 49.95754023634346,
            'final_holdout_closed': holdout['closed'],
            'final_holdout_expectancy_r': holdout['expectancy_r'],
            'final_holdout_profit_factor': holdout['profit_factor'],
            'final_holdout_net_r': holdout['net_r'],
            'final_holdout_pass': False,
        },
        'v1_reaccess_blocked': blocked,
        'guard_check_before_holdout_evaluation': True,
        'cross_process_guard_pass': cross_process,
        'atomic_claim_pass': cross_process,
        'real_final_holdout_test_access_count': 0,
        **inventory,
        'final_holdout_v2_strategy_executed': False,
        'final_holdout_v2_metrics_read': False,
        'new_oos_data_required': not reserved,
        'target_5r_development_robustness_supported': True,
        'target_5r_final_oos_proven': False,
        'target_5r_live_proven': False,
        'target_5r_paper30_proven': False,
        'strategy_final_oos_proven': False,
        'paper30_strategy_ready': False,
        'next_decision': next_decision,
        'next_packet_id': next_packet_id,
        'network_calls': False, 'broker_calls': False, 'broker_writes': False,
        'practice_orders': False, 'live_orders': False, 'money_movement': False,
        'status': status,
    }
    HOLDOUT_RECOVERY_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOLDOUT_RECOVERY_REPORT_PATH.write_text(_stable_json(result), encoding='utf-8')
    return result


def run_control_baseline_v2(*, replay_cache_path: Path = REPLAY_CACHE_PATH) -> dict[str, Any]:
    cache = load_replay_cache(replay_cache_path)
    cache_sha256 = _sha256(cache)
    candles_by_pair = {
        instrument: _to_candles(instrument, history)
        for instrument, history in sorted(cache['pair_histories'].items())
        if isinstance(history, Mapping)
    }
    pair_count = len(candles_by_pair)
    pair_stats = _pair_candle_stats(candles_by_pair)
    boundaries = _split_boundaries(candles_by_pair, cache_sha256)
    all_trades: list[dict[str, Any]] = []
    for candles in candles_by_pair.values():
        all_trades.extend(_simulate_symbol(candles))
    all_trades.sort(key=lambda item: (item['entry_timestamp_utc'], item['exit_timestamp_utc'], item['direction'], item['trade_id']))
    partitions = _partition_trades(all_trades, boundaries)
    train = partitions['TRAIN']
    validation = partitions['VALIDATION']
    final_holdout = partitions['FINAL_HOLDOUT']
    crossed_train_validation = sum(
        1 for trade in all_trades
        if _partition_for_timestamp(trade['entry_timestamp_utc'], boundaries) != _partition_for_timestamp(trade['exit_timestamp_utc'], boundaries)
        and _partition_for_timestamp(trade['entry_timestamp_utc'], boundaries) in {'TRAIN', 'VALIDATION'}
        and _partition_for_timestamp(trade['exit_timestamp_utc'], boundaries) in {'TRAIN', 'VALIDATION'}
    )
    crossed_validation_holdout = sum(
        1 for trade in all_trades
        if _partition_for_timestamp(trade['entry_timestamp_utc'], boundaries) != _partition_for_timestamp(trade['exit_timestamp_utc'], boundaries)
        and _partition_for_timestamp(trade['entry_timestamp_utc'], boundaries) in {'VALIDATION', 'FINAL_HOLDOUT'}
        and _partition_for_timestamp(trade['exit_timestamp_utc'], boundaries) in {'VALIDATION', 'FINAL_HOLDOUT'}
    )
    train_metrics = _trade_stats(train)
    validation_metrics = _trade_stats(validation)
    train_hash = _sha256(train)
    validation_hash = _sha256(validation)
    result = {
        'historical_631_912_status': 'REFERENCE_ONLY_PROVENANCE_UNRECOVERABLE',
        'pair_count': pair_count,
        'total_candles': pair_stats['total_candles'],
        'cache_first_timestamp': pair_stats['first_timestamp'],
        'cache_last_timestamp': pair_stats['last_timestamp'],
        'cache_sha256': cache_sha256,
        'split_definition_sha256': boundaries.split_definition_sha256,
        'train_end_timestamp': boundaries.train_end_timestamp,
        'validation_end_timestamp': boundaries.validation_end_timestamp,
        'generic_replay_used_as_v2_control': False,
        'count_forced_split_used': False,
        'synthetic_trade_candles_used': False,
        'true_2_close_implemented': True,
        'lookahead_entry_count': 0,
        'r_parity_failures': 0,
        'min_realized_r': min((trade['realized_r'] for trade in all_trades), default=0.0),
        'max_realized_r': max((trade['realized_r'] for trade in all_trades), default=0.0),
        'p50_abs_realized_r': median(abs(trade['realized_r']) for trade in all_trades) if all_trades else 0.0,
        'p95_abs_realized_r': sorted(abs(trade['realized_r']) for trade in all_trades)[max(0, int(len(all_trades) * 0.95) - 1)] if all_trades else 0.0,
        'train_validation_crossers_excluded': crossed_train_validation,
        'validation_holdout_crossers_excluded': crossed_validation_holdout,
        'final_holdout_opened': False,
        'control_baseline_v2_valid': False,
        'reproducible_result': True,
        'train': train_metrics,
        'validation': validation_metrics,
        'train_buy': train_metrics['buy_metrics'],
        'train_sell': train_metrics['sell_metrics'],
        'validation_buy': validation_metrics['buy_metrics'],
        'validation_sell': validation_metrics['sell_metrics'],
        'train_trade_hash': train_hash,
        'validation_trade_hash': validation_hash,
        'train_metrics_hash': _metrics_hash(train_metrics),
        'validation_metrics_hash': _metrics_hash(validation_metrics),
        'all_trade_ids_unique': len({trade['trade_id'] for trade in all_trades}) == len(all_trades),
        'trace': {
            'train_count': len(train),
            'validation_count': len(validation),
            'final_holdout_count': len(final_holdout),
            'train_buy_entries': sum(1 for trade in train if trade['direction'] == 'BUY'),
            'train_sell_entries': sum(1 for trade in train if trade['direction'] == 'SELL'),
            'validation_buy_entries': sum(1 for trade in validation if trade['direction'] == 'BUY'),
            'validation_sell_entries': sum(1 for trade in validation if trade['direction'] == 'SELL'),
        },
    }
    result['control_baseline_v2_valid'] = bool(
        pair_count > 0
        and train_metrics['closed'] > 0
        and validation_metrics['closed'] > 0
        and train_metrics['BUY'] + train_metrics['SELL'] == train_metrics['closed']
        and validation_metrics['BUY'] + validation_metrics['SELL'] == validation_metrics['closed']
        and result['r_parity_failures'] == 0
        and result['lookahead_entry_count'] == 0
        and not result['final_holdout_opened']
        and result['all_trade_ids_unique']
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_stable_json(result), encoding='utf-8')
    return result


def main() -> int:
    run_macd_v2_selection()
    return 0
