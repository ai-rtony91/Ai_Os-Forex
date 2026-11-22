"""Deterministic, completed-candle-only market-context research features.

This module is deliberately separate from signal and execution code.  It emits
auditable snapshots that can be joined to an existing setup/rejection record;
future outcomes are never accepted as feature inputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence

from automation.forex_engine.indicators import DOWN, FLAT, UP, atr, supertrend, true_range
from automation.forex_engine.models import Candle


def _get(candle: Candle | Mapping[str, Any], name: str, default: Any = None) -> Any:
    return getattr(candle, name, default) if not isinstance(candle, Mapping) else candle.get(name, default)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 10)


def _candle(value: Candle | Mapping[str, Any]) -> Candle:
    if isinstance(value, Candle):
        return value
    required = {key: _number(value.get(key)) for key in ("open", "high", "low", "close")}
    if any(item is None for item in required.values()):
        raise ValueError("Each candle needs finite OHLC values")
    return Candle(
        symbol=str(value.get("symbol", "")), timeframe=str(value.get("timeframe", "")),
        timestamp=str(value.get("timestamp", "")), **required,
        volume=_number(value.get("volume")) or 0.0, source=str(value.get("source", "local fixture")),
    )


def _validate_completed(candles: Sequence[Candle | Mapping[str, Any]]) -> list[Candle]:
    if not candles:
        raise ValueError("At least one completed candle is required")
    normalized = [_candle(item) for item in candles]
    for raw, candle in zip(candles, normalized):
        completed = _get(raw, "completed", _get(raw, "closed", True))
        if completed is not True:
            raise ValueError(f"Candle {candle.timestamp} is not completed")
        if not candle.timestamp:
            raise ValueError("Candle timestamp must not be empty")
    symbols = {item.symbol for item in normalized}
    timeframes = {item.timeframe for item in normalized}
    if len(symbols) != 1 or len(timeframes) != 1:
        raise ValueError("A snapshot sequence must contain one pair and timeframe")
    if [item.timestamp for item in normalized] != sorted(item.timestamp for item in normalized):
        raise ValueError("Candle timestamps must be sorted")
    return normalized


def _ema(closes: Sequence[float], period: int) -> list[float | None]:
    values: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return values
    current = sum(closes[:period]) / period
    values[period - 1] = current
    alpha = 2.0 / (period + 1)
    for index in range(period, len(closes)):
        current = (closes[index] - current) * alpha + current
        values[index] = current
    return [_round(value) for value in values]


def _percentile(values: Sequence[float], value: float, window: int) -> float | None:
    sample = list(values[-window:])
    if not sample:
        return None
    return round(100.0 * sum(item <= value for item in sample) / len(sample), 10)


def _session(timestamp: str) -> str | None:
    try:
        text = timestamp.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        hour = parsed.astimezone(timezone.utc).hour
    except ValueError:
        return None
    if 7 <= hour < 12:
        return "LONDON"
    if 12 <= hour < 17:
        return "NEW_YORK"
    if 0 <= hour < 7:
        return "ASIA"
    return "OFF_HOURS"


def build_market_context_snapshots(
    candles: Iterable[Candle | Mapping[str, Any]], *,
    atr_period: int = 14, ema_periods: tuple[int, int] = (10, 20),
    supertrend_period: int = 10, supertrend_multiplier: float = 3.0,
    volatility_window: int = 20, swing_window: int = 2,
) -> list[dict[str, Any]]:
    """Return one snapshot per candle, using only candles through that index."""
    source = list(candles)
    all_candles = _validate_completed(source)
    if swing_window < 1 or atr_period < 1 or volatility_window < 1:
        raise ValueError("lookback periods must be positive")
    ranges = true_range(all_candles)
    atr_values = atr(all_candles, atr_period)
    trends = supertrend(all_candles, supertrend_period, supertrend_multiplier)
    closes = [item.close for item in all_candles]
    ema_values = {period: _ema(closes, period) for period in ema_periods}
    fast_period, slow_period = ema_periods
    if fast_period >= slow_period:
        raise ValueError("ema_periods must be ordered fast, slow")
    output: list[dict[str, Any]] = []
    prior_direction = FLAT
    direction_age = 0
    prior_spread: float | None = None
    for index, candle in enumerate(all_candles):
        high, low, open_, close = candle.high, candle.low, candle.open, candle.close
        candle_range = high - low
        body = abs(close - open_)
        upper = high - max(open_, close)
        lower = min(open_, close) - low
        current_atr = atr_values[index]
        trend = trends[index]
        direction = trend["direction"]
        if direction != FLAT and direction != prior_direction:
            direction_age = 0
        elif direction != FLAT:
            direction_age += 1
        prior_direction = direction
        fast = ema_values[fast_period][index]
        slow = ema_values[slow_period][index]
        spread = None if fast is None or slow is None else fast - slow
        spread_change = None if spread is None or prior_spread is None else spread - prior_spread
        prior_spread = spread if spread is not None else prior_spread
        earlier = all_candles[:index]
        left = all_candles[max(0, index - swing_window):index]
        swing_high = max((item.high for item in left), default=None) if len(left) == swing_window else None
        swing_low = min((item.low for item in left), default=None) if len(left) == swing_window else None
        recent_high = max((item.high for item in earlier), default=None)
        recent_low = min((item.low for item in earlier), default=None)
        prior_atrs = [item for item in atr_values[:index] if item is not None]
        volatility_pct = _percentile(prior_atrs, current_atr, volatility_window) if current_atr is not None else None
        previous_atr = prior_atrs[-1] if prior_atrs else None
        volatility_state = None if current_atr is None or previous_atr is None else ("EXPANDING" if current_atr > previous_atr else "COMPRESSING" if current_atr < previous_atr else "STABLE")
        higher_high = lower_high = higher_low = lower_low = None
        if len(left) == swing_window:
            higher_high = high > max(item.high for item in left)
            lower_high = high < max(item.high for item in left)
            higher_low = low > min(item.low for item in left)
            lower_low = low < min(item.low for item in left)
        def norm(distance: float | None) -> float | None:
            return _round(distance / current_atr) if distance is not None and current_atr not in (None, 0) else None
        setup = _get(source[index], "setup_id", _get(source[index], "candidate_id"))
        rejection = _get(source[index], "rejection_reason", _get(source[index], "rejection_reasons"))
        output.append({
            "schema": "AIOS_FOREX_MARKET_CONTEXT_SNAPSHOT_V1", "pair": candle.symbol,
            "timestamp": candle.timestamp, "timeframe": candle.timeframe, "completed": True,
            "ohlc": {"open": open_, "high": high, "low": low, "close": close},
            "candle": {"range": _round(candle_range), "body": _round(body), "body_range_ratio": _round(body / candle_range) if candle_range else None,
                        "upper_wick_ratio": _round(upper / candle_range) if candle_range else None, "lower_wick_ratio": _round(lower / candle_range) if candle_range else None,
                        "close_location": _round((close - low) / candle_range) if candle_range else None},
            "atr": current_atr, "atr_normalized": {"range": norm(candle_range), "body": norm(body), "upper_wick": norm(upper), "lower_wick": norm(lower)},
            "volatility": {"percentile": volatility_pct, "regime": volatility_state},
            "supertrend": {"direction": direction, "value": trend["supertrend"], "bars_since_change": direction_age if direction != FLAT else None,
                            "distance": norm(close - trend["supertrend"] if trend["supertrend"] is not None else None)},
            "ema": {"values": {str(period): ema_values[period][index] for period in ema_periods}, "ordering": None if fast is None or slow is None else ("FAST_ABOVE" if fast > slow else "FAST_BELOW" if fast < slow else "EQUAL"),
                    "fast_slope": None if index == 0 or fast is None or ema_values[fast_period][index - 1] is None else _round(fast - ema_values[fast_period][index - 1]),
                    "spread": spread, "spread_change": spread_change, "spread_state": None if spread_change is None else ("EXPANDING" if abs(spread_change) > 0 else "FLAT")},
            "structure": {"recent_swing_high": swing_high, "recent_swing_low": swing_low, "higher_high": higher_high, "lower_high": lower_high, "higher_low": higher_low, "lower_low": lower_low,
                           "distance_to_high": norm(None if recent_high is None else recent_high - close), "distance_to_low": norm(None if recent_low is None else close - recent_low),
                           "pullback_depth_atr": norm(None if swing_high is None or swing_low is None else max(0.0, swing_high - close))},
            "trend_age": direction_age if direction != FLAT else None,
            "momentum": {"close_change": None if index == 0 else _round(close - all_candles[index - 1].close), "close_change_atr": norm(None if index == 0 else close - all_candles[index - 1].close)},
            "execution_context": {"bid": _number(_get(source[index], "bid")), "ask": _number(_get(source[index], "ask")), "spread": _number(_get(source[index], "ask")) - _number(_get(source[index], "bid")) if _number(_get(source[index], "bid")) is not None and _number(_get(source[index], "ask")) is not None else None},
            "session": _session(candle.timestamp), "setup_id": setup, "rejection_reason": rejection,
            "available_history_bars": index + 1,
        })
    return output
